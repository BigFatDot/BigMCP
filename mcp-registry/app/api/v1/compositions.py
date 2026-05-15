"""
Compositions API endpoints.

CRUD operations for workflow compositions with RBAC.
All compositions visible to org members (team context).
"""

import asyncio
import logging
from datetime import datetime
from uuid import UUID
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from ...db.database import get_async_session
from ...models.user import User
from ...models.organization import UserRole
from ...models.composition import CompositionStatus
from ...models.audit_log import AuditAction
from ...services.composition_service import CompositionService
from ...services.audit_service import AuditService
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
        err_lower = error.lower()
        if "not found" in err_lower:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error)
        if "input_schema" in err_lower:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error
            )
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

    # When the caller passes a NL `goal` (and no full inputs), delegate to the
    # same execute path used by the `execute` MCP tool. This lets the web UI
    # offer a "test with prompt" panel that mirrors the agent experience.
    nl_goal = (data.goal or "").strip()
    if nl_goal and not data.inputs:
        from ...routers.mcp_gateway.pool.execute_handler import handle_execute

        nl_payload = await handle_execute(
            arguments={"composition_id": str(composition_id), "goal": nl_goal},
            user_id=str(user.id),
            organization_id=str(org_id),
            gateway=gateway,
        )
        # Surface the inner executor result so the response shape stays the
        # same as a regular execution. handle_execute wraps in {"result": ...}.
        result = nl_payload.get("result") if isinstance(nl_payload, dict) else None
        if not isinstance(result, dict):
            return CompositionExecuteResponse(
                composition_id=composition_id,
                execution_id=None,
                status="failed",
                outputs={},
                duration_ms=0,
                step_results=[],
                started_at=datetime.now(),
                completed_at=datetime.now(),
                error=(nl_payload.get("error") if isinstance(nl_payload, dict) else "NL execution failed"),
            )
    else:
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
        share_request_status=getattr(composition, "share_request_status", None),
        share_requested_by=getattr(composition, "share_requested_by", None),
        share_requested_at=getattr(composition, "share_requested_at", None),
        share_review_notes=getattr(composition, "share_review_notes", None),
        share_reviewed_by=getattr(composition, "share_reviewed_by", None),
        share_reviewed_at=getattr(composition, "share_reviewed_at", None),
        can_execute=can_execute,
        can_edit=can_edit
    )



# =============================================================================
# LLM-FIRST COMPOSITION PROPOSAL
# =============================================================================


class CompositionProposeRequest(BaseModel):
    """Request a draft composition from a natural-language description."""

    query: str = Field(..., min_length=4, description="What the composed tool should do")
    feedback: Optional[str] = Field(
        None,
        description="Optional iteration feedback on a previous proposal",
    )
    previous_proposal: Optional[Dict[str, Any]] = Field(
        None, description="Previous proposal to refine (kept for next iteration)"
    )


class CompositionProposeResponse(BaseModel):
    """Draft composition proposed by the LLM."""

    name: str
    description: str
    steps: List[Dict[str, Any]]
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    intent: Optional[str] = None
    available_tool_count: int


@router.post(
    "/propose",
    response_model=CompositionProposeResponse,
    summary="Propose a composition draft from a NL description",
    description=(
        "LLM-first composition builder. Reuses the IntentAnalyzer over every "
        "tool from the org's enabled servers (NOT limited to the dynamic "
        "session pool) to produce a draft the user can save or iterate on."
    ),
)
async def propose_composition(
    payload: CompositionProposeRequest,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    db: AsyncSession = Depends(get_async_session),
):
    _membership, org_id = org_context

    # Build available_tools: every tool whose server is enabled in this org.
    from sqlalchemy import select as _select
    from ...models.mcp_server import MCPServer
    from ...models.tool import Tool
    import re as _re

    stmt = (
        _select(Tool, MCPServer)
        .join(MCPServer, Tool.server_id == MCPServer.id)
        .where(
            Tool.organization_id == org_id,
            MCPServer.enabled.is_(True),
        )
    )
    rows = (await db.execute(stmt)).all()
    available_tools: List[Dict[str, Any]] = []
    for tool, server in rows:
        prefix = _re.sub(r"_+", "_", _re.sub(r"[^a-zA-Z0-9_]", "_", server.name or "")).strip("_")
        prefixed = f"{prefix}__{tool.tool_name}" if prefix else tool.tool_name
        available_tools.append(
            {
                "id": str(tool.id),
                "name": prefixed,
                "description": tool.description or "",
                "parameters": tool.parameters_schema or {"type": "object"},
                "metadata": {
                    "server_uuid": str(server.id),
                    "server_display_name": server.name,
                    "original_tool_name": tool.tool_name,
                },
            }
        )

    if not available_tools:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No enabled servers in your organization. Connect at least one "
                "MCP server before composing tools."
            ),
        )

    # If iterating, augment the query with the feedback context.
    composed_query = payload.query
    if payload.feedback and payload.feedback.strip():
        previous_summary = ""
        if payload.previous_proposal:
            try:
                steps_summary = ", ".join(
                    s.get("tool", "?") for s in (payload.previous_proposal.get("steps") or [])
                )
                previous_summary = f"\nPrevious draft used tools: {steps_summary}."
            except Exception:  # noqa: BLE001
                previous_summary = ""
        composed_query = (
            f"{payload.query}\n\nUser feedback on previous proposal: "
            f"{payload.feedback}{previous_summary}"
        )

    from ...routers.mcp_unified import gateway

    analyzer = gateway.orchestration_tools.intent_analyzer
    analysis = await analyzer.analyze(
        query=composed_query,
        context={
            "source": "web_propose",
            "user_id": str(user.id),
            "organization_id": str(org_id),
        },
        available_tools=available_tools,
    )

    proposed = (analysis or {}).get("proposed_composition") or {}
    if not proposed or not proposed.get("steps"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                analysis.get("message")
                if isinstance(analysis, dict) and analysis.get("message")
                else "The LLM could not build a coherent draft from this description."
            ),
        )

    return CompositionProposeResponse(
        name=proposed.get("name") or f"Workflow: {payload.query[:60]}",
        description=proposed.get("description") or payload.query,
        steps=proposed.get("steps") or [],
        input_schema=proposed.get("input_schema") or {"type": "object", "properties": {}, "required": []},
        output_schema=proposed.get("output_schema"),
        confidence=analysis.get("confidence") if isinstance(analysis, dict) else None,
        intent=analysis.get("intent") if isinstance(analysis, dict) else None,
        available_tool_count=len(available_tools),
    )


