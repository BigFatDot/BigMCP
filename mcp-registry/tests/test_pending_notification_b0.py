"""Phase B-0 chunk 9: pending_notification queue + flush tests.

Validates the offline notification path:
- A subscribed but offline session triggers a row insert when the
  executor fires ``notify_resource_updated``.
- ``flush_pending_notifications`` replays queued rows in created_at
  order and deletes them on success.
- Stale rows (>7d) are dropped without replay.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Tuple
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
    PendingNotification,
)
from app.models.organization import OrganizationMember
from app.models.user import User
from app.orchestration.composition_resources import (
    EXECUTION_URI_PREFIX,
    ExecutionSubscriptionTracker,
    execution_uri,
    flush_pending_notifications,
    get_subscription_tracker,
    notify_resource_updated,
    _reset_subscription_tracker_for_tests,
)
from app.orchestration.resumable_executor import (
    create_execution,
    _reset_executor_for_tests,
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
) -> Composition:
    comp = Composition(
        organization_id=org_id,
        created_by=owner_id,
        name=name,
        description="b0 chunk9",
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
def _fresh_state():
    _reset_executor_for_tests()
    _reset_subscription_tracker_for_tests()
    yield
    _reset_executor_for_tests()
    _reset_subscription_tracker_for_tests()


@pytest.fixture(autouse=True)
def _patch_session_local(db_engine, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession as _AS, async_sessionmaker
    from app.db import session as session_module

    test_factory = async_sessionmaker(db_engine, class_=_AS, expire_on_commit=False)
    monkeypatch.setattr(session_module, "AsyncSessionLocal", test_factory)
    yield test_factory


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_notify_persists_pending_when_pusher_returns_false(
    db_session: AsyncSession, test_user: dict
):
    """Live push reports offline → row lands in pending_notification."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(db_session, org_id, user_id, name="b0_pn_offline")
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    uri = execution_uri(eid)

    tracker = get_subscription_tracker()
    tracker.subscribe("S-offline", uri)

    async def offline_pusher(session_id: str, u: str) -> bool:
        return False  # Always offline

    await notify_resource_updated(eid, live_pusher=offline_pusher)

    rows = (
        await db_session.execute(
            select(PendingNotification).where(
                PendingNotification.session_id == "S-offline"
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].uri == uri
    assert rows[0].method == "notifications/resources/updated"


async def test_notify_skips_persist_when_pusher_returns_true(
    db_session: AsyncSession, test_user: dict
):
    """Live push reports delivered → no row in pending_notification."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(db_session, org_id, user_id, name="b0_pn_live")
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    uri = execution_uri(eid)

    tracker = get_subscription_tracker()
    tracker.subscribe("S-live", uri)

    async def live_pusher(session_id: str, u: str) -> bool:
        return True

    await notify_resource_updated(eid, live_pusher=live_pusher)

    rows = (
        await db_session.execute(
            select(PendingNotification).where(
                PendingNotification.session_id == "S-live"
            )
        )
    ).scalars().all()
    assert rows == []


async def test_notify_with_no_pusher_persists_for_offline_sessions(
    db_session: AsyncSession, test_user: dict
):
    """live_pusher=None → every subscribed session gets queued."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(db_session, org_id, user_id, name="b0_pn_nopush")
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    uri = execution_uri(eid)

    tracker = get_subscription_tracker()
    tracker.subscribe("S-a", uri)
    tracker.subscribe("S-b", uri)

    await notify_resource_updated(eid, live_pusher=None)

    rows = (
        await db_session.execute(
            select(PendingNotification).where(PendingNotification.uri == uri)
        )
    ).scalars().all()
    session_ids = {r.session_id for r in rows}
    assert session_ids == {"S-a", "S-b"}


async def test_flush_replays_in_created_at_order_and_deletes(
    db_session: AsyncSession, test_user: dict
):
    """Flush sends each row through the pusher and deletes on success."""
    base = datetime.utcnow() - timedelta(seconds=10)
    rows = [
        PendingNotification(
            session_id="S-flush",
            uri=f"{EXECUTION_URI_PREFIX}{UUID(int=i)}",
            method="notifications/resources/updated",
            created_at=base + timedelta(seconds=i),
        )
        for i in range(3)
    ]
    for r in rows:
        db_session.add(r)
    await db_session.commit()

    pushed: List[Tuple[str, str]] = []

    async def pusher(session_id: str, uri: str) -> bool:
        pushed.append((session_id, uri))
        return True

    drained = await flush_pending_notifications("S-flush", live_pusher=pusher)
    assert drained == 3
    # Sorted by created_at — index in URI matches insertion order
    assert [u for _, u in pushed] == [
        f"{EXECUTION_URI_PREFIX}{UUID(int=i)}" for i in range(3)
    ]

    remaining = (
        await db_session.execute(
            select(PendingNotification).where(
                PendingNotification.session_id == "S-flush"
            )
        )
    ).scalars().all()
    assert remaining == []


async def test_flush_keeps_rows_when_pusher_still_offline(
    db_session: AsyncSession, test_user: dict
):
    """If the pusher reports False, rows stay queued for the next try."""
    pn = PendingNotification(
        session_id="S-still-offline",
        uri=f"{EXECUTION_URI_PREFIX}{UUID(int=42)}",
        method="notifications/resources/updated",
        created_at=datetime.utcnow(),
    )
    db_session.add(pn)
    await db_session.commit()

    async def offline_pusher(session_id: str, uri: str) -> bool:
        return False

    drained = await flush_pending_notifications(
        "S-still-offline", live_pusher=offline_pusher
    )
    # Nothing was delivered nor expired → counted as 0 drained
    assert drained == 0

    remaining = (
        await db_session.execute(
            select(PendingNotification).where(
                PendingNotification.session_id == "S-still-offline"
            )
        )
    ).scalars().all()
    assert len(remaining) == 1


async def test_flush_drops_stale_rows_without_replay(
    db_session: AsyncSession, test_user: dict
):
    """Rows older than max_age_days are deleted, never pushed."""
    # 8 days old, max_age=7 → stale
    stale = PendingNotification(
        session_id="S-stale",
        uri=f"{EXECUTION_URI_PREFIX}{UUID(int=99)}",
        method="notifications/resources/updated",
        created_at=datetime.utcnow() - timedelta(days=8),
    )
    fresh = PendingNotification(
        session_id="S-stale",
        uri=f"{EXECUTION_URI_PREFIX}{UUID(int=100)}",
        method="notifications/resources/updated",
        created_at=datetime.utcnow(),
    )
    db_session.add(stale)
    db_session.add(fresh)
    await db_session.commit()

    pushed: List[Tuple[str, str]] = []

    async def pusher(session_id: str, uri: str) -> bool:
        pushed.append((session_id, uri))
        return True

    drained = await flush_pending_notifications(
        "S-stale", live_pusher=pusher, max_age_days=7
    )
    # Both removed (1 stale + 1 delivered)
    assert drained == 2
    # Only the fresh one was actually pushed
    assert pushed == [("S-stale", f"{EXECUTION_URI_PREFIX}{UUID(int=100)}")]

    remaining = (
        await db_session.execute(
            select(PendingNotification).where(
                PendingNotification.session_id == "S-stale"
            )
        )
    ).scalars().all()
    assert remaining == []


async def test_flush_returns_zero_when_no_rows(
    db_session: AsyncSession, test_user: dict
):
    """Empty queue → no work, returns 0."""

    async def pusher(session_id: str, uri: str) -> bool:
        return True

    drained = await flush_pending_notifications(
        "S-nobody", live_pusher=pusher
    )
    assert drained == 0


async def test_flush_with_empty_session_id_is_noop(
    db_session: AsyncSession, test_user: dict
):
    """Defensive: empty session_id never queries the DB."""

    async def pusher(session_id: str, uri: str) -> bool:
        raise AssertionError("should never be called")

    drained = await flush_pending_notifications("", live_pusher=pusher)
    assert drained == 0


async def test_round_trip_offline_then_online(
    db_session: AsyncSession, test_user: dict
):
    """Offline notify queues → flush replays → queue is empty."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_pn_round_trip"
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    uri = execution_uri(eid)

    tracker = get_subscription_tracker()
    tracker.subscribe("S-rt", uri)

    # First fire: pusher reports offline → queues
    async def offline(_session_id: str, _uri: str) -> bool:
        return False

    await notify_resource_updated(eid, live_pusher=offline)

    # Now reconnect: pusher delivers → drains the queue
    delivered: List[Tuple[str, str]] = []

    async def online(session_id: str, uri_in: str) -> bool:
        delivered.append((session_id, uri_in))
        return True

    drained = await flush_pending_notifications("S-rt", live_pusher=online)
    assert drained == 1
    assert delivered == [("S-rt", uri)]

    remaining = (
        await db_session.execute(
            select(PendingNotification).where(
                PendingNotification.session_id == "S-rt"
            )
        )
    ).scalars().all()
    assert remaining == []
