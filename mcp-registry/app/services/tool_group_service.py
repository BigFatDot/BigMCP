"""
ToolGroup Service - Management of specialized tool groups for AI agents.

Provides CRUD operations for ToolGroups and ToolGroupItems,
enabling users to create custom tool selections for different use cases.
"""

import logging
from typing import List, Optional, Set
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tool_group import ToolGroup, ToolGroupItem, ToolGroupVisibility, ToolGroupItemType
from ..models.tool import Tool
from ..models.mcp_server import MCPServer
from ..models.organization import Organization, OrganizationMember, UserRole


logger = logging.getLogger(__name__)


class ToolGroupService:
    """
    Service for managing tool groups.

    Tool groups allow users to create specialized AI agents by:
    - Selecting specific tools (e.g., only read operations)
    - Selecting specific compositions (e.g., pre-built workflows)
    - Controlling visibility to Claude via API key restrictions
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_groups(
        self,
        user_id: UUID,
        organization_id: UUID,
        include_org_groups: bool = True
    ) -> List[ToolGroup]:
        """
        List tool groups accessible to the user.

        Args:
            user_id: Current user's ID
            organization_id: Organization context
            include_org_groups: Whether to include organization-visible groups

        Returns:
            List of accessible ToolGroups with items loaded
        """
        conditions = [ToolGroup.organization_id == organization_id]

        if include_org_groups:
            # User's private groups OR organization-visible groups
            conditions.append(
                or_(
                    ToolGroup.user_id == user_id,
                    ToolGroup.visibility == ToolGroupVisibility.ORGANIZATION
                )
            )
        else:
            # Only user's own groups
            conditions.append(ToolGroup.user_id == user_id)

        stmt = (
            select(ToolGroup)
            .where(and_(*conditions))
            .options(selectinload(ToolGroup.items))
            .order_by(ToolGroup.name)
        )

        result = await self.db.execute(stmt)
        groups = result.scalars().all()

        # Enrich items with tool info
        for group in groups:
            await self._enrich_group_items(group)

        return list(groups)

    async def get_group(
        self,
        group_id: UUID,
        user_id: UUID,
        organization_id: UUID
    ) -> Optional[ToolGroup]:
        """
        Get a specific tool group if accessible.

        Args:
            group_id: ToolGroup UUID
            user_id: Current user's ID
            organization_id: Organization context

        Returns:
            ToolGroup if found and accessible, None otherwise
        """
        stmt = (
            select(ToolGroup)
            .where(
                and_(
                    ToolGroup.id == group_id,
                    ToolGroup.organization_id == organization_id,
                    or_(
                        ToolGroup.user_id == user_id,
                        ToolGroup.visibility == ToolGroupVisibility.ORGANIZATION
                    )
                )
            )
            .options(selectinload(ToolGroup.items))
        )

        result = await self.db.execute(stmt)
        group = result.scalar_one_or_none()

        if group:
            await self._enrich_group_items(group)

        return group

    async def create_group(
        self,
        user_id: UUID,
        organization_id: UUID,
        name: str,
        description: Optional[str] = None,
        icon: Optional[str] = None,
        color: Optional[str] = None,
        visibility: ToolGroupVisibility = ToolGroupVisibility.PRIVATE
    ) -> ToolGroup:
        """
        Create a new tool group.

        Args:
            user_id: Owner of the group
            organization_id: Organization context
            name: Group name
            description: Optional description
            icon: Optional icon identifier
            color: Optional hex color
            visibility: Visibility level

        Returns:
            Created ToolGroup

        Raises:
            ValueError: If name already exists in organization
        """
        # Check for duplicate name
        existing_stmt = select(ToolGroup).where(
            and_(
                ToolGroup.organization_id == organization_id,
                ToolGroup.name == name
            )
        )
        existing_result = await self.db.execute(existing_stmt)
        if existing_result.scalar_one_or_none():
            raise ValueError(f"Tool group '{name}' already exists in this organization")

        group = ToolGroup(
            user_id=user_id,
            organization_id=organization_id,
            name=name,
            description=description,
            icon=icon,
            color=color,
            visibility=visibility,
            is_active=True,
            extra_metadata={}
        )

        self.db.add(group)
        await self.db.commit()

        # Refresh with eager loading of items relationship to avoid lazy load errors
        stmt = (
            select(ToolGroup)
            .where(ToolGroup.id == group.id)
            .options(selectinload(ToolGroup.items))
        )
        result = await self.db.execute(stmt)
        group = result.scalar_one()

        logger.info(f"Created tool group '{name}' (id={group.id}) for user {user_id}")
        return group

    async def update_group(
        self,
        group_id: UUID,
        user_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        icon: Optional[str] = None,
        color: Optional[str] = None,
        visibility: Optional[ToolGroupVisibility] = None,
        is_active: Optional[bool] = None
    ) -> Optional[ToolGroup]:
        """
        Update a tool group (owner or org admin for shared groups).

        Args:
            group_id: Group to update
            user_id: Must be owner OR org admin (for organization-visible groups)
            name: New name (optional)
            description: New description (optional)
            icon: New icon (optional)
            color: New color (optional)
            visibility: New visibility (optional)
            is_active: New active status (optional)

        Returns:
            Updated ToolGroup or None if not found/not authorized
        """
        stmt = select(ToolGroup).where(ToolGroup.id == group_id)
        result = await self.db.execute(stmt)
        group = result.scalar_one_or_none()

        if not group:
            return None

        # Check if user can manage this group (owner or org admin for shared)
        if not await self._can_manage_group(group, user_id):
            return None

        # Check for duplicate name if changing
        if name and name != group.name:
            existing_stmt = select(ToolGroup).where(
                and_(
                    ToolGroup.organization_id == group.organization_id,
                    ToolGroup.name == name,
                    ToolGroup.id != group_id
                )
            )
            existing_result = await self.db.execute(existing_stmt)
            if existing_result.scalar_one_or_none():
                raise ValueError(f"Tool group '{name}' already exists in this organization")
            group.name = name

        if description is not None:
            group.description = description
        if icon is not None:
            group.icon = icon
        if color is not None:
            group.color = color
        if visibility is not None:
            group.visibility = visibility
        if is_active is not None:
            group.is_active = is_active

        await self.db.commit()
        await self.db.refresh(group)

        return group

    async def delete_group(
        self,
        group_id: UUID,
        user_id: UUID
    ) -> bool:
        """
        Delete a tool group (owner or org admin for shared groups).

        Args:
            group_id: Group to delete
            user_id: Must be owner OR org admin (for organization-visible groups)

        Returns:
            True if deleted, False if not found/not authorized
        """
        stmt = select(ToolGroup).where(ToolGroup.id == group_id)
        result = await self.db.execute(stmt)
        group = result.scalar_one_or_none()

        if not group:
            return False

        # Check if user can manage this group
        if not await self._can_manage_group(group, user_id):
            return False

        await self.db.delete(group)
        await self.db.commit()

        logger.info(f"Deleted tool group '{group.name}' (id={group_id})")
        return True

    async def add_tool_to_group(
        self,
        group_id: UUID,
        tool_id: UUID,
        user_id: UUID,
        order: int = 0,
        config: Optional[dict] = None
    ) -> Optional[ToolGroupItem]:
        """
        Add a tool to a group.

        Args:
            group_id: Target group
            tool_id: Tool to add
            user_id: Must be group owner OR org admin (for organization-visible groups)
            order: Display order
            config: Optional configuration overrides

        Returns:
            Created ToolGroupItem or None if group not found/not authorized
        """
        # Get group
        group_stmt = select(ToolGroup).where(ToolGroup.id == group_id)
        group_result = await self.db.execute(group_stmt)
        group = group_result.scalar_one_or_none()

        if not group:
            return None

        # Check if user can manage this group
        if not await self._can_manage_group(group, user_id):
            return None

        # Verify tool exists and belongs to same org
        tool_stmt = select(Tool).where(
            and_(
                Tool.id == tool_id,
                Tool.organization_id == group.organization_id
            )
        )
        tool_result = await self.db.execute(tool_stmt)
        tool = tool_result.scalar_one_or_none()

        if not tool:
            raise ValueError(f"Tool {tool_id} not found in organization")

        # Check if already in group
        existing_stmt = select(ToolGroupItem).where(
            and_(
                ToolGroupItem.tool_group_id == group_id,
                ToolGroupItem.tool_id == tool_id
            )
        )
        existing_result = await self.db.execute(existing_stmt)
        if existing_result.scalar_one_or_none():
            raise ValueError(f"Tool already in group")

        item = ToolGroupItem(
            tool_group_id=group_id,
            item_type=ToolGroupItemType.TOOL,
            tool_id=tool_id,
            order=order,
            config=config or {}
        )

        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)

        return item

    async def remove_item_from_group(
        self,
        group_id: UUID,
        item_id: UUID,
        user_id: UUID
    ) -> bool:
        """
        Remove an item from a group.

        Args:
            group_id: Group containing the item
            item_id: Item to remove
            user_id: Must be group owner OR org admin (for organization-visible groups)

        Returns:
            True if removed, False otherwise
        """
        # Get group
        group_stmt = select(ToolGroup).where(ToolGroup.id == group_id)
        group_result = await self.db.execute(group_stmt)
        group = group_result.scalar_one_or_none()

        if not group:
            return False

        # Check if user can manage this group
        if not await self._can_manage_group(group, user_id):
            return False

        # Find and delete item
        item_stmt = select(ToolGroupItem).where(
            and_(
                ToolGroupItem.id == item_id,
                ToolGroupItem.tool_group_id == group_id
            )
        )
        item_result = await self.db.execute(item_stmt)
        item = item_result.scalar_one_or_none()

        if not item:
            return False

        await self.db.delete(item)
        await self.db.commit()

        return True

    async def get_tools_in_group(self, group_id: UUID) -> Set[UUID]:
        """
        Get all tool IDs in a group.

        Used by MCP gateway to filter tools.

        Args:
            group_id: ToolGroup UUID

        Returns:
            Set of Tool UUIDs
        """
        stmt = select(ToolGroupItem.tool_id).where(
            and_(
                ToolGroupItem.tool_group_id == group_id,
                ToolGroupItem.item_type == ToolGroupItemType.TOOL,
                ToolGroupItem.tool_id.isnot(None)
            )
        )
        result = await self.db.execute(stmt)
        tool_ids = result.scalars().all()
        return set(tool_ids)

    async def list_available_tools(
        self,
        organization_id: UUID
    ) -> List[dict]:
        """
        List all tools available for adding to groups.

        Tool Groups can include ANY tool regardless of OAuth visibility.
        Hidden tools (is_visible_to_oauth_clients=False) ARE available for groups.
        Only RUNNING servers' tools are available (stopped servers excluded).

        Args:
            organization_id: Organization context

        Returns:
            List of tool info dicts with server details
        """
        from ..models.mcp_server import ServerStatus

        # Get all tools from RUNNING servers (visibility doesn't matter for tool groups)
        stmt = (
            select(Tool, MCPServer)
            .join(MCPServer, Tool.server_id == MCPServer.id)
            .where(
                and_(
                    Tool.organization_id == organization_id,
                    MCPServer.enabled == True,
                    MCPServer.status == ServerStatus.RUNNING  # Only running servers
                    # NOTE: is_visible_to_oauth_clients is NOT filtered here
                    # Tool groups can include hidden tools
                )
            )
            .order_by(MCPServer.name, Tool.tool_name)
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        # Get which tools are already in groups
        tool_ids = [row[0].id for row in rows]
        in_groups_stmt = select(
            ToolGroupItem.tool_id,
            ToolGroupItem.tool_group_id
        ).where(
            ToolGroupItem.tool_id.in_(tool_ids)
        )
        in_groups_result = await self.db.execute(in_groups_stmt)
        tool_to_groups = {}
        for tool_id, group_id in in_groups_result.all():
            if tool_id not in tool_to_groups:
                tool_to_groups[tool_id] = []
            tool_to_groups[tool_id].append(group_id)

        tools = []
        for tool, server in rows:
            tools.append({
                "id": tool.id,
                "server_id": server.id,
                "server_name": server.name,
                "tool_name": tool.tool_name,
                "display_name": tool.display_name,
                "description": tool.description,
                "category": tool.category,
                "tags": tool.tags,
                "in_groups": tool_to_groups.get(tool.id, [])
            })

        return tools

    async def record_usage(self, group_id: UUID) -> None:
        """
        Record usage of a tool group.

        Called by MCP gateway when a tool from this group is used.

        Args:
            group_id: Group that was used
        """
        stmt = select(ToolGroup).where(ToolGroup.id == group_id)
        result = await self.db.execute(stmt)
        group = result.scalar_one_or_none()

        if group:
            group.usage_count += 1
            group.last_used_at = datetime.utcnow()
            await self.db.commit()

    async def _is_org_admin(self, user_id: UUID, organization_id: UUID) -> bool:
        """
        Check if user is an admin or owner of the organization.

        Args:
            user_id: User to check
            organization_id: Organization context

        Returns:
            True if user is ADMIN or OWNER role
        """
        stmt = select(OrganizationMember).where(
            and_(
                OrganizationMember.user_id == user_id,
                OrganizationMember.organization_id == organization_id
            )
        )
        result = await self.db.execute(stmt)
        member = result.scalar_one_or_none()

        return member is not None and member.role in [UserRole.ADMIN, UserRole.OWNER]

    async def _can_manage_group(
        self,
        group: ToolGroup,
        user_id: UUID
    ) -> bool:
        """
        Check if user can manage (update/delete) a group.

        Rules:
        - Owner (creator) can always manage
        - Org admin can manage organization-visible groups

        Args:
            group: ToolGroup to check
            user_id: User attempting to manage

        Returns:
            True if user can manage the group
        """
        # Owner can always manage
        if group.user_id == user_id:
            return True

        # Org admin can manage organization-visible groups
        if group.visibility == ToolGroupVisibility.ORGANIZATION:
            return await self._is_org_admin(user_id, group.organization_id)

        return False

    async def _enrich_group_items(self, group: ToolGroup) -> None:
        """
        Load tool details for group items.

        Modifies items in-place to add tool_name, description, server info.
        """
        tool_ids = [
            item.tool_id for item in group.items
            if item.item_type == ToolGroupItemType.TOOL and item.tool_id
        ]

        if not tool_ids:
            return

        stmt = (
            select(Tool, MCPServer)
            .join(MCPServer, Tool.server_id == MCPServer.id)
            .where(Tool.id.in_(tool_ids))
        )
        result = await self.db.execute(stmt)

        tool_info = {}
        for tool, server in result.all():
            tool_info[tool.id] = {
                "tool_name": tool.tool_name,
                "tool_description": tool.description,
                "server_id": server.id,
                "server_name": server.name
            }

        for item in group.items:
            if item.tool_id and item.tool_id in tool_info:
                info = tool_info[item.tool_id]
                # These are dynamic attributes for serialization
                item._tool_name = info["tool_name"]
                item._tool_description = info["tool_description"]
                item._server_id = info["server_id"]
                item._server_name = info["server_name"]
