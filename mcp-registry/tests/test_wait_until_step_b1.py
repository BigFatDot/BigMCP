"""Phase B-1.2 chunk 1: ``wait_until`` step type — config + dispatch.

Validates the static config (mutual exclusion + range), the resume_at
computation (relative + absolute forms), and the end-to-end
yield/resume round-trip via the executor. The expiry scanner that
auto-resumes when the clock hits lands in chunk 2.
"""

from __future__ import annotations

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
)
from app.models.organization import OrganizationMember
from app.models.user import User
from app.orchestration.composition_routing import SUSPENDING_STEP_TYPES
from app.orchestration.resumable_executor import (
    create_execution,
    get_executor,
    _reset_executor_for_tests,
)
from app.orchestration.wait_until_step import (
    MAX_WAIT_SECONDS,
    MIN_WAIT_SECONDS,
    WaitUntilConfigError,
    auto_resume_payload,
    build_suspend,
    compute_resume_at,
    validate_config,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers / fixtures
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
        description="b1.2 wait_until",
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


# ---------------------------------------------------------------------------
# Sanity
# ---------------------------------------------------------------------------


def test_wait_until_in_suspending_step_types():
    assert "wait_until" in SUSPENDING_STEP_TYPES


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


def test_validate_requires_object():
    with pytest.raises(WaitUntilConfigError):
        validate_config(None)
    with pytest.raises(WaitUntilConfigError):
        validate_config("60")


def test_validate_requires_seconds_or_absolute():
    with pytest.raises(WaitUntilConfigError):
        validate_config({})


def test_validate_rejects_both_forms():
    with pytest.raises(WaitUntilConfigError):
        validate_config({"wait_seconds": 60, "resume_at": "2099-01-01T00:00:00Z"})


def test_validate_seconds_must_be_int():
    with pytest.raises(WaitUntilConfigError):
        validate_config({"wait_seconds": "60"})
    with pytest.raises(WaitUntilConfigError):
        validate_config({"wait_seconds": 60.5})


def test_validate_seconds_must_be_in_range():
    with pytest.raises(WaitUntilConfigError):
        validate_config({"wait_seconds": MIN_WAIT_SECONDS - 1})
    with pytest.raises(WaitUntilConfigError):
        validate_config({"wait_seconds": MAX_WAIT_SECONDS + 1})


def test_validate_resume_at_invalid_iso():
    with pytest.raises(WaitUntilConfigError):
        validate_config({"resume_at": "not a date"})


def test_validate_resume_at_in_past_rejected():
    past = (datetime.utcnow() - timedelta(minutes=5)).isoformat() + "Z"
    with pytest.raises(WaitUntilConfigError):
        validate_config({"resume_at": past})


def test_validate_resume_at_too_far_rejected():
    far_future = (datetime.utcnow() + timedelta(days=60)).isoformat() + "Z"
    with pytest.raises(WaitUntilConfigError):
        validate_config({"resume_at": far_future})


def test_validate_seconds_accepts_in_range():
    validate_config({"wait_seconds": 60})


def test_validate_resume_at_accepts_future():
    future = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
    validate_config({"resume_at": future})


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------


def test_compute_resume_at_relative():
    before = datetime.utcnow()
    out = compute_resume_at({"wait_seconds": 120})
    after = datetime.utcnow()
    # Allow a small clock-tick wiggle
    assert (out - before).total_seconds() >= 120 - 1
    assert (out - after).total_seconds() <= 120 + 1


def test_compute_resume_at_absolute_iso():
    target = datetime.utcnow() + timedelta(minutes=30)
    out = compute_resume_at({"resume_at": target.isoformat() + "Z"})
    # Equality modulo trailing-Z timezone normalisation
    assert abs((out - target).total_seconds()) < 1


def test_auto_resume_payload_has_iso_timestamp():
    payload = auto_resume_payload()
    assert "resumed_at" in payload
    # Parseable round-trip
    raw = payload["resumed_at"]
    assert raw.endswith("Z")
    datetime.fromisoformat(raw[:-1])


# ---------------------------------------------------------------------------
# Suspend builder
# ---------------------------------------------------------------------------


def test_build_suspend_carries_reason_and_payload():
    out = build_suspend({
        "step_id": "wait_a_bit",
        "type": "wait_until",
        "wait_until": {"wait_seconds": 90},
    })
    assert out.reason == "wait_until"
    assert out.payload["step_id"] == "wait_a_bit"
    assert "resume_at" in out.payload
    assert out.payload["resume_at"].endswith("Z")
    # ttl_seconds maps to the wait
    assert 80 <= out.ttl_seconds <= 100


# ---------------------------------------------------------------------------
# End-to-end: executor yields
# ---------------------------------------------------------------------------


async def test_executor_yields_with_resume_at(
    db_session: AsyncSession, test_user: dict
):
    """The run loop hits a wait_until step and lands at SUSPENDED with
    expires_at set to the future fire time."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b1_wait_until_yield",
        steps=[{
            "step_id": "wait",
            "type": "wait_until",
            "wait_until": {"wait_seconds": 60},
        }],
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    status_str = await get_executor().run(eid)
    assert status_str == ExecutionStatus.SUSPENDED.value

    row = await db_session.get(CompositionExecution, eid)
    await db_session.refresh(row)
    susp = row.state.get("suspension") or {}
    assert susp.get("reason") == "wait_until"
    assert susp.get("payload", {}).get("step_id") == "wait"
    assert row.expires_at is not None
    # Fire time is ~60s out
    delta = (row.expires_at - datetime.utcnow()).total_seconds()
    assert 50 <= delta <= 70


async def test_executor_resume_completes_with_resumed_at_payload(
    db_session: AsyncSession, test_user: dict
):
    """Manually firing executor.resume with the auto payload should
    complete the composition and inject {resumed_at} into the step
    result."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b1_wait_until_round_trip",
        steps=[{
            "step_id": "wait",
            "type": "wait_until",
            "wait_until": {"wait_seconds": 60},
        }],
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    executor = get_executor()
    await executor.run(eid)

    payload = auto_resume_payload()
    final = await executor.resume(eid, payload)
    assert final == ExecutionStatus.COMPLETED.value

    row = await db_session.get(CompositionExecution, eid)
    await db_session.refresh(row)
    injected = row.state["step_results"]["wait"]
    assert "resumed_at" in injected
    assert row.state["suspension"] is None


async def test_executor_malformed_config_fails_step(
    db_session: AsyncSession, test_user: dict
):
    """Missing both wait_seconds and resume_at → step fails at dispatch."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b1_wait_until_bad",
        steps=[{
            "step_id": "wait",
            "type": "wait_until",
            "wait_until": {},  # neither form supplied
        }],
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    status_str = await get_executor().run(eid)
    assert status_str == ExecutionStatus.FAILED.value
