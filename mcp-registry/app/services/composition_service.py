"""
Composition Service - CRUD operations for workflow compositions.

Provides database operations for compositions with:
- Organization-scoped access (all org members can view)
- Creator/admin-based edit permissions
- RBAC execution control via allowed_roles
"""

import logging
from typing import List, Optional, Tuple
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.composition import Composition, CompositionStatus, CompositionVisibility
from ..models.organization import OrganizationMember, UserRole

logger = logging.getLogger(__name__)


class CompositionService:
    """
    Service for managing compositions in database.

    Visibility: All compositions visible to org members (team context)
    Edit: Creator or admin/owner
    Execute: Controlled by allowed_roles field
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # LIST / GET
    # =========================================================================

    async def list_compositions(
        self,
        organization_id: UUID,
        user_id: UUID,
        status: Optional[str] = None,
        created_by: Optional[UUID] = None,
        visibility_filter: Optional[str] = None
    ) -> List[Composition]:
        """
        List compositions visible to the user.

        Visibility rules:
        - PRIVATE: Only creator can see
        - ORGANIZATION: All org members can see
        - PUBLIC: Anyone can see (future)

        Args:
            organization_id: Organization context
            user_id: User requesting the list (for visibility filtering)
            status: Optional filter by status (temporary, validated, production)
            created_by: Optional filter by creator
            visibility_filter: Optional filter by visibility (private, organization)

        Returns:
            List of Composition objects visible to the user
        """
        # Base condition: org membership
        conditions = [Composition.organization_id == organization_id]

        # Visibility filter: user can see their own private + all organization-visible
        visibility_condition = or_(
            Composition.created_by == user_id,  # Always see own compositions
            Composition.visibility == CompositionVisibility.ORGANIZATION.value,  # See shared ones
            Composition.visibility == CompositionVisibility.PUBLIC.value  # See public ones (future)
        )
        conditions.append(visibility_condition)

        if status:
            conditions.append(Composition.status == status)

        if created_by:
            conditions.append(Composition.created_by == created_by)

        if visibility_filter:
            conditions.append(Composition.visibility == visibility_filter)

        stmt = (
            select(Composition)
            .where(and_(*conditions))
            .order_by(Composition.updated_at.desc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_composition(
        self,
        composition_id: UUID,
        organization_id: UUID,
        user_id: Optional[UUID] = None
    ) -> Optional[Composition]:
        """
        Get a composition by ID within an organization.

        Respects visibility rules if user_id is provided.

        Args:
            composition_id: Composition UUID
            organization_id: Organization context (for security)
            user_id: Optional user ID for visibility check

        Returns:
            Composition if found and visible, None otherwise
        """
        conditions = [
            Composition.id == composition_id,
            Composition.organization_id == organization_id
        ]

        # If user_id provided, apply visibility rules
        if user_id:
            visibility_condition = or_(
                Composition.created_by == user_id,
                Composition.visibility == CompositionVisibility.ORGANIZATION.value,
                Composition.visibility == CompositionVisibility.PUBLIC.value
            )
            conditions.append(visibility_condition)

        stmt = select(Composition).where(and_(*conditions))

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # =========================================================================
    # CREATE
    # =========================================================================

    async def create_composition(
        self,
        organization_id: UUID,
        created_by: UUID,
        name: str,
        description: Optional[str] = None,
        visibility: str = CompositionVisibility.PRIVATE.value,
        steps: Optional[list] = None,
        data_mappings: Optional[list] = None,
        input_schema: Optional[dict] = None,
        output_schema: Optional[dict] = None,
        server_bindings: Optional[dict] = None,
        allowed_roles: Optional[list] = None,
        force_org_credentials: bool = False,
        status: str = CompositionStatus.TEMPORARY.value,
        ttl: Optional[int] = None,
        extra_metadata: Optional[dict] = None
    ) -> Composition:
        """
        Create a new composition.

        Owner, admin, and member roles can create compositions.

        Args:
            organization_id: Organization this composition belongs to
            created_by: User creating the composition
            name: Composition name
            description: Optional description
            visibility: Visibility level (private, organization, public)
            steps: Workflow steps list
            data_mappings: Data flow mappings
            input_schema: JSON Schema for inputs
            output_schema: JSON Schema for outputs
            server_bindings: Server ID to UUID mapping
            allowed_roles: Roles allowed to execute (empty = all except viewer)
            force_org_credentials: Use org credentials instead of user's
            status: Lifecycle status
            ttl: Time-to-live for temporary compositions
            extra_metadata: Additional metadata

        Returns:
            Created Composition
        """
        composition = Composition(
            organization_id=organization_id,
            created_by=created_by,
            name=name,
            description=description,
            visibility=visibility,
            steps=steps or [],
            data_mappings=data_mappings or [],
            input_schema=input_schema or {},
            output_schema=output_schema,
            server_bindings=server_bindings or {},
            allowed_roles=allowed_roles or [],
            force_org_credentials=force_org_credentials,
            requires_approval=False,
            status=status,
            ttl=ttl,
            extra_metadata=extra_metadata or {}
        )

        self.db.add(composition)
        await self.db.commit()
        await self.db.refresh(composition)

        logger.info(f"Created composition '{name}' (id={composition.id}) by user {created_by}")
        return composition

    # =========================================================================
    # UPDATE
    # =========================================================================

    async def update_composition(
        self,
        composition_id: UUID,
        organization_id: UUID,
        user_id: UUID,
        user_role: UserRole,
        name: Optional[str] = None,
        description: Optional[str] = None,
        visibility: Optional[str] = None,
        steps: Optional[list] = None,
        data_mappings: Optional[list] = None,
        input_schema: Optional[dict] = None,
        output_schema: Optional[dict] = None,
        server_bindings: Optional[dict] = None,
        allowed_roles: Optional[list] = None,
        force_org_credentials: Optional[bool] = None,
        status: Optional[str] = None,
        ttl: Optional[int] = None,
        extra_metadata: Optional[dict] = None
    ) -> Tuple[Optional[Composition], Optional[str]]:
        """
        Update a composition.

        Permissions:
        - Creator can update their own composition
        - Admin/Owner can update any composition in org

        Args:
            composition_id: Composition to update
            organization_id: Organization context
            user_id: User making the update
            user_role: User's role in organization
            visibility: Visibility level (private, organization, public)
            ... other fields to update

        Returns:
            Tuple of (Composition or None, error_message or None)
        """
        composition = await self.get_composition(composition_id, organization_id)

        if not composition:
            return (None, "Composition not found")

        # Permission check: creator or admin/owner
        if composition.created_by != user_id:
            if user_role not in [UserRole.ADMIN, UserRole.OWNER]:
                return (None, "Only the creator or admin can update this composition")

        # Apply updates
        if name is not None:
            composition.name = name
        if description is not None:
            composition.description = description
        if visibility is not None:
            composition.visibility = visibility
        if steps is not None:
            composition.steps = steps
        if data_mappings is not None:
            composition.data_mappings = data_mappings
        if input_schema is not None:
            composition.input_schema = input_schema
        if output_schema is not None:
            composition.output_schema = output_schema
        if server_bindings is not None:
            composition.server_bindings = server_bindings
        if allowed_roles is not None:
            composition.allowed_roles = allowed_roles
        if force_org_credentials is not None:
            composition.force_org_credentials = force_org_credentials
        if status is not None:
            composition.status = status
        if ttl is not None:
            composition.ttl = ttl
        if extra_metadata is not None:
            composition.extra_metadata = extra_metadata

        await self.db.commit()
        await self.db.refresh(composition)

        logger.info(f"Updated composition '{composition.name}' (id={composition_id})")
        return (composition, None)

    # =========================================================================
    # DELETE
    # =========================================================================

    async def delete_composition(
        self,
        composition_id: UUID,
        organization_id: UUID,
        user_id: UUID,
        user_role: UserRole
    ) -> Tuple[bool, Optional[str]]:
        """
        Delete a composition.

        Permissions:
        - Creator can delete their own composition
        - Admin/Owner can delete any composition in org

        Args:
            composition_id: Composition to delete
            organization_id: Organization context
            user_id: User making the deletion
            user_role: User's role in organization

        Returns:
            Tuple of (success: bool, error_message or None)
        """
        composition = await self.get_composition(composition_id, organization_id)

        if not composition:
            return (False, "Composition not found")

        # Permission check: creator or admin/owner
        if composition.created_by != user_id:
            if user_role not in [UserRole.ADMIN, UserRole.OWNER]:
                return (False, "Only the creator or admin can delete this composition")

        await self.db.delete(composition)
        await self.db.commit()

        logger.info(f"Deleted composition '{composition.name}' (id={composition_id})")
        return (True, None)

    # =========================================================================
    # EXECUTION PERMISSIONS
    # =========================================================================

    async def can_execute(
        self,
        composition: Composition,
        user_id: UUID,
        organization_id: UUID
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if user can execute a composition.

        Rules:
        1. User must be org member
        2. If allowed_roles is set, user's role must be in the list
        3. VIEWER cannot execute unless explicitly allowed

        Args:
            composition: Composition to execute
            user_id: User attempting execution
            organization_id: Organization context

        Returns:
            Tuple of (can_execute: bool, reason or None)
        """
        # Get user's role
        user_role = await self._get_user_role(user_id, organization_id)

        if not user_role:
            return (False, "User is not a member of this organization")

        # Check allowed_roles if set
        if composition.allowed_roles:
            role_str = user_role.value
            if role_str not in composition.allowed_roles:
                allowed = ", ".join(composition.allowed_roles)
                return (False, f"Required role: {allowed}, your role: {role_str}")

        # Default: VIEWER cannot execute
        if user_role == UserRole.VIEWER:
            if not composition.allowed_roles or "viewer" not in [r.lower() for r in composition.allowed_roles]:
                return (False, "Viewers have read-only access")

        return (True, None)

    # =========================================================================
    # PROMOTE STATUS
    # =========================================================================

    async def promote_status(
        self,
        composition_id: UUID,
        organization_id: UUID,
        user_id: UUID,
        user_role: UserRole,
        new_status: str
    ) -> Tuple[Optional[Composition], Optional[str]]:
        """
        Promote composition to a new status (validated, production).

        Only admin/owner can promote to validated or production.

        Args:
            composition_id: Composition to promote
            organization_id: Organization context
            user_id: User making the promotion
            user_role: User's role
            new_status: Target status

        Returns:
            Tuple of (Composition or None, error or None)
        """
        composition = await self.get_composition(composition_id, organization_id)

        if not composition:
            return (None, "Composition not found")

        # Only admin/owner can promote
        if new_status in [CompositionStatus.VALIDATED.value, CompositionStatus.PRODUCTION.value]:
            if user_role not in [UserRole.ADMIN, UserRole.OWNER]:
                return (None, "Only admin or owner can promote to validated/production")

        composition.status = new_status
        composition.ttl = None  # Remove TTL when promoted

        await self.db.commit()
        await self.db.refresh(composition)

        logger.info(f"Promoted composition '{composition.name}' to {new_status}")
        return (composition, None)

    # =========================================================================
    # STATS / METADATA
    # =========================================================================

    async def update_execution_stats(
        self,
        composition_id: UUID,
        organization_id: UUID,
        success: bool,
        duration_ms: int
    ) -> None:
        """
        Update composition execution statistics.

        Args:
            composition_id: Composition that was executed
            organization_id: Organization context
            success: Whether execution succeeded
            duration_ms: Execution duration in milliseconds
        """
        composition = await self.get_composition(composition_id, organization_id)

        if not composition:
            return

        metadata = composition.extra_metadata or {}

        # Initialize stats if needed
        if "execution_count" not in metadata:
            metadata["execution_count"] = 0
            metadata["successes"] = 0
            metadata["failures"] = 0
            metadata["total_duration_ms"] = 0

        # Update stats
        metadata["execution_count"] += 1
        if success:
            metadata["successes"] += 1
        else:
            metadata["failures"] += 1

        metadata["total_duration_ms"] += duration_ms
        metadata["avg_duration_ms"] = metadata["total_duration_ms"] / metadata["execution_count"]
        metadata["success_rate"] = metadata["successes"] / metadata["execution_count"]
        metadata["last_executed_at"] = datetime.utcnow().isoformat()

        composition.extra_metadata = metadata

        await self.db.commit()

    # =========================================================================
    # HELPERS
    # =========================================================================

    async def _get_user_role(
        self,
        user_id: UUID,
        organization_id: UUID
    ) -> Optional[UserRole]:
        """Get user's role in organization."""
        stmt = select(OrganizationMember).where(
            and_(
                OrganizationMember.user_id == user_id,
                OrganizationMember.organization_id == organization_id
            )
        )

        result = await self.db.execute(stmt)
        member = result.scalar_one_or_none()

        return member.role if member else None


# Dependency injection factory
def get_composition_service(db: AsyncSession) -> CompositionService:
    """
    Get CompositionService instance.

    Usage:
        from app.services.composition_service import get_composition_service

        service = get_composition_service(db)
        compositions = await service.list_compositions(org_id)
    """
    return CompositionService(db)
