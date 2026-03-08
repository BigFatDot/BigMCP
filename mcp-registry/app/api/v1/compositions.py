"""
Compositions API endpoints.

CRUD operations for workflow compositions with RBAC.
All compositions visible to org members (team context).
"""

import asyncio
import logging
from datetime import datetime
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from ...db.database import get_async_session
from ...models.user import User
from ...models.organization import UserRole
from ...models.composition import CompositionStatus
from ...services.composition_service import CompositionService
from ...schemas.composition import (
    CompositionCreate,
    CompositionUpdate,
    CompositionPromote,
    CompositionResponse,
    CompositionListResponse,
    CompositionExecuteRequest,
    CompositionExecuteResponse
)
from ..dependencies import get_current_user_jwt, get_current_organization_jwt


router = APIRouter(prefix="/compositions", tags=["Compositions"])


# =============================================================================
# DEPENDENCIES
# =============================================================================

async def get_composition_service(
    db: AsyncSession = Depends(get_async_session)
) -> CompositionService:
    """Get CompositionService instance."""
    return CompositionService(db)



# =============================================================================
# LIST / GET ENDPOINTS
# =============================================================================

@router.get(
    "",
    response_model=CompositionListResponse,
    summary="List compositions",
    description="List compositions visible to the user"
)
async def list_compositions(
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by status (temporary, validated, production)"
    ),
    visibility_filter: Optional[str] = Query(
        None,
        alias="visibility",
        description="Filter by visibility (private, organization)"
    ),
    mine_only: bool = Query(
        False,
        description="Show only my compositions"
    ),
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    service: CompositionService = Depends(get_composition_service)
):
    """
    List compositions visible to the user.

    Visibility rules:
    - Private compositions: only visible to creator
    - Organization compositions: visible to all org members
    """
    membership, org_id = org_context
    user_role = membership.role

    compositions = await service.list_compositions(
        organization_id=org_id,
        user_id=user.id,
        status=status_filter,
        created_by=user.id if mine_only else None,
        visibility_filter=visibility_filter
    )

    # Enrich with permission info
    response_list = []
    for comp in compositions:
        can_exec, _ = await service.can_execute(comp, user.id, org_id)
        can_edit = (
            comp.created_by == user.id or
            user_role in [UserRole.ADMIN, UserRole.OWNER]
        )

        response_list.append(_composition_to_response(comp, can_exec, can_edit))

    return CompositionListResponse(
        compositions=response_list,
        total=len(response_list)
    )


@router.get(
    "/{composition_id}",
    response_model=CompositionResponse,
    summary="Get composition",
    description="Get details of a specific composition"
)
async def get_composition(
    composition_id: UUID,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    service: CompositionService = Depends(get_composition_service)
):
    """Get a specific composition by ID (respects visibility rules)."""
    membership, org_id = org_context
    user_role = membership.role

    composition = await service.get_composition(composition_id, org_id, user_id=user.id)

    if not composition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Composition not found"
        )

    can_exec, _ = await service.can_execute(composition, user.id, org_id)
    can_edit = (
        composition.created_by == user.id or
        user_role in [UserRole.ADMIN, UserRole.OWNER]
    )

    return _composition_to_response(composition, can_exec, can_edit)


# =============================================================================
# CREATE ENDPOINT
# =============================================================================

@router.post(
    "",
    response_model=CompositionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create composition",
    description="Create a new composition"
)
async def create_composition(
    data: CompositionCreate,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    service: CompositionService = Depends(get_composition_service)
):
    """
    Create a new composition.

    Owner, admin, and member roles can create compositions.
    Viewers cannot create.
    """
    membership, org_id = org_context
    user_role = membership.role

    # Viewers cannot create
    if user_role == UserRole.VIEWER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot create compositions"
        )

    composition = await service.create_composition(
        organization_id=org_id,
        created_by=user.id,
        name=data.name,
        description=data.description,
        visibility=data.visibility,
        steps=data.steps,
        data_mappings=data.data_mappings,
        input_schema=data.input_schema,
        output_schema=data.output_schema,
        server_bindings=data.server_bindings,
        allowed_roles=data.allowed_roles,
        force_org_credentials=data.force_org_credentials,
        status=data.status,
        ttl=data.ttl,
        extra_metadata=data.extra_metadata
    )

    from ...routers.mcp_unified import broadcast_resources_changed
    asyncio.create_task(broadcast_resources_changed(org_id))

    return _composition_to_response(composition, can_execute=True, can_edit=True)


