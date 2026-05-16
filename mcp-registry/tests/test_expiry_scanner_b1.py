"""Phase B-1.2 chunk 2: expiry scanner — wait_until fires + others expire.

Covers ``queue_worker.scan_expiry_batch`` end-to-end against a real
SQLite + a real ResumableExecutor singleton.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Tuple
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.composition import (
    Composition,
    CompositionStatus,
    CompositionVisibility,
)
from app.models.composition_execution import (
    CompositionExecution,
    ExecutionStatus,
    ExecutionStepEvent,
)
from app.models.organization import OrganizationMember
from app.models.user import User
from app.orchestration.execution_state import ExecutionState
from app.orchestration.queue_worker import scan_expiry_batch
from app.orchestration.resumable_executor import (
    create_execution,
    _reset_executor_for_tests,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
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
    db: AsyncSession, org_id: UUID, owner_id: UUID, *, name: str, steps: list,
) -> Composition:
    comp = Composition(
        organization_id=org_id,
        created_by=owner_id,
        name=name,
        description="b1.2 expiry",
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

    test_factory = async_sessionmaker(db_engine, class_=_AS, expire_on_commit=False)
    monkeypatch.setattr(session_module, "AsyncSessionLocal", test_factory)
    yield test_factory


async def _setup_suspended_with_expired_ttl(
    db: AsyncSession,
    *,
    user_id: UUID,
    org_id: UUID,
    composition_id: UUID,
    reason: str,
    payload: dict | None = None,
    minutes_overdue: int = 5,
) -> UUID:
    """Helper: create a row already suspended + past TTL."""
    eid = await create_execution(
        composition_id=composition_id,
        user_id=user_id,
        organization_id=org_id,
        trigger="manual",
    )
    row = await db.get(CompositionExecution, eid)
    state = ExecutionState.from_jsonb(row.state)
    state.current_step_id = "step"
    state.suspension = {
        "reason": reason,
        "payload": payload or {},
        "ttl_seconds": 60,
    }
    row.state = state.to_jsonb()
    row.status = ExecutionStatus.SUSPENDED.value
    row.expires_at = datetime.utcnow() - timedelta(minutes=minutes_overdue)
    await db.commit()
    return eid


async def _poll_until_status(
    execution_id: UUID, target: str, iterations: int = 30, interval: float = 0.1
):
    """Poll a fresh probe session until status matches."""
    from app.db import session as session_module
    for _ in range(iterations):
        await asyncio.sleep(interval)
        async with session_module.AsyncSessionLocal() as probe:
            row = await probe.get(CompositionExecution, execution_id)
            if row and row.status == target:
                return row
    return None


# ---------------------------------------------------------------------------
# wait_until: auto-resume path
# ---------------------------------------------------------------------------


async def test_wait_until_fires_when_clock_hits(
    db_session: AsyncSession, test_user: dict
):
    """Past-expiry wait_until → background resume → completed."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    # A 1-step composition; once resumed, _next_step returns None →
    # _mark_terminal(COMPLETED). The suspended step is whatever the
    # state.current_step_id says; we mark it succeeded via resume's
    # mutation path.
    comp = await _make_composition(
        db_session, org_id, user_id, name="b1_wait_fire",
        steps=[{
            "step_id": "step",
            "type": "wait_until",
            "wait_until": {"wait_seconds": 60},
        }],
    )
    eid = await _setup_suspended_with_expired_ttl(
        db_session,
        user_id=user_id,
        org_id=org_id,
        composition_id=comp.id,
        reason="wait_until",
        payload={"step_id": "step", "resume_at": "<past>"},
    )

    result = await scan_expiry_batch(batch_limit=50)
    # The actual resume is fire-and-forget; we poll for the terminal.
    row = await _poll_until_status(eid, ExecutionStatus.COMPLETED.value)
    assert row is not None
    # Auto-resume payload landed in the step result
    injected = (row.state or {}).get("step_results", {}).get("step")
    assert isinstance(injected, dict)
    assert "resumed_at" in injected


