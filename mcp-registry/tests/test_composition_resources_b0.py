"""Phase B-0 chunk 7: MCP resource handler tests.

Validates per-user scoping on list/read, the subscription tracker,
and the notify-on-transition hook with parent-chain propagation.
"""

from __future__ import annotations

import asyncio
from typing import List, Tuple
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
from app.orchestration.composition_resources import (
    EXECUTION_URI_PREFIX,
    ExecutionSubscriptionTracker,
    execution_uri,
    get_subscription_tracker,
    list_user_execution_resources,
    notify_resource_updated,
    parse_execution_uri,
    read_execution_resource,
    _reset_subscription_tracker_for_tests,
)
from app.orchestration.execution_state import ExecutionState
from app.orchestration.resumable_executor import (
    create_execution,
    _reset_executor_for_tests,
    get_executor,
    set_live_pusher,
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
    db: AsyncSession, org_id: UUID, owner_id: UUID, *, name: str, steps: list
) -> Composition:
    comp = Composition(
        organization_id=org_id, created_by=owner_id, name=name, description="b0",
        visibility=CompositionVisibility.PRIVATE.value,
        steps=steps, data_mappings=[],
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=None, server_bindings={}, allowed_roles=[],
        force_org_credentials=False,
        status=CompositionStatus.PRODUCTION.value, ttl=None, extra_metadata={},
    )
    db.add(comp)
    await db.commit()
    await db.refresh(comp)
    return comp


@pytest.fixture(autouse=True)
def _fresh_state():
    _reset_executor_for_tests()
    _reset_subscription_tracker_for_tests()
    set_live_pusher(None)
    yield
    _reset_executor_for_tests()
    _reset_subscription_tracker_for_tests()
    set_live_pusher(None)


