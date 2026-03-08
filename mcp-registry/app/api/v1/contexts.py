"""
Context API endpoints.

Provides REST API for hierarchical context management:
- Create/update/delete contexts
- Navigate context tree (children, descendants, ancestors)
- Archive/unarchive contexts
- Move contexts
- Search by ltree patterns
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_async_session
from ...models.user import User
from ...models.api_key import APIKey
from ..dependencies import get_current_user, get_current_organization
from ...services.context_service import ContextService
from ...schemas.context import (
    ContextCreate,
    ContextUpdate,
    ContextResponse
)


router = APIRouter()


# Dependency to get context service
async def get_context_service(
    db: AsyncSession = Depends(get_async_session)
) -> ContextService:
    """Dependency to create context service."""
    return ContextService(db)


@router.post(
    "/",
    response_model=ContextResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create context",
    description="Create a new hierarchical context"
)
async def create_context(
    context_data: ContextCreate,
    request: Request,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ContextService = Depends(get_context_service)
):
    """Create a new context."""
    current_user, _ = auth

    membership, organization_id = org_context
    created_by = current_user.id

    try:
        context = await service.create_context(
            organization_id=organization_id,
            name=context_data.name,
            context_type=context_data.context_type,
            parent_id=context_data.parent_id,
            description=context_data.description,
            ttl_seconds=context_data.ttl_seconds,
            metadata=context_data.metadata,
            created_by=created_by
        )
        return ContextResponse.model_validate(context)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/",
    response_model=List[ContextResponse],
    summary="List root contexts",
    description="Get all root-level contexts for the organization"
)
async def list_root_contexts(
    request: Request,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    include_archived: bool = False,
    service: ContextService = Depends(get_context_service)
):
    """List all root contexts."""
    current_user, _ = auth

    membership, organization_id = org_context

    contexts = await service.list_root_contexts(
        organization_id=organization_id,
        include_archived=include_archived
    )
    return [ContextResponse.model_validate(c) for c in contexts]


@router.get(
    "/{context_id}",
    response_model=ContextResponse,
    summary="Get context",
    description="Get details of a specific context"
)
async def get_context(
    context_id: UUID,
    request: Request,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ContextService = Depends(get_context_service)
):
    """Get a specific context."""
    current_user, _ = auth

    membership, organization_id = org_context

    # TODO: Service should verify context belongs to organization
    context = await service.get_context(context_id)

    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context {context_id} not found"
        )

    # Verify context belongs to user's organization
    if context.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context {context_id} not found"
        )

    return ContextResponse.model_validate(context)


@router.patch(
    "/{context_id}",
    response_model=ContextResponse,
    summary="Update context",
    description="Update context metadata"
)
async def update_context(
    context_id: UUID,
    context_data: ContextUpdate,
    request: Request,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ContextService = Depends(get_context_service)
):
    """Update a context."""
    current_user, _ = auth

    membership, organization_id = org_context

    # Verify context belongs to user's organization before updating
    context = await service.get_context(context_id)
    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context {context_id} not found"
        )

    if context.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context {context_id} not found"
        )

    try:
        context = await service.update_context(
            context_id=context_id,
            name=context_data.name,
            description=context_data.description,
            metadata=context_data.metadata,
            ttl_seconds=context_data.ttl_seconds
        )
        return ContextResponse.model_validate(context)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.delete(
    "/{context_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete context",
    description="Delete a context and optionally its descendants"
)
async def delete_context(
    context_id: UUID,
    request: Request,
    delete_descendants: bool = Query(
        True,
        description="Whether to delete all descendants"
    ),
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ContextService = Depends(get_context_service)
):
    """Delete a context."""
    current_user, _ = auth

    membership, organization_id = org_context

    # Verify context belongs to user's organization before deleting
    context = await service.get_context(context_id)
    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context {context_id} not found"
        )

    if context.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context {context_id} not found"
        )

    try:
        await service.delete_context(
            context_id=context_id,
            delete_descendants=delete_descendants
        )
        return None
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/{context_id}/children",
    response_model=List[ContextResponse],
    summary="Get children",
    description="Get immediate children of a context"
)
async def get_children(
    context_id: UUID,
    request: Request,
    include_archived: bool = False,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ContextService = Depends(get_context_service)
):
    """Get immediate children of a context."""
    current_user, _ = auth

    membership, organization_id = org_context

    # Verify parent context belongs to user's organization
    parent_context = await service.get_context(context_id)
    if not parent_context or parent_context.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context {context_id} not found"
        )

    children = await service.get_children(
        context_id=context_id,
        include_archived=include_archived
    )
    return [ContextResponse.model_validate(c) for c in children]


@router.get(
    "/{context_id}/descendants",
    response_model=List[ContextResponse],
    summary="Get descendants",
    description="Get all descendants of a context (entire subtree)"
)
async def get_descendants(
    context_id: UUID,
    request: Request,
    include_archived: bool = False,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ContextService = Depends(get_context_service)
):
    """Get all descendants of a context."""
    current_user, _ = auth

    membership, organization_id = org_context

    # Verify context belongs to user's organization
    context = await service.get_context(context_id)
    if not context or context.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context {context_id} not found"
        )

    try:
        descendants = await service.get_descendants(
            context_id=context_id,
            include_archived=include_archived
        )
        return [ContextResponse.model_validate(c) for c in descendants]
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get(
    "/{context_id}/ancestors",
    response_model=List[ContextResponse],
    summary="Get ancestors",
    description="Get all ancestors of a context (path to root)"
)
async def get_ancestors(
    context_id: UUID,
    request: Request,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ContextService = Depends(get_context_service)
):
    """Get all ancestors of a context."""
    current_user, _ = auth

    membership, organization_id = org_context

    # Verify context belongs to user's organization
    context = await service.get_context(context_id)
    if not context or context.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context {context_id} not found"
        )

    try:
        ancestors = await service.get_ancestors(context_id)
        return [ContextResponse.model_validate(c) for c in ancestors]
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post(
    "/{context_id}/move",
    response_model=ContextResponse,
    summary="Move context",
    description="Move a context to a new parent"
)
async def move_context(
    context_id: UUID,
    request: Request,
    new_parent_id: Optional[UUID] = Query(
        None,
        description="New parent UUID (null for root)"
    ),
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ContextService = Depends(get_context_service)
):
    """Move a context to a new parent."""
    current_user, _ = auth

    membership, organization_id = org_context

    # Verify context belongs to user's organization
    context = await service.get_context(context_id)
    if not context or context.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context {context_id} not found"
        )

    # Verify new parent (if specified) also belongs to same organization
    if new_parent_id:
        new_parent = await service.get_context(new_parent_id)
        if not new_parent or new_parent.organization_id != organization_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Parent context {new_parent_id} not found"
            )

    try:
        context = await service.move_context(
            context_id=context_id,
            new_parent_id=new_parent_id
        )
        return ContextResponse.model_validate(context)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post(
    "/{context_id}/archive",
    response_model=ContextResponse,
    summary="Archive context",
    description="Archive a context and optionally its descendants"
)
async def archive_context(
    context_id: UUID,
    request: Request,
    archive_descendants: bool = Query(
        True,
        description="Whether to archive all descendants"
    ),
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ContextService = Depends(get_context_service)
):
    """Archive a context."""
    current_user, _ = auth

    membership, organization_id = org_context

    # Verify context belongs to user's organization
    context = await service.get_context(context_id)
    if not context or context.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context {context_id} not found"
        )

    try:
        context = await service.archive_context(
            context_id=context_id,
            archive_descendants=archive_descendants
        )
        return ContextResponse.model_validate(context)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post(
    "/{context_id}/unarchive",
    response_model=ContextResponse,
    summary="Unarchive context",
    description="Unarchive a context"
)
async def unarchive_context(
    context_id: UUID,
    request: Request,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ContextService = Depends(get_context_service)
):
    """Unarchive a context."""
    current_user, _ = auth

    membership, organization_id = org_context

    # Verify context belongs to user's organization
    context = await service.get_context(context_id)
    if not context or context.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Context {context_id} not found"
        )

    try:
        context = await service.unarchive_context(context_id)
        return ContextResponse.model_validate(context)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get(
    "/search/",
    response_model=List[ContextResponse],
    summary="Search by pattern",
    description="Search contexts using ltree pattern (e.g., 'root.*' or 'root.*.docs')"
)
async def search_by_pattern(
    request: Request,
    pattern: str = Query(
        ...,
        description="ltree pattern to match",
        examples=["root.*", "root.*{1,2}", "root.*.docs"]
    ),
    include_archived: bool = False,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ContextService = Depends(get_context_service)
):
    """Search contexts by ltree pattern."""
    current_user, _ = auth

    membership, organization_id = org_context

    contexts = await service.search_by_pattern(
        organization_id=organization_id,
        pattern=pattern,
        include_archived=include_archived
    )
    return [ContextResponse.model_validate(c) for c in contexts]


@router.post(
    "/cleanup-expired",
    summary="Cleanup expired contexts",
    description="Delete all expired contexts for the organization"
)
async def cleanup_expired_contexts(
    request: Request,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ContextService = Depends(get_context_service)
):
    """Delete all expired contexts."""
    current_user, _ = auth

    membership, organization_id = org_context

    count = await service.cleanup_expired_contexts(organization_id)
    return {
        "deleted_count": count,
        "message": f"Deleted {count} expired context(s)"
    }
