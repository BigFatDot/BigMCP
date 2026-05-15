"""Phase B-0 chunk 3: ResumableExecutor unit tests.

Validates the suspension state machine in isolation — no MCP wiring
yet (chunk #6 will add the routing layer + tool dispatch). Every
test injects its own tool dispatcher via
``ResumableExecutor.set_tool_dispatcher`` so we don't depend on the
gateway being up.

Covered invariants from the design doc §10:
- _test_suspend round-trip (yield + resume continues correctly)
- Idempotence guard (default-safe + opt-in re-run)
- Concurrent resume — only one wins
- Cancel mid-flight (boundary check, in-flight step finishes)
- Size cap enforcement (>1MB → fail)
- Per-execution isolation (independent step results)

The remaining E2E tests (orphan recovery on restart, queue
promotion, sub-composition propagation, per-user resource isolation,
pending notification flush) belong to the chunks that ship those
features. Each chunk extends this test file.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional, Tuple
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
    ExecutionStepEvent,
)
from app.models.organization import OrganizationMember
from app.models.user import User
from app.orchestration.execution_state import ExecutionState
from app.orchestration.resumable_executor import (
    ExecutionStateConflict,
    ResumableExecutor,
    StepResultTooLarge,
    ToolDispatchUnconfigured,
    create_execution,
    _reset_executor_for_tests,
    get_executor,
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


async def _poll_until(
    db_session: AsyncSession,
    execution_id: UUID,
    predicate,
    *,
    iterations: int = 50,
    interval_seconds: float = 0.1,
):
    """Poll an execution row until ``predicate(row)`` is truthy.

    Re-opens a short-lived session each iteration via the patched
    ``AsyncSessionLocal``: SQLite snapshot isolation otherwise pins
    the long-lived ``db_session`` to its pre-poll view, masking
    writes done by the executor's background tasks. We also commit
    on the test session so it doesn't hold a write lock that would
    block the worker session.
    """
    from app.db import session as _session_module

    last_row: Optional[CompositionExecution] = None
    for _ in range(iterations):
        await asyncio.sleep(interval_seconds)
        try:
            await db_session.commit()
        except Exception:
            pass
        async with _session_module.AsyncSessionLocal() as probe:
            row = await probe.get(CompositionExecution, execution_id)
            last_row = row
            if predicate(row):
                return row
    return last_row


async def _make_composition(
    db: AsyncSession,
    org_id: UUID,
    owner_id: UUID,
    *,
    name: str,
    steps: list,
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
    """Drop the executor singleton between tests so dispatchers don't leak."""
    _reset_executor_for_tests()
    yield
    _reset_executor_for_tests()


@pytest.fixture(autouse=True)
def _patch_session_local(db_engine, monkeypatch):
    """Make ``ResumableExecutor`` see the test SQLite engine.

    The executor calls ``_db_session_module.AsyncSessionLocal()`` to
    open its own session (it's invoked from background tasks, not
    request handlers, so it can't depend on FastAPI's
    ``get_async_session`` override). We swap the module-level
    factory for a ``async_sessionmaker`` bound to the test engine
    (SQLite in-memory + StaticPool, so all sessions share state with
    the ``db_session`` fixture).
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from app.db import session as session_module

    test_factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    monkeypatch.setattr(session_module, "AsyncSessionLocal", test_factory)
    yield test_factory


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_test_suspend_round_trip(db_session: AsyncSession, test_user: dict):
    """A composition with a _test_suspend step yields, resume continues."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session,
        org_id,
        user_id,
        name="b0_suspend",
        steps=[
            {"step_id": "1", "type": "_test_suspend"},
        ],
    )

    execution_id = await create_execution(
        composition_id=comp.id,
        user_id=user_id,
        organization_id=org_id,
        trigger="manual",
    )

    executor = get_executor()
    status = await executor.run(execution_id)
    assert status == ExecutionStatus.SUSPENDED.value

    # State reflects the suspension
    row = await db_session.get(CompositionExecution, execution_id)
    await db_session.refresh(row)
    assert row.state["current_step_id"] == "1"
    assert row.state["suspension"]["reason"] == "_test_suspend"
    assert row.expires_at is not None

    # Resume injects the response and the composition completes
    final = await executor.resume(execution_id, {"value": 42})
    assert final == ExecutionStatus.COMPLETED.value

    await db_session.refresh(row)
    assert row.status == ExecutionStatus.COMPLETED.value
    assert row.state["step_status"]["1"] == "succeeded"
    assert row.state["step_results"]["1"] == {"value": 42}
    assert row.state["suspension"] is None


