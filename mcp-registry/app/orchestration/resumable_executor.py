"""Resumable composition executor (Phase B-0).

Replaces the synchronous ``CompositionExecutor.execute_direct`` for
compositions that need durable state (suspension on elicit, wait,
cron-triggered, etc.). The legacy executor is kept untouched — chunk
#6 will route MCP ``tools/call composition_X`` through this new
executor and delegate the actual tool dispatch back to the legacy
code via the pluggable ``tool_dispatcher``.

Design contract (see ``mcp-registry/docs/composition_executions_b0.md``):

- **Singleton, stateless wrt instance.** All state lives in the
  ``composition_execution`` row.

- **Status-as-lock.** No Postgres advisory locks. Mutating ops use
  conditional ``UPDATE ... WHERE status = ? RETURNING *`` (via
  SQLAlchemy ORM, backend-portable) so only one mutator wins per row;
  subsequent attempts get 0 rows and surface a clean conflict.

- **Idempotence is author-controlled.** A step that crashed mid-flight
  re-runs only if the composition author marked it ``idempotent=True``;
  otherwise it fails with a clear reason and the user can retry.

- **Persist after every step.** Crash recovery is OK at any boundary.
  Result size is hard-capped at 1MB inline (256KB warn).

- **Tool dispatch is pluggable.** The executor doesn't know HOW to
  call upstream tools — it gets a dispatcher injected. Until chunk
  #6, ``type=tool`` raises ``ToolDispatchUnconfigured``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db import session as _db_session_module
from ..models.audit_log import AuditAction
from ..models.composition_execution import (
    CompositionExecution,
    ExecutionStatus,
    ExecutionStepEvent,
)
from .execution_state import ExecutionState, Suspend

logger = logging.getLogger("orchestration.resumable_executor")


# Hard cap on persisted step result size (Postgres TOAST handles
# bigger but inline JSONB updates rewrite the whole row, so we keep
# it bounded for predictable perf).
MAX_STEP_RESULT_BYTES = 1_048_576       # 1 MB
WARN_STEP_RESULT_BYTES = 262_144        # 256 KB

# Sub-composition recursion guard.
MAX_SUBCOMPOSITION_DEPTH = 5


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ExecutionNotFound(Exception):
    """The execution does not exist or is not visible to the caller."""


class ExecutionStateConflict(Exception):
    """Tried to transition from a status that no longer matches.

    Surfaces as 409 in the REST layer."""


class StepResultTooLarge(Exception):
    """Tool returned a value larger than ``MAX_STEP_RESULT_BYTES``."""


class ToolDispatchUnconfigured(Exception):
    """No tool dispatcher injected. Chunk #6 wires it."""


# ---------------------------------------------------------------------------
# Pluggable tool dispatcher signature
# ---------------------------------------------------------------------------