# =============================================================================
# SHARE-WITH-ORG REVIEW WORKFLOW (Phase 4)
# =============================================================================


class CompositionShareRequest(BaseModel):
    """Optional notes the requester wants the admin to see."""
    notes: Optional[str] = Field(
        None,
        max_length=2000,
        description="Free-text rationale for the share request",
    )


class CompositionShareReview(BaseModel):
    """Admin's approve/reject decision payload."""
    notes: Optional[str] = Field(
        None,
        max_length=2000,
        description="Reviewer's rationale (typically used for rejections)",
    )


class CompositionShareResponse(BaseModel):
    """Reply to POST /compositions/{id}/share."""
    composition: CompositionResponse
    applied: bool = Field(
        ...,
        description=(
            "True when the share was applied immediately (admin path). "
            "False when a review request was queued instead."
        ),
    )


@router.post(
    "/{composition_id}/share",
    response_model=CompositionShareResponse,
    summary="Share a composition with the org (review-gated for non-admins)",
)
async def share_composition(
    composition_id: UUID,
    payload: CompositionShareRequest,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    db: AsyncSession = Depends(get_async_session),
    service: CompositionService = Depends(get_composition_service),
):
    """Ask to make a composition org-visible.

    Admin/owner: applied immediately (visibility=organization, status=production).
    Anyone else: queued for admin review (composition stays unchanged).
    """
    membership, org_id = org_context
    composition, error, applied = await service.request_or_apply_share(
        composition_id=composition_id,
        organization_id=org_id,
        user_id=user.id,
        user_role=membership.role,
    )
    if error:
        err_lower = error.lower()
        if "not found" in err_lower:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=error)
        if "already pending" in err_lower:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=error)
        if "input_schema" in err_lower:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error)
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=error)

    try:
        await AuditService(db).log_action(
            action=(
                AuditAction.COMPOSITION_SHARE_DIRECT
                if applied
                else AuditAction.COMPOSITION_SHARE_REQUEST
            ),
            actor_id=user.id,
            organization_id=org_id,
            resource_type="composition",
            resource_id=str(composition_id),
            details={
                "name": composition.name,
                "applied": applied,
                "notes": payload.notes,
            },
        )
    except Exception:
        pass

    if applied:
        from ...routers.mcp_unified import broadcast_resources_changed
        asyncio.create_task(broadcast_resources_changed(org_id))

    can_exec, _ = await service.can_execute(composition, user.id, org_id)
    can_edit = (
        composition.created_by == user.id
        or membership.role in (UserRole.ADMIN, UserRole.OWNER)
    )
    return CompositionShareResponse(
        composition=_composition_to_response(composition, can_exec, can_edit),
        applied=applied,
    )


@router.get(
    "/admin/share-requests",
    response_model=CompositionListResponse,
    summary="List pending share-requests in the caller's org (admin only)",
)
async def list_share_requests(
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    service: CompositionService = Depends(get_composition_service),
):
    """Admin-only review queue."""
    membership, org_id = org_context
    if membership.role not in (UserRole.ADMIN, UserRole.OWNER):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Admin or owner role required",
        )
    rows = await service.list_pending_share_requests(org_id)
    items: List[CompositionResponse] = []
    for c in rows:
        can_exec, _ = await service.can_execute(c, user.id, org_id)
        items.append(_composition_to_response(c, can_exec, can_edit=True))
    return CompositionListResponse(compositions=items, total=len(items))