@pytest.fixture(autouse=True)
def _patch_session_local(db_engine, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession as _AS, async_sessionmaker
    from app.db import session as session_module

    test_factory = async_sessionmaker(db_engine, class_=_AS, expire_on_commit=False)
    monkeypatch.setattr(session_module, "AsyncSessionLocal", test_factory)
    yield test_factory


# ---------------------------------------------------------------------------
# URI parse helpers
# ---------------------------------------------------------------------------


def test_parse_execution_uri_valid():
    eid = uuid4()
    assert parse_execution_uri(f"{EXECUTION_URI_PREFIX}{eid}") == eid


def test_parse_execution_uri_rejects_other_schemes():
    assert parse_execution_uri("composition://production/abc") is None
    assert parse_execution_uri("composition://executions/not-a-uuid") is None
    assert parse_execution_uri("https://example.com") is None


# ---------------------------------------------------------------------------
# list_user_execution_resources
# ---------------------------------------------------------------------------


async def test_list_returns_only_caller_user_executions(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_list",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )
    eid_user = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    # Another user
    other = User(
        email="other-resource-user@example.com",
        password_hash="x", name="Other", email_verified=True,
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    eid_other = await create_execution(
        composition_id=comp.id, user_id=other.id, organization_id=org_id,
        trigger="manual",
    )

    listed = await list_user_execution_resources(user_id=user_id)
    uris = {r["uri"] for r in listed}
    assert execution_uri(eid_user) in uris
    assert execution_uri(eid_other) not in uris


async def test_list_excludes_terminal_by_default(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_list_terminal",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )
    completed_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    # Mark it completed
    from sqlalchemy import update
    await db_session.execute(
        update(CompositionExecution)
        .where(CompositionExecution.id == completed_id)
        .values(status=ExecutionStatus.COMPLETED.value)
    )
    await db_session.commit()

    listed = await list_user_execution_resources(user_id=user_id)
    uris = {r["uri"] for r in listed}
    assert execution_uri(completed_id) not in uris

    # Explicit request includes it
    listed_all = await list_user_execution_resources(
        user_id=user_id,
        statuses=[
            ExecutionStatus.RUNNING.value,
            ExecutionStatus.SUSPENDED.value,
            ExecutionStatus.QUEUED.value,
            ExecutionStatus.COMPLETED.value,
        ],
    )
    assert execution_uri(completed_id) in {r["uri"] for r in listed_all}


# ---------------------------------------------------------------------------
# read_execution_resource — per-user scoping
# ---------------------------------------------------------------------------


async def test_read_returns_payload_for_owner(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_read",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    content = await read_execution_resource(
        uri=execution_uri(eid), user_id=user_id
    )
    assert content is not None
    assert content["uri"] == execution_uri(eid)
    assert content["mimeType"] == "application/json"
    import json as _j
    payload = _j.loads(content["text"])
    assert payload["execution_id"] == str(eid)
    assert payload["status"] in {"queued", "running", "suspended"}


async def test_read_returns_none_for_cross_user(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    other = User(
        email="other-read@example.com",
        password_hash="x", name="Other", email_verified=True,
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_cross",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )
    # Create execution as USER (the test_user) — try to read as OTHER
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    content = await read_execution_resource(
        uri=execution_uri(eid), user_id=other.id
    )
    assert content is None  # cross-user → 404, indistinguishable from non-existent


async def test_read_returns_none_for_unknown_uuid(
    db_session: AsyncSession, test_user: dict
):
    user_id, _ = await _ids(db_session, test_user["email"])
    fake_uri = f"{EXECUTION_URI_PREFIX}{uuid4()}"
    assert await read_execution_resource(uri=fake_uri, user_id=user_id) is None


async def test_read_returns_none_for_non_execution_uri(
    db_session: AsyncSession, test_user: dict
):
    user_id, _ = await _ids(db_session, test_user["email"])
    assert await read_execution_resource(
        uri="composition://production/abc", user_id=user_id
    ) is None


# ---------------------------------------------------------------------------
# Subscription tracker
# ---------------------------------------------------------------------------


def test_subscription_tracker_subscribe_unsubscribe():
    tracker = ExecutionSubscriptionTracker()
    eid = uuid4()
    uri = execution_uri(eid)
    tracker.subscribe("session-A", uri)
    tracker.subscribe("session-B", uri)
    assert tracker.sessions_for_uri(uri) == {"session-A", "session-B"}
    assert tracker.uris_for_session("session-A") == {uri}
    assert tracker.unsubscribe("session-A", uri) is True
    assert tracker.unsubscribe("session-A", uri) is False  # second time = noop
    assert tracker.sessions_for_uri(uri) == {"session-B"}


def test_subscription_tracker_drop_session():
    tracker = ExecutionSubscriptionTracker()
    uri1 = execution_uri(uuid4())
    uri2 = execution_uri(uuid4())
    tracker.subscribe("S", uri1)
    tracker.subscribe("S", uri2)
    tracker.drop_session("S")
    assert tracker.uris_for_session("S") == set()
    assert tracker.sessions_for_uri(uri1) == set()
    assert tracker.sessions_for_uri(uri2) == set()


# ---------------------------------------------------------------------------
# notify_resource_updated — direct + parent-chain propagation
# ---------------------------------------------------------------------------


async def test_notify_pushes_to_subscribed_sessions(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_notify_direct",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    uri = execution_uri(eid)
    tracker = get_subscription_tracker()
    tracker.subscribe("session-X", uri)

    pushed: List[Tuple[str, str]] = []

    async def fake_pusher(session_id: str, u: str) -> bool:
        pushed.append((session_id, u))
        return True

    await notify_resource_updated(eid, live_pusher=fake_pusher)
    assert ("session-X", uri) in pushed


async def test_notify_walks_parent_chain_for_subcomposition(
    db_session: AsyncSession, test_user: dict
):
    """Child notification should bubble up to subscribed parent ancestors."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    parent_comp = await _make_composition(
        db_session, org_id, user_id, name="b0_notify_parent",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )
    child_comp = await _make_composition(
        db_session, org_id, user_id, name="b0_notify_child",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )

    parent_eid = await create_execution(
        composition_id=parent_comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    child_eid = await create_execution(
        composition_id=child_comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
        parent_execution_id=parent_eid,
    )

    # Manually mark parent suspended on this child (subcomposition)
    parent_row = await db_session.get(CompositionExecution, parent_eid)
    parent_state = ExecutionState.from_jsonb(parent_row.state)
    parent_state.current_step_id = "1"
    parent_state.suspension = {
        "reason": "subcomposition",
        "payload": {"child_execution_id": str(child_eid)},
        "ttl_seconds": 300,
    }
    parent_row.state = parent_state.to_jsonb()
    parent_row.status = ExecutionStatus.SUSPENDED.value
    await db_session.commit()

    parent_uri = execution_uri(parent_eid)
    child_uri = execution_uri(child_eid)
    tracker = get_subscription_tracker()
    tracker.subscribe("S-parent", parent_uri)
    tracker.subscribe("S-child", child_uri)

    pushed: List[Tuple[str, str]] = []

    async def fake_pusher(session_id: str, u: str) -> bool:
        pushed.append((session_id, u))
        return True

    # Notify on the CHILD execution → parent should also fire
    await notify_resource_updated(child_eid, live_pusher=fake_pusher)
    assert ("S-child", child_uri) in pushed
    assert ("S-parent", parent_uri) in pushed


async def test_notify_skips_parent_when_not_suspended_on_subcomposition(
    db_session: AsyncSession, test_user: dict
):
    """Parent suspended on something else (not subcomposition) → no
    propagation."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    parent_comp = await _make_composition(
        db_session, org_id, user_id, name="b0_notify_unrelated_parent",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )
    child_comp = await _make_composition(
        db_session, org_id, user_id, name="b0_notify_unrelated_child",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )
    parent_eid = await create_execution(
        composition_id=parent_comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    child_eid = await create_execution(
        composition_id=child_comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
        parent_execution_id=parent_eid,
    )

    # Parent suspended on _test_suspend (NOT subcomposition)
    parent_row = await db_session.get(CompositionExecution, parent_eid)
    parent_state = ExecutionState.from_jsonb(parent_row.state)
    parent_state.suspension = {
        "reason": "_test_suspend",
        "payload": {},
        "ttl_seconds": 300,
    }
    parent_row.state = parent_state.to_jsonb()
    parent_row.status = ExecutionStatus.SUSPENDED.value
    await db_session.commit()

    tracker = get_subscription_tracker()
    tracker.subscribe("S-parent", execution_uri(parent_eid))
    pushed: List[Tuple[str, str]] = []

    async def fake_pusher(session_id: str, u: str) -> bool:
        pushed.append((session_id, u))
        return True

    await notify_resource_updated(child_eid, live_pusher=fake_pusher)
    # Parent NOT in the pushed list — only the child URI (which has
    # no subscriber here).
    parent_pushed = [p for p in pushed if p[0] == "S-parent"]
    assert parent_pushed == []


# ---------------------------------------------------------------------------
# End-to-end: executor transition fires notification
# ---------------------------------------------------------------------------


async def test_executor_suspension_fires_notification(
    db_session: AsyncSession, test_user: dict
):
    """The executor's _mark_suspended hook calls notify_resource_updated,
    and a subscriber receives the push."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_e2e_notify",
        steps=[{"step_id": "1", "type": "_test_suspend"}],
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    uri = execution_uri(eid)
    tracker = get_subscription_tracker()
    tracker.subscribe("S", uri)

    pushed: List[Tuple[str, str]] = []

    async def fake_pusher(session_id: str, u: str) -> bool:
        pushed.append((session_id, u))
        return True

    set_live_pusher(fake_pusher)

    status = await get_executor().run(eid)
    assert status == ExecutionStatus.SUSPENDED.value
    assert ("S", uri) in pushed
