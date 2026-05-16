"""``subcomposition`` step type — Phase B-1.3.

Lets a composition call ANOTHER composition as a step. The parent
yields with ``reason="subcomposition"``; the B-0 propagation hook
(``ResumableExecutor._propagate_to_parent``) auto-resumes the parent
when the child reaches a terminal state, injecting the child's
result (or an error envelope) into the parent's step result.

Most of the heavy lifting was already in place after B-0:

- ``create_execution(parent_execution_id=...)`` enforces the
  depth cap pre-flight (B-0 chunk 13 → :data:`MAX_SUBCOMPOSITION_DEPTH`).
- ``_propagate_to_parent`` fires the parent's resume automatically
  when the child completes/fails (B-0 chunk 4).
- The MCP resource notify walks the parent chain so a subscriber on
  the parent's URI sees the child's transitions too (B-0 chunk 7).

This module adds the FRONT END: dispatch + author config validation
+ input resolution. No new state-machine work.

Design highlights:
- Author specifies the target by ``composition_id`` (UUID). Target
  must exist in the same org. Production-only restriction enforced
  at promote AND dispatch time (a draft/temporary composition can't
  be called as a subcomposition — it might be mid-edit).
- Inputs map is resolved at suspend time using the same convention
  as elicit (``${input.X}`` / ``${step_id.path}``); the resolved map
  is what the child sees as its ``${input.X}`` substitutions.
- Child inherits ``user_id``, ``organization_id``, ``mcp_session_id``,
  and ``client_capabilities`` from the parent. Same user/org means
  credentials resolve naturally; same session_id means notifications
  reach the same client.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.composition import Composition, CompositionStatus
from ..models.composition_execution import CompositionExecution, ExecutionStatus
from .execution_state import ExecutionState, Suspend
from .resumable_executor import INPUTS_KEY


logger = logging.getLogger("orchestration.subcomposition_step")


# Suspended child waits indefinitely by default — the parent's overall
# TTL is the real cap. 7 days is a soft default for the parent step's
# expires_at, mostly so the expiry scanner has something to scan.
DEFAULT_TTL_SECONDS = 7 * 24 * 3600


class SubcompositionConfigError(ValueError):
    """Author-supplied ``step.subcomposition`` config is malformed."""


# ---------------------------------------------------------------------------
# Author config validation (static — no DB access required)
# ---------------------------------------------------------------------------


def validate_config(subcomposition: Optional[Dict[str, Any]]) -> None:
    """Validate the static author-supplied ``step.subcomposition`` block.

    Raises :class:`SubcompositionConfigError` for any structural issue.
    Production-status + same-org checks need DB access and live in
    :func:`validate_target_composition`.
    """
    if not isinstance(subcomposition, dict):
        raise SubcompositionConfigError(
            "subcomposition step requires a 'subcomposition' object on "
            f"the step definition; got {type(subcomposition).__name__}"
        )
    raw_id = subcomposition.get("composition_id")
    if not isinstance(raw_id, str) or not raw_id.strip():
        raise SubcompositionConfigError(
            "subcomposition.composition_id must be a non-empty string"
        )
    try:
        UUID(raw_id)
    except (ValueError, TypeError):
        raise SubcompositionConfigError(
            f"subcomposition.composition_id is not a valid UUID: {raw_id!r}"
        )
    inputs = subcomposition.get("inputs")
    if inputs is not None and not isinstance(inputs, dict):
        raise SubcompositionConfigError(
            f"subcomposition.inputs must be an object, got "
            f"{type(inputs).__name__}"
        )


# ---------------------------------------------------------------------------
# Same-org + production-status check (DB-bound, used at promote AND dispatch)
# ---------------------------------------------------------------------------


async def validate_target_composition(
    db: AsyncSession,
    *,
    target_id: UUID,
    parent_organization_id: UUID,
) -> Optional[str]:
    """Verify that the target composition exists, is same-org, prod.

    Returns ``None`` on success or an error string. The error is
    surfaced as the step's failure message at dispatch time and as
    the promote-time 422 detail.
    """
    target = (
        await db.execute(
            select(Composition).where(Composition.id == target_id)
        )
    ).scalar_one_or_none()
    if target is None:
        return (
            f"subcomposition target {target_id} does not exist "
            "(or was deleted)"
        )
    if target.organization_id != parent_organization_id:
        # Match the no-info-leak rule used elsewhere: report "not found"
        # instead of "wrong org" — never confirm the existence of
        # another org's resource.
        return (
            f"subcomposition target {target_id} does not exist "
            "(or was deleted)"
        )
    if target.status != CompositionStatus.PRODUCTION.value:
        return (
            f"subcomposition target {target_id} is in status "
            f"{target.status!r}; only production compositions can be "
            "called as a subcomposition (avoid pointing at a draft "
            "that might be mid-edit)"
        )
    return None


# ---------------------------------------------------------------------------
# Input resolution (dict walker that reuses the elicit substitution rules)
# ---------------------------------------------------------------------------


def resolve_inputs(
    raw_inputs: Optional[Dict[str, Any]],
    state: ExecutionState,
) -> Dict[str, Any]:
    """Substitute ${input.X} and ${step_id.path} in every leaf value.

    Dict + list walker on top of :func:`elicit_step.resolve_message`.
    Non-string leaves are returned as-is. Unresolved references stay
    as ``${ref}`` placeholders so authors can see what didn't resolve.
    """
    from .elicit_step import resolve_message

    if raw_inputs is None:
        return {}

    def _walk(node: Any) -> Any:
        if isinstance(node, str):
            return resolve_message(node, state)
        if isinstance(node, dict):
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(v) for v in node]
        return node

    return _walk(raw_inputs)


# ---------------------------------------------------------------------------
# Dispatch — called by ResumableExecutor._execute_step
# ---------------------------------------------------------------------------


async def dispatch(
    step: Dict[str, Any],
    state: ExecutionState,
    execution: CompositionExecution,
) -> Suspend:
    """Spawn the child execution + return the parent's Suspend payload.

    Steps:
    1. Validate the author config (raises SubcompositionConfigError →
       caught by the executor's per-step try/except → step fails).
    2. Verify the target composition (same-org, production).
    3. Resolve the inputs map.
    4. ``create_execution(parent_execution_id=execution.id, ...)`` —
       the depth cap is enforced pre-flight here (B-0 chunk 13).
    5. Fire-and-forget ``ResumableExecutor.run_detached(child_id)``.
    6. Yield ``Suspend(reason="subcomposition", payload={"child_execution_id": ...})``.

    The B-0 propagation hook will resume the parent automatically
    when the child reaches a terminal state.
    """
    import asyncio

    from ..db import session as _db_session_module
    from .resumable_executor import (
        SubcompositionDepthExceeded,
        ResumableExecutor,
        create_execution,
    )

    subcomp = step.get("subcomposition") or {}
    validate_config(subcomp)
    target_id = UUID(subcomp["composition_id"])

    # Same-org + production check (separate DB session so the executor's
    # session stays untouched if this raises mid-check).
    async with _db_session_module.AsyncSessionLocal() as probe:
        check_err = await validate_target_composition(
            probe,
            target_id=target_id,
            parent_organization_id=execution.organization_id,
        )
    if check_err:
        raise SubcompositionConfigError(check_err)

    resolved_inputs = resolve_inputs(subcomp.get("inputs"), state)

    # depth + cycle protection happens INSIDE create_execution — if the
    # parent's depth + 1 > MAX_SUBCOMPOSITION_DEPTH, SubcompositionDepthExceeded
    # raises here and the step fails cleanly.
    try:
        child_id = await create_execution(
            composition_id=target_id,
            user_id=execution.user_id,
            organization_id=execution.organization_id,
            trigger="mcp_call",
            mcp_session_id=execution.mcp_session_id,
            client_capabilities=execution.client_capabilities,
            inputs=resolved_inputs,
            parent_execution_id=execution.id,
            initial_status=ExecutionStatus.RUNNING,
        )
    except SubcompositionDepthExceeded as e:
        raise SubcompositionConfigError(str(e))

    # Fire the child in the background. The detached wrapper marks the
    # child failed on crash so we never leak orphan ``running`` rows.
    asyncio.create_task(ResumableExecutor.run_detached(child_id))

    ttl = int(subcomp.get("ttl_seconds") or DEFAULT_TTL_SECONDS)

    return Suspend(
        reason="subcomposition",
        payload={
            "step_id": step.get("step_id") or step.get("id"),
            "child_execution_id": str(child_id),
            "target_composition_id": str(target_id),
        },
        ttl_seconds=ttl,
    )
