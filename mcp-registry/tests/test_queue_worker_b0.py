"""Phase B-0 chunk 5: orphan recovery + queue worker tests."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Tuple
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.composition import (
    Composition,
    CompositionStatus,
    CompositionVisibility,
)
from app.models.composition_execution import (
    CompositionExecution,
    ExecutionStatus,
)
from app.models.organization import OrganizationMember
from app.models.user import User
from app.orchestration.execution_state import ExecutionState
from app.orchestration.queue_worker import (
    promote_queued_batch,
    recover_orphan_executions,
)
from app.orchestration.resumable_executor import (
    create_execution,
    _reset_executor_for_tests,
    get_executor,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers (mirror test_resumable_executor)
# ---------------------------------------------------------------------------


async def _ids(db: AsyncSession, email: str) -> Tuple[UUID, UUID]:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    member = (
        await db.execute(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        )
    ).scalar_one()
    return user.id, member.organization_id


async def _make_composition(
    db: AsyncSession, org_id: UUID, owner_id: UUID, *, name: str, steps: list
) -> Composition:
    comp = Composition(
        organization_id=org_id,
        created_by=owner_id,
        name=name,
        description="b0 test",
        visibility=CompositionVisibility.PRIVATE.value,
        steps=steps,
        data_mappings=[],
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=None,
        server_bindings={},
        allowed_roles=[],
        force_org_credentials=False,
        status=CompositionStatus.PRODUCTION.value,
        ttl=None,
        extra_metadata={},
    )
    db.add(comp)
    await db.commit()
    await db.refresh(comp)
    return comp


@pytest.fixture(autouse=True)
def _fresh_executor():
    _reset_executor_for_tests()
    yield
    _reset_executor_for_tests()


@pytest.fixture(autouse=True)
def _patch_session_local(db_engine, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession as _AS, async_sessionmaker
    from app.db import session as session_module

    test_factory = async_sessionmaker(
        db_engine, class_=_AS, expire_on_commit=False
    )
    monkeypatch.setattr(session_module, "AsyncSessionLocal", test_factory)
    yield test_factory


# ---------------------------------------------------------------------------
# Orphan recovery
# ---------------------------------------------------------------------------


async def test_orphan_recovery_marks_running_as_failed(
    db_session: AsyncSession, test_user: dict
):
    """A row stuck in 'running' (previous backend died) → 'failed' with reason."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="orphan",
        steps=[{"step_id": "1", "type": "tool", "tool": "x"}],
    )
    execution_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
        initial_status=ExecutionStatus.RUNNING,  # simulate crashed-mid-run
    )

    recovered = await recover_orphan_executions()
    assert execution_id in recovered

    row = await db_session.get(CompositionExecution, execution_id)
    await db_session.refresh(row)
    assert row.status == ExecutionStatus.FAILED.value
    assert row.error == "backend_restart_orphan"


async def test_orphan_recovery_leaves_suspended_alone(
    db_session: AsyncSession, test_user: dict
):
    """Suspended rows keep waiting; only 'running' is touched."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="suspended_keepalive",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )
    execution_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    await get_executor().run(execution_id)
    row = await db_session.get(CompositionExecution, execution_id)
    await db_session.refresh(row)
    assert row.status == ExecutionStatus.SUSPENDED.value

    recovered = await recover_orphan_executions()
    assert execution_id not in recovered

    await db_session.refresh(row)
    assert row.status == ExecutionStatus.SUSPENDED.value


async def test_orphan_recovery_leaves_queued_alone(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="queued_keepalive",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )
    execution_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual", initial_status=ExecutionStatus.QUEUED,
    )

    recovered = await recover_orphan_executions()
    assert execution_id not in recovered

    row = await db_session.get(CompositionExecution, execution_id)
    await db_session.refresh(row)
    assert row.status == ExecutionStatus.QUEUED.value


# ---------------------------------------------------------------------------
# Queue worker promote logic
# ---------------------------------------------------------------------------


async def test_promote_queued_below_quota(db_session: AsyncSession, test_user: dict):
    """A queued execution under the per-user limit is promoted."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="q_under",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )
    execution_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual", initial_status=ExecutionStatus.QUEUED,
    )

    promoted = await promote_queued_batch(batch_limit=10)
    assert execution_id in promoted

    row = await db_session.get(CompositionExecution, execution_id)
    await db_session.refresh(row)
    assert row.status == ExecutionStatus.RUNNING.value