# =============================================================================
# UPDATE ENDPOINT
# =============================================================================

@router.patch(
    "/{composition_id}",
    response_model=CompositionResponse,
    summary="Update composition",
    description="Update a composition (creator or admin)"
)
async def update_composition(
    composition_id: UUID,
    data: CompositionUpdate,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    service: CompositionService = Depends(get_composition_service)
):
    """
    Update a composition.

    Permissions:
    - Creator can update their own composition
    - Admin/Owner can update any composition
    """
    membership, org_id = org_context
    user_role = membership.role

    composition, error = await service.update_composition(
        composition_id=composition_id,
        organization_id=org_id,
        user_id=user.id,
        user_role=user_role,
        name=data.name,
        description=data.description,
        visibility=data.visibility,
        steps=data.steps,
        data_mappings=data.data_mappings,
        input_schema=data.input_schema,
        output_schema=data.output_schema,
        server_bindings=data.server_bindings,
        allowed_roles=data.allowed_roles,
        force_org_credentials=data.force_org_credentials,
        status=data.status,
        ttl=data.ttl,
        extra_metadata=data.extra_metadata
    )

    if error:
        if "not found" in error.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=error)

    can_exec, _ = await service.can_execute(composition, user.id, org_id)

    from ...routers.mcp_unified import broadcast_resources_changed
    asyncio.create_task(broadcast_resources_changed(org_id))

    return _composition_to_response(composition, can_exec, can_edit=True)


# =============================================================================
# DELETE ENDPOINT
# =============================================================================

@router.delete(
    "/{composition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete composition",
    description="Delete a composition (creator or admin)"
)
async def delete_composition(
    composition_id: UUID,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    service: CompositionService = Depends(get_composition_service)
):
    """
    Delete a composition.

    Permissions:
    - Creator can delete their own composition
    - Admin/Owner can delete any composition
    """
    membership, org_id = org_context
    user_role = membership.role

    success, error = await service.delete_composition(
        composition_id=composition_id,
        organization_id=org_id,
        user_id=user.id,
        user_role=user_role
    )

    if not success:
        if error and "not found" in error.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=error)

    from ...routers.mcp_unified import broadcast_resources_changed
    asyncio.create_task(broadcast_resources_changed(org_id))

    return None


# =============================================================================
# PROMOTE ENDPOINT
# =============================================================================

@router.post(
    "/{composition_id}/promote",
    response_model=CompositionResponse,
    summary="Promote composition",
    description="Promote composition to validated or production (admin only)"
)
async def promote_composition(
    composition_id: UUID,
    data: CompositionPromote,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    service: CompositionService = Depends(get_composition_service)
):
    """
    Promote a composition to a new status.

    Only admin/owner can promote to validated or production.
    """
    membership, org_id = org_context
    user_role = membership.role

    # Validate status value
    valid_statuses = [s.value for s in CompositionStatus]
    if data.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {valid_statuses}"
        )

    composition, error = await service.promote_status(
        composition_id=composition_id,
        organization_id=org_id,
        user_id=user.id,
        user_role=user_role,
        new_status=data.status
    )

    if error:
        if "not found" in error.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=error)

    can_exec, _ = await service.can_execute(composition, user.id, org_id)
    can_edit = user_role in [UserRole.ADMIN, UserRole.OWNER]

    from ...routers.mcp_unified import broadcast_resources_changed
    asyncio.create_task(broadcast_resources_changed(org_id))

    return _composition_to_response(composition, can_exec, can_edit)


# =============================================================================
# EXECUTE ENDPOINT
# =============================================================================

