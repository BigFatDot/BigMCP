"""Pattern A/B/C routing for ``tools/call composition_X`` (Phase B-0 chunk 6).

The MCP gateway hands every call for a composition tool to
:func:`route_composition_call`, which decides:

- **Pattern A (sync)** — the composition has no suspending step types.
  Delegate to the legacy ``CompositionExecutor.execute_composition``
  via ``orchestration_tools`` and return the result inline. Zero
  regression for every production composition that exists today.

- **Pattern C (detached)** — at least one step has a type that can
  suspend (``_test_suspend`` in B-0; ``elicit``/``wait_callback``/
  ``wait_until``/``approval`` in B-1+). Create a durable
  ``composition_execution`` row, fire-and-forget the ResumableExecutor,
  and return immediately with the execution_id + the MCP resource URI
  ``composition://executions/{id}``. Clients with
  ``resources.subscribe`` watch that URI; everyone else can poll the
  ``composition_status`` meta-tool (added in chunk #8).

Pattern B (progress-streamed) is not implemented in B-0 — it's an
optimisation for sync compositions > 30s and lands in a polish phase
once we've measured demand.

This module is pure routing logic — it does not own the HTTP/MCP
serialisation. The caller in ``mcp_unified.py`` wraps the returned
dict into the standard ``tools/call`` result envelope.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select

from ..db import session as _db_session_module
from ..models.composition import Composition
from .execution_state import ExecutionState
from .resumable_executor import (
    INPUTS_KEY,
    ExecutionStatus,
    ResumableExecutor,
    ToolDispatcher,
    create_execution,
    get_executor,
)

logger = logging.getLogger("orchestration.composition_routing")


# Step types that can yield a Suspend signal. B-0 ships
# ``_test_suspend`` (debug); B-1 adds ``elicit`` (human-in-the-loop),
# ``wait_until`` (clock-driven), ``subcomposition`` (calls another
# composition), and ``wait_callback`` (HMAC-signed external webhook).
# B-1.4 will add ``approval`` (cross-user elicitation).
SUSPENDING_STEP_TYPES: frozenset[str] = frozenset(
    {"_test_suspend", "elicit", "wait_until", "subcomposition", "wait_callback"}
)


# ---------------------------------------------------------------------------
# Static analysis
# ---------------------------------------------------------------------------


def composition_has_suspending_steps(composition: Composition) -> bool:
    """True when at least one step uses a type that can suspend."""
    for step in composition.steps or []:
        if step.get("type") in SUSPENDING_STEP_TYPES:
            return True
    # ``requires_async`` extra_metadata flag also forces detached mode
    # — useful when the composition author knows their tools are slow
    # even without explicit suspending step types.
    if (composition.extra_metadata or {}).get("requires_async") is True:
        return True
    return False


# ---------------------------------------------------------------------------
# Routing entry point
# ---------------------------------------------------------------------------


async def route_composition_call(
    *,
    composition_id: UUID,
    tool_arguments: Dict[str, Any],
    user_id: UUID,
    organization_id: UUID,
    legacy_executor,
    mcp_session_id: Optional[str] = None,
    client_capabilities: Optional[Dict[str, Any]] = None,
    trigger: str = "mcp_call",
) -> Any:
    """Route a single composition_X / workflow_X call.

    Returns either the inline result (Pattern A) or a dict shaped for
    Pattern C — the caller wraps it for MCP transport.

    ``legacy_executor`` is the ``OrchestrationTools`` instance held by
    the gateway. We only fall back to it for Pattern A, but it has to
    be passed in so this module stays import-cycle-free.
    """
    composition = await _load_composition(composition_id)
    if composition is None:
        raise ValueError(f"composition {composition_id} not found")

    if not composition_has_suspending_steps(composition):
        # Pattern A — let the legacy sync executor handle it. The
        # returned dict bubbles up unchanged to the MCP client.
        return await legacy_executor.execute_composition(
            {
                "composition_id": str(composition_id),
                "parameters": tool_arguments,
                "_user_id": str(user_id),
                "_organization_id": str(organization_id),
                "_user_server_pool": legacy_executor._user_server_pool
                if hasattr(legacy_executor, "_user_server_pool")
                else None,
            }
        )

    # Pattern C — create a durable execution + fire-and-forget run.
    execution_id = await create_execution(
        composition_id=composition.id,
        user_id=user_id,
        organization_id=organization_id,
        trigger=trigger,
        mcp_session_id=mcp_session_id,
        client_capabilities=client_capabilities,
        inputs=tool_arguments,
        initial_status=ExecutionStatus.RUNNING,
    )
    asyncio.create_task(ResumableExecutor.run_detached(execution_id))

    # Build the response payload. We always return BOTH the structured
    # content (for clients with resources.subscribe) AND a text body
    # (for everyone else, with explicit instructions to use
    # composition_status). Adaptive shaping based on client capabilities
    # can be refined later — for B-0 the uniform payload is safe and
    # informative for all clients.
    resource_uri = f"composition://executions/{execution_id}"
    webapp_url = f"https://bigmcp.cloud/app/compositions/executions/{execution_id}"

    return {
        "execution_id": str(execution_id),
        "resource_uri": resource_uri,
        "status": ExecutionStatus.RUNNING.value,
        "polling_tool": "composition_status",
        "webapp_url": webapp_url,
        "_message": (
            f"Composition started. Subscribe to {resource_uri} for live "
            f"updates, or call composition_status(execution_id="
            f'"{execution_id}") to poll. Web UI: {webapp_url}'
        ),
    }


async def _load_composition(composition_id: UUID) -> Optional[Composition]:
    async with _db_session_module.AsyncSessionLocal() as db:
        return (
            await db.execute(
                select(Composition).where(Composition.id == composition_id)
            )
        ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Tool dispatcher factory — bridges the new executor to the legacy
# CompositionExecutor's tool dispatch logic (server_bindings,
# prefix resolution, user_server_pool).
# ---------------------------------------------------------------------------


def build_tool_dispatcher(user_server_pool) -> ToolDispatcher:
    """Return a dispatcher that ResumableExecutor can plug into.

    Wraps ``CompositionExecutor._execute_tool`` so the new executor
    can run real tool steps via the same plumbing as the legacy code
    (single source of truth for resolution + execution).
    """
    from ..dependencies import get_registry
    from .composition_executor import CompositionExecutor

    legacy = CompositionExecutor(get_registry())

    async def _dispatch(
        step: Dict[str, Any],
        state: ExecutionState,
        execution,
    ) -> Any:
        # Build the context the legacy executor expects
        inputs = state.step_results.get(INPUTS_KEY, {})
        # Step results without our internal key, so ${step_X.path}
        # resolution stays clean
        public_step_results = {
            sid: val
            for sid, val in state.step_results.items()
            if sid != INPUTS_KEY
        }
        context = {
            "user_id": str(execution.user_id),
            "organization_id": str(execution.organization_id),
            "user_server_pool": user_server_pool,
            "server_bindings": (execution.composition.server_bindings or {})
            if execution.composition is not None
            else {},
            "parameters": inputs,
            "step_results": public_step_results,
        }

        # Resolve ${input.X} and ${step_X.path} substitutions via the
        # legacy executor's existing helper — DRY, single source of
        # truth for the param resolution semantics.
        resolved = legacy._resolve_parameters(
            step.get("parameters") or {},
            context,
        )

        # Dispatch the actual tool call
        return await legacy._execute_tool(
            step.get("tool"),
            resolved,
            context,
        )

    return _dispatch


def install_tool_dispatcher_singleton(user_server_pool) -> None:
    """Wire the dispatcher into the singleton executor at startup.

    Idempotent — re-calling overwrites silently. Called from
    ``app/main.py:_startup_impl`` once UserServerPool is ready.
    """
    dispatcher = build_tool_dispatcher(user_server_pool)
    get_executor().set_tool_dispatcher(dispatcher)
    logger.info(
        "Tool dispatcher installed on ResumableExecutor "
        "(bridges to legacy CompositionExecutor._execute_tool)"
    )
