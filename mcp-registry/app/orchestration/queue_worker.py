"""Composition execution lifecycle helpers (Phase B-0).

Two pieces wired at lifespan startup:

- ``recover_orphan_executions()`` — one-shot sweep that flips any
  ``status='running'`` row to ``failed`` with reason
  ``backend_restart_orphan``. The previous backend process died with
  these executions in flight; their detached coroutines are gone.
  Suspended and queued rows are untouched (suspended waits for an
  external event, queued is picked up by the worker on next tick).

- ``QueueWorker`` — single asyncio task that periodically promotes
  ``status='queued'`` rows to ``running`` while respecting the
  per-user concurrency limit, then dispatches them via
  ``ResumableExecutor.run_detached``.

Both are single-instance assumptions (see design doc §13). The
``UPDATE ... WHERE status='queued' RETURNING`` pattern is multi-
instance-safe by construction even when we eventually scale.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, select, update

from ..core.metrics import COMPOSITION_STEP_ABANDONMENTS
from ..db import session as _db_session_module
from ..models.composition_execution import CompositionExecution, ExecutionStatus
from .resumable_executor import ResumableExecutor

logger = logging.getLogger("orchestration.queue_worker")


# Configurables (env-tunable for ops without a redeploy)
MAX_CONCURRENT_EXECUTIONS_PER_USER = int(
    os.getenv("MAX_CONCURRENT_EXECUTIONS_PER_USER", "50")
)
QUEUE_TICK_SECONDS = int(os.getenv("COMPOSITION_QUEUE_TICK_SECONDS", "5"))
QUEUE_BATCH_LIMIT = int(os.getenv("COMPOSITION_QUEUE_BATCH_LIMIT", "200"))


# ---------------------------------------------------------------------------
# Orphan recovery
# ---------------------------------------------------------------------------


async def recover_orphan_executions() -> List[UUID]:
    """Sweep ``running`` executions on backend startup → ``failed``.

    Returns the list of recovered IDs.

    Each orphan also gets:
    - one ``COMPOSITION_EXECUTION_FAILED`` audit row with reason
      ``backend_restart_orphan``
    - one ``execution_step_event`` timeline entry of type
      ``orphan_recovery`` so the UI shows WHY the row failed

    Suspended and queued rows are untouched:
    - Suspended will resume on its external event — backend restart
      doesn't change that.
    - Queued will be picked up by the queue worker on its next tick.
    """
    from uuid import uuid4
    from ..models.audit_log import AuditAction
    from ..models.composition_execution import ExecutionStepEvent
    from ..services.audit_service import AuditService

    async with _db_session_module.AsyncSessionLocal() as db:
        # Capture (id, user_id, organization_id, current_step_id) BEFORE
        # the UPDATE so we can emit per-row audit/timeline rows from the
        # snapshot. Doing the SELECT first then UPDATE-by-id keeps the
        # critical mutation small and avoids needing RETURNING of all
        # columns.
        from sqlalchemy import select
        prelim = await db.execute(
            select(CompositionExecution).where(
                CompositionExecution.status == ExecutionStatus.RUNNING.value
            )
        )
        orphan_rows = list(prelim.scalars().all())

        if not orphan_rows:
            logger.info("No orphan executions to recover at startup")
            return []

        orphan_ids = [r.id for r in orphan_rows]
        await db.execute(
            update(CompositionExecution)
            .where(CompositionExecution.id.in_(orphan_ids))
            .values(
                status=ExecutionStatus.FAILED.value,
                error="backend_restart_orphan",
                updated_at=datetime.utcnow(),
            )
        )
        # Audit + timeline events
        audit = AuditService(db)
        for r in orphan_rows:
            current_step_id = (r.state or {}).get("current_step_id") or "?"
            try:
                await audit.log_action(
                    action=AuditAction.COMPOSITION_EXECUTION_FAILED,
                    actor_id=r.user_id,
                    organization_id=r.organization_id,
                    resource_type="composition_execution",
                    resource_id=str(r.id),
                    details={"error": "backend_restart_orphan"},
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    f"failed to emit audit log for orphan {r.id}",
                    exc_info=True,
                )
            db.add(
                ExecutionStepEvent(
                    id=uuid4(),
                    execution_id=r.id,
                    step_id=current_step_id,
                    event_type="orphan_recovery",
                    payload={"error": "backend_restart_orphan"},
                    timestamp=datetime.utcnow(),
                )
            )
        await db.commit()

    logger.warning(
        f"Recovered {len(orphan_ids)} orphan execution(s) from previous "
        f"backend process: {orphan_ids}"
    )
    return orphan_ids


# ---------------------------------------------------------------------------
# Queue worker
# ---------------------------------------------------------------------------


class QueueWorker:
    """Singleton background loop that promotes queued executions.

    Run state is process-local. To restart cleanly across deploys,
    call ``stop()`` from the lifespan shutdown handler.
    """

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task[None]] = None
        self._stop_event: Optional[asyncio.Event] = None

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Idempotent — calling twice is safe."""
        if self.is_running():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._loop(), name="composition_queue_worker")
        logger.info(
            f"Composition queue worker started (tick={QUEUE_TICK_SECONDS}s, "
            f"batch_limit={QUEUE_BATCH_LIMIT}, "
            f"per_user={MAX_CONCURRENT_EXECUTIONS_PER_USER})"
        )

    async def stop(self) -> None:
        if not self.is_running():
            return
        assert self._stop_event is not None
        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=10)
        except asyncio.TimeoutError:
            logger.warning("Queue worker didn't stop in time, cancelling")
            self._task.cancel()
        self._task = None
        self._stop_event = None
        logger.info("Composition queue worker stopped")

    async def _loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                promoted = await promote_queued_batch(QUEUE_BATCH_LIMIT)
                for execution_id in promoted:
                    asyncio.create_task(
                        ResumableExecutor.run_detached(execution_id)
                    )
                # B-1.2: fire wait_until rows whose clock has hit and
                # expire other suspended rows past their TTL.
                await scan_expiry_batch(QUEUE_BATCH_LIMIT)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("Queue worker tick failed")

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=QUEUE_TICK_SECONDS,
                )
            except asyncio.TimeoutError:
                pass  # normal — tick interval elapsed


