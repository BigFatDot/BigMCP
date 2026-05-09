"""
Hybrid session store for MCP sessions.

Why this exists
---------------
`mcp_unified.py` historically kept `mcp_sessions: Dict[str, Dict[str, Any]]`
as a module-level Python dict. That dict is reset on every backend restart,
so every code redeploy invalidates every active SSE session. Some clients
(Claude Desktop, Cursor, ...) reconnect SSE without redoing `initialize`
and end up with a stale tool list.

What this provides
------------------
A drop-in replacement that splits the old session shape into two halves:

  * **Metadata** (user_id, organization_id, api_key_id, tool_group_id,
    user_email, created_at, last_activity, ...) — JSON-serializable —
    persisted in Redis through the existing `CacheBackend` abstraction
    with a TTL aligned to SESSION_TIMEOUT_SECONDS. Survives restarts.

  * **`message_queue`** — `asyncio.Queue` instance — NOT persisted.
    Queues are inherently per-process (the SSE event_generator awaits
    them locally) so we keep an in-memory dict keyed by `session_id`.
    Recreated on demand when an SSE client reconnects.

Behaviour after a backend restart
---------------------------------
1. Process boot: in-memory `_local_queues` is empty.
2. Client reconnects SSE with the same `Mcp-Session-Id`.
3. We look up the metadata in Redis → found → we recreate a fresh
   `asyncio.Queue` locally and reattach it to the metadata.
4. The client never had to redo `initialize`. The next pool mutation
   pushes its `notifications/tools/list_changed` into the freshly-bound
   queue, and the SSE event_generator drains it normally.

Limitation (out of scope)
-------------------------
Horizontal scaling: if BigMCP runs more than one backend process, queues
created in process A are unreachable from process B. Notifications would
need a Redis Pub/Sub fan-out. Today the production deployment runs a
single backend container, so this is acceptable; revisit when we scale.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from ..core.cache_backend import get_cache_backend

logger = logging.getLogger(__name__)


_SESSION_KEY_PREFIX = "mcp_session:"
_ORG_INDEX_PREFIX = "mcp_session_index_org:"
_USER_INDEX_PREFIX = "mcp_session_index_user:"


def _serialise(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Strip non-serialisable fields and stringify UUIDs."""
    out: Dict[str, Any] = {}
    for k, v in metadata.items():
        if k == "message_queue":
            continue
        if isinstance(v, UUID):
            out[k] = str(v)
        else:
            out[k] = v
    return out


