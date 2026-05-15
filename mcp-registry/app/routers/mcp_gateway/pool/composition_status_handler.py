"""Server-side handler for the ``composition_status`` MCP meta-tool.

Polling fallback for clients that don't (or can't) subscribe to
``composition://executions/{id}`` via ``resources/subscribe``. Returns
SUMMARY only (status, current step, suspension reason, error, dates) —
full state lives in the resource read and the REST endpoint
(``/api/v1/compositions/executions/{id}``), so this tool stays small
and cheap.

Per-user scoping is enforced internally: a cross-user execution_id
returns ``status='not_found'`` — same as a non-existent UUID — to
avoid leaking the existence of someone else's row.

See design doc §7 ``composition_executions_b0.md``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....db import session as _db_session_module
from ....models.composition_execution import CompositionExecution, ExecutionStatus

logger = logging.getLogger("composition_status")


_NOT_FOUND_STATUS = "not_found"


def _empty_response(execution_id: str) -> Dict[str, Any]:
    body = {
        "execution_id": execution_id,
        "status": _NOT_FOUND_STATUS,
        "current_step_id": None,
        "suspension_reason": None,
        "error": None,
        "expires_at": None,
        "started_at": None,
        "updated_at": None,
        "result_uri": None,
    }
    return {
        "structuredContent": body,
        "content": [
            {
                "type": "text",
                "text": f"Execution {execution_id} not found.",
            }
        ],
    }


async def handle_composition_status(
    arguments: Dict[str, Any],
    *,
    user_id: str,
    organization_id: str,
    db: Optional[AsyncSession] = None,
) -> Dict[str, Any]:
    """Return summary status for one execution owned by the caller.

    ``db`` is an optional dependency-injected session, used only by
    tests that need to share the in-memory SQLite fixture.
    """
    raw_id = (arguments or {}).get("execution_id", "")
    raw_id = (raw_id or "").strip() if isinstance(raw_id, str) else ""
    if not raw_id:
        return {
            "structuredContent": {
                "execution_id": "",
                "status": _NOT_FOUND_STATUS,
                "current_step_id": None,
                "suspension_reason": None,
                "error": None,
                "expires_at": None,
                "started_at": None,
                "updated_at": None,
                "result_uri": None,
            },
            "content": [
                {"type": "text", "text": "Missing 'execution_id' argument."}
            ],
            "isError": True,
        }

    try:
        execution_uuid = UUID(raw_id)
    except (ValueError, TypeError):
        return _empty_response(raw_id)

    try:
        user_uuid = UUID(str(user_id))
    except (ValueError, TypeError):
        return _empty_response(raw_id)

    async def _query(session: AsyncSession) -> Optional[CompositionExecution]:
        stmt = select(CompositionExecution).where(
            CompositionExecution.id == execution_uuid,
            CompositionExecution.user_id == user_uuid,
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    if db is not None:
        row = await _query(db)
    else:
        async with _db_session_module.AsyncSessionLocal() as session:
            row = await _query(session)

    if row is None:
        return _empty_response(raw_id)

    state = row.state or {}
    current_step_id = state.get("current_step_id")
    suspension = state.get("suspension") or {}
    suspension_reason = suspension.get("reason") if isinstance(suspension, dict) else None

    result_uri: Optional[str] = None
    if row.status == ExecutionStatus.COMPLETED.value:
        result_uri = f"composition://executions/{row.id}"

    body = {
        "execution_id": str(row.id),
        "status": row.status,
        "current_step_id": current_step_id,
        "suspension_reason": suspension_reason,
        "error": row.error,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "result_uri": result_uri,
    }

    summary_lines = [
        f"Execution {body['execution_id']} — status: {body['status']}",
    ]
    if current_step_id:
        summary_lines.append(f"current step: {current_step_id}")
    if suspension_reason:
        summary_lines.append(f"suspended: {suspension_reason}")
    if row.error:
        summary_lines.append(f"error: {row.error}")
    if result_uri:
        summary_lines.append(f"result: {result_uri}")

    return {
        "structuredContent": body,
        "content": [{"type": "text", "text": "\n".join(summary_lines)}],
    }
