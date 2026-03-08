"""
Tool Groups API endpoints.

Allows users to create specialized tool groups for AI agents,
controlling which tools are exposed to Claude Desktop.
"""

from uuid import UUID
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_async_session
from ...models.user import User
from ...models.tool_group import ToolGroupVisibility, ToolGroupItemType
from ...services.tool_group_service import ToolGroupService
from ...schemas.tool_group import (
    ToolGroupCreate,
    ToolGroupUpdate,
    ToolGroupResponse,
    ToolGroupListResponse,
    ToolGroupItemCreate,
    ToolGroupItemResponse,
    ToolInfoResponse
)
from ..dependencies import get_current_user_jwt, get_current_organization_jwt


router = APIRouter(prefix="/tool-groups", tags=["Tool Groups"])


# ===== Dependencies =====

async def get_tool_group_service(
    db: AsyncSession = Depends(get_async_session)
) -> ToolGroupService:
    """Get ToolGroupService instance."""
    return ToolGroupService(db)



# ===== Endpoints =====

@router.get(
    "",
    response_model=ToolGroupListResponse,
    summary="List tool groups",
    description="List all tool groups accessible to the current user"
)
async def list_tool_groups(
    include_org_groups: bool = Query(
        True,
        description="Include organization-visible groups (not just own groups)"
    ),
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    service: ToolGroupService = Depends(get_tool_group_service)
):
    """
    List tool groups for the current user.

    Returns:
        - User's private groups
        - Organization-visible groups (if include_org_groups=True)
    """
    _, org_id = org_context

    groups = await service.list_groups(
        user_id=user.id,
        organization_id=org_id,
        include_org_groups=include_org_groups
    )

    return ToolGroupListResponse(
        groups=[_group_to_response(g) for g in groups],
        total=len(groups)
    )


@router.post(
    "",
    response_model=ToolGroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create tool group",
    description="Create a new tool group"
)
async def create_tool_group(
    data: ToolGroupCreate,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    service: ToolGroupService = Depends(get_tool_group_service)
):
    """
    Create a new tool group.

    The group starts empty - use POST /tool-groups/{id}/items to add tools.
    """
    _, org_id = org_context

    try:
        group = await service.create_group(
            user_id=user.id,
            organization_id=org_id,
            name=data.name,
            description=data.description,
            icon=data.icon,
            color=data.color,
            visibility=data.visibility
        )
        return _group_to_response(group)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/available-tools",
    response_model=List[ToolInfoResponse],
    summary="List available tools",
    description="List all tools that can be added to groups"
)
async def list_available_tools(
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    service: ToolGroupService = Depends(get_tool_group_service)
):
    """
    List all tools available for adding to groups.

    Returns tools from all enabled MCP servers in the user's organization,
    along with which groups each tool is already in.
    """
    _, org_id = org_context

    tools = await service.list_available_tools(organization_id=org_id)

    return [
        ToolInfoResponse(
            id=t["id"],
            server_id=t["server_id"],
            server_name=t["server_name"],
            tool_name=t["tool_name"],
            display_name=t.get("display_name"),
            description=t.get("description"),
            category=t.get("category"),
            tags=t.get("tags"),
            in_groups=t.get("in_groups", [])
        )
        for t in tools
    ]


@router.get(
    "/{group_id}",
    response_model=ToolGroupResponse,
    summary="Get tool group",
    description="Get details of a specific tool group"
)
async def get_tool_group(
    group_id: UUID,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    service: ToolGroupService = Depends(get_tool_group_service)
):
    """Get a specific tool group by ID."""
    _, org_id = org_context

    group = await service.get_group(
        group_id=group_id,
        user_id=user.id,
        organization_id=org_id
    )

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool group not found or not accessible"
        )

    return _group_to_response(group)


