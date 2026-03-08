"""
Context Service - Hierarchical context management using PostgreSQL ltree.

Provides efficient tree operations for organizing workspaces, projects,
folders, tasks, and documents.
"""

import logging
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from ..models.context import Context
from ..models.organization import Organization


logger = logging.getLogger(__name__)


class ContextService:
    """
    Service for managing hierarchical contexts.

    Uses PostgreSQL ltree extension for efficient tree queries:
    - Find all children of a context
    - Find all ancestors of a context
    - Move subtrees
    - Calculate depth
    - Search by path patterns
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_context(
        self,
        organization_id: UUID,
        name: str,
        context_type: str,
        parent_id: Optional[UUID] = None,
        description: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        meta: Optional[dict] = None,
        created_by: Optional[UUID] = None
    ) -> Context:
        """
        Create a new context.

        Args:
            organization_id: Organization owning the context
            name: Human-readable name
            context_type: Type (workspace, project, folder, task, document, etc.)
            parent_id: Parent context UUID (None for root)
            description: Optional description
            ttl_seconds: Time-to-live in seconds (None = permanent)
            meta: Flexible metadata storage
            created_by: User who created the context

        Returns:
            Created Context instance

        Raises:
            ValueError: If parent not found or organization limit reached
        """
        # Check organization limits
        org_stmt = select(Organization).where(Organization.id == organization_id)
        org_result = await self.db.execute(org_stmt)
        org = org_result.scalar_one_or_none()
        if not org:
            raise ValueError(f"Organization {organization_id} not found")

        # Count existing contexts
        count_stmt = select(Context).where(Context.organization_id == organization_id)
        count_result = await self.db.execute(count_stmt)
        existing_count = len(count_result.scalars().all())

        if existing_count >= org.max_contexts:
            raise ValueError(
                f"Organization has reached max contexts limit ({org.max_contexts})"
            )

        # Build ltree path
        if parent_id:
            parent_stmt = select(Context).where(Context.id == parent_id)
            parent_result = await self.db.execute(parent_stmt)
            parent = parent_result.scalar_one_or_none()

            if not parent:
                raise ValueError(f"Parent context {parent_id} not found")

            if parent.organization_id != organization_id:
                raise ValueError("Parent context must belong to same organization")

            path = Context.build_path(parent.path, name)
        else:
            # Root context
            path = Context.build_path(None, name)

        # Create context
        context = Context(
            organization_id=organization_id,
            path=path,
            name=name,
            description=description,
            context_type=context_type,
            parent_id=parent_id,
            meta=meta or {},
            created_by=created_by
        )

        # Set TTL if provided
        if ttl_seconds:
            context.set_ttl(ttl_seconds)

        self.db.add(context)
        await self.db.commit()
        await self.db.refresh(context)

        logger.info(f"Created context: {path} (type: {context_type})")
        return context

    async def get_context(self, context_id: UUID) -> Optional[Context]:
        """Get context by UUID."""
        stmt = select(Context).where(Context.id == context_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_context_by_path(
        self,
        organization_id: UUID,
        path: str
    ) -> Optional[Context]:
        """
        Get context by ltree path within organization.

        Args:
            organization_id: Organization UUID
            path: ltree path (e.g., 'root.team_alpha.project_x')

        Returns:
            Context or None
        """
        stmt = select(Context).where(
            Context.organization_id == organization_id,
            Context.path == path
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_children(
        self,
        context_id: UUID,
        include_archived: bool = False
    ) -> List[Context]:
        """
        Get immediate children of a context.

        Args:
            context_id: Parent context UUID
            include_archived: Whether to include archived contexts

        Returns:
            List of child contexts
        """
        stmt = select(Context).where(Context.parent_id == context_id)

        if not include_archived:
            stmt = stmt.where(Context.archived == False)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_descendants(
        self,
        context_id: UUID,
        include_archived: bool = False
    ) -> List[Context]:
        """
        Get all descendants of a context (entire subtree).

        Uses ltree descendant query: path <@ parent_path

        Args:
            context_id: Parent context UUID
            include_archived: Whether to include archived contexts

        Returns:
            List of all descendant contexts
        """
        # Get parent context
        parent = await self.get_context(context_id)
        if not parent:
            raise ValueError(f"Context {context_id} not found")

        # ltree descendant query
        query = text("""
            SELECT * FROM contexts
            WHERE organization_id = :org_id
            AND path <@ :parent_path::ltree
            AND id != :context_id
        """)

        params = {
            "org_id": str(parent.organization_id),
            "parent_path": parent.path,
            "context_id": str(context_id)
        }

        if not include_archived:
            query = text("""
                SELECT * FROM contexts
                WHERE organization_id = :org_id
                AND path <@ :parent_path::ltree
                AND id != :context_id
                AND archived = false
            """)

        result = await self.db.execute(query, params)
        rows = result.fetchall()

        # Convert rows to Context objects
        contexts = []
        for row in rows:
            stmt = select(Context).where(Context.id == row[0])
            ctx_result = await self.db.execute(stmt)
            ctx = ctx_result.scalar_one_or_none()
            if ctx:
                contexts.append(ctx)

        return contexts

    async def get_ancestors(self, context_id: UUID) -> List[Context]:
        """
        Get all ancestors of a context (path to root).

        Uses ltree ancestor query: parent_path @> path

        Args:
            context_id: Context UUID

        Returns:
            List of ancestor contexts (ordered from root to parent)
        """
        context = await self.get_context(context_id)
        if not context:
            raise ValueError(f"Context {context_id} not found")

        # ltree ancestor query
        query = text("""
            SELECT * FROM contexts
            WHERE organization_id = :org_id
            AND path @> :context_path::ltree
            AND id != :context_id
            ORDER BY path
        """)

        params = {
            "org_id": str(context.organization_id),
            "context_path": context.path,
            "context_id": str(context_id)
        }

        result = await self.db.execute(query, params)
        rows = result.fetchall()

        # Convert rows to Context objects
        ancestors = []
        for row in rows:
            stmt = select(Context).where(Context.id == row[0])
            ctx_result = await self.db.execute(stmt)
            ctx = ctx_result.scalar_one_or_none()
            if ctx:
                ancestors.append(ctx)

        return ancestors

    async def search_by_pattern(
        self,
        organization_id: UUID,
        pattern: str,
        include_archived: bool = False
    ) -> List[Context]:
        """
        Search contexts by ltree pattern.

        Patterns:
        - 'root.*' = all direct children of root
        - 'root.*{1,2}' = children and grandchildren of root
        - 'root.*.docs' = all 'docs' contexts under root

        Args:
            organization_id: Organization UUID
            pattern: ltree query pattern
            include_archived: Whether to include archived contexts

        Returns:
            List of matching contexts
        """
        query = text("""
            SELECT * FROM contexts
            WHERE organization_id = :org_id
            AND path ~ :pattern::lquery
        """)

        params = {
            "org_id": str(organization_id),
            "pattern": pattern
        }

        if not include_archived:
            query = text("""
                SELECT * FROM contexts
                WHERE organization_id = :org_id
                AND path ~ :pattern::lquery
                AND archived = false
            """)

        result = await self.db.execute(query, params)
        rows = result.fetchall()

        # Convert rows to Context objects
        contexts = []
        for row in rows:
            stmt = select(Context).where(Context.id == row[0])
            ctx_result = await self.db.execute(stmt)
            ctx = ctx_result.scalar_one_or_none()
            if ctx:
                contexts.append(ctx)

        return contexts

    async def move_context(
        self,
        context_id: UUID,
        new_parent_id: Optional[UUID]
    ) -> Context:
        """
        Move a context to a new parent.

        Updates the context's path and all descendant paths.

        Args:
            context_id: Context to move
            new_parent_id: New parent UUID (None for root)

        Returns:
            Updated context

        Raises:
            ValueError: If moving to descendant (circular reference)
        """
        context = await self.get_context(context_id)
        if not context:
            raise ValueError(f"Context {context_id} not found")

        old_path = context.path

        # Build new path
        if new_parent_id:
            new_parent = await self.get_context(new_parent_id)
            if not new_parent:
                raise ValueError(f"New parent {new_parent_id} not found")

            if new_parent.organization_id != context.organization_id:
                raise ValueError("Cannot move context to different organization")

            # Check for circular reference
            if new_parent.path.startswith(old_path + '.'):
                raise ValueError("Cannot move context to its own descendant")

            new_path = Context.build_path(new_parent.path, context.name)
        else:
            new_path = Context.build_path(None, context.name)

        # Update context
        context.path = new_path
        context.parent_id = new_parent_id

        # Update all descendant paths
        descendants = await self.get_descendants(context_id, include_archived=True)
        for descendant in descendants:
            # Replace old path prefix with new path
            descendant.path = descendant.path.replace(old_path, new_path, 1)

        await self.db.commit()
        await self.db.refresh(context)

        logger.info(f"Moved context from {old_path} to {new_path}")
        return context

    async def archive_context(
        self,
        context_id: UUID,
        archive_descendants: bool = True
    ) -> Context:
        """
        Archive a context.

        Args:
            context_id: Context UUID
            archive_descendants: Whether to archive all descendants

        Returns:
            Archived context
        """
        context = await self.get_context(context_id)
        if not context:
            raise ValueError(f"Context {context_id} not found")

        context.archived = True

        if archive_descendants:
            descendants = await self.get_descendants(context_id, include_archived=False)
            for descendant in descendants:
                descendant.archived = True

        await self.db.commit()
        await self.db.refresh(context)

        logger.info(f"Archived context: {context.path}")
        return context

    async def unarchive_context(self, context_id: UUID) -> Context:
        """Unarchive a context."""
        context = await self.get_context(context_id)
        if not context:
            raise ValueError(f"Context {context_id} not found")

        context.archived = False
        await self.db.commit()
        await self.db.refresh(context)

        logger.info(f"Unarchived context: {context.path}")
        return context

    async def delete_context(
        self,
        context_id: UUID,
        delete_descendants: bool = True
    ) -> None:
        """
        Delete a context.

        Args:
            context_id: Context UUID
            delete_descendants: Whether to delete all descendants (default: True)

        Raises:
            ValueError: If context has children and delete_descendants=False
        """
        context = await self.get_context(context_id)
        if not context:
            raise ValueError(f"Context {context_id} not found")

        if not delete_descendants:
            children = await self.get_children(context_id)
            if children:
                raise ValueError(
                    f"Context has {len(children)} children. "
                    "Set delete_descendants=True or move children first."
                )

        # Delete context (cascade deletes descendants and bindings)
        await self.db.delete(context)
        await self.db.commit()

        logger.info(f"Deleted context: {context.path}")

    async def cleanup_expired_contexts(self, organization_id: UUID) -> int:
        """
        Delete expired contexts for an organization.

        Returns:
            Number of contexts deleted
        """
        stmt = select(Context).where(
            Context.organization_id == organization_id,
            Context.expires_at != None,
            Context.expires_at < datetime.now()
        )
        result = await self.db.execute(stmt)
        expired = result.scalars().all()

        count = 0
        for context in expired:
            await self.delete_context(context.id)
            count += 1

        logger.info(f"Cleaned up {count} expired contexts for org {organization_id}")
        return count

    async def update_context(
        self,
        context_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
        ttl_seconds: Optional[int] = None
    ) -> Context:
        """
        Update context metadata.

        Args:
            context_id: Context UUID
            name: New name (will update path)
            description: New description
            metadata: New metadata (replaces existing)
            ttl_seconds: New TTL in seconds

        Returns:
            Updated context
        """
        context = await self.get_context(context_id)
        if not context:
            raise ValueError(f"Context {context_id} not found")

        if name and name != context.name:
            # Update name and rebuild path
            parent_path = context.get_parent_path()
            new_path = Context.build_path(parent_path, name)

            old_path = context.path
            context.name = name
            context.path = new_path

            # Update descendant paths
            descendants = await self.get_descendants(context_id, include_archived=True)
            for descendant in descendants:
                descendant.path = descendant.path.replace(old_path, new_path, 1)

        if description is not None:
            context.description = description

        if metadata is not None:
            context.metadata = metadata

        if ttl_seconds is not None:
            context.set_ttl(ttl_seconds)

        await self.db.commit()
        await self.db.refresh(context)

        logger.info(f"Updated context: {context.path}")
        return context

    async def list_root_contexts(
        self,
        organization_id: UUID,
        include_archived: bool = False
    ) -> List[Context]:
        """
        List all root contexts for an organization.

        Args:
            organization_id: Organization UUID
            include_archived: Whether to include archived contexts

        Returns:
            List of root contexts (depth = 1)
        """
        stmt = select(Context).where(
            Context.organization_id == organization_id,
            Context.parent_id == None
        )

        if not include_archived:
            stmt = stmt.where(Context.archived == False)

        result = await self.db.execute(stmt)
        return result.scalars().all()