async def test_concurrent_resume_only_one_succeeds(
    db_session: AsyncSession, test_user: dict
):
    """Two parallel resumes: first wins, second raises ExecutionStateConflict."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_concurrent",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )
    execution_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    executor = get_executor()
    await executor.run(execution_id)

    # Two concurrent resumes
    results = await asyncio.gather(
        executor.resume(execution_id, {"first": True}),
        executor.resume(execution_id, {"second": True}),
        return_exceptions=True,
    )
    successes = [r for r in results if r == ExecutionStatus.COMPLETED.value]
    conflicts = [r for r in results if isinstance(r, ExecutionStateConflict)]
    assert len(successes) == 1
    assert len(conflicts) == 1


async def test_cancel_during_suspended(
    db_session: AsyncSession, test_user: dict
):
    """Cancel on a suspended execution: next run() observes the flag."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_cancel",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )
    execution_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    executor = get_executor()
    assert (await executor.run(execution_id)) == ExecutionStatus.SUSPENDED.value

    # Mark cancel_requested
    touched = await executor.request_cancel(execution_id)
    assert touched is True

    # Resume sees the cancel at the boundary and transitions to cancelled
    # (resume itself succeeds — the cancel boundary check fires inside the loop)
    status = await executor.resume(execution_id, {"value": 1})
    assert status == ExecutionStatus.CANCELLED.value


async def test_idempotence_default_safe_blocks_re_run(
    db_session: AsyncSession, test_user: dict
):
    """Step in_progress on resume + idempotent=false → fails with reason."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_non_idempotent",
        steps=[{"step_id": "1", "type": "tool", "tool": "fake_tool"}],
    )
    execution_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )

    # Manually simulate a crash mid-step: mark in_progress, leave it.
    row = await db_session.get(CompositionExecution, execution_id)
    state = ExecutionState.from_jsonb(row.state)
    state.step_status["1"] = "in_progress"
    state.current_step_id = "1"
    row.state = state.to_jsonb()
    await db_session.commit()

    # No tool dispatcher registered — it shouldn't matter, the
    # idempotence guard fires first and prevents the call.
    executor = get_executor()
    status = await executor.run(execution_id)
    assert status == ExecutionStatus.FAILED.value
    await db_session.refresh(row)
    assert row.state["step_results"]["1"] == {
        "error": "resumed_after_crash_non_idempotent"
    }


async def test_idempotence_opt_in_re_runs(
    db_session: AsyncSession, test_user: dict
):
    """Step in_progress on resume + idempotent=true → re-runs cleanly."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_idempotent",
        steps=[{
            "step_id": "1",
            "type": "tool",
            "tool": "fake_tool",
            "idempotent": True,
        }],
    )
    execution_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )

    # Simulate crash mid-step
    row = await db_session.get(CompositionExecution, execution_id)
    state = ExecutionState.from_jsonb(row.state)
    state.step_status["1"] = "in_progress"
    state.current_step_id = "1"
    row.state = state.to_jsonb()
    await db_session.commit()

    # Inject a tool dispatcher that returns a value
    calls = []

    async def dispatcher(step, state, execution):
        calls.append(step["step_id"])
        return {"ok": True, "step": step["step_id"]}

    executor = get_executor()
    executor.set_tool_dispatcher(dispatcher)

    status = await executor.run(execution_id)
    assert status == ExecutionStatus.COMPLETED.value
    assert calls == ["1"], "idempotent step should re-run exactly once"
    await db_session.refresh(row)
    assert row.state["step_results"]["1"] == {"ok": True, "step": "1"}


async def test_size_cap_enforced(db_session: AsyncSession, test_user: dict):
    """A tool returning >1MB → step fails, execution fails."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_size",
        steps=[{"step_id": "1", "type": "tool", "tool": "blob_tool"}],
    )
    execution_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )

    async def big_dispatcher(step, state, execution):
        return {"blob": "x" * 2_000_000}  # ~2MB JSON

    executor = get_executor()
    executor.set_tool_dispatcher(big_dispatcher)

    status = await executor.run(execution_id)
    assert status == ExecutionStatus.FAILED.value
    row = await db_session.get(CompositionExecution, execution_id)
    await db_session.refresh(row)
    assert "step_result_too_large" in (row.error or "")


async def test_tool_dispatch_unconfigured_fails_loudly(
    db_session: AsyncSession, test_user: dict
):
    """type=tool without an injected dispatcher → composition fails."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_no_dispatcher",
        steps=[{"step_id": "1", "type": "tool", "tool": "missing"}],
    )
    execution_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    executor = get_executor()  # no dispatcher set
    status = await executor.run(execution_id)
    assert status == ExecutionStatus.FAILED.value