# ---------------------------------------------------------------------------
# Non-wait_until: expire path
# ---------------------------------------------------------------------------


async def test_elicit_past_ttl_marked_expired(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b1_elicit_expire",
        steps=[{
            "step_id": "ask",
            "type": "elicit",
            "elicit": {"message": "ok?", "schema": {"type": "object"}},
        }],
    )
    eid = await _setup_suspended_with_expired_ttl(
        db_session,
        user_id=user_id,
        org_id=org_id,
        composition_id=comp.id,
        reason="elicit",
        payload={"step_id": "ask"},
    )

    result = await scan_expiry_batch(batch_limit=50)
    assert eid in result["expired"]

    from app.db import session as session_module
    async with session_module.AsyncSessionLocal() as probe:
        row = await probe.get(CompositionExecution, eid)
        assert row.status == ExecutionStatus.EXPIRED.value
        assert "ttl_expired" in (row.error or "")

        # Timeline event emitted
        events = (
            await probe.execute(
                select(ExecutionStepEvent).where(
                    ExecutionStepEvent.execution_id == eid,
                    ExecutionStepEvent.event_type == "expired",
                )
            )
        ).scalars().all()
        assert len(events) == 1


async def test_scanner_skips_rows_not_yet_due(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b1_not_due",
        steps=[{
            "step_id": "step",
            "type": "wait_until",
            "wait_until": {"wait_seconds": 60},
        }],
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    row = await db_session.get(CompositionExecution, eid)
    state = ExecutionState.from_jsonb(row.state)
    state.suspension = {
        "reason": "wait_until",
        "payload": {"step_id": "step"},
        "ttl_seconds": 600,
    }
    row.state = state.to_jsonb()
    row.status = ExecutionStatus.SUSPENDED.value
    row.expires_at = datetime.utcnow() + timedelta(hours=1)  # NOT yet due
    await db_session.commit()

    result = await scan_expiry_batch(batch_limit=50)
    assert eid not in result["expired"]
    assert eid not in result["resumed"]


async def test_scanner_ignores_rows_with_no_expires_at(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b1_no_expiry",
        steps=[{
            "step_id": "step",
            "type": "_test_suspend",
        }],
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    row = await db_session.get(CompositionExecution, eid)
    state = ExecutionState.from_jsonb(row.state)
    state.suspension = {
        "reason": "_test_suspend",
        "payload": {},
        "ttl_seconds": 300,
    }
    row.state = state.to_jsonb()
    row.status = ExecutionStatus.SUSPENDED.value
    row.expires_at = None  # no TTL at all
    await db_session.commit()

    result = await scan_expiry_batch(batch_limit=50)
    assert eid not in result["expired"]


async def test_scanner_handles_mixed_batch(
    db_session: AsyncSession, test_user: dict
):
    """One wait_until + one elicit, both past TTL → one fires, one expires."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b1_mixed",
        steps=[{
            "step_id": "step",
            "type": "wait_until",
            "wait_until": {"wait_seconds": 60},
        }],
    )

    wait_eid = await _setup_suspended_with_expired_ttl(
        db_session,
        user_id=user_id, org_id=org_id, composition_id=comp.id,
        reason="wait_until", payload={"step_id": "step"},
    )
    elicit_eid = await _setup_suspended_with_expired_ttl(
        db_session,
        user_id=user_id, org_id=org_id, composition_id=comp.id,
        reason="elicit", payload={"step_id": "step"},
    )

    result = await scan_expiry_batch(batch_limit=50)
    assert elicit_eid in result["expired"]

    # Wait until fires in the background — poll for the terminal state
    completed_wait = await _poll_until_status(
        wait_eid, ExecutionStatus.COMPLETED.value
    )
    assert completed_wait is not None

    from app.db import session as session_module
    async with session_module.AsyncSessionLocal() as probe:
        elicit_row = await probe.get(CompositionExecution, elicit_eid)
        assert elicit_row.status == ExecutionStatus.EXPIRED.value