@router.patch(
    "/{group_id}",
    response_model=ToolGroupResponse,
    summary="Update tool group",
    description="Update tool group metadata (owner only)"
)
async def update_tool_group(
    group_id: UUID,
    data: ToolGroupUpdate,
    user: User = Depends(get_current_user_jwt),
    service: ToolGroupService = Depends(get_tool_group_service)
):
    """
    Update a tool group.

    Only the owner can update a group.
    """
    try:
        group = await service.update_group(
            group_id=group_id,
            user_id=user.id,
            name=data.name,
            description=data.description,
            icon=data.icon,
            color=data.color,
            visibility=data.visibility,
            is_active=data.is_active
        )

        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tool group not found or you are not the owner"
            )

        return _group_to_response(group)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete tool group",
    description="Delete a tool group (owner only)"
)
async def delete_tool_group(
    group_id: UUID,
    user: User = Depends(get_current_user_jwt),
    service: ToolGroupService = Depends(get_tool_group_service)
):
    """
    Delete a tool group.

    Only the owner can delete a group.
    Warning: Any API keys linked to this group will lose their tool restriction.
    """
    success = await service.delete_group(
        group_id=group_id,
        user_id=user.id
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool group not found or you are not the owner"
        )

    return None


@router.post(
    "/{group_id}/items",
    response_model=ToolGroupItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add tool to group",
    description="Add a tool to a tool group (owner only)"
)
async def add_item_to_group(
    group_id: UUID,
    data: ToolGroupItemCreate,
    user: User = Depends(get_current_user_jwt),
    service: ToolGroupService = Depends(get_tool_group_service)
):
    """
    Add a tool to a group.

    Only the group owner can add items.
    """
    if data.item_type == ToolGroupItemType.TOOL:
        if not data.tool_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tool_id is required for item_type=TOOL"
            )

        try:
            item = await service.add_tool_to_group(
                group_id=group_id,
                tool_id=data.tool_id,
                user_id=user.id,
                order=data.order,
                config=data.config
            )

            if not item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Tool group not found or you are not the owner"
                )

            return ToolGroupItemResponse(
                id=item.id,
                tool_group_id=item.tool_group_id,
                item_type=item.item_type.value if hasattr(item.item_type, 'value') else item.item_type,
                tool_id=item.tool_id,
                composition_id=item.composition_id,
                order=item.order,
                config=item.config
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
    else:
        # Composition support to be added later
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Composition items not yet supported"
        )


@router.delete(
    "/{group_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove item from group",
    description="Remove a tool from a tool group (owner only)"
)
async def remove_item_from_group(
    group_id: UUID,
    item_id: UUID,
    user: User = Depends(get_current_user_jwt),
    service: ToolGroupService = Depends(get_tool_group_service)
):
    """
    Remove a tool from a group.

    Only the group owner can remove items.
    """
    success = await service.remove_item_from_group(
        group_id=group_id,
        item_id=item_id,
        user_id=user.id
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found or you are not the group owner"
        )

    return None


# ===== Helper Functions =====

def _group_to_response(group) -> ToolGroupResponse:
    """Convert ToolGroup model to response schema."""
    items = []
    for item in group.items:
        item_response = ToolGroupItemResponse(
            id=item.id,
            tool_group_id=item.tool_group_id,
            item_type=item.item_type.value if hasattr(item.item_type, 'value') else item.item_type,
            tool_id=item.tool_id,
            composition_id=item.composition_id,
            order=item.order,
            config=item.config,
            # Enriched fields
            tool_name=getattr(item, '_tool_name', None),
            tool_description=getattr(item, '_tool_description', None),
            server_id=getattr(item, '_server_id', None),
            server_name=getattr(item, '_server_name', None)
        )
        items.append(item_response)

    return ToolGroupResponse(
        id=group.id,
        user_id=group.user_id,
        organization_id=group.organization_id,
        name=group.name,
        description=group.description,
        icon=group.icon,
        color=group.color,
        visibility=group.visibility.value if hasattr(group.visibility, 'value') else group.visibility,
        is_active=group.is_active,
        usage_count=group.usage_count,
        last_used_at=group.last_used_at,
        items=items,
        created_at=group.created_at,
        updated_at=group.updated_at
    )
