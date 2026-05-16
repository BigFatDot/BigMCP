"""Phase B-1.3: ``subcomposition`` step type — dispatch + propagation.

The propagation INFRA already exists in B-0 (chunk 4 hook +
chunk 13 depth cap). What's new in B-1.3 is the front-end:
config validation, target lookup, input resolution, and the
dispatch branch in ``ResumableExecutor._execute_step``.

The end-to-end propagation (child completes → parent resumes) is
already covered by tests in test_resumable_executor.py — this file
focuses on the new authored-config surface.
"""

from __future__ import annotations

import asyncio
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
from app.orchestration.composition_routing import SUSPENDING_STEP_TYPES
from app.orchestration.execution_state import ExecutionState
from app.orchestration.resumable_executor import (
    INPUTS_KEY,
    create_execution,
    get_executor,
    _reset_executor_for_tests,
)
from app.orchestration.subcomposition_step import (
    SubcompositionConfigError,
    dispatch,
    resolve_inputs,
    validate_config,
    validate_target_composition,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
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
    db: AsyncSession,
    org_id: UUID,
    owner_id: UUID,
    *,
    name: str,
    steps: list,
    status: CompositionStatus = CompositionStatus.PRODUCTION,
) -> Composition:
    comp = Composition(
        organization_id=org_id,
        created_by=owner_id,
        name=name,
        description="b1.3 subcomposition",
        visibility=CompositionVisibility.PRIVATE.value,
        steps=steps,
        data_mappings=[],
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=None,
        server_bindings={},
        allowed_roles=[],
        force_org_credentials=False,
        status=status.value,
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


def test_subcomposition_in_suspending_step_types():
    assert "subcomposition" in SUSPENDING_STEP_TYPES


# ---------------------------------------------------------------------------
# Static config validation
# ---------------------------------------------------------------------------


def test_validate_requires_object():
    with pytest.raises(SubcompositionConfigError):
        validate_config(None)


def test_validate_requires_composition_id():
    with pytest.raises(SubcompositionConfigError):
        validate_config({})


def test_validate_rejects_non_uuid_id():
    with pytest.raises(SubcompositionConfigError):
        validate_config({"composition_id": "not-a-uuid"})


def test_validate_rejects_non_dict_inputs():
    with pytest.raises(SubcompositionConfigError):
        validate_config({"composition_id": str(uuid4()), "inputs": "oops"})


def test_validate_accepts_minimal():
    validate_config({"composition_id": str(uuid4())})


def test_validate_accepts_with_inputs():
    validate_config({"composition_id": str(uuid4()), "inputs": {"x": 1}})


# ---------------------------------------------------------------------------
# Target-composition DB-bound check
# ---------------------------------------------------------------------------


async def test_validate_target_unknown_id_returns_error(
    db_session: AsyncSession, test_user: dict
):
    _, org_id = await _ids(db_session, test_user["email"])
    err = await validate_target_composition(
        db_session,
        target_id=uuid4(),
        parent_organization_id=org_id,
    )
    assert err is not None
    assert "does not exist" in err


async def test_validate_target_other_org_reports_not_found(
    db_session: AsyncSession, test_user: dict
):
    """Cross-org targets must report 'does not exist' — no info leak."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    other_org_id = uuid4()  # any UUID that's not the caller's org

    target = await _make_composition(
        db_session, org_id, user_id, name="b1_xorg",
        steps=[{"step_id": "1", "type": "tool", "tool": "noop"}],
    )
    err = await validate_target_composition(
        db_session,
        target_id=target.id,
        parent_organization_id=other_org_id,
    )
    assert err is not None
    assert "does not exist" in err


async def test_validate_target_non_production_rejected(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    target = await _make_composition(
        db_session, org_id, user_id, name="b1_temp",
        steps=[{"step_id": "1", "type": "tool", "tool": "noop"}],
        status=CompositionStatus.TEMPORARY,
    )
    err = await validate_target_composition(
        db_session,
        target_id=target.id,
        parent_organization_id=org_id,
    )
    assert err is not None
    assert "production" in err.lower()


async def test_validate_target_production_same_org_passes(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    target = await _make_composition(
        db_session, org_id, user_id, name="b1_prod",
        steps=[{"step_id": "1", "type": "tool", "tool": "noop"}],
    )
    err = await validate_target_composition(
        db_session,
        target_id=target.id,
        parent_organization_id=org_id,
    )
    assert err is None


# ---------------------------------------------------------------------------
# Input resolution
# ---------------------------------------------------------------------------


def test_resolve_inputs_walks_nested_dict():
    state = ExecutionState(
        step_results={
            INPUTS_KEY: {"name": "Alice", "id": 42},
            "load": {"title": "Foo"},
        }
    )
    raw = {
        "user": "${input.name}",
        "nested": {
            "id": "${input.id}",
            "title": "${load.title}",
        },
        "items": ["${input.name}", "static"],
    }
    out = resolve_inputs(raw, state)
    assert out["user"] == "Alice"
    assert out["nested"]["id"] == "42"
    assert out["nested"]["title"] == "Foo"
    assert out["items"] == ["Alice", "static"]


def test_resolve_inputs_handles_none():
    state = ExecutionState(step_results={INPUTS_KEY: {}})
    assert resolve_inputs(None, state) == {}


def test_resolve_inputs_passes_non_string_leaves_through():
    state = ExecutionState(step_results={INPUTS_KEY: {}})
    out = resolve_inputs({"n": 42, "b": True, "l": None}, state)
    assert out == {"n": 42, "b": True, "l": None}


# ---------------------------------------------------------------------------
# End-to-end dispatch
# ---------------------------------------------------------------------------


async def test_dispatch_creates_child_and_yields_subcomposition_suspend(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    # Child composition with a _test_suspend so we can observe the
    # child landing in suspended (not running to completion).
    child_comp = await _make_composition(
        db_session, org_id, user_id, name="b1_child",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )
    parent_comp = await _make_composition(
        db_session, org_id, user_id, name="b1_parent",
        steps=[{
            "step_id": "call",
            "type": "subcomposition",
            "subcomposition": {
                "composition_id": str(child_comp.id),
                "inputs": {"x": 1},
            },
        }],
    )
    parent_eid = await create_execution(
        composition_id=parent_comp.id,
        user_id=user_id, organization_id=org_id,
        trigger="manual",
    )

    status_str = await get_executor().run(parent_eid)
    assert status_str == ExecutionStatus.SUSPENDED.value

    # Parent state shape
    parent_row = await db_session.get(CompositionExecution, parent_eid)
    await db_session.refresh(parent_row)
    susp = (parent_row.state or {}).get("suspension") or {}
    assert susp.get("reason") == "subcomposition"
    payload = susp.get("payload") or {}
    assert payload.get("step_id") == "call"
    child_id = UUID(payload["child_execution_id"])
    assert payload["target_composition_id"] == str(child_comp.id)

    # Child row exists with parent link
    from app.db import session as session_module
    async with session_module.AsyncSessionLocal() as probe:
        child_row = await probe.get(CompositionExecution, child_id)
        assert child_row is not None
        assert child_row.composition_id == child_comp.id
        assert child_row.parent_execution_id == parent_eid
        assert child_row.user_id == user_id
        assert child_row.organization_id == org_id


async def test_dispatch_unknown_target_fails_step(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    parent_comp = await _make_composition(
        db_session, org_id, user_id, name="b1_bad_target",
        steps=[{
            "step_id": "call",
            "type": "subcomposition",
            "subcomposition": {"composition_id": str(uuid4())},
        }],
    )
    parent_eid = await create_execution(
        composition_id=parent_comp.id,
        user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    status_str = await get_executor().run(parent_eid)
    assert status_str == ExecutionStatus.FAILED.value


async def test_dispatch_inherits_session_and_capabilities(
    db_session: AsyncSession, test_user: dict
):
    """Child gets the parent's mcp_session_id + client_capabilities."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    child_comp = await _make_composition(
        db_session, org_id, user_id, name="b1_inherit_child",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )
    parent_comp = await _make_composition(
        db_session, org_id, user_id, name="b1_inherit_parent",
        steps=[{
            "step_id": "call",
            "type": "subcomposition",
            "subcomposition": {"composition_id": str(child_comp.id)},
        }],
    )
    parent_eid = await create_execution(
        composition_id=parent_comp.id,
        user_id=user_id, organization_id=org_id,
        trigger="manual",
        mcp_session_id="parent-session-xyz",
        client_capabilities={"resources": {"subscribe": True}},
    )
    await get_executor().run(parent_eid)

    parent_row = await db_session.get(CompositionExecution, parent_eid)
    payload = ((parent_row.state or {}).get("suspension") or {}).get("payload") or {}
    child_id = UUID(payload["child_execution_id"])

    from app.db import session as session_module
    async with session_module.AsyncSessionLocal() as probe:
        child_row = await probe.get(CompositionExecution, child_id)
        assert child_row.mcp_session_id == "parent-session-xyz"
        assert child_row.client_capabilities == {"resources": {"subscribe": True}}