@router.post(
    "/{composition_id}/execute",
    response_model=CompositionExecuteResponse,
    summary="Execute composition",
    description="Execute a composition with provided inputs"
)
async def execute_composition(
    composition_id: UUID,
    data: CompositionExecuteRequest,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    service: CompositionService = Depends(get_composition_service)
):
    """
    Execute a composition.

    Permissions controlled by composition's allowed_roles field.
    VIEWER cannot execute by default.

    The execution uses the user's server pool for multi-tenant isolation,
    ensuring each user's credentials are used for tool execution.
    """
    membership, org_id = org_context

    composition = await service.get_composition(composition_id, org_id)

    if not composition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Composition not found"
        )

    # Check execution permission
    can_exec, reason = await service.can_execute(composition, user.id, org_id)
    if not can_exec:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=reason or "Cannot execute this composition"
        )

    # Import executor and gateway
    from ...orchestration.composition_executor import CompositionExecutor
    from ...routers.mcp_unified import gateway

    # Instantiate executor with global registry
    executor = CompositionExecutor(registry=gateway.registry)

    # Execute with multi-tenant context
    try:
        result = await executor.execute(
            composition_id=str(composition_id),
            parameters=data.inputs,
            user_id=str(user.id),
            organization_id=str(org_id),
            user_server_pool=gateway.user_server_pool
        )
    except Exception as e:
        logger.error(f"Composition execution failed: {e}", exc_info=True)
        return CompositionExecuteResponse(
            composition_id=composition_id,
            execution_id=None,
            status="failed",
            outputs={},
            duration_ms=0,
            step_results=[],
            started_at=datetime.now(),
            completed_at=datetime.now(),
            error=str(e)
        )

    # Map executor result to response schema
    # Parse timestamps if they are strings
    started_at = None
    completed_at = None
    if result.get("started_at"):
        try:
            started_at = datetime.fromisoformat(result["started_at"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            started_at = None
    if result.get("completed_at"):
        try:
            completed_at = datetime.fromisoformat(result["completed_at"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            completed_at = None

    # Build step_results with proper schema
    step_results = []
    for step in result.get("steps_executed", []):
        step_results.append({
            "step_id": step.get("step_id", ""),
            "tool": step.get("tool", ""),
            "status": step.get("status", "failed"),
            "duration_ms": step.get("duration_ms", 0),
            "result": step.get("result") if step.get("status") == "success" else None,
            "error": step.get("error"),
            "retries": step.get("retries", 0)
        })

    # Combine errors into single string
    errors_list = result.get("errors", [])
    error_message = "; ".join(errors_list) if errors_list else result.get("error")

    # Update execution stats in database
    try:
        await service.update_execution_stats(
            composition_id=composition_id,
            organization_id=org_id,
            success=result.get("status") == "success",
            duration_ms=result.get("total_duration_ms", 0)
        )
    except Exception as e:
        logger.warning(f"Failed to update execution stats: {e}")

    return CompositionExecuteResponse(
        composition_id=composition_id,
        execution_id=result.get("execution_id"),
        status=result.get("status", "failed"),
        outputs=result.get("result") or {},
        duration_ms=result.get("total_duration_ms", 0),
        step_results=step_results,
        started_at=started_at,
        completed_at=completed_at,
        error=error_message
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _composition_to_response(
    composition,
    can_execute: bool = None,
    can_edit: bool = None
) -> CompositionResponse:
    """Convert Composition model to response schema."""
    return CompositionResponse(
        id=composition.id,
        organization_id=composition.organization_id,
        created_by=composition.created_by,
        name=composition.name,
        description=composition.description,
        visibility=composition.visibility,
        steps=composition.steps,
        data_mappings=composition.data_mappings,
        input_schema=composition.input_schema,
        output_schema=composition.output_schema,
        server_bindings=composition.server_bindings,
        allowed_roles=composition.allowed_roles,
        force_org_credentials=composition.force_org_credentials,
        requires_approval=composition.requires_approval,
        status=composition.status,
        ttl=composition.ttl,
        extra_metadata=composition.extra_metadata,
        created_at=composition.created_at,
        updated_at=composition.updated_at,
        can_execute=can_execute,
        can_edit=can_edit
    )
