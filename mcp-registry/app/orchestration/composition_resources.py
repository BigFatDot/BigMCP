"""MCP resource handler for ``composition://executions/{id}`` (B-0 chunk 7).

Exposes composition executions as readable + subscribable MCP
resources. The URI scheme is:

    composition://executions/<uuid>

All operations are **per-user scoped** — a user can only list, read,
or subscribe to their own executions. Cross-user attempts return
empty results / 404 (no information leak about existence).

Three surface areas:

- :func:`list_user_execution_resources` — included in the gateway's
  ``resources/list`` response. Defaults to non-terminal statuses
  (running / suspended / queued) so the list stays usable on busy
  users; terminal rows are accessible via ``resources/read`` and
  the REST API.

- :func:`read_execution_resource` — backs ``resources/read``. Returns
  the JSON payload defined in
  :class:`schemas.composition_execution.ExecutionResourcePayload`.

- :class:`ExecutionSubscriptionTracker` — process-local map of
  ``(session_id → set[uri])``. Mutated by ``resources/subscribe``
  and ``resources/unsubscribe`` dispatchers. The executor's
  transition methods call :func:`notify_resource_updated` to push
  ``notifications/resources/updated`` to live subscribers; offline
  ones get queued in ``pending_notification`` (chunk #9).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from ..db import session as _db_session_module
from ..models.composition_execution import (
    CompositionExecution,
    ExecutionStatus,
    PendingNotification,
)

logger = logging.getLogger("orchestration.composition_resources")

EXECUTION_URI_PREFIX = "composition://executions/"

# Statuses that appear in resources/list by default. Terminal rows
# stay accessible via resources/read and the REST list endpoint;
# excluding them from the list keeps it bounded for users with long
# execution histories.
_LIST_DEFAULT_STATUSES = (
    ExecutionStatus.RUNNING.value,
    ExecutionStatus.SUSPENDED.value,
    ExecutionStatus.QUEUED.value,
)


# ---------------------------------------------------------------------------
# URI parsing
# ---------------------------------------------------------------------------


def parse_execution_uri(uri: str) -> Optional[UUID]:
    """Extract the execution UUID from ``composition://executions/<uuid>``.

    Returns None when the URI doesn't match the scheme or the UUID
    portion is malformed. Callers treat None as "not an execution
    resource" — let other URI schemes flow through untouched.
    """
    if not uri.startswith(EXECUTION_URI_PREFIX):
        return None
    raw = uri[len(EXECUTION_URI_PREFIX):]
    try:
        return UUID(raw)
    except (ValueError, AttributeError):
        return None


def execution_uri(execution_id: UUID) -> str:
    return f"{EXECUTION_URI_PREFIX}{execution_id}"


# ---------------------------------------------------------------------------
# List + Read
# ---------------------------------------------------------------------------


async def list_user_execution_resources(
    *,
    user_id: UUID,
    statuses: Optional[List[str]] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Resources for ``resources/list``, scoped to one user.

    Returns dicts in the MCP resource shape: ``{uri, name, description,
    mimeType, annotations}``. The ``annotations`` block carries
    ``status`` + ``trigger`` so a client can render badges without
    a follow-up ``resources/read``.
    """
    statuses = statuses or list(_LIST_DEFAULT_STATUSES)

    async with _db_session_module.AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(CompositionExecution)
                .options(selectinload(CompositionExecution.composition))
                .where(
                    CompositionExecution.user_id == user_id,
                    CompositionExecution.status.in_(statuses),
                )
                .order_by(CompositionExecution.updated_at.desc())
                .limit(limit)
            )
        ).scalars().all()

    out: List[Dict[str, Any]] = []
    for row in rows:
        comp_name = row.composition.name if row.composition else "(unknown)"
        out.append({
            "uri": execution_uri(row.id),
            "name": f"{comp_name} — {row.status}",
            "description": (
                f"Composition execution: {comp_name} "
                f"(status={row.status}, trigger={row.trigger})"
            ),
            "mimeType": "application/json",
            "annotations": {
                "status": row.status,
                "trigger": row.trigger,
                "started_at": row.started_at.isoformat()
                if row.started_at else None,
                "updated_at": row.updated_at.isoformat()
                if row.updated_at else None,
            },
        })
    return out