async def test_pure_tool_composition_runs_to_completion(
    db_session: AsyncSession, test_user: dict
):
    """Multi-step tool composition with a dispatcher: runs through."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_pure_tools",
        steps=[
            {"step_id": "a", "type": "tool", "tool": "t1"},
            {"step_id": "b", "type": "tool", "tool": "t2"},
            {"step_id": "c", "type": "tool", "tool": "t3"},
        ],
    )
    execution_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )

    seen = []

    async def dispatcher(step, state, execution):
        seen.append(step["step_id"])
        return {"out": step["step_id"]}

    executor = get_executor()
    executor.set_tool_dispatcher(dispatcher)

    status = await executor.run(execution_id)
    assert status == ExecutionStatus.COMPLETED.value
    assert seen == ["a", "b", "c"]
    row = await db_session.get(CompositionExecution, execution_id)
    await db_session.refresh(row)
    assert row.state["step_status"] == {
        "a": "succeeded", "b": "succeeded", "c": "succeeded"
    }
    # _extract_result returns the LAST successful step's payload
    assert row.result == {"out": "c"}


async def test_subcomposition_propagation_on_complete(
    db_session: AsyncSession, test_user: dict
):
    """Direct DB setup: parent suspended pointing at child;
    transition child to completed → parent resumes automatically."""
    user_id, org_id = await _ids(db_session, test_user["email"])

    # Parent composition with one step (the step that "called" the
    # child). The step type doesn't matter for B-0 — we set the
    # state manually to look like the parent is suspended waiting.
    parent_comp = await _make_composition(
        db_session, org_id, user_id, name="b0_parent",
        steps=[{"step_id": "call_child", "type": "tool", "tool": "child_proxy"}],
    )
    child_comp = await _make_composition(
        db_session, org_id, user_id, name="b0_child",
        steps=[{"step_id": "1", "type": "tool", "tool": "leaf"}],
    )

    parent_execution_id = await create_execution(
        composition_id=parent_comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    child_execution_id = await create_execution(
        composition_id=child_comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
        parent_execution_id=parent_execution_id,
    )

    # Manually put the parent in suspended state pointing at the child
    parent_row = await db_session.get(CompositionExecution, parent_execution_id)
    parent_state = ExecutionState.from_jsonb(parent_row.state)
    parent_state.current_step_id = "call_child"
    parent_state.step_status["call_child"] = "in_progress"
    parent_state.suspension = {
        "reason": "subcomposition",
        "payload": {"child_execution_id": str(child_execution_id)},
        "ttl_seconds": 3600,
    }
    parent_row.state = parent_state.to_jsonb()
    parent_row.status = ExecutionStatus.SUSPENDED.value
    await db_session.commit()

    # Mark parent's call_child step as idempotent so the resume path
    # (which sees in_progress) re-enters cleanly. The actual tool
    # call would be the second step the parent runs — but we have a
    # mock dispatcher.
    # Actually since the parent step is idempotent and the resume
    # injects the response, the executor sees it as succeeded and
    # moves on — we don't even need a dispatcher.

    # Now run the child to completion. A simple dispatcher returns
    # a payload that should bubble up to the parent.
    async def child_dispatcher(step, state, execution):
        return {"child_output": "hello"}

    executor = get_executor()
    executor.set_tool_dispatcher(child_dispatcher)

    # Run the child — it completes, propagation kicks in
    child_status = await executor.run(child_execution_id)
    assert child_status == ExecutionStatus.COMPLETED.value

    # Wait briefly for the background propagation task. Two-step poll:
    # commit the test session to release its read snapshot, then
    # refresh the row. db_session.refresh re-reads through the same
    # session — by committing first we ensure SQLite's snapshot
    # isolation isn't pinning us to the pre-propagation view.
    final_row = await _poll_until(
        db_session,
        parent_execution_id,
        lambda r: r is not None and r.status == ExecutionStatus.COMPLETED.value,
    )
    assert final_row is not None
    assert final_row.status == ExecutionStatus.COMPLETED.value, (
        f"parent should have completed via propagation, got "
        f"{final_row.status if final_row else 'gone'}"
    )
    # The injected response is the child's result
    assert final_row.state["step_results"]["call_child"] == {
        "child_output": "hello"
    }


async def test_subcomposition_propagation_on_failure(
    db_session: AsyncSession, test_user: dict
):
    """Child failure surfaces to the parent as an error envelope."""
    user_id, org_id = await _ids(db_session, test_user["email"])

    parent_comp = await _make_composition(
        db_session, org_id, user_id, name="b0_parent_fail",
        steps=[{"step_id": "call_child", "type": "tool", "tool": "child_proxy"}],
    )
    child_comp = await _make_composition(
        db_session, org_id, user_id, name="b0_child_fail",
        steps=[{"step_id": "1", "type": "tool", "tool": "leaf"}],
    )

    parent_execution_id = await create_execution(
        composition_id=parent_comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    child_execution_id = await create_execution(
        composition_id=child_comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
        parent_execution_id=parent_execution_id,
    )

    parent_row = await db_session.get(CompositionExecution, parent_execution_id)
    parent_state = ExecutionState.from_jsonb(parent_row.state)
    parent_state.current_step_id = "call_child"
    parent_state.step_status["call_child"] = "in_progress"
    parent_state.suspension = {
        "reason": "subcomposition",
        "payload": {"child_execution_id": str(child_execution_id)},
        "ttl_seconds": 3600,
    }
    parent_row.state = parent_state.to_jsonb()
    parent_row.status = ExecutionStatus.SUSPENDED.value
    await db_session.commit()

    # Failing child dispatcher
    async def failing_dispatcher(step, state, execution):
        raise RuntimeError("upstream blew up")

    executor = get_executor()
    executor.set_tool_dispatcher(failing_dispatcher)
    child_status = await executor.run(child_execution_id)
    assert child_status == ExecutionStatus.FAILED.value

    # Poll for propagation — same SQLite-snapshot dance as the
    # _on_complete sibling above.
    final_row = await _poll_until(
        db_session,
        parent_execution_id,
        lambda r: (
            r is not None
            and isinstance(
                (r.state.get("step_results") or {}).get("call_child"), dict
            )
            and "child_status" in (r.state["step_results"]["call_child"] or {})
        ),
    )
    assert final_row is not None
    injected = (final_row.state.get("step_results") or {}).get("call_child")
    assert injected is not None and "error" in injected
    assert injected["child_status"] == ExecutionStatus.FAILED.value


async def test_subcomposition_propagation_skips_when_parent_not_waiting(
    db_session: AsyncSession, test_user: dict
):
    """If the parent has moved on or is suspended on something else,
    propagation is silently skipped (no exception, no resume)."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    parent_comp = await _make_composition(
        db_session, org_id, user_id, name="b0_parent_skip",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )
    child_comp = await _make_composition(
        db_session, org_id, user_id, name="b0_child_skip",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )

    parent_execution_id = await create_execution(
        composition_id=parent_comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    child_execution_id = await create_execution(
        composition_id=child_comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
        parent_execution_id=parent_execution_id,
    )

    # Parent suspended on a _test_suspend (NOT subcomposition).
    # Child terminal should not touch parent.
    executor = get_executor()
    await executor.run(parent_execution_id)  # parent → suspended on _test_suspend
    await executor.run(child_execution_id)   # child → suspended on _test_suspend

    parent_row = await db_session.get(CompositionExecution, parent_execution_id)
    await db_session.refresh(parent_row)
    parent_status_before = parent_row.status
    assert parent_status_before == ExecutionStatus.SUSPENDED.value

    # Resume the child; it completes
    await executor.resume(child_execution_id, {"value": 1})
    await asyncio.sleep(0.2)

    await db_session.refresh(parent_row)
    # Parent should still be suspended on its OWN _test_suspend,
    # untouched by the child's transition.
    assert parent_row.status == ExecutionStatus.SUSPENDED.value
    assert parent_row.state["suspension"]["reason"] == "_test_suspend"


async def test_run_detached_marks_failed_on_dispatcher_crash(
    db_session: AsyncSession, test_user: dict
):
    """run_detached wrapper catches dispatcher exceptions and marks failed.

    Critical safety net: an asyncio.create_task(run_detached(...))
    that swallows exceptions silently would leak orphan running rows.
    The wrapper must always leave the row in a terminal state.
    """
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_detached_crash",
        steps=[{"step_id": "1", "type": "tool", "tool": "boom"}],
    )
    execution_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )

    async def crashing_dispatcher(step, state, execution):
        raise RuntimeError("upstream exploded")

    executor = get_executor()
    executor.set_tool_dispatcher(crashing_dispatcher)

    # The wrapper is what asyncio.create_task would invoke. Awaiting
    # directly here exercises the same exception-handling path.
    await ResumableExecutor.run_detached(execution_id)

    row = await db_session.get(CompositionExecution, execution_id)
    await db_session.refresh(row)
    assert row.status == ExecutionStatus.FAILED.value, (
        f"run_detached must leave a terminal status, got {row.status}"
    )
    assert row.error  # some non-empty error message


async def test_step_events_recorded(db_session: AsyncSession, test_user: dict):
    """Each step transition appends to execution_step_event timeline."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_events",
        steps=[{"step_id": "1", "type": "tool", "tool": "t"}],
    )
    execution_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )

    async def dispatcher(step, state, execution):
        return {"ok": True}

    executor = get_executor()
    executor.set_tool_dispatcher(dispatcher)
    await executor.run(execution_id)

    events = (
        await db_session.execute(
            select(ExecutionStepEvent)
            .where(ExecutionStepEvent.execution_id == execution_id)
            .order_by(ExecutionStepEvent.timestamp)
        )
    ).scalars().all()

    event_types = [e.event_type for e in events]
    assert "started" in event_types
    assert "succeeded" in event_types