ToolDispatcher = Callable[
    [Dict[str, Any], ExecutionState, CompositionExecution],
    Awaitable[Any],
]


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class ResumableExecutor:
    """Singleton executor.

    Use :func:`get_executor` to obtain the shared instance.
    """

    def __init__(self) -> None:
        self._tool_dispatcher: Optional[ToolDispatcher] = None
        self.default_timeout_seconds: int = 60

    # -- Wiring -----------------------------------------------------------

    def set_tool_dispatcher(self, dispatcher: ToolDispatcher) -> None:
        """Inject the tool dispatch backend (called from chunk #6)."""
        self._tool_dispatcher = dispatcher

    # -- Public API -------------------------------------------------------

    async def run(self, execution_id: UUID) -> str:
        """Run from current state until terminal or suspended.

        Returns the final status string. Idempotent: an already-
        terminal execution returns its status without side effects.
        """
        async with _db_session_module.AsyncSessionLocal() as db:
            execution = await self._load(db, execution_id)
            if execution is None:
                raise ExecutionNotFound(str(execution_id))

            if execution.status in {
                ExecutionStatus.COMPLETED.value,
                ExecutionStatus.FAILED.value,
                ExecutionStatus.CANCELLED.value,
                ExecutionStatus.EXPIRED.value,
            }:
                return execution.status

            # Atomically transition queued → running.
            if execution.status == ExecutionStatus.QUEUED.value:
                rows = await db.execute(
                    update(CompositionExecution)
                    .where(
                        CompositionExecution.id == execution_id,
                        CompositionExecution.status == ExecutionStatus.QUEUED.value,
                    )
                    .values(
                        status=ExecutionStatus.RUNNING.value,
                        updated_at=datetime.utcnow(),
                    )
                    .returning(CompositionExecution.id)
                )
                if rows.scalar_one_or_none() is None:
                    await db.commit()
                    return ExecutionStatus.QUEUED.value
                await db.commit()
                await self._emit_audit(
                    db,
                    AuditAction.COMPOSITION_EXECUTION_STARTED,
                    execution,
                )

            # Re-load freshest state and start the loop.
            execution = await self._load(db, execution_id)
            assert execution is not None
            state = ExecutionState.from_jsonb(execution.state)
            return await self._run_loop(db, execution, state)

    async def resume(self, execution_id: UUID, response: Any) -> str:
        """Inject ``response`` into the suspended step and continue."""
        async with _db_session_module.AsyncSessionLocal() as db:
            existing = await self._load(db, execution_id)
            if existing is None:
                raise ExecutionNotFound(str(execution_id))
            if existing.status != ExecutionStatus.SUSPENDED.value:
                raise ExecutionStateConflict(
                    f"execution {execution_id} is {existing.status!r}, "
                    f"not 'suspended'"
                )
            current_state = ExecutionState.from_jsonb(existing.state)
            current_step_id = current_state.current_step_id
            if not current_step_id:
                raise ExecutionStateConflict(
                    f"execution {execution_id} has no current_step_id "
                    f"to inject the resume response into"
                )

            # Build new state Python-side, then atomic UPDATE WHERE
            # status='suspended'. Two concurrent resumes: both prepare
            # mutations, both UPDATE; only the first matches the
            # WHERE, the second gets 0 rows.
            current_state.step_results[current_step_id] = response
            current_state.step_status[current_step_id] = "succeeded"
            current_state.suspension = None

            rows = await db.execute(
                update(CompositionExecution)
                .where(
                    CompositionExecution.id == execution_id,
                    CompositionExecution.status == ExecutionStatus.SUSPENDED.value,
                )
                .values(
                    status=ExecutionStatus.RUNNING.value,
                    state=current_state.to_jsonb(),
                    updated_at=datetime.utcnow(),
                )
                .returning(CompositionExecution.id)
            )
            if rows.scalar_one_or_none() is None:
                await db.commit()
                refreshed = await self._load(db, execution_id)
                raise ExecutionStateConflict(
                    f"execution {execution_id} was already mutated "
                    f"(now {refreshed.status if refreshed else 'gone'})"
                )
            await db.commit()

            await self._emit_audit(
                db,
                AuditAction.COMPOSITION_EXECUTION_RESUMED,
                existing,
                payload={"step_id": current_step_id},
            )
            await self._emit_event(
                db, execution_id, current_step_id, "succeeded",
            )

            execution = await self._load(db, execution_id)
            assert execution is not None
            state = ExecutionState.from_jsonb(execution.state)
            return await self._run_loop(db, execution, state)

    async def request_cancel(self, execution_id: UUID) -> bool:
        """Mark cancel_requested. Returns True if the row was touched.

        Cancel always succeeds for non-terminal rows. Tools currently
        in flight are NOT interrupted — the transition lands at the
        next step boundary.
        """
        terminal = {
            ExecutionStatus.COMPLETED.value,
            ExecutionStatus.FAILED.value,
            ExecutionStatus.EXPIRED.value,
            ExecutionStatus.CANCELLED.value,
        }
        async with _db_session_module.AsyncSessionLocal() as db:
            rows = await db.execute(
                update(CompositionExecution)
                .where(
                    CompositionExecution.id == execution_id,
                    ~CompositionExecution.status.in_(terminal),
                )
                .values(cancel_requested=True, updated_at=datetime.utcnow())
                .returning(CompositionExecution.id)
            )
            touched = rows.scalar_one_or_none() is not None
            await db.commit()
            return touched

    # -- Internals --------------------------------------------------------

    async def _load(
        self, db: AsyncSession, execution_id: UUID
    ) -> Optional[CompositionExecution]:
        stmt = (
            select(CompositionExecution)
            .options(selectinload(CompositionExecution.composition))
            .where(CompositionExecution.id == execution_id)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    async def _run_loop(
        self,
        db: AsyncSession,
        execution: CompositionExecution,
        state: ExecutionState,
    ) -> str:
        """Iterate steps in declaration order until terminal/suspended."""
        steps = list(execution.composition.steps or [])
        try:
            while True:
                # Cancel boundary check — re-read flag from DB so a
                # cancel that arrived between iterations is honored.
                cancel_flag = (
                    await db.execute(
                        select(CompositionExecution.cancel_requested).where(
                            CompositionExecution.id == execution.id
                        )
                    )
                ).scalar()
                if cancel_flag is True:
                    return await self._mark_terminal(
                        db, execution, ExecutionStatus.CANCELLED, state=state
                    )

                step = self._next_step(state, steps)
                if step is None:
                    return await self._mark_terminal(
                        db,
                        execution,
                        ExecutionStatus.COMPLETED,
                        state=state,
                        result=self._extract_result(state),
                    )

                outcome = await self._execute_step(db, step, state, execution)

                if isinstance(outcome, Suspend):
                    return await self._mark_suspended(
                        db, execution, state, outcome
                    )

                step_id = step.get("step_id") or step.get("id")
                state.step_results[step_id] = outcome
                state.step_status[step_id] = "succeeded"
                state.current_step_id = None
                await self._save(db, execution, state)
                await self._emit_event(
                    db, execution.id, step_id, "succeeded"
                )

        except StepResultTooLarge as e:
            logger.warning(f"Execution {execution.id}: step result too large: {e}")
            return await self._mark_terminal(
                db,
                execution,
                ExecutionStatus.FAILED,
                state=state,
                error=f"step_result_too_large: {e}",
            )
        except Exception as e:  # noqa: BLE001
            logger.exception(f"Execution {execution.id}: unexpected failure")
            return await self._mark_terminal(
                db,
                execution,
                ExecutionStatus.FAILED,
                state=state,
                error=str(e),
            )

    def _next_step(
        self, state: ExecutionState, steps: list
    ) -> Optional[Dict[str, Any]]:
        """Next step in declaration order that hasn't succeeded.

        Sequential B-0 — depends_on is data-only. A step in
        ``failed`` status was either optional+skipped or already
        propagated a composition failure (we wouldn't be here).
        """
        for s in steps:
            sid = s.get("step_id") or s.get("id")
            if not sid:
                continue
            status = state.step_status.get(sid)
            if status in {"succeeded", "failed"}:
                continue
            return s
        return None

    async def _execute_step(
        self,
        db: AsyncSession,
        step: Dict[str, Any],
        state: ExecutionState,
        execution: CompositionExecution,
    ) -> Any:
        step_id = step.get("step_id") or step.get("id")
        step_type = step.get("type", "tool")
        is_idempotent = bool(step.get("idempotent", False))
        is_optional = bool(step.get("optional", False))

        # Idempotence guard for resumed-after-crash steps.
        prior = state.step_status.get(step_id)
        if prior == "succeeded":
            return state.step_results[step_id]
        if prior == "in_progress":
            if not is_idempotent:
                state.step_status[step_id] = "failed"
                state.step_results[step_id] = {
                    "error": "resumed_after_crash_non_idempotent"
                }
                await self._save(db, execution, state)
                await self._emit_event(
                    db, execution.id, step_id, "failed",
                    payload={"error": "resumed_after_crash_non_idempotent"},
                )
                if is_optional:
                    return None
                raise RuntimeError(
                    f"Step {step_id} crashed mid-flight and is not "
                    f"marked idempotent"
                )
            # else: idempotent, fall through to re-run

        # Mark in-progress and persist BEFORE the call.
        state.step_status[step_id] = "in_progress"
        state.step_started_at[step_id] = datetime.utcnow().isoformat()
        state.current_step_id = step_id
        await self._save(db, execution, state)
        await self._emit_event(db, execution.id, step_id, "started")

        try:
            if step_type == "_test_suspend":
                # Debug-only step type for B-0 to validate suspension
                # round-trips. Never appears in real compositions.
                return Suspend(
                    reason="_test_suspend",
                    payload={"step_id": step_id},
                    ttl_seconds=300,
                )

            if step_type == "tool":
                if self._tool_dispatcher is None:
                    raise ToolDispatchUnconfigured(
                        "ResumableExecutor.set_tool_dispatcher() not called — "
                        "tool dispatch is wired in B-0 chunk #6"
                    )
                result = await self._tool_dispatcher(step, state, execution)
                self._enforce_size_cap(step_id, result)
                return result

            raise NotImplementedError(
                f"Step type {step_type!r} not implemented in this version. "
                f"B-0 supports: tool, _test_suspend."
            )
        except StepResultTooLarge:
            state.step_status[step_id] = "failed"
            await self._save(db, execution, state)
            await self._emit_event(
                db, execution.id, step_id, "failed",
                payload={"reason": "step_result_too_large"},
            )
            raise
        except Exception:
            state.step_status[step_id] = "failed"
            await self._save(db, execution, state)
            await self._emit_event(
                db, execution.id, step_id, "failed",
                payload={"reason": "exception"},
            )
            raise

    @staticmethod
    def _enforce_size_cap(step_id: str, result: Any) -> None:
        try:
            blob = json.dumps(result, default=str)
        except (TypeError, ValueError):
            return  # non-serializable; let caller surface differently
        size = len(blob.encode("utf-8"))
        if size > MAX_STEP_RESULT_BYTES:
            raise StepResultTooLarge(
                f"step {step_id} returned {size} bytes (max "
                f"{MAX_STEP_RESULT_BYTES})"
            )
        if size > WARN_STEP_RESULT_BYTES:
            logger.warning(
                f"large step result for {step_id}: {size} bytes "
                f"(soft warn at {WARN_STEP_RESULT_BYTES})"
            )

    @staticmethod
    def _extract_result(state: ExecutionState) -> Optional[Dict[str, Any]]:
        """Composition result = the last successful step's output.

        Skips the synthetic ``__inputs`` key seeded by ``create_execution``.
        """
        successful = [
            (sid, val)
            for sid, val in state.step_results.items()
            if sid != "__inputs" and state.step_status.get(sid) == "succeeded"
        ]
        if not successful:
            return None
        last_id, last_value = successful[-1]
        if isinstance(last_value, dict):
            return last_value
        return {"value": last_value}

    # -- Persistence helpers ---------------------------------------------

    async def _save(
        self,
        db: AsyncSession,
        execution: CompositionExecution,
        state: ExecutionState,
    ) -> None:
        """Persist state + bump updated_at."""
        await db.execute(
            update(CompositionExecution)
            .where(CompositionExecution.id == execution.id)
            .values(state=state.to_jsonb(), updated_at=datetime.utcnow())
        )
        await db.commit()

    async def _mark_terminal(
        self,
        db: AsyncSession,
        execution: CompositionExecution,
        status: ExecutionStatus,
        *,
        state: Optional[ExecutionState] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> str:
        terminal = {
            ExecutionStatus.COMPLETED.value,
            ExecutionStatus.FAILED.value,
            ExecutionStatus.EXPIRED.value,
            ExecutionStatus.CANCELLED.value,
        }
        values: Dict[str, Any] = {
            "status": status.value,
            "result": result,
            "error": error,
            "updated_at": datetime.utcnow(),
        }
        if state is not None:
            values["state"] = state.to_jsonb()

        rows = await db.execute(
            update(CompositionExecution)
            .where(
                CompositionExecution.id == execution.id,
                ~CompositionExecution.status.in_(terminal),
            )
            .values(**values)
            .returning(CompositionExecution.id)
        )
        landed = rows.scalar_one_or_none() is not None
        await db.commit()

        if landed:
            audit_action_map = {
                ExecutionStatus.COMPLETED: AuditAction.COMPOSITION_EXECUTION_COMPLETED,
                ExecutionStatus.FAILED: AuditAction.COMPOSITION_EXECUTION_FAILED,
                ExecutionStatus.CANCELLED: AuditAction.COMPOSITION_EXECUTION_CANCELLED,
                ExecutionStatus.EXPIRED: AuditAction.COMPOSITION_EXECUTION_EXPIRED,
            }
            await self._emit_audit(
                db,
                audit_action_map[status],
                execution,
                payload={"error": error} if error else None,
            )
        return status.value

    async def _mark_suspended(
        self,
        db: AsyncSession,
        execution: CompositionExecution,
        state: ExecutionState,
        suspend: Suspend,
    ) -> str:
        state.suspension = suspend.to_jsonb()
        # current_step_id was set by _execute_step at start
        expires_at = datetime.utcnow() + timedelta(seconds=suspend.ttl_seconds)

        await db.execute(
            update(CompositionExecution)
            .where(
                CompositionExecution.id == execution.id,
                CompositionExecution.status == ExecutionStatus.RUNNING.value,
            )
            .values(
                status=ExecutionStatus.SUSPENDED.value,
                state=state.to_jsonb(),
                expires_at=expires_at,
                updated_at=datetime.utcnow(),
            )
        )
        await db.commit()
        await self._emit_audit(
            db,
            AuditAction.COMPOSITION_EXECUTION_SUSPENDED,
            execution,
            payload={"reason": suspend.reason, "ttl_seconds": suspend.ttl_seconds},
        )
        await self._emit_event(
            db, execution.id, state.current_step_id or "?", "suspended",
            payload={"reason": suspend.reason},
        )
        return ExecutionStatus.SUSPENDED.value

    async def _emit_event(
        self,
        db: AsyncSession,
        execution_id: UUID,
        step_id: str,
        event_type: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append a row to ``execution_step_event``. Best-effort."""
        try:
            db.add(
                ExecutionStepEvent(
                    id=uuid4(),
                    execution_id=execution_id,
                    step_id=step_id,
                    event_type=event_type,
                    payload=payload,
                    timestamp=datetime.utcnow(),
                )
            )
            await db.commit()
        except Exception:  # noqa: BLE001
            logger.warning(
                f"failed to emit step event for execution {execution_id} "
                f"step {step_id} event {event_type}",
                exc_info=True,
            )
            try:
                await db.rollback()
            except Exception:
                pass

    async def _emit_audit(
        self,
        db: AsyncSession,
        action: AuditAction,
        execution: CompositionExecution,
        *,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            from ..services.audit_service import AuditService

            await AuditService(db).log_action(
                action=action,
                actor_id=execution.user_id,
                organization_id=execution.organization_id,
                resource_type="composition_execution",
                resource_id=str(execution.id),
                details=payload,
            )
        except Exception:  # noqa: BLE001
            logger.warning(f"failed to emit audit log {action.value}", exc_info=True)

    # -- Detached-task wrapper -------------------------------------------

    @staticmethod
    async def run_detached(execution_id: UUID) -> None:
        """Wrapper for ``asyncio.create_task``.

        Catches any unhandled exception, logs it, and best-effort
        marks the execution failed so we never leak orphan
        ``running`` rows from background coroutines.
        """
        try:
            await get_executor().run(execution_id)
        except ExecutionNotFound:
            logger.warning(
                f"detached task: execution {execution_id} not found"
            )
        except Exception:  # noqa: BLE001
            logger.exception(f"detached execution {execution_id} crashed")
            try:
                async with _db_session_module.AsyncSessionLocal() as db:
                    terminal = {
                        ExecutionStatus.COMPLETED.value,
                        ExecutionStatus.FAILED.value,
                        ExecutionStatus.EXPIRED.value,
                        ExecutionStatus.CANCELLED.value,
                    }
                    await db.execute(
                        update(CompositionExecution)
                        .where(
                            CompositionExecution.id == execution_id,
                            ~CompositionExecution.status.in_(terminal),
                        )
                        .values(
                            status=ExecutionStatus.FAILED.value,
                            error="detached_crash",
                            updated_at=datetime.utcnow(),
                        )
                    )
                    await db.commit()
            except Exception:
                logger.exception(
                    "could not mark crashed execution as failed"
                )


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_executor_singleton: Optional[ResumableExecutor] = None


def get_executor() -> ResumableExecutor:
    """Return the process-wide ResumableExecutor instance."""
    global _executor_singleton
    if _executor_singleton is None:
        _executor_singleton = ResumableExecutor()
    return _executor_singleton


def _reset_executor_for_tests() -> None:
    """Drop the singleton — only for tests that need a clean dispatcher."""
    global _executor_singleton
    _executor_singleton = None


# ---------------------------------------------------------------------------
# Create a fresh execution row.
# Called by the routing layer in chunk #6.
# ---------------------------------------------------------------------------


async def create_execution(
    *,
    composition_id: UUID,
    user_id: UUID,
    organization_id: UUID,
    trigger: str,
    mcp_session_id: Optional[str] = None,
    client_capabilities: Optional[Dict[str, Any]] = None,
    inputs: Optional[Dict[str, Any]] = None,
    parent_execution_id: Optional[UUID] = None,
    initial_status: ExecutionStatus = ExecutionStatus.RUNNING,
    depth: int = 0,
) -> UUID:
    """Insert a fresh ``composition_execution`` row and return its id.

    The initial state seeds ``step_results`` with the user-supplied
    inputs under a synthetic ``__inputs`` key so steps can substitute
    them via the existing ``${input.X}`` runtime convention.
    """
    initial_state = ExecutionState(
        step_results={"__inputs": inputs or {}},
        depth=depth,
    )

    row_id = uuid4()
    now = datetime.utcnow()

    async with _db_session_module.AsyncSessionLocal() as db:
        db.add(
            CompositionExecution(
                id=row_id,
                composition_id=composition_id,
                user_id=user_id,
                organization_id=organization_id,
                parent_execution_id=parent_execution_id,
                status=initial_status.value,
                state=initial_state.to_jsonb(),
                trigger=trigger,
                mcp_session_id=mcp_session_id,
                client_capabilities=client_capabilities,
                cancel_requested=False,
                started_at=now,
                updated_at=now,
            )
        )
        await db.commit()

        try:
            from ..services.audit_service import AuditService
            await AuditService(db).log_action(
                action=AuditAction.COMPOSITION_EXECUTION_CREATED,
                actor_id=user_id,
                organization_id=organization_id,
                resource_type="composition_execution",
                resource_id=str(row_id),
                details={
                    "composition_id": str(composition_id),
                    "trigger": trigger,
                    "initial_status": initial_status.value,
                },
            )
        except Exception:  # noqa: BLE001
            logger.warning("failed to emit creation audit", exc_info=True)

    return row_id
