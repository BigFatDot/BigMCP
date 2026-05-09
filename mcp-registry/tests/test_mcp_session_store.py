"""Unit tests for MCPSessionStore (Redis-backed session metadata + per-process queues)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _isolated_cache_backend():
    """Force a fresh InMemoryCacheBackend for each test so state is not shared."""
    from app.core import cache_backend as cb

    cb._cache_backend = None  # noqa: SLF001
    cb.init_cache_backend(redis_client=None, prefix="test:")
    yield
    cb._cache_backend = None  # noqa: SLF001


@pytest.fixture(autouse=True)
def _reset_session_store_singleton():
    from app.services.mcp_session_store import reset_session_store_for_tests

    reset_session_store_for_tests()
    yield
    reset_session_store_for_tests()


@pytest.mark.asyncio
async def test_create_persists_metadata_and_returns_local_queue():
    from app.services.mcp_session_store import MCPSessionStore

    store = MCPSessionStore(ttl_seconds=60)
    sid = "sid-" + str(uuid4())[:8]
    user_id = uuid4()
    org_id = uuid4()

    queue = await store.create(
        sid,
        {
            "user_id": user_id,
            "organization_id": org_id,
            "user_email": "u@example.com",
            "api_key_id": None,
            "tool_group_id": None,
        },
    )

    assert isinstance(queue, asyncio.Queue)
    assert store.has_local_queue(sid)

    fetched = await store.get(sid)
    assert fetched is not None
    assert str(fetched["user_id"]) == str(user_id)
    assert fetched["message_queue"] is queue
    # UUIDs must be serialised to strings in storage.
    assert isinstance(fetched["user_id"], str)
    assert isinstance(fetched["organization_id"], str)


@pytest.mark.asyncio
async def test_indexes_track_org_and_user():
    from app.services.mcp_session_store import MCPSessionStore

    store = MCPSessionStore(ttl_seconds=60)
    org_id = uuid4()
    user_id = uuid4()

    sids = []
    for _ in range(3):
        sid = "sid-" + str(uuid4())[:8]
        sids.append(sid)
        await store.create(
            sid,
            {"user_id": user_id, "organization_id": org_id},
        )

    assert sorted(await store.list_for_org(str(org_id))) == sorted(sids)
    assert sorted(await store.list_for_user(str(user_id))) == sorted(sids)


@pytest.mark.asyncio
async def test_reattach_after_simulated_process_restart():
    """Metadata in Redis must let a fresh store rebind a queue without
    losing the session — this is the post-restart reconnect path."""
    from app.services.mcp_session_store import MCPSessionStore

    store_a = MCPSessionStore(ttl_seconds=60)
    sid = "persist-" + str(uuid4())[:8]
    user_id = uuid4()
    org_id = uuid4()
    await store_a.create(
        sid,
        {"user_id": user_id, "organization_id": org_id},
    )

    # New process boots → fresh in-memory queue map, but the same backend.
    store_b = MCPSessionStore(ttl_seconds=60)
    assert not store_b.has_local_queue(sid)

    queue = await store_b.attach_local_queue(sid)
    assert queue is not None
    assert store_b.has_local_queue(sid)

    # Confirm the rebinding sticks: subsequent get() returns the same queue.
    fetched = await store_b.get(sid)
    assert fetched is not None
    assert fetched["message_queue"] is queue


@pytest.mark.asyncio
async def test_attach_returns_none_for_unknown_session():
    from app.services.mcp_session_store import MCPSessionStore

    store = MCPSessionStore(ttl_seconds=60)
    assert await store.attach_local_queue("does-not-exist") is None


@pytest.mark.asyncio
async def test_iter_local_sessions_for_org_skips_remote_sessions():
    """Sessions registered in Redis but with no local queue (created in
    another process) must NOT be returned: the caller would have nothing
    to push notifications into."""
    from app.services.mcp_session_store import MCPSessionStore

    store = MCPSessionStore(ttl_seconds=60)
    org_id = uuid4()

    sid_local = "local-" + str(uuid4())[:8]
    sid_remote = "remote-" + str(uuid4())[:8]

    await store.create(sid_local, {"user_id": uuid4(), "organization_id": org_id})
    # Register the remote one straight in the backend so the index sees it
    # but no queue is bound locally.
    backend = store._backend()  # noqa: SLF001
    await backend.set(
        store._meta_key(sid_remote),  # noqa: SLF001
        {"user_id": str(uuid4()), "organization_id": str(org_id)},
        ttl=60,
    )
    await store._index_add(store._org_index_key(str(org_id)), sid_remote)  # noqa: SLF001

    matches = await store.iter_local_sessions_for_org(str(org_id))
    matched_sids = {sid for sid, _ in matches}
    assert sid_local in matched_sids
    assert sid_remote not in matched_sids


@pytest.mark.asyncio
async def test_delete_drops_metadata_queue_and_indexes():
    from app.services.mcp_session_store import MCPSessionStore

    store = MCPSessionStore(ttl_seconds=60)
    sid = "del-" + str(uuid4())[:8]
    user_id = uuid4()
    org_id = uuid4()
    await store.create(sid, {"user_id": user_id, "organization_id": org_id})

    await store.delete(sid)

    assert await store.get(sid) is None
    assert not store.has_local_queue(sid)
    assert sid not in await store.list_for_org(str(org_id))
    assert sid not in await store.list_for_user(str(user_id))


@pytest.mark.asyncio
async def test_touch_refreshes_last_activity():
    from app.services.mcp_session_store import MCPSessionStore

    store = MCPSessionStore(ttl_seconds=60)
    sid = "touch-" + str(uuid4())[:8]
    await store.create(sid, {"user_id": uuid4(), "organization_id": uuid4()})

    before = (await store.get_metadata(sid))["last_activity"]
    await asyncio.sleep(0.01)
    await store.touch(sid)
    after = (await store.get_metadata(sid))["last_activity"]

    assert after > before