async def test_promote_skips_when_user_at_quota(
    db_session: AsyncSession, test_user: dict, monkeypatch
):
    """When the user already has MAX_CONCURRENT running, queued stays queued."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    # Override the per-user limit to a small number for this test
    from app.orchestration import queue_worker as qw_module
    monkeypatch.setattr(qw_module, "MAX_CONCURRENT_EXECUTIONS_PER_USER", 1)

    comp = await _make_composition(
        db_session, org_id, user_id, name="q_over",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )

    # One running execution already
    running_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual", initial_status=ExecutionStatus.RUNNING,
    )
    # One queued — should NOT promote (user at quota)
    queued_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual", initial_status=ExecutionStatus.QUEUED,
    )

    promoted = await promote_queued_batch(batch_limit=10)
    assert queued_id not in promoted

    row = await db_session.get(CompositionExecution, queued_id)
    await db_session.refresh(row)
    assert row.status == ExecutionStatus.QUEUED.value


async def test_orphan_recovery_emits_audit_and_timeline(
    db_session: AsyncSession, test_user: dict
):
    """Each orphan gets a COMPOSITION_EXECUTION_FAILED audit row +
    one execution_step_event of type ``orphan_recovery``."""
    from app.models.audit_log import AuditLog, AuditAction
    from app.models.composition_execution import ExecutionStepEvent

    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="orphan_evt",
        steps=[{"step_id": "1", "type": "tool", "tool": "x"}],
    )
    execution_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
        initial_status=ExecutionStatus.RUNNING,
    )
    # Seed the state with a current_step_id so the timeline event
    # carries something meaningful (not "?")
    state = ExecutionState.from_jsonb({})
    state.current_step_id = "1"
    state.step_status["1"] = "in_progress"
    await db_session.execute(
        update(CompositionExecution)
        .where(CompositionExecution.id == execution_id)
        .values(state=state.to_jsonb())
    )
    await db_session.commit()

    recovered = await recover_orphan_executions()
    assert execution_id in recovered

    # Audit row
    audits = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == AuditAction.COMPOSITION_EXECUTION_FAILED.value,
                AuditLog.resource_id == str(execution_id),
            )
        )
    ).scalars().all()
    assert len(audits) == 1
    assert audits[0].details == {"error": "backend_restart_orphan"}

    # Timeline event
    events = (
        await db_session.execute(
            select(ExecutionStepEvent).where(
                ExecutionStepEvent.execution_id == execution_id,
                ExecutionStepEvent.event_type == "orphan_recovery",
            )
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].step_id == "1"
    assert events[0].payload == {"error": "backend_restart_orphan"}


async def test_queue_worker_start_stop_clean_shutdown(
    db_session: AsyncSession, test_user: dict
):
    """start() spawns a task, stop() awaits it cleanly, no leak."""
    from app.orchestration.queue_worker import (
        QueueWorker,
        _reset_queue_worker_for_tests,
    )

    _reset_queue_worker_for_tests()
    worker = QueueWorker()
    assert not worker.is_running()

    await worker.start()
    assert worker.is_running()

    # Calling start() twice is idempotent
    await worker.start()
    assert worker.is_running()

    await worker.stop()
    assert not worker.is_running()

    # Calling stop() after stop is also idempotent
    await worker.stop()
    assert not worker.is_running()


async def test_promote_releases_slot_after_terminal(
    db_session: AsyncSession, test_user: dict, monkeypatch
):
    """When a running execution terminates, the next queued one promotes."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    from app.orchestration import queue_worker as qw_module
    monkeypatch.setattr(qw_module, "MAX_CONCURRENT_EXECUTIONS_PER_USER", 1)

    comp = await _make_composition(
        db_session, org_id, user_id, name="q_slot",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )
    running_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual", initial_status=ExecutionStatus.RUNNING,
    )
    queued_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual", initial_status=ExecutionStatus.QUEUED,
    )

    # First tick: nothing promotes (quota full)
    assert queued_id not in await promote_queued_batch(batch_limit=10)

    # Mark the running one as terminal manually (simulate finish)
    await db_session.execute(
        update(CompositionExecution)
        .where(CompositionExecution.id == running_id)
        .values(status=ExecutionStatus.COMPLETED.value)
    )
    await db_session.commit()

    # Next tick: queued promotes
    promoted = await promote_queued_batch(batch_limit=10)
    assert queued_id in promoted