class MCPSessionStore:
    """Hybrid Redis-backed metadata store + in-process queue registry.

    The instance is module-level (see the singleton at the bottom). Tests
    can construct their own to swap the backend.
    """

    def __init__(self, ttl_seconds: int = 600) -> None:
        self._ttl = ttl_seconds
        # Per-process queues. Ephemeral by design — each process maintains
        # its own. The metadata in Redis is the source of truth for
        # "session exists / who it belongs to".
        self._queues: Dict[str, asyncio.Queue] = {}

    # -- Backend access (lazy so tests can swap before first call) -------

    def _backend(self):
        return get_cache_backend()

    # -- Key helpers -----------------------------------------------------

    @staticmethod
    def _meta_key(sid: str) -> str:
        return f"{_SESSION_KEY_PREFIX}{sid}"

    @staticmethod
    def _org_index_key(org_id: str) -> str:
        return f"{_ORG_INDEX_PREFIX}{org_id}"

    @staticmethod
    def _user_index_key(user_id: str) -> str:
        return f"{_USER_INDEX_PREFIX}{user_id}"

    # -- Index maintenance -----------------------------------------------

    async def _index_add(self, key: str, sid: str) -> None:
        backend = self._backend()
        existing = (await backend.get(key)) or []
        if sid not in existing:
            existing.append(sid)
        await backend.set(key, existing, ttl=self._ttl)

    async def _index_remove(self, key: str, sid: str) -> None:
        backend = self._backend()
        existing = (await backend.get(key)) or []
        if sid in existing:
            existing = [s for s in existing if s != sid]
            await backend.set(key, existing, ttl=self._ttl)

    # -- Public API ------------------------------------------------------

    async def create(self, sid: str, metadata: Dict[str, Any]) -> asyncio.Queue:
        """Persist metadata in Redis and return a fresh local queue.

        The queue is bound to this process; it is NOT persisted.
        """
        clean = _serialise(metadata)
        clean.setdefault("created_at", time.time())
        clean["last_activity"] = time.time()

        backend = self._backend()
        await backend.set(self._meta_key(sid), clean, ttl=self._ttl)

        org_id = clean.get("organization_id")
        if org_id:
            await self._index_add(self._org_index_key(str(org_id)), sid)

        user_id = clean.get("user_id")
        if user_id:
            await self._index_add(self._user_index_key(str(user_id)), sid)

        q: asyncio.Queue = asyncio.Queue()
        self._queues[sid] = q
        logger.debug(f"session_store: created session {sid[:8]}... org={str(org_id)[:8]}...")
        return q

    async def get(self, sid: str) -> Optional[Dict[str, Any]]:
        """Return the session metadata + an attached local queue.

        If the metadata exists in Redis but no queue exists in this
        process (e.g. after a restart and SSE reconnect), one is created
        on the fly so the caller can resume operations transparently.

        Returns None if the session has expired or never existed.
        """
        meta = await self._backend().get(self._meta_key(sid))
        if meta is None:
            return None
        if sid not in self._queues:
            self._queues[sid] = asyncio.Queue()
        # Attach the live queue so callers can `.put(...)` / `.get(...)`
        meta = dict(meta)
        meta["message_queue"] = self._queues[sid]
        return meta

    async def get_metadata(self, sid: str) -> Optional[Dict[str, Any]]:
        """Same as `get` but without binding a queue."""
        return await self._backend().get(self._meta_key(sid))

    async def delete(self, sid: str) -> None:
        """Forget the session in Redis and locally."""
        meta = await self.get_metadata(sid)
        if meta:
            org_id = meta.get("organization_id")
            if org_id:
                await self._index_remove(self._org_index_key(str(org_id)), sid)
            user_id = meta.get("user_id")
            if user_id:
                await self._index_remove(self._user_index_key(str(user_id)), sid)
        await self._backend().delete(self._meta_key(sid))
        self._queues.pop(sid, None)
        logger.debug(f"session_store: deleted session {sid[:8]}...")

    async def touch(self, sid: str) -> None:
        """Refresh `last_activity` and reset TTL on the metadata."""
        backend = self._backend()
        meta = await backend.get(self._meta_key(sid))
        if not meta:
            return
        meta["last_activity"] = time.time()
        await backend.set(self._meta_key(sid), meta, ttl=self._ttl)

    async def list_for_org(self, org_id: str) -> List[str]:
        """Return SIDs registered for the given org (may include expired)."""
        return (await self._backend().get(self._org_index_key(org_id))) or []

    async def list_for_user(self, user_id: str) -> List[str]:
        return (await self._backend().get(self._user_index_key(user_id))) or []

    def get_local_queue(self, sid: str) -> Optional[asyncio.Queue]:
        """Return the in-process queue for a session if one exists.

        Used by `notify_*` to push notifications into the live SSE
        stream. Returns None if the session is registered in Redis but
        was created by another process (multi-instance scenario).
        """
        return self._queues.get(sid)

    def has_local_queue(self, sid: str) -> bool:
        return sid in self._queues

    def local_count(self) -> int:
        return len(self._queues)

    def iter_local(self) -> List[tuple[str, asyncio.Queue]]:
        """Return (sid, queue) for every session served by this process."""
        return list(self._queues.items())

    async def attach_local_queue(self, sid: str) -> Optional[asyncio.Queue]:
        """Bind a fresh in-memory queue to a session that exists in Redis.

        Used by the SSE endpoint when a client reconnects with the same
        Mcp-Session-Id header after a backend restart: the metadata is
        still in Redis but the queue is gone. Returns the new queue, or
        None if the session is unknown / expired.
        """
        meta = await self._backend().get(self._meta_key(sid))
        if meta is None:
            return None
        if sid not in self._queues:
            self._queues[sid] = asyncio.Queue()
        # Refresh activity + TTL while we are here.
        meta["last_activity"] = time.time()
        await self._backend().set(self._meta_key(sid), meta, ttl=self._ttl)
        return self._queues[sid]

    # -- Iteration helpers used by `notify_org_tools_changed` -----------

    async def iter_local_sessions_for_org(
        self, org_id: str, user_id: Optional[str] = None
    ) -> List[tuple[str, Dict[str, Any]]]:
        """Return (sid, metadata) for live local sessions matching the
        org (and optionally a specific user). Skips sessions whose queue
        lives in another process — they will pick up changes via the
        background refresh once they reconnect.
        """
        out: List[tuple[str, Dict[str, Any]]] = []
        sids = await self.list_for_org(org_id)
        if user_id:
            user_sids = set(await self.list_for_user(user_id))
            sids = [s for s in sids if s in user_sids]
        for sid in sids:
            if sid not in self._queues:
                continue
            meta = await self.get_metadata(sid)
            if meta is None:
                # TTL expired — drop the local queue too
                self._queues.pop(sid, None)
                continue
            out.append((sid, meta))
        return out


# -- Module-level singleton ----------------------------------------------

_store: Optional[MCPSessionStore] = None


def get_session_store() -> MCPSessionStore:
    global _store
    if _store is None:
        _store = MCPSessionStore()
    return _store


def reset_session_store_for_tests() -> None:
    """Wipe the singleton — tests only."""
    global _store
    _store = None
