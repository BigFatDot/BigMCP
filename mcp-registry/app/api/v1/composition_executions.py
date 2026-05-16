"""REST endpoints for composition executions (Phase B-0 chunk 10).

Per-user-scoped CRUD over the ``composition_execution`` table that
backs the durable suspension layer:

- ``GET    /compositions/executions``           — paginated list
- ``GET    /compositions/executions/{id}``      — full detail + timeline
- ``POST   /compositions/executions/{id}/cancel`` — cooperative cancel
- ``POST   /compositions/executions/{id}/resume`` — inject suspended response

All four endpoints enforce ``execution.user_id == current_user.id``;
a cross-user attempt returns 404 (same response as a non-existent
row — no information leak about row existence). The admin governance
view (``GET /compositions/{id}/executions``) lives in the parent
``compositions.py`` router because it shares the ``{composition_id}``
prefix.

Resume is JWT-only in B-0 (the design doc keeps webhook-token
alternative for B-3 on the same endpoint via Authorization scheme
branching).
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_async_session
from ...models.composition_execution import (
    CompositionExecution,
    ExecutionStatus,
    ExecutionStepEvent,
)
from ...models.organization import OrganizationMember
from ...models.user import User
from ...orchestration.resumable_executor import (
    ExecutionNotFound,
    ExecutionStateConflict,
    get_executor,
)
from ...schemas.composition_execution import (
    ExecutionDetail,
    ExecutionListResponse,
    ExecutionStepEventOut,
    ExecutionSummary,
    ResumeRequest,
)
from ..dependencies import get_current_organization_jwt, get_current_user_jwt


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/compositions/executions",
    tags=["Composition Executions"],
)


# Default columns excluded from the list view to keep responses small.
_TERMINAL_STATUSES = {
    ExecutionStatus.COMPLETED.value,
    ExecutionStatus.FAILED.value,
    ExecutionStatus.EXPIRED.value,
    ExecutionStatus.CANCELLED.value,
}
_NON_TERMINAL_STATUSES = {
    ExecutionStatus.RUNNING.value,
    ExecutionStatus.SUSPENDED.value,
    ExecutionStatus.QUEUED.value,
}

# Per-call cap to keep the timeline small in the detail response.
_RECENT_EVENTS_LIMIT = 100


def _summarize_row(row: CompositionExecution) -> ExecutionSummary:
    """Project a row into the list-view shape with derived state fields."""
    state = row.state or {}
    suspension = state.get("suspension") or {}
    return ExecutionSummary(
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


def _parse_status_filter(raw: Optional[str]) -> Optional[List[str]]:
    """``?status=running,suspended`` → ``["running", "suspended"]``."""
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts or None


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=ExecutionListResponse,
    summary="List my composition executions",
)
async def list_my_executions(
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description=(
            "Comma-separated status filter (e.g., 'running,suspended'). "
            "Default: non-terminal statuses unless include_terminal=true."
        ),
    ),
    include_terminal: bool = Query(
        False,
        description=(
            "When true, include completed/failed/expired/cancelled rows. "
            "Ignored when an explicit status= filter is supplied."
        ),
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session),
):
    """List executions owned by the current user, paginated."""
    statuses = _parse_status_filter(status_filter)

    base = select(CompositionExecution).where(
        CompositionExecution.user_id == user.id
    )
    if statuses is not None:
        base = base.where(CompositionExecution.status.in_(statuses))
    elif not include_terminal:
        base = base.where(
            CompositionExecution.status.in_(list(_NON_TERMINAL_STATUSES))
        )

    total = (
        await db.execute(
            select(func.count())
            .select_from(base.subquery())
        )
    ).scalar_one()

    rows = (
        await db.execute(
            base.order_by(CompositionExecution.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()

    items = [_summarize_row(r) for r in rows]
    return ExecutionListResponse(
        items=items, total=int(total), limit=limit, offset=offset
    )


# ---------------------------------------------------------------------------
# DETAIL
# ---------------------------------------------------------------------------


async def _load_owned_or_404(
    db: AsyncSession, execution_id: UUID, user: User
) -> CompositionExecution:
    """Fetch the row and enforce ownership; 404 on miss or cross-user."""
    row = (
        await db.execute(
            select(CompositionExecution).where(
                CompositionExecution.id == execution_id,
                CompositionExecution.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found",
        )
    return row


# ---------------------------------------------------------------------------
# /pending-approvals MUST be declared BEFORE /{execution_id} — FastAPI
# matches in declaration order, so the literal-segment route has to win
# over the UUID-param route. The handler body lives further down with the
# rest of the B-1.4 approval surface; this is just the route hook.
# ---------------------------------------------------------------------------


@router.get(
    "/pending-approvals",
    summary="List executions suspended on approval that the current user can act on",
)
async def _list_pending_approvals_route(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    db: AsyncSession = Depends(get_async_session),
):
    return await _impl_list_pending_approvals(
        limit=limit, offset=offset, user=user,
        org_context=org_context, db=db,
    )


@router.get(
    "/{execution_id}",
    response_model=ExecutionDetail,
    summary="Get execution detail (state + recent events)",
)
async def get_execution_detail(
    execution_id: UUID,
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session),
):
    """Full execution row + the most recent timeline events."""
    row = await _load_owned_or_404(db, execution_id, user)

    events = (
        await db.execute(
            select(ExecutionStepEvent)
            .where(ExecutionStepEvent.execution_id == execution_id)
            .order_by(ExecutionStepEvent.timestamp.desc())
            .limit(_RECENT_EVENTS_LIMIT)
        )
    ).scalars().all()
    # Reverse so the oldest of the recent slice ships first — matches
    # how a UI timeline expects to render.
    events_chrono = list(reversed(events))

    summary = _summarize_row(row)
    return ExecutionDetail(
        **summary.model_dump(),
        state=row.state or {},
        client_capabilities=row.client_capabilities,
        mcp_session_id=row.mcp_session_id,
        result=row.result,
        events=[ExecutionStepEventOut.model_validate(e) for e in events_chrono],
    )


# ---------------------------------------------------------------------------
# CANCEL
# ---------------------------------------------------------------------------


@router.post(
    "/{execution_id}/cancel",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request cooperative cancel",
)
async def cancel_execution(
    execution_id: UUID,
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session),
):
    """Set ``cancel_requested=true`` if the caller owns the row.

    Returns 202 (Accepted) — the cancel lands at the next step
    boundary, the in-flight step finishes its own work first.
    Already-terminal rows are a no-op (still 202, body ``cancelled=false``).
    """
    # Ownership pre-check: 404 cross-user, never reveal existence.
    await _load_owned_or_404(db, execution_id, user)

    touched = await get_executor().request_cancel(execution_id)
    return {
        "execution_id": str(execution_id),
        "cancel_requested": True if touched else False,
        "detail": (
            "cancel_requested set; will land at next step boundary"
            if touched
            else "execution is already terminal"
        ),
    }


# ---------------------------------------------------------------------------
# RESUME
# ---------------------------------------------------------------------------


@router.post(
    "/{execution_id}/resume",
    summary="Inject the suspended step's response and continue",
)
async def resume_execution(
    execution_id: UUID,
    body: ResumeRequest,
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session),
):
    """Resume a suspended execution with the caller-supplied response.

    Returns 200 with the new status on success, 409 if the row is no
    longer in ``suspended``, 404 if it doesn't belong to the caller.
    B-0 only authenticates JWT user owners; B-3 will branch on the
    Authorization scheme to also accept HMAC webhook tokens.
    """
    row = await _load_owned_or_404(db, execution_id, user)

    if row.status != ExecutionStatus.SUSPENDED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Execution is {row.status!r}, not 'suspended'. "
                "Only suspended executions can be resumed."
            ),
        )

    # B-1 chunk 2: per-step-type validation BEFORE delegating to the
    # executor. ``elicit`` carries an author-declared JSON Schema in
    # ``state.suspension.payload.schema``; the response must validate
    # or we 422 with the schema error path. The row stays suspended so
    # the user can retry with a corrected payload.
    suspension = (row.state or {}).get("suspension") or {}
    if suspension.get("reason") == "elicit":
        from ...orchestration.elicit_step import validate_response as _validate_elicit
        ok, err = _validate_elicit(suspension.get("payload") or {}, body.response)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err or "elicit response failed schema validation",
            )

    try:
        new_status = await get_executor().resume(execution_id, body.response)
    except ExecutionNotFound:
        # Race: the row vanished between the ownership check and the
        # resume call. Surface as 404 to match the no-info-leak rule.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found",
        )
    except ExecutionStateConflict as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    return {
        "execution_id": str(execution_id),
        "status": new_status,
    }


# ---------------------------------------------------------------------------
# CALLBACK (B-1.5) — HMAC-protected webhook resume, NO JWT
# ---------------------------------------------------------------------------


@router.post(
    "/{execution_id}/callback/{token}",
    summary=(
        "External webhook resume — HMAC-protected, no JWT. The token IS "
        "the auth; brute force is infeasible (32-byte entropy)."
    ),
)
async def callback_execution(
    execution_id: UUID,
    token: str,
    body: Optional[dict] = None,
    db: AsyncSession = Depends(get_async_session),
):
    """Resume a ``wait_callback``-suspended execution via webhook.

    NO authentication header required — the ``token`` segment in the
    URL is the credential. It hashes (SHA-256, constant-time) against
    the value stored at suspend time. Failures all return the same
    401 shape ("Unauthorized") to avoid distinguishing
    invalid-token vs wrong-state probes.

    Body shape: any JSON the external system wants to ship. When the
    author declared ``wait_callback.expected_schema``, the body is
    validated against it; mismatch → 422.

    Race/idempotence: the executor's atomic UPDATE WHERE
    status='suspended' RETURNING means a token replayed after a
    successful resume hits a 409 (no state change).
    """
    from ...orchestration.wait_callback_step import validate_callback

    # Single SELECT — no ownership join because there's no user
    # context. The token IS the authorisation.
    row = (
        await db.execute(
            select(CompositionExecution).where(
                CompositionExecution.id == execution_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        # Same 401 as a bad token — no info leak about row existence.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
    if row.status != ExecutionStatus.SUSPENDED.value:
        # Already resumed / cancelled / expired — 409.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Execution is {row.status!r}, not 'suspended'. "
                "Callback token can only fire once."
            ),
        )
    suspension = (row.state or {}).get("suspension") or {}
    if suspension.get("reason") != "wait_callback":
        # Suspended on a different reason — 401 (no leak).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    payload = suspension.get("payload") or {}
    received_body = body if body is not None else {}
    ok, err = validate_callback(payload, token, received_body)
    if not ok:
        # Distinguish token failure from schema failure for callers
        # — the token check failed → 401; the schema check failed →
        # 422 with the helpful detail.
        if err == "invalid token" or err == "execution is not waiting on a callback":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized",
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err or "callback body failed schema validation",
        )

    try:
        new_status = await get_executor().resume(execution_id, received_body)
    except ExecutionNotFound:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
    except ExecutionStateConflict:
        # Two concurrent callbacks; second one loses the race.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Execution was resumed concurrently",
        )

    return {
        "execution_id": str(execution_id),
        "status": new_status,
    }


# ---------------------------------------------------------------------------
# APPROVAL (B-1.4) — cross-user resume with role/user gating
# ---------------------------------------------------------------------------


from pydantic import BaseModel as _BaseModel, ConfigDict as _ConfigDict, Field as _Field


class _ApprovalDecisionRequest(_BaseModel):
    """Body shape for /approve and /reject.

    ``extra_fields`` carries the optional author-declared
    ``response_schema`` payload (rationale, ticket id, …). Server
    augments with ``decision`` / ``approved_by`` / ``approved_at``
    before resuming — clients cannot spoof those.
    """

    model_config = _ConfigDict(extra="forbid")

    extra_fields: Optional[dict] = _Field(
        default=None,
        description=(
            "Optional payload validated against the step's "
            "response_schema (when declared). Cannot contain "
            "'decision', 'approved_by', or 'approved_at' — those "
            "are server-set."
        ),
    )


async def _load_for_approver_or_403(
    db: AsyncSession,
    execution_id: UUID,
    user: User,
) -> Tuple[CompositionExecution, dict, str]:
    """Cross-user variant of _load_owned_or_404.

    Returns ``(row, suspension_payload, actor_role)`` on success.
    All failures collapse to **403 Forbidden** with a uniform
    message — never reveals whether the row exists, whether it is
    suspended, on what reason, or which approver gate failed. The
    log keeps the precise reason for the auditor.
    """
    from ...orchestration.approval_step import can_approve

    UNIFORM = HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden",
    )

    row = (
        await db.execute(
            select(CompositionExecution).where(
                CompositionExecution.id == execution_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        logger.info(
            f"approval: execution {execution_id} not found for actor {user.id}"
        )
        raise UNIFORM

    # Same-org check — never allow cross-org approval. The approver
    # must be a member of the execution's organization.
    membership = (
        await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.user_id == user.id,
                OrganizationMember.organization_id == row.organization_id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        logger.info(
            f"approval: actor {user.id} not in org {row.organization_id} "
            f"(execution {execution_id})"
        )
        raise UNIFORM

    if row.status != ExecutionStatus.SUSPENDED.value:
        logger.info(
            f"approval: execution {execution_id} is "
            f"{row.status!r}, not suspended"
        )
        raise UNIFORM

    suspension = (row.state or {}).get("suspension") or {}
    if suspension.get("reason") != "approval":
        logger.info(
            f"approval: execution {execution_id} suspended on "
            f"{suspension.get('reason')!r}, not approval"
        )
        raise UNIFORM

    payload = suspension.get("payload") or {}
    actor_role = (
        membership.role.value
        if hasattr(membership.role, "value")
        else str(membership.role)
    )
    ok, reason = can_approve(
        payload,
        actor_user_id=user.id,
        actor_role=actor_role,
    )
    if not ok:
        logger.info(
            f"approval: actor {user.id} denied on "
            f"execution {execution_id}: {reason}"
        )
        raise UNIFORM

    return row, payload, actor_role


async def _record_approval_decision(
    db: AsyncSession,
    *,
    execution_id: UUID,
    suspension_payload: dict,
    actor_user: User,
    decision: str,
    extra_fields: Optional[dict],
) -> str:
    """Common implementation behind /approve and /reject.

    Validates the optional response_schema, builds the envelope,
    fires executor.resume, and emits the audit event. Returns the
    new execution status string.
    """
    from ...models.audit_log import AuditAction
    from ...orchestration.approval_step import (
        build_response_envelope,
        validate_response_schema,
    )
    from ...services.audit_service import AuditService

    ok, err = validate_response_schema(suspension_payload, extra_fields or {})
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err or "approval response failed schema validation",
        )

    envelope = build_response_envelope(
        decision=decision,
        actor_user_id=actor_user.id,
        suspension_payload=suspension_payload,
        extra_fields=extra_fields,
    )

    try:
        new_status = await get_executor().resume(execution_id, envelope)
    except ExecutionNotFound:
        # Race: the row vanished between the permission check and the
        # resume call.  Same uniform 403 to keep the no-info-leak
        # invariant — the row is effectively unreachable.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )
    except ExecutionStateConflict as e:
        # Two concurrent approve/reject calls — second one loses.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    audit_action = (
        AuditAction.COMPOSITION_APPROVAL_APPROVED
        if decision == "approved"
        else AuditAction.COMPOSITION_APPROVAL_REJECTED
    )
    try:
        await AuditService(db).log_action(
            action=audit_action,
            actor_id=actor_user.id,
            organization_id=None,  # auditor will derive from execution
            resource_type="composition_execution",
            resource_id=str(execution_id),
            details={
                "step_id": suspension_payload.get("step_id"),
                "decision": decision,
            },
        )
    except Exception:
        # Audit failures never break the user action.
        pass

    return new_status


async def _impl_list_pending_approvals(
    *,
    limit: int,
    offset: int,
    user: User,
    org_context: tuple,
    db: AsyncSession,
) -> "ExecutionListResponse":
    """Filtered subset of pending approvals visible to the current user.

    The actual route declaration lives near the top of the module so it
    is registered BEFORE the ``/{execution_id}`` parametric route — see
    :func:`_list_pending_approvals_route`. Keep this helper in sync.

    Rules (mirror the per-row permission gate enforced by
    :func:`_load_for_approver_or_403`):

    - Execution must be in the caller's org.
    - Status = ``suspended``.
    - ``state.suspension.reason == 'approval'``.
    - Caller's user_id is in ``payload.approver_user_ids`` OR caller's
      role is in ``payload.allowed_roles``.
    - Four-eyes: if caller IS the launcher and
      ``allow_self_approval`` is false → excluded.

    The filtering is done in-memory after a coarse SQL prefilter
    (org + status). SQLite JSON ops are awkward enough that this is
    simpler than a Postgres-specific WHERE; the volume of suspended
    rows per org is bounded by the queue worker quota (50/user)
    anyway, so the post-filter is cheap.
    """
    from ...orchestration.approval_step import can_approve

    membership, org_id = org_context
    actor_role = (
        membership.role.value
        if hasattr(membership.role, "value")
        else str(membership.role)
    )

    candidates = (
        await db.execute(
            select(CompositionExecution)
            .where(
                CompositionExecution.organization_id == org_id,
                CompositionExecution.status == ExecutionStatus.SUSPENDED.value,
            )
            .order_by(CompositionExecution.updated_at.desc())
        )
    ).scalars().all()

    visible = []
    for row in candidates:
        suspension = (row.state or {}).get("suspension") or {}
        if suspension.get("reason") != "approval":
            continue
        payload = suspension.get("payload") or {}
        ok, _ = can_approve(payload, actor_user_id=user.id, actor_role=actor_role)
        if ok:
            visible.append(row)

    total = len(visible)
    page = visible[offset : offset + limit]
    return ExecutionListResponse(
        items=[_summarize_row(r) for r in page],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{execution_id}/approve",
    summary="Approve a suspended composition execution",
)
async def approve_execution(
    execution_id: UUID,
    body: Optional[_ApprovalDecisionRequest] = None,
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session),
):
    """Approve and resume an execution suspended on ``reason='approval'``.

    Returns 200 with the new status, 403 (uniform) for any
    permission/state failure, 409 on concurrent decision race, 422
    on schema mismatch.
    """
    row, suspension_payload, _ = await _load_for_approver_or_403(
        db, execution_id, user
    )
    extra = body.extra_fields if body else None
    new_status = await _record_approval_decision(
        db,
        execution_id=execution_id,
        suspension_payload=suspension_payload,
        actor_user=user,
        decision="approved",
        extra_fields=extra,
    )
    return {
        "execution_id": str(execution_id),
        "status": new_status,
        "decision": "approved",
    }


@router.post(
    "/{execution_id}/reject",
    summary="Reject a suspended composition execution",
)
async def reject_execution(
    execution_id: UUID,
    body: Optional[_ApprovalDecisionRequest] = None,
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session),
):
    """Reject and resume an execution suspended on ``reason='approval'``.

    Same permission/error shape as ``/approve``. The composition
    step result carries ``decision='rejected'``; whether the
    composition then fails or continues is governed by the step's
    ``optional`` flag (B-0 contract).
    """
    row, suspension_payload, _ = await _load_for_approver_or_403(
        db, execution_id, user
    )
    extra = body.extra_fields if body else None
    new_status = await _record_approval_decision(
        db,
        execution_id=execution_id,
        suspension_payload=suspension_payload,
        actor_user=user,
        decision="rejected",
        extra_fields=extra,
    )
    return {
        "execution_id": str(execution_id),
        "status": new_status,
        "decision": "rejected",
    }
