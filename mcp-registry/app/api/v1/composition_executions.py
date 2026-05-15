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
