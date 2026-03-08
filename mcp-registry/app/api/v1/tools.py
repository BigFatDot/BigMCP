"""
API endpoints for tool visibility management.

Provides endpoints to list and update tool visibility settings
for multi-tenant organizations.
"""

import asyncio
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_db
from ...api.dependencies import get_current_user
from ...models.user import User
from ...models.api_key import APIKey
from ...services.tool_service import ToolService
from ...services.organization_tool_cache import tool_cache
from ...services.user_tool_cache import get_user_tool_cache
from ...schemas.tool import (
    ToolResponse,
    ToolUpdateVisibility,
    ToolListResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["Tools"])


@router.get("/", response_model=ToolListResponse)
async def list_tools(
    organization_id: Optional[UUID] = Query(None, description="Filter by organization"),
    server_id: Optional[str] = Query(None, description="Filter by server"),
    include_hidden: bool = Query(False, description="Include hidden tools (OAuth)"),
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List tools with visibility filtering.

    Multi-tenant: Returns only tools for the user's organization.

    For OAuth clients:
    - Returns only visible tools by default
    - Set include_hidden=true to see all tools

    For API Key clients:
    - Returns all enabled tools
    - Respects tool_group_id if set on API key

    Args:
        organization_id: Filter by specific organization (defaults to user's org)
        server_id: Filter by specific server
        include_hidden: Include tools hidden from OAuth (OAuth only)
        auth: Authentication (JWT or API Key)
        db: Database session

    Returns:
        List of tools matching filters
    """
    user, api_key = auth

    # Determine organization
    if api_key:
        # API key: use key's organization
        org_id = api_key.organization_id
    elif organization_id:
        # OAuth: use provided organization (TODO: validate membership)
        org_id = organization_id
    else:
        # OAuth: need organization_id
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="organization_id required for OAuth authentication"
        )

    # Get tools based on auth type
    service = ToolService(db)

    if api_key:
        # API Key: all tools (respect tool_group if set)
        tools = await service.list_tools_for_api_key(
            organization_id=org_id,
            tool_group_id=api_key.tool_group_id,
            server_id=server_id
        )
    else:
        # OAuth: Use tool cache for instant response
        tool_cache_service = get_user_tool_cache()
        cached_tools = await tool_cache_service.get(user.id)

        if cached_tools is not None:
            # Cache hit - return immediately and trigger background refresh
            # The background refresh will update cache + notify MCP SSE clients
            logger.info(
                f"Returning {len(cached_tools)} cached tools for user {user.id}, "
                "triggering background refresh with notification"
            )

            from ...routers.mcp_unified import gateway
            asyncio.create_task(
                gateway._background_refresh_tools(
                    user_uuid=user.id,
                    org_uuid=org_id
                )
            )

            # Return cached tools immediately
            tool_responses = [
                ToolResponse(**tool)
                for tool in cached_tools
                if server_id is None or tool.get("server_id") == server_id
            ]

            return ToolListResponse(
                tools=tool_responses,
                total=len(tool_responses),
                cached=True
            )

        # Cache miss - trigger background refresh and query DB
        # The background refresh will populate cache + notify MCP SSE clients
        # once servers are started
        logger.info(
            f"Cache miss for user {user.id}, triggering background refresh "
            "and querying database"
        )

        from ...routers.mcp_unified import gateway
        asyncio.create_task(
            gateway._background_refresh_tools(
                user_uuid=user.id,
                org_uuid=org_id
            )
        )

        # Query database (might be empty on first call)
        if include_hidden:
            # Show all tools (requires elevated permissions - TODO: check admin)
            tools = await service.list_tools_for_api_key(
                organization_id=org_id,
                server_id=server_id
            )
        else:
            # Show only visible tools
            tools = await service.list_tools_for_oauth(
                organization_id=org_id,
                server_id=server_id
            )

    # Convert to response schema
    tool_responses = [
        ToolResponse(
            id=tool.id,
            server_id=tool.server_id,
            organization_id=tool.organization_id,
            tool_name=tool.tool_name,
            display_name=tool.display_name,
            description=tool.description,
            parameters_schema=tool.parameters_schema,
            returns_schema=tool.returns_schema,
            tags=tool.tags,
            category=tool.category,
            is_visible_to_oauth_clients=tool.is_visible_to_oauth_clients,
            created_at=tool.created_at,
            updated_at=tool.updated_at
        )
        for tool in tools
    ]

    logger.info(
        f"Listed {len(tool_responses)} tools for org {org_id} "
        f"(auth={'api_key' if api_key else 'oauth'})"
    )

    return ToolListResponse(
        tools=tool_responses,
        total=len(tool_responses)
    )


@router.patch("/{tool_id}/visibility", response_model=ToolResponse)
async def update_tool_visibility(
    tool_id: UUID,
    update: ToolUpdateVisibility,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update tool visibility for OAuth clients.

    Multi-tenant: Only allows updating tools in user's organization.

    Validation:
    - Cannot make tool visible if server is hidden
    - User must have access to tool's organization

    Args:
        tool_id: Tool UUID
        update: Visibility update
        auth: Authentication (JWT or API Key)
        db: Database session

    Returns:
        Updated tool

    Raises:
        404: Tool not found
        400: Invalid visibility update (e.g., server is hidden)
        403: User not authorized
    """
    user, api_key = auth

    # Get tool to check organization
    service = ToolService(db)

    try:
        # Update visibility
        updated_tool = await service.update_tool_visibility(
            tool_id=tool_id,
            is_visible=update.is_visible_to_oauth_clients,
            user_id=user.id
        )

        # Verify user has access to this organization
        if api_key:
            if updated_tool.organization_id != api_key.organization_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot update tool from different organization"
                )
        # TODO: For OAuth, validate organization membership

        # Invalidate caches (org + all users in this org)
        await tool_cache.invalidate_organization(updated_tool.organization_id)
        user_cache = get_user_tool_cache()
        await user_cache.invalidate_organization(updated_tool.organization_id)

        logger.info(
            f"Updated tool {tool_id} visibility to "
            f"{update.is_visible_to_oauth_clients} by user {user.id}, caches invalidated"
        )

        # Notify connected MCP clients (cache refresh + SSE notification)
        from ...routers.mcp_unified import notify_org_tools_changed
        asyncio.create_task(notify_org_tools_changed(updated_tool.organization_id))

        # Return response
        return ToolResponse(
            id=updated_tool.id,
            server_id=updated_tool.server_id,
            organization_id=updated_tool.organization_id,
            tool_name=updated_tool.tool_name,
            display_name=updated_tool.display_name,
            description=updated_tool.description,
            parameters_schema=updated_tool.parameters_schema,
            returns_schema=updated_tool.returns_schema,
            tags=updated_tool.tags,
            category=updated_tool.category,
            is_visible_to_oauth_clients=updated_tool.is_visible_to_oauth_clients,
            created_at=updated_tool.created_at,
            updated_at=updated_tool.updated_at
        )

    except ValueError as e:
        # Validation error (e.g., can't make tool visible when server hidden)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to update tool visibility: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update tool visibility"
        )
