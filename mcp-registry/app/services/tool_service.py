"""
Tool Service - Tool management with visibility filtering.

Provides tool filtering for different authentication types:
- OAuth clients: Only visible tools from visible servers
- API key clients: All tools from enabled servers (+ optional tool_group filtering)
"""

import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tool import Tool
from ..models.mcp_server import MCPServer
from ..models.tool_group import ToolGroupItem

logger = logging.getLogger(__name__)


class ToolService:
    """
    Service for managing tools with visibility filtering.

    Distinguishes:
    - OAuth clients: only visible tools
    - API key clients: all tools (+ optional tool_group filtering)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_tools_for_oauth(
        self,
        organization_id: UUID,
        server_id: Optional[str] = None
    ) -> List[Tool]:
        """
        List tools visible to OAuth clients.

        Filters:
        - Server must be enabled AND visible
        - Tool must be visible

        Args:
            organization_id: Organization UUID
            server_id: Optional server_id to filter by specific server

        Returns:
            List of visible tools
        """
        stmt = (
            select(Tool)
            .join(Tool.server)
            .where(
                and_(
                    MCPServer.organization_id == organization_id,
                    MCPServer.enabled == True,
                    MCPServer.is_visible_to_oauth_clients == True,
                    Tool.is_visible_to_oauth_clients == True
                )
            )
            .options(selectinload(Tool.server))
        )

        if server_id:
            stmt = stmt.where(MCPServer.server_id == server_id)

        result = await self.db.execute(stmt)
        tools = result.scalars().all()

        logger.debug(f"OAuth tools for org {organization_id}: {len(tools)} tools")
        return list(tools)

    async def list_tools_for_api_key(
        self,
        organization_id: UUID,
        tool_group_id: Optional[UUID] = None,
        server_id: Optional[str] = None
    ) -> List[Tool]:
        """
        List tools accessible via API key.

        Filters:
        - Server must be enabled (visibility doesn't matter)
        - If tool_group_id: only tools in that group
        - Otherwise: all tools from enabled servers

        Args:
            organization_id: Organization UUID
            tool_group_id: Optional tool group to filter by
            server_id: Optional server_id to filter by specific server

        Returns:
            List of accessible tools
        """
        stmt = (
            select(Tool)
            .join(Tool.server)
            .where(
                and_(
                    MCPServer.organization_id == organization_id,
                    MCPServer.enabled == True
                )
            )
            .options(selectinload(Tool.server))
        )

        if server_id:
            stmt = stmt.where(MCPServer.server_id == server_id)

        # Filter by tool group if specified
        if tool_group_id:
            stmt = (
                stmt
                .join(ToolGroupItem, ToolGroupItem.tool_id == Tool.id)
                .where(ToolGroupItem.tool_group_id == tool_group_id)
            )

        result = await self.db.execute(stmt)
        tools = result.scalars().all()

        logger.debug(
            f"API key tools for org {organization_id}: {len(tools)} tools "
            f"(tool_group={tool_group_id})"
        )
        return list(tools)

    async def update_tool_visibility(
        self,
        tool_id: UUID,
        is_visible: bool,
        user_id: Optional[UUID] = None
    ) -> Tool:
        """
        Update tool visibility for OAuth clients.

        Validation:
        - User must have access to tool's organization
        - If making tool visible, server must also be visible

        Args:
            tool_id: Tool UUID
            is_visible: New visibility state
            user_id: User making the change (for audit)

        Returns:
            Updated tool

        Raises:
            ValueError: If validation fails
        """
        # Get tool
        stmt = select(Tool).where(Tool.id == tool_id).options(selectinload(Tool.server))
        result = await self.db.execute(stmt)
        tool = result.scalar_one_or_none()

        if not tool:
            raise ValueError(f"Tool {tool_id} not found")

        # Validation: can't make tool visible if server is hidden
        if is_visible and not tool.server.is_visible_to_oauth_clients:
            raise ValueError(
                "Cannot make tool visible when server is hidden. "
                "Make server visible first."
            )

        # Update
        tool.is_visible_to_oauth_clients = is_visible
        await self.db.commit()
        await self.db.refresh(tool)

        logger.info(
            f"Tool {tool_id} visibility updated to {is_visible} by user {user_id or 'system'}"
        )

        return tool

    async def bulk_update_tool_visibility(
        self,
        server_id: UUID,
        is_visible: bool,
        user_id: Optional[UUID] = None
    ) -> int:
        """
        Update visibility for all tools of a server.

        Used when making a server hidden: hide all its tools.

        Args:
            server_id: Server UUID (database id, not server_id string)
            is_visible: New visibility state
            user_id: User making the change

        Returns:
            Number of tools updated
        """
        stmt = (
            select(Tool)
            .where(Tool.server_id == server_id)
        )
        result = await self.db.execute(stmt)
        tools = result.scalars().all()

        count = 0
        for tool in tools:
            tool.is_visible_to_oauth_clients = is_visible
            count += 1

        await self.db.commit()

        logger.info(
            f"Bulk updated {count} tools for server {server_id} "
            f"to visibility={is_visible} by user {user_id or 'system'}"
        )

        return count
