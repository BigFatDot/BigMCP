"""
MCP Server API endpoints.

Provides REST API for dynamic MCP server management:
- Create/delete servers
- Install/start/stop/restart servers
- List servers with status
- Update server configuration
"""

import asyncio
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...db.database import get_async_session
from ...models.user import User
from ...models.api_key import APIKey
from ...models.mcp_server import MCPServer
from ...models.organization import UserRole, OrganizationType
from ..dependencies import get_current_user, get_current_organization
from ...services.mcp_server_service import MCPServerService
from ...schemas.mcp_server import (
    MCPServerCreate,
    MCPServerUpdate,
    MCPServerResponse,
    MCPServerListResponse
)


def _require_admin_for_team_org(membership) -> None:
    """Check admin role for team orgs."""
    if membership.role not in [UserRole.ADMIN, UserRole.OWNER, UserRole.MEMBER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization members can manage MCP servers"
        )

# Import gateway for UserServerPool access
from ...routers.mcp_unified import gateway


router = APIRouter()


# Dependency to get MCP server service
async def get_mcp_server_service(
    db: AsyncSession = Depends(get_async_session)
) -> MCPServerService:
    """Dependency to create MCP server service."""
    return MCPServerService(db)


@router.post(
    "/",
    response_model=MCPServerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create MCP server",
    description="Create a new MCP server configuration for the organization"
)
async def create_mcp_server(
    server_data: MCPServerCreate,
    org_context: tuple = Depends(get_current_organization),
    service: MCPServerService = Depends(get_mcp_server_service)
):
    """Create a new MCP server (admin only for team orgs)."""
    membership, organization_id = org_context

    # RBAC: Only admins can create servers in team orgs
    _require_admin_for_team_org(membership)

    try:
        server = await service.create_server(
            organization_id=organization_id,
            server_id=server_data.server_id,
            name=server_data.name,
            install_type=server_data.install_type,
            install_package=server_data.install_package,
            command=server_data.command,
            args=server_data.args,
            env=server_data.env,
            version=server_data.version,
            auto_start=server_data.auto_start
        )
        return MCPServerResponse.model_validate(server)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/",
    response_model=MCPServerListResponse,
    summary="List MCP servers",
    description="Get all MCP servers for the organization"
)
async def list_mcp_servers(
    org_context: tuple = Depends(get_current_organization),
    include_disabled: bool = False,
    service: MCPServerService = Depends(get_mcp_server_service)
):
    """List all MCP servers for an organization."""
    membership, organization_id = org_context

    servers = await service.list_servers(
        organization_id=organization_id,
        include_disabled=include_disabled
    )
    return MCPServerListResponse(
        servers=[MCPServerResponse.model_validate(s) for s in servers],
        total=len(servers)
    )


@router.get(
    "/{server_id}",
    response_model=MCPServerResponse,
    summary="Get MCP server",
    description="Get details of a specific MCP server by UUID or server_id"
)
async def get_mcp_server(
    server_id: str,
    org_context: tuple = Depends(get_current_organization),
    service: MCPServerService = Depends(get_mcp_server_service)
):
    """Get a specific MCP server by UUID or server_id string."""
    membership, organization_id = org_context

    # Try UUID first, then string server_id
    server = await service.get_server(
        organization_id=organization_id,
        identifier=server_id
    )

    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{server_id}' not found"
        )

    return MCPServerResponse.model_validate(server)


@router.patch(
    "/{server_id}",
    response_model=MCPServerResponse,
    summary="Update MCP server",
    description="Update MCP server configuration (accepts UUID or server_id)"
)
async def update_mcp_server(
    server_id: str,
    server_data: MCPServerUpdate,
    org_context: tuple = Depends(get_current_organization),
    service: MCPServerService = Depends(get_mcp_server_service)
):
    """Update MCP server configuration (admin only for team orgs)."""
    membership, organization_id = org_context

    # RBAC: Only admins can update servers in team orgs
    _require_admin_for_team_org(membership)

    # Try UUID first, then string server_id
    server = await service.get_server(
        organization_id=organization_id,
        identifier=server_id
    )

    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{server_id}' not found"
        )

    try:
        updated_server = await service.update_config(
            server_id=server.id,
            command=server_data.command,
            args=server_data.args,
            env=server_data.env,
            enabled=server_data.enabled,
            is_visible_to_oauth_clients=server_data.is_visible_to_oauth_clients
        )

        # Notify connected MCP clients if visibility or enabled state changed
        # This triggers cache refresh + SSE notification for all connected users in the org
        if server_data.is_visible_to_oauth_clients is not None or server_data.enabled is not None:
            from ...routers.mcp_unified import notify_org_tools_changed
            asyncio.create_task(notify_org_tools_changed(organization_id))

        return MCPServerResponse.model_validate(updated_server)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete(
    "/{server_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete MCP server",
    description="Delete an MCP server (accepts UUID or server_id)"
)
async def delete_mcp_server(
    server_id: str,
    org_context: tuple = Depends(get_current_organization),
    service: MCPServerService = Depends(get_mcp_server_service)
):
    """Delete an MCP server (admin only for team orgs)."""
    membership, organization_id = org_context

    # RBAC: Only admins can delete servers in team orgs
    _require_admin_for_team_org(membership)

    # Try UUID first, then string server_id
    server = await service.get_server(
        organization_id=organization_id,
        identifier=server_id
    )

    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{server_id}' not found"
        )

    await service.delete_server(server.id)

    # Invalidate caches for all users in this organization
    from ...services.organization_tool_cache import tool_cache
    from ...services.user_tool_cache import get_user_tool_cache
    await tool_cache.invalidate_organization(organization_id)
    user_cache = get_user_tool_cache()
    await user_cache.invalidate_organization(organization_id)
    logger.info(f"Invalidated caches for org {organization_id} after server deletion")

    # Notify SSE-connected clients (e.g. Claude Desktop) that tools changed
    try:
        from ...routers.mcp_unified import notify_org_tools_changed
        asyncio.create_task(notify_org_tools_changed(organization_id))
        logger.info(f"Scheduled tools/list_changed notification for org {organization_id} after server deletion")
    except Exception as e:
        logger.warning(f"Could not schedule tools notification after server deletion: {e}")

    return None