async def read_execution_resource(
    *,
    uri: str,
    user_id: UUID,
) -> Optional[Dict[str, Any]]:
    """Body of ``resources/read`` for ``composition://executions/{id}``.

    Returns ``None`` when:
    - The URI is not an execution URI (caller falls through to other
      schemes).
    - The execution doesn't exist OR belongs to a different user.

    The two cases are intentionally indistinguishable to the caller —
    no information leak about cross-user execution existence.

    On success, returns the standard MCP resource content envelope:
    ``{uri, mimeType, text}`` where text is the JSON-encoded
    :class:`ExecutionResourcePayload`.
    """
    execution_id = parse_execution_uri(uri)
    if execution_id is None:
        return None  # Not an execution URI — let caller try other schemes

    async with _db_session_module.AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(CompositionExecution).where(
                    CompositionExecution.id == execution_id,
                    CompositionExecution.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    if row is None:
        return None  # 404 / cross-user — same response

    state = row.state or {}
    payload = {
        "execution_id": str(row.id),
        "status": row.status,
        "current_step_id": state.get("current_step_id"),
        "step_results": state.get("step_results") or {},
        "step_status": state.get("step_status") or {},
        "suspension": state.get("suspension"),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "result": row.result,
        "error": row.error,
        # Stable URI clients can link to once the execution completes
        "result_uri": (
            execution_uri(row.id)
            if row.status == ExecutionStatus.COMPLETED.value
            else None
        ),
    }
    return {
        "uri": uri,
        "mimeType": "application/json",
        "text": json.dumps(payload, default=str),
    }


# ---------------------------------------------------------------------------
# Subscription tracker
# ---------------------------------------------------------------------------

# Type alias for the live notification dispatcher injected at
# lifespan startup. Receives ``(session_id, uri)`` and returns
# ``True`` if the notification was delivered to a live SSE queue,
# ``False`` otherwise — the False case triggers a pending_notification
# row insert so the next ``initialize`` from the same session_id
# can replay it (chunk #9).
LiveNotificationDispatcher = Callable[[str, str], Awaitable[bool]]
# Backwards-compatible alias retained in case external callers
# imported the old name.
NotificationDispatcher = LiveNotificationDispatcher


class ExecutionSubscriptionTracker:
    """Process-local map of MCP session → set of subscribed URIs.

    Single-instance for B-0 (see design doc §13). Multi-instance
    migration replaces the in-memory dict with a Redis pub/sub.
    """

    def __init__(self) -> None:
        # session_id → set of subscribed uris
        self._subs: Dict[str, Set[str]] = {}
        # uri → set of session_ids (reverse index, hot path on notify)
        self._reverse: Dict[str, Set[str]] = {}

    def subscribe(self, session_id: str, uri: str) -> None:
        self._subs.setdefault(session_id, set()).add(uri)
        self._reverse.setdefault(uri, set()).add(session_id)

    def unsubscribe(self, session_id: str, uri: str) -> bool:
        s = self._subs.get(session_id)
        if not s or uri not in s:
            return False
        s.discard(uri)
        if not s:
            self._subs.pop(session_id, None)
        rev = self._reverse.get(uri)
        if rev:
            rev.discard(session_id)
            if not rev:
                self._reverse.pop(uri, None)
        return True

    def drop_session(self, session_id: str) -> None:
        """Called when an SSE session disconnects — clean up."""
        uris = self._subs.pop(session_id, set())
        for uri in uris:
            rev = self._reverse.get(uri)
            if rev:
                rev.discard(session_id)
                if not rev:
                    self._reverse.pop(uri, None)

    def sessions_for_uri(self, uri: str) -> Set[str]:
        """All session_ids currently subscribed to this URI."""
        return set(self._reverse.get(uri, ()))

    def uris_for_session(self, session_id: str) -> Set[str]:
        return set(self._subs.get(session_id, ()))


# Singleton accessor + reset helper (the latter only for tests).
_tracker_singleton: Optional[ExecutionSubscriptionTracker] = None


def get_subscription_tracker() -> ExecutionSubscriptionTracker:
    global _tracker_singleton
    if _tracker_singleton is None:
        _tracker_singleton = ExecutionSubscriptionTracker()
    return _tracker_singleton


def _reset_subscription_tracker_for_tests() -> None:
    global _tracker_singleton
    _tracker_singleton = None


# ---------------------------------------------------------------------------
# Notify on state transition
# ---------------------------------------------------------------------------


async def notify_resource_updated(
    execution_id: UUID,
    *,
    live_pusher: Optional[LiveNotificationDispatcher] = None,
) -> None:
    """Fire ``notifications/resources/updated`` for one execution.

    Walks the parent chain so subscribers of an ancestor that's
    suspended waiting on this child also get a notification (sub-
    composition propagation, design doc §6.3).

    For each subscribed session, calls ``live_pusher(session_id, uri)``;
    if it returns ``False`` (offline / unreachable on this process),
    persists a ``pending_notification`` row keyed on the same
    ``(session_id, uri)`` so the next ``initialize`` from that session
    replays it (chunk #9).

    Best-effort — neither live push nor queue persistence raises out
    of this function; failures are logged.
    """
    tracker = get_subscription_tracker()

    # Build the URI chain: this execution + any suspended ancestor
    # waiting on a descendant in this chain.
    uris_to_fire: List[str] = []
    visited: Set[UUID] = set()
    current_id: Optional[UUID] = execution_id

    async with _db_session_module.AsyncSessionLocal() as db:
        for _ in range(10):  # bound by MAX_SUBCOMPOSITION_DEPTH * 2 safety
            if current_id is None or current_id in visited:
                break
            visited.add(current_id)
            uris_to_fire.append(execution_uri(current_id))

            row = (
                await db.execute(
                    select(
                        CompositionExecution.parent_execution_id,
                        CompositionExecution.status,
                    ).where(CompositionExecution.id == current_id)
                )
            ).first()
            if row is None:
                break
            parent_id = row[0]
            if parent_id is None:
                break
            # Only walk up to a parent that is actually suspended on a
            # subcomposition pointing at us — otherwise the ancestor
            # has no business getting our notification.
            parent_row = (
                await db.execute(
                    select(
                        CompositionExecution.status,
                        CompositionExecution.state,
                    ).where(CompositionExecution.id == parent_id)
                )
            ).first()
            if parent_row is None:
                break
            parent_status, parent_state = parent_row
            if parent_status != ExecutionStatus.SUSPENDED.value:
                break
            suspension = (parent_state or {}).get("suspension") or {}
            if suspension.get("reason") != "subcomposition":
                break
            expected_child = (suspension.get("payload") or {}).get(
                "child_execution_id"
            )
            if expected_child and str(expected_child) != str(current_id):
                break
            current_id = parent_id

    # For each URI in the chain, deliver per subscribed session.
    # Collect failed pushes so we persist them in one DB session.
    pending_inserts: List[tuple[str, str]] = []
    for uri in uris_to_fire:
        sessions = tracker.sessions_for_uri(uri)
        for session_id in sessions:
            delivered = False
            if live_pusher is not None:
                try:
                    delivered = bool(await live_pusher(session_id, uri))
                except Exception:  # noqa: BLE001
                    logger.warning(
                        f"live notify failed for session {session_id} "
                        f"uri {uri}",
                        exc_info=True,
                    )
            if not delivered:
                pending_inserts.append((session_id, uri))

    if pending_inserts:
        await _persist_pending_notifications(pending_inserts)


async def _persist_pending_notifications(
    rows: List[tuple[str, str]],
) -> None:
    """Insert one ``pending_notification`` row per ``(session_id, uri)``.

    Best-effort — wraps any DB error in a warning. Duplicates are OK:
    the flush path replays in created_at order and deletes by primary
    key, so if a session legitimately connects between two transitions
    it receives both notifications. The model doesn't enforce a
    composite UNIQUE on ``(session_id, uri)`` and we don't dedup here
    either.
    """
    try:
        now = datetime.utcnow()
        async with _db_session_module.AsyncSessionLocal() as db:
            for session_id, uri in rows:
                db.add(
                    PendingNotification(
                        id=uuid4(),
                        session_id=session_id,
                        uri=uri,
                        method="notifications/resources/updated",
                        created_at=now,
                    )
                )
            await db.commit()
    except Exception:  # noqa: BLE001
        logger.warning(
            f"failed to persist pending notifications ({len(rows)} rows)",
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Pending notification flush (B-0 chunk 9)
# ---------------------------------------------------------------------------


async def flush_pending_notifications(
    session_id: str,
    *,
    live_pusher: Optional[LiveNotificationDispatcher] = None,
    max_age_days: int = 7,
) -> int:
    """Replay queued notifications for ``session_id`` then delete them.

    Called by the gateway right after a successful ``initialize``
    response is sent for ``session_id``. Returns the count of rows
    drained from the queue (replayed + dropped-as-stale).

    - Reads in ``created_at`` order so the client sees them in the
      same sequence the executor fired them.
    - Pushes each via ``live_pusher`` (typically the gateway's
      broadcast helper). If the push reports ``False`` (still
      unreachable) we leave the row in place so the NEXT initialize
      gets another shot.
    - Drops rows older than ``max_age_days`` regardless — they are
      stale per the design doc retention policy.
    """
    if not session_id:
        return 0

    async with _db_session_module.AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(PendingNotification)
                .where(PendingNotification.session_id == session_id)
                .order_by(PendingNotification.created_at.asc())
            )
        ).scalars().all()

        if not rows:
            return 0

        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        delivered_ids: List[UUID] = []
        stale_ids: List[UUID] = []

        for row in rows:
            if row.created_at < cutoff:
                stale_ids.append(row.id)
                continue
            if live_pusher is None:
                # No pusher wired — drop after counting (we counted)
                # rather than spinning the row forever.
                stale_ids.append(row.id)
                continue
            try:
                ok = bool(await live_pusher(session_id, row.uri))
            except Exception:  # noqa: BLE001
                logger.warning(
                    f"flush push failed for session {session_id} uri {row.uri}",
                    exc_info=True,
                )
                ok = False
            if ok:
                delivered_ids.append(row.id)
            # If still unreachable: leave the row untouched so a later
            # flush retries it.

        ids_to_delete = delivered_ids + stale_ids
        if ids_to_delete:
            await db.execute(
                delete(PendingNotification).where(
                    PendingNotification.id.in_(ids_to_delete)
                )
            )
            await db.commit()

        return len(ids_to_delete)
