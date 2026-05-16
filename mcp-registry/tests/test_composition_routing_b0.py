"""Phase B-0 chunk 6: Pattern A/B/C routing tests.

Validates the static-analysis dispatcher and the routing entry
point. These are pure unit tests — they don't go through the MCP
gateway, just exercise route_composition_call() with a mock legacy
executor and assert the right path is taken.

The integration with mcp_unified.py (composition_X / workflow_X
branches) is exercised by the existing live smoke pattern in the
browser walk + by chunk #13's E2E tests.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Tuple
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
from app.orchestration.composition_routing import (
    SUSPENDING_STEP_TYPES,
    composition_has_suspending_steps,
    route_composition_call,
)
from app.orchestration.resumable_executor import (
    _reset_executor_for_tests,
    get_executor,
)


pytestmark = pytest.mark.asyncio


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
    extra_metadata: dict | None = None,
) -> Composition:
    comp = Composition(
        organization_id=org_id,
        created_by=owner_id,
        name=name,
        description="b0",
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
        extra_metadata=extra_metadata or {},
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
# Static analysis
# ---------------------------------------------------------------------------


def test_no_suspending_steps_in_pure_tool_composition():
    class _C:
        steps = [
            {"step_id": "1", "type": "tool", "tool": "x"},
            {"step_id": "2", "type": "tool", "tool": "y"},
        ]
        extra_metadata: Dict[str, Any] = {}

    assert composition_has_suspending_steps(_C()) is False


def test_test_suspend_triggers_suspending_classification():
    class _C:
        steps = [
            {"step_id": "1", "type": "tool", "tool": "x"},
            {"step_id": "2", "type": "_test_suspend"},
        ]
        extra_metadata: Dict[str, Any] = {}

    assert composition_has_suspending_steps(_C()) is True


def test_requires_async_metadata_forces_pattern_c():
    class _C:
        steps = [{"step_id": "1", "type": "tool", "tool": "x"}]
        extra_metadata: Dict[str, Any] = {"requires_async": True}

    assert composition_has_suspending_steps(_C()) is True


def test_suspending_step_types_grows_with_each_phase():
    """Sanity guard: the set of suspending step types is intentional.

    Every entry here corresponds to a step type with a documented
    contract. Widening the set MUST come with a matching dispatch
    branch in ``ResumableExecutor._execute_step`` — this assertion
    fails loudly so a typo in the routing layer can't silently
    bypass the suspension state machine.

    B-0:   ``_test_suspend`` (debug only).
    B-1:   + ``elicit`` (human-in-the-loop, JSON-schema-validated).
    B-1.2: + ``wait_until`` (clock-driven auto-resume).
    B-1.3: + ``subcomposition`` (spawn another composition).
    """
    expected = frozenset(
        {"_test_suspend", "elicit", "wait_until", "subcomposition"}
    )
    assert SUSPENDING_STEP_TYPES == expected, (
        f"SUSPENDING_STEP_TYPES drift: got {sorted(SUSPENDING_STEP_TYPES)}, "
        f"expected {sorted(expected)}. If you added a new step type, "
        f"update this assertion AND the dispatch branch in "
        f"ResumableExecutor._execute_step + the B-1 design doc."
    )


# ---------------------------------------------------------------------------
# Routing entry point
# ---------------------------------------------------------------------------


async def test_pattern_a_delegates_to_legacy_executor(
    db_session: AsyncSession, test_user: dict
):
    """Pure-tool composition → legacy executor invoked, result returned inline."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_pattern_a",
        steps=[{"step_id": "1", "type": "tool", "tool": "noop"}],
    )

    legacy_calls = []

    class FakeLegacyExecutor:
        _user_server_pool = None  # routing does setattr-then-passes-through

        async def execute_composition(self, payload):
            legacy_calls.append(payload)
            return {"status": "success", "outputs": {"value": 42}}

    result = await route_composition_call(
        composition_id=comp.id,
        tool_arguments={"input_x": "test"},
        user_id=user_id,
        organization_id=org_id,
        legacy_executor=FakeLegacyExecutor(),
    )

    assert len(legacy_calls) == 1, "Pattern A must call legacy executor"
    assert legacy_calls[0]["composition_id"] == str(comp.id)
    assert legacy_calls[0]["parameters"] == {"input_x": "test"}
    assert result == {"status": "success", "outputs": {"value": 42}}

    # No execution row was created — Pattern A bypasses the durable layer
    rows = (
        await db_session.execute(
            select(CompositionExecution).where(
                CompositionExecution.composition_id == comp.id
            )
        )
    ).scalars().all()
    assert rows == []


async def test_pattern_c_creates_execution_row_and_returns_resource_uri(
    db_session: AsyncSession, test_user: dict
):
    """Suspending composition → execution row + Pattern C response."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_pattern_c",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )

    class FakeLegacyExecutor:
        _user_server_pool = None

        async def execute_composition(self, payload):
            raise AssertionError(
                "Pattern C must NOT delegate to legacy executor"
            )

    result = await route_composition_call(
        composition_id=comp.id,
        tool_arguments={},
        user_id=user_id,
        organization_id=org_id,
        legacy_executor=FakeLegacyExecutor(),
        mcp_session_id="test-session",
    )

    # Response shape is the structured handle, not an inline result
    assert "execution_id" in result
    assert result["resource_uri"].startswith("composition://executions/")
    assert result["resource_uri"].endswith(result["execution_id"])
    assert result["status"] in {"running", "suspended"}
    assert result["polling_tool"] == "composition_status"
    assert "webapp_url" in result
    assert "_message" in result

    # Execution row exists in DB and is for this user/org/composition
    execution_id = UUID(result["execution_id"])
    row = await db_session.get(CompositionExecution, execution_id)
    await db_session.refresh(row)
    assert row is not None
    assert row.composition_id == comp.id
    assert row.user_id == user_id
    assert row.organization_id == org_id
    assert row.trigger == "mcp_call"
    assert row.mcp_session_id == "test-session"


async def test_pattern_c_kicks_run_detached_and_reaches_suspension(
    db_session: AsyncSession, test_user: dict
):
    """End-to-end: Pattern C call returns immediately, the background
    task runs the executor, and the row reaches 'suspended' on
    _test_suspend (the only B-0 suspending type)."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_pattern_c_e2e",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )

    class FakeLegacyExecutor:
        _user_server_pool = None

    result = await route_composition_call(
        composition_id=comp.id,
        tool_arguments={},
        user_id=user_id,
        organization_id=org_id,
        legacy_executor=FakeLegacyExecutor(),
    )
    execution_id = UUID(result["execution_id"])

    # Wait for the detached task to land at suspension
    for _ in range(50):  # up to ~5s
        row = await db_session.get(CompositionExecution, execution_id)
        await db_session.refresh(row)
        if row.status == ExecutionStatus.SUSPENDED.value:
            break
        await asyncio.sleep(0.1)

    assert row.status == ExecutionStatus.SUSPENDED.value, (
        f"Pattern C background task should reach suspended, got {row.status}"
    )
    assert row.state["current_step_id"] == "1"
    assert row.state["suspension"]["reason"] == "_test_suspend"


async def test_route_raises_on_unknown_composition(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])

    class FakeLegacyExecutor:
        _user_server_pool = None

    from uuid import uuid4
    with pytest.raises(ValueError, match="not found"):
        await route_composition_call(
            composition_id=uuid4(),
            tool_arguments={},
            user_id=user_id,
            organization_id=org_id,
            legacy_executor=FakeLegacyExecutor(),
        )