@router.post(
    "/{server_id}/install",
    response_model=MCPServerResponse,
    summary="Install MCP server",
    description="Install dependencies for an MCP server (accepts UUID or server_id)"
)
async def install_mcp_server(
    server_id: str,
    org_context: tuple = Depends(get_current_organization),
    service: MCPServerService = Depends(get_mcp_server_service)
):
    """Install an MCP server (admin only for team orgs)."""
    membership, organization_id = org_context

    # RBAC: Only admins can install servers in team orgs
    _require_admin_for_team_org(membership)

    # Try UUID first, then string server_id
    server = await service.get_server(
        organization_id=organization_id,
        identifier=server_id
    )

    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{server_id}' not found"
        )

    try:
        installed_server = await service.install(server.id)
        return MCPServerResponse.model_validate(installed_server)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/{server_uuid}/start",
    response_model=MCPServerResponse,
    summary="Start MCP server",
    description="Start an MCP server process via UserServerPool (with tool sync)"
)
async def start_mcp_server(
    server_uuid: UUID,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_session)
):
    """Start an MCP server using UserServerPool for proper tool discovery."""
    current_user, _ = auth
    membership, organization_id = org_context

    try:
        # Use UserServerPool for proper tool sync on start
        await gateway.user_server_pool.get_or_start_server(
            user_id=current_user.id,
            server_id=server_uuid,
            organization_id=organization_id
        )

        # Get updated server for response
        stmt = select(MCPServer).where(MCPServer.id == server_uuid)
        result = await db.execute(stmt)
        server = result.scalar_one_or_none()

        if not server:
            raise HTTPException(status_code=404, detail="Server not found")

        # Invalidate caches and notify connected MCP clients (new tools available)
        from ...services.organization_tool_cache import tool_cache
        from ...services.user_tool_cache import get_user_tool_cache
        await tool_cache.invalidate_organization(organization_id)
        user_cache = get_user_tool_cache()
        await user_cache.invalidate_organization(organization_id)
        from ...routers.mcp_unified import notify_org_tools_changed
        asyncio.create_task(notify_org_tools_changed(organization_id))

        return MCPServerResponse.model_validate(server)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/{server_uuid}/stop",
    response_model=MCPServerResponse,
    summary="Stop MCP server",
    description="Stop a running MCP server"
)
async def stop_mcp_server(
    server_uuid: UUID,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_session)
):
    """Stop an MCP server using UserServerPool."""
    current_user, _ = auth
    membership, organization_id = org_context

    try:
        # Stop via UserServerPool
        await gateway.user_server_pool.stop_user_server(
            user_id=current_user.id,
            server_id=server_uuid
        )

        # Get updated server for response
        stmt = select(MCPServer).where(MCPServer.id == server_uuid)
        result = await db.execute(stmt)
        server = result.scalar_one_or_none()

        if not server:
            raise HTTPException(status_code=404, detail="Server not found")

        # Invalidate caches and notify connected MCP clients (tools removed)
        from ...services.organization_tool_cache import tool_cache
        from ...services.user_tool_cache import get_user_tool_cache
        await tool_cache.invalidate_organization(organization_id)
        user_cache = get_user_tool_cache()
        await user_cache.invalidate_organization(organization_id)
        from ...routers.mcp_unified import notify_org_tools_changed
        asyncio.create_task(notify_org_tools_changed(organization_id))

        return MCPServerResponse.model_validate(server)

    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post(
    "/{server_uuid}/restart",
    response_model=MCPServerResponse,
    summary="Restart MCP server",
    description="Restart an MCP server"
)
async def restart_mcp_server(
    server_uuid: UUID,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    db: AsyncSession = Depends(get_async_session)
):
    """Restart an MCP server using UserServerPool (stop + start with tool sync)."""
    current_user, _ = auth
    membership, organization_id = org_context

    try:
        # Stop first (if running)
        await gateway.user_server_pool.stop_user_server(
            user_id=current_user.id,
            server_id=server_uuid
        )

        # Then start (with tool sync)
        await gateway.user_server_pool.get_or_start_server(
            user_id=current_user.id,
            server_id=server_uuid,
            organization_id=organization_id
        )

        # Get updated server for response
        stmt = select(MCPServer).where(MCPServer.id == server_uuid)
        result = await db.execute(stmt)
        server = result.scalar_one_or_none()

        if not server:
            raise HTTPException(status_code=404, detail="Server not found")

        # Invalidate caches and notify connected MCP clients (tools refreshed)
        from ...services.organization_tool_cache import tool_cache
        from ...services.user_tool_cache import get_user_tool_cache
        await tool_cache.invalidate_organization(organization_id)
        user_cache = get_user_tool_cache()
        await user_cache.invalidate_organization(organization_id)
        from ...routers.mcp_unified import notify_org_tools_changed
        asyncio.create_task(notify_org_tools_changed(organization_id))

        return MCPServerResponse.model_validate(server)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
