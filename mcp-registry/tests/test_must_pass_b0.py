"""Phase B-0 chunk 13: 14-must-pass coverage map + missing tests.

The design doc lists 14 tests that MUST pass before B-0 ships. This
file collects the ones that didn't naturally fit elsewhere (currently
just the depth-limit pre-flight) and verifies the others exist via
import-and-call asserts so the coverage map can't silently rot.

Coverage:

| #  | Must-pass test name                              | Lives in                            |
|----|--------------------------------------------------|-------------------------------------|
| 1  | sync_composition_unchanged                       | test_composition_routing_b0         |
| 2  | test_suspend_round_trip                          | test_resumable_executor             |
| 3  | pattern_c_resource_flow                          | test_composition_routing_b0         |
| 4  | capability_negotiation_no_subscribe              | test_composition_routing_b0 (uniform payload — see test_pattern_c_creates_execution_row_and_returns_resource_uri) |
| 5  | idempotence_after_crash_default_safe             | test_resumable_executor             |
| 6  | idempotence_after_crash_marked_idempotent        | test_resumable_executor             |
| 7  | orphan_recovery_on_restart                       | test_queue_worker_b0                |
| 8  | concurrent_resume_only_one_succeeds              | test_resumable_executor             |
| 9  | cancel_during_running                            | test_resumable_executor (cancel boundary on suspended) |
| 10 | subcomposition_propagation                       | test_resumable_executor (×2)        |
| 11 | subcomposition_depth_limit                       | this file                           |
| 12 | quota_promotes_via_queue                         | test_queue_worker_b0                |
| 13 | per_user_resource_isolation                      | test_composition_resources_b0       |
| 14 | pending_notification_flush_on_reconnect          | test_pending_notification_b0        |
"""

from __future__ import annotations

from typing import Tuple
from uuid import UUID, uuid4

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
from app.orchestration.execution_state import ExecutionState
from app.orchestration.resumable_executor import (
    MAX_SUBCOMPOSITION_DEPTH,
    SubcompositionDepthExceeded,
    create_execution,
    _reset_executor_for_tests,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers (mirror the other B-0 test files)
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
    db: AsyncSession, org_id: UUID, owner_id: UUID, *, name: str
) -> Composition:
    comp = Composition(
        organization_id=org_id,
        created_by=owner_id,
        name=name,
        description="b0 chunk13",
        visibility=CompositionVisibility.PRIVATE.value,
        steps=[{"step_id": "1", "type": "_test_suspend"}],
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
# Must-pass #11: subcomposition_depth_limit
# ---------------------------------------------------------------------------


async def test_subcomposition_depth_limit(
    db_session: AsyncSession, test_user: dict
):
    """Direct DB setup: parent.state.depth=cap; child create raises.

    Per design doc §10 must-pass #11: the executor must refuse to
    create a sub-composition that would push past
    ``MAX_SUBCOMPOSITION_DEPTH`` (5 in B-0). The check fires
    pre-flight in ``create_execution`` so the row never lands in the
    DB and the parent step gets a clear failure envelope.
    """
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_depth_parent"
    )

    # Parent at the cap depth
    parent_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    parent_row = await db_session.get(CompositionExecution, parent_id)
    state = ExecutionState.from_jsonb(parent_row.state)
    state.depth = MAX_SUBCOMPOSITION_DEPTH  # already at the cap
    parent_row.state = state.to_jsonb()
    await db_session.commit()

    # Attempting to create a child must raise pre-flight
    with pytest.raises(SubcompositionDepthExceeded):
        await create_execution(
            composition_id=comp.id,
            user_id=user_id,
            organization_id=org_id,
            trigger="manual",
            parent_execution_id=parent_id,
        )

    # No child row was created
    children = (
        await db_session.execute(
            select(CompositionExecution).where(
                CompositionExecution.parent_execution_id == parent_id
            )
        )
    ).scalars().all()
    assert children == []


async def test_subcomposition_depth_below_cap_succeeds(
    db_session: AsyncSession, test_user: dict
):
    """Child with parent_depth + 1 still under the cap → row created."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_depth_ok"
    )
    parent_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    parent_row = await db_session.get(CompositionExecution, parent_id)
    state = ExecutionState.from_jsonb(parent_row.state)
    state.depth = MAX_SUBCOMPOSITION_DEPTH - 2  # plenty of room
    parent_row.state = state.to_jsonb()
    await db_session.commit()

    child_id = await create_execution(
        composition_id=comp.id,
        user_id=user_id,
        organization_id=org_id,
        trigger="manual",
        parent_execution_id=parent_id,
    )
    child_row = await db_session.get(CompositionExecution, child_id)
    await db_session.refresh(child_row)
    assert child_row is not None
    assert child_row.state["depth"] == MAX_SUBCOMPOSITION_DEPTH - 1


async def test_subcomposition_depth_overrides_caller_supplied_depth(
    db_session: AsyncSession, test_user: dict
):
    """A caller can't bypass the cap by passing a low ``depth=`` kwarg.

    The cap is enforced based on the parent's stored depth, not the
    caller's word. This is the security invariant for the depth
    check — without it, a malicious or buggy step handler could
    spawn unbounded sub-compositions.
    """
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_depth_override"
    )
    parent_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    parent_row = await db_session.get(CompositionExecution, parent_id)
    state = ExecutionState.from_jsonb(parent_row.state)
    state.depth = MAX_SUBCOMPOSITION_DEPTH  # at the cap
    parent_row.state = state.to_jsonb()
    await db_session.commit()

    # Caller lies about depth — must still be rejected
    with pytest.raises(SubcompositionDepthExceeded):
        await create_execution(
            composition_id=comp.id,
            user_id=user_id,
            organization_id=org_id,
            trigger="manual",
            parent_execution_id=parent_id,
            depth=0,  # the lie
        )


# ---------------------------------------------------------------------------
# Coverage map sanity check — every must-pass test exists
# ---------------------------------------------------------------------------


def test_must_pass_tests_exist():
    """Import-and-attribute-check the 14 must-pass tests.

    If any test name in the design doc is renamed without updating
    the map at the top of this file, this assertion fails loudly.
    """
    must_pass_map = {
        "test_composition_routing_b0": [
            "test_pattern_a_delegates_to_legacy_executor",  # #1
            "test_pattern_c_creates_execution_row_and_returns_resource_uri",  # #3 + #4
        ],
        "test_resumable_executor": [
            "test_test_suspend_round_trip",  # #2
            "test_idempotence_default_safe_blocks_re_run",  # #5
            "test_idempotence_opt_in_re_runs",  # #6
            "test_concurrent_resume_only_one_succeeds",  # #8
            "test_cancel_during_suspended",  # #9
            "test_subcomposition_propagation_on_complete",  # #10
            "test_subcomposition_propagation_on_failure",  # #10
        ],
        "test_queue_worker_b0": [
            "test_orphan_recovery_marks_running_as_failed",  # #7
            "test_promote_skips_when_user_at_quota",  # #12
        ],
        "test_composition_resources_b0": [
            "test_read_returns_none_for_cross_user",  # #13
        ],
        "test_pending_notification_b0": [
            "test_round_trip_offline_then_online",  # #14
        ],
    }
    import importlib

    missing: list[str] = []
    for module_name, test_names in must_pass_map.items():
        module = importlib.import_module(f"tests.{module_name}")
        for test_name in test_names:
            if not hasattr(module, test_name):
                missing.append(f"{module_name}::{test_name}")

    assert not missing, (
        "Must-pass coverage map drift: tests referenced in the design "
        f"doc are missing from the codebase: {missing}"
    )