# ---------------------------------------------------------------------------
# Propagation round-trip (sanity — full path is tested elsewhere)
# ---------------------------------------------------------------------------


async def test_child_completes_propagates_back_to_parent(
    db_session: AsyncSession, test_user: dict
):
    """Parent calls a child made of a single tool step that returns
    a fixed value. Child completes synchronously inside its detached
    run → B-0 propagation hook resumes the parent → parent completes
    with the child's result injected into ``step_results['call']``.

    This validates that the B-1.3 dispatch correctly chains into
    the existing _propagate_to_parent path with NO race-prone
    suspended-then-manual-resume of the child.
    """
    user_id, org_id = await _ids(db_session, test_user["email"])
    child_comp = await _make_composition(
        db_session, org_id, user_id, name="b1_chain_child",
        steps=[{"step_id": "1", "type": "tool", "tool": "leaf"}],
    )
    parent_comp = await _make_composition(
        db_session, org_id, user_id, name="b1_chain_parent",
        steps=[{
            "step_id": "call",
            "type": "subcomposition",
            "subcomposition": {"composition_id": str(child_comp.id)},
        }],
    )
    parent_eid = await create_execution(
        composition_id=parent_comp.id,
        user_id=user_id, organization_id=org_id,
        trigger="manual",
    )

    async def dispatcher(step, state, execution):
        return {"value": "from-child"}

    executor = get_executor()
    executor.set_tool_dispatcher(dispatcher)
    await executor.run(parent_eid)

    # Parent should land at SUSPENDED on subcomposition; the detached
    # child run + propagation back unfold in the background.
    from app.db import session as session_module
    for _ in range(50):
        await asyncio.sleep(0.1)
        async with session_module.AsyncSessionLocal() as probe:
            row = await probe.get(CompositionExecution, parent_eid)
            if row and row.status == ExecutionStatus.COMPLETED.value:
                injected = (row.state or {}).get("step_results", {}).get("call")
                assert injected == {"value": "from-child"}
                return
    pytest.fail("parent did not complete via subcomposition propagation")