@router.post(
    "/{composition_id}/share-request/approve",
    response_model=CompositionResponse,
    summary="Admin approves a pending share-request",
)
async def approve_share_request(
    composition_id: UUID,
    payload: CompositionShareReview,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    db: AsyncSession = Depends(get_async_session),
    service: CompositionService = Depends(get_composition_service),
):
    membership, org_id = org_context
    if membership.role not in (UserRole.ADMIN, UserRole.OWNER):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Admin or owner role required",
        )
    composition, error = await service.approve_share_request(
        composition_id=composition_id,
        organization_id=org_id,
        admin_user_id=user.id,
        notes=payload.notes,
    )
    if error:
        err_lower = error.lower()
        if "not found" in err_lower:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=error)
        if "no pending" in err_lower:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=error)
        if "input_schema" in err_lower:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=error)

    try:
        await AuditService(db).log_action(
            action=AuditAction.COMPOSITION_SHARE_APPROVE,
            actor_id=user.id,
            organization_id=org_id,
            resource_type="composition",
            resource_id=str(composition_id),
            details={"name": composition.name, "notes": payload.notes},
        )
    except Exception:
        pass

    from ...routers.mcp_unified import broadcast_resources_changed
    asyncio.create_task(broadcast_resources_changed(org_id))

    can_exec, _ = await service.can_execute(composition, user.id, org_id)
    return _composition_to_response(composition, can_exec, can_edit=True)


@router.post(
    "/{composition_id}/share-request/reject",
    response_model=CompositionResponse,
    summary="Admin rejects a pending share-request",
)
async def reject_share_request(
    composition_id: UUID,
    payload: CompositionShareReview,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    db: AsyncSession = Depends(get_async_session),
    service: CompositionService = Depends(get_composition_service),
):
    membership, org_id = org_context
    if membership.role not in (UserRole.ADMIN, UserRole.OWNER):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Admin or owner role required",
        )
    composition, error = await service.reject_share_request(
        composition_id=composition_id,
        organization_id=org_id,
        admin_user_id=user.id,
        notes=payload.notes,
    )
    if error:
        err_lower = error.lower()
        if "not found" in err_lower:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=error)
        if "no pending" in err_lower:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=error)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=error)

    try:
        await AuditService(db).log_action(
            action=AuditAction.COMPOSITION_SHARE_REJECT,
            actor_id=user.id,
            organization_id=org_id,
            resource_type="composition",
            resource_id=str(composition_id),
            details={"name": composition.name, "notes": payload.notes},
        )
    except Exception:
        pass

    can_exec, _ = await service.can_execute(composition, user.id, org_id)
    return _composition_to_response(composition, can_exec, can_edit=True)


# =============================================================================
# ADMIN GOVERNANCE — list all executions of a composition (B-0 chunk 10)
# =============================================================================


@router.get(
    "/{composition_id}/executions",
    summary="List all executions of one composition (admin governance)",
)
async def list_composition_executions_admin(
    composition_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    db: AsyncSession = Depends(get_async_session),
    service: CompositionService = Depends(get_composition_service),
):
    """Audit view: every execution of a composition for this org.

    Admin/Owner only. The org-scoped check is enforced by loading the
    composition through the service (which respects visibility +
    organization). 404 leaks no information about other orgs.
    """
    from sqlalchemy import func, select
    from ...models.composition_execution import CompositionExecution
    from ...schemas.composition_execution import (
        ExecutionListResponse,
        ExecutionSummary,
    )

    membership, org_id = org_context
    if membership.role not in (UserRole.ADMIN, UserRole.OWNER):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Admin or owner role required",
        )

    composition = await service.get_composition(
        composition_id, org_id, user_id=user.id
    )
    if not composition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Composition not found",
        )

    base = select(CompositionExecution).where(
        CompositionExecution.composition_id == composition_id,
        CompositionExecution.organization_id == org_id,
    )
    total = (
        await db.execute(
            select(func.count()).select_from(base.subquery())
        )
    ).scalar_one()
    rows = (
        await db.execute(
            base.order_by(CompositionExecution.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()

    items: List[ExecutionSummary] = []
    for row in rows:
        state = row.state or {}
        suspension = state.get("suspension") or {}
        items.append(
            ExecutionSummary(
                id=row.id,
                composition_id=row.composition_id,
                user_id=row.user_id,
                organization_id=row.organization_id,
                parent_execution_id=row.parent_execution_id,
                status=row.status,
                trigger=row.trigger,
                cancel_requested=bool(row.cancel_requested),
                started_at=row.started_at,
                updated_at=row.updated_at,
                expires_at=row.expires_at,
                error=row.error,
                current_step_id=state.get("current_step_id"),
                suspension_reason=(
                    suspension.get("reason") if isinstance(suspension, dict) else None
                ),
            )
        )

    return ExecutionListResponse(
        items=items, total=int(total), limit=limit, offset=offset
    )