# Singleton accessor
_queue_worker_singleton: Optional[QueueWorker] = None


def get_queue_worker() -> QueueWorker:
    global _queue_worker_singleton
    if _queue_worker_singleton is None:
        _queue_worker_singleton = QueueWorker()
    return _queue_worker_singleton


def _reset_queue_worker_for_tests() -> None:
    """Drop the singleton — only for tests."""
    global _queue_worker_singleton
    _queue_worker_singleton = None


# ---------------------------------------------------------------------------
# The actual promotion logic — extracted for testability
# ---------------------------------------------------------------------------


async def promote_queued_batch(batch_limit: int = QUEUE_BATCH_LIMIT) -> List[UUID]:
    """One worker tick: promote queued rows up to per-user concurrency limit.

    Returns the list of promoted execution IDs. Caller is responsible
    for spawning the detached run tasks.

    The promotion uses a conditional ``UPDATE WHERE status='queued'
    RETURNING`` for each candidate — even if multiple workers ran
    concurrently (multi-instance future), each row would be promoted
    by exactly one of them.
    """
    promoted: List[UUID] = []

    async with _db_session_module.AsyncSessionLocal() as db:
        # Count currently-running per user so we know remaining slots
        running_rows = await db.execute(
            select(
                CompositionExecution.user_id,
                func.count(CompositionExecution.id),
            )
            .where(CompositionExecution.status == ExecutionStatus.RUNNING.value)
            .group_by(CompositionExecution.user_id)
        )
        per_user_running = {row[0]: row[1] for row in running_rows.all()}

        # Pull oldest queued candidates
        candidates = (
            await db.execute(
                select(CompositionExecution.id, CompositionExecution.user_id)
                .where(
                    CompositionExecution.status == ExecutionStatus.QUEUED.value
                )
                .order_by(CompositionExecution.started_at.asc())
                .limit(batch_limit)
            )
        ).all()

        for execution_id, user_id in candidates:
            cur = per_user_running.get(user_id, 0)
            if cur >= MAX_CONCURRENT_EXECUTIONS_PER_USER:
                continue  # over-quota, leave queued for the next tick

            # Conditional UPDATE — atomic, multi-instance-safe
            updated = await db.execute(
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
            if updated.scalar_one_or_none() is not None:
                promoted.append(execution_id)
                per_user_running[user_id] = cur + 1

        await db.commit()

    if promoted:
        logger.info(
            f"Queue worker promoted {len(promoted)} execution(s): {promoted}"
        )
    return promoted


# ---------------------------------------------------------------------------
# B-1.2: expiry scanner (wait_until auto-resume + other-reason expire)
# ---------------------------------------------------------------------------


async def scan_expiry_batch(batch_limit: int = QUEUE_BATCH_LIMIT) -> dict:
    """One worker tick: handle suspended rows whose ``expires_at`` passed.

    Two paths based on the suspension reason:

    - ``wait_until`` → call ``executor.resume(id, auto_resume_payload())``
      in the background. The resume's conditional UPDATE WHERE
      status='suspended' is atomic, so a user manually firing /resume
      between our SELECT and the resume call simply wins (we get
      ExecutionStateConflict and move on).

    - any other reason (``elicit``, ``_test_suspend``, future
      ``approval``/``wait_callback``) → the TTL legitimately ran out
      → mark the row ``expired`` via UPDATE WHERE status='suspended'
      RETURNING. Audit + timeline event emitted.

    Returns ``{'resumed': [ids], 'expired': [ids]}`` for telemetry.
    """
    from uuid import uuid4
    from ..models.audit_log import AuditAction
    from ..models.composition_execution import ExecutionStepEvent
    from ..services.audit_service import AuditService
    from .resumable_executor import (
        ExecutionStateConflict,
        get_executor,
    )
    from .wait_until_step import auto_resume_payload

    now = datetime.utcnow()
    resumed: List[UUID] = []
    expired: List[UUID] = []

    async with _db_session_module.AsyncSessionLocal() as db:
        candidates = (
            await db.execute(
                select(CompositionExecution)
                .where(
                    CompositionExecution.status == ExecutionStatus.SUSPENDED.value,
                    CompositionExecution.expires_at.is_not(None),
                    CompositionExecution.expires_at <= now,
                )
                .limit(batch_limit)
            )
        ).scalars().all()

        wait_until_ids: List[UUID] = []
        for row in candidates:
            reason = (
                (row.state or {}).get("suspension") or {}
            ).get("reason")
            if reason == "wait_until":
                wait_until_ids.append(row.id)
                continue

            # Expire path — atomic UPDATE; emit audit + timeline if it lands.
            updated = await db.execute(
                update(CompositionExecution)
                .where(
                    CompositionExecution.id == row.id,
                    CompositionExecution.status == ExecutionStatus.SUSPENDED.value,
                )
                .values(
                    status=ExecutionStatus.EXPIRED.value,
                    error=f"ttl_expired_on_{reason or 'unknown'}",
                    updated_at=datetime.utcnow(),
                )
                .returning(CompositionExecution.id)
            )
            if updated.scalar_one_or_none() is None:
                continue  # someone else changed it in the meantime
            expired.append(row.id)
            COMPOSITION_STEP_ABANDONMENTS.labels(reason=reason or "unknown").inc()
            current_step_id = (row.state or {}).get("current_step_id") or "?"
            db.add(
                ExecutionStepEvent(
                    id=uuid4(),
                    execution_id=row.id,
                    step_id=current_step_id,
                    event_type="expired",
                    payload={"reason": reason},
                    timestamp=datetime.utcnow(),
                )
            )
        await db.commit()

        # Audit + tombstone events for expirations land in a separate
        # session (mirroring the executor's audit isolation invariant)
        if expired:
            try:
                async with _db_session_module.AsyncSessionLocal() as audit_db:
                    audit = AuditService(audit_db)
                    for ex_id in expired:
                        owner = (
                            await audit_db.execute(
                                select(
                                    CompositionExecution.user_id,
                                    CompositionExecution.organization_id,
                                ).where(CompositionExecution.id == ex_id)
                            )
                        ).first()
                        if owner is None:
                            continue
                        try:
                            await audit.log_action(
                                action=AuditAction.COMPOSITION_EXECUTION_EXPIRED,
                                actor_id=owner[0],
                                organization_id=owner[1],
                                resource_type="composition_execution",
                                resource_id=str(ex_id),
                                details={"reason": "ttl_expired"},
                            )
                        except Exception:  # noqa: BLE001
                            logger.warning(
                                f"audit emit failed for expired execution {ex_id}",
                                exc_info=True,
                            )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "expiry audit batch failed", exc_info=True
                )

    # Auto-resume wait_until candidates as background tasks. resume()
    # is async + opens its own session; we don't want to serialise N
    # resumes inside the tick.
    for execution_id in wait_until_ids:
        async def _fire(eid: UUID = execution_id) -> None:
            payload = auto_resume_payload()
            try:
                await get_executor().resume(eid, payload)
                resumed.append(eid)
            except ExecutionStateConflict:
                # User manually resumed / cancelled between our SELECT
                # and now — fine, leave it.
                logger.info(
                    f"wait_until {eid}: already mutated before auto-resume"
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    f"wait_until auto-resume failed for {eid}"
                )

        asyncio.create_task(_fire())

    if resumed or expired or wait_until_ids:
        logger.info(
            f"Expiry scan: {len(wait_until_ids)} wait_until fired, "
            f"{len(expired)} other expired"
        )
    return {"resumed": resumed, "expired": expired}
