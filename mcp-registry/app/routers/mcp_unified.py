"""
MCP Unified Router - Production-Ready Implementation
====================================================

Implements Model Context Protocol 2025-03-26 specification
(Streamable HTTP transport) with full MCP compliance.

Features:
- Streamable HTTP: POST / handles all client→server JSON-RPC messages
- SSE stream: GET /mcp/sse (and GET / proxy) for server→client notifications
- Session termination: DELETE / closes named sessions
- Tool aggregation from multiple MCP servers with OAuth visibility filter
- Orchestration tools (meta-level), resource management (compositions)
- Session management with keepalive and org-level cache invalidation
- MCP notifications: tools/list_changed, resources/list_changed
- Cursor-based pagination for tools/list
- Ping handler ({"result": {}})
- Client notifications (notifications/initialized, etc.) → HTTP 202
"""

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Dict, Any, List, Optional, AsyncGenerator
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Request, Response, Depends, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse
from starlette.requests import ClientDisconnect

from ..dependencies import get_registry
from ..api.models import ToolInfo, ServerInfo
from ..api.dependencies import get_current_user_api_key, get_current_user, get_current_user_optional, _resolve_organization
from ..orchestration.tools import OrchestrationTools
from ..core.user_server_pool import UserServerPool
from ..services.mcp_session_store import get_session_store

# Import utilities from modular structure
from .mcp_gateway.utils import (
    parse_json_string_arguments,
    _parse_json_value,
    _error_response,
    _normalize_parameters,
)
from .mcp_gateway.orchestration import get_orchestration_tools
from .mcp_gateway.pool import (
    handle_composition_status,
    handle_describe_tool,
    POOL_TOOL_NAMES,
    get_pool_tools,
    handle_execute,
    handle_search,
)

# Configure logging
logger = logging.getLogger("mcp_unified")

# Create router
router = APIRouter(
    prefix="/mcp",
    tags=["MCP Unified Gateway"]
)

# Get the shared registry instance
registry = get_registry()

# Session management.
#
# Sessions are now stored in the hybrid `MCPSessionStore` (Redis-backed
# metadata + per-process asyncio.Queue). The `mcp_sessions` symbol was
# removed: every read/write goes through `get_session_store()`. Metadata
# survives backend restarts; queues are recreated on demand when an SSE
# client reconnects with the same `Mcp-Session-Id`. See
# `app/services/mcp_session_store.py` for the rationale.
SESSION_TIMEOUT_SECONDS = 600  # 10 minutes
KEEPALIVE_INTERVAL_SECONDS = 30

# Pending notifications for Streamable HTTP POST clients (no persistent SSE session).
# Maps org_id_str → True when tools changed. Drained on next authenticated POST
# response when client sends Accept: text/event-stream (MCP 2025-03-26 §6.3.2).
pending_org_notifications: Dict[str, bool] = {}

# Track recently active users per org (last tools/list request timestamp).
# Used by notify_org_tools_changed to trigger background refresh even for users
# without an active SSE session (e.g. Claude Desktop, which closes SSE after init).
# Maps org_id_str → { user_id_str → unix timestamp }
org_active_users: Dict[str, Dict[str, float]] = {}
ORG_ACTIVE_USER_TTL_SECONDS = 600  # 10 minutes — matches SESSION_TIMEOUT_SECONDS

# Protocol version
MCP_PROTOCOL_VERSION = "2025-06-18"


async def push_resource_updated_to_session(session_id: str, uri: str) -> bool:
    """Send ``notifications/resources/updated`` to one MCP session.

    Returns ``True`` if the notification was delivered to a live SSE
    queue (or queued in-memory for the local SSE pump), ``False``
    when the session is not connected on this process. Callers are
    expected to enqueue a row in ``pending_notification`` on False
    so a future ``initialize`` from the same session_id can replay it.

    B-0 ships single-instance, so "no local queue" effectively means
    "session is offline". Multi-instance (B-1+) will redirect via
    Redis pub/sub before falling back to the persisted queue.
    """
    notification = {
        "jsonrpc": "2.0",
        "method": "notifications/resources/updated",
        "params": {"uri": uri},
    }
    store = get_session_store()
    queue = store.get_local_queue(session_id)
    if queue is None:
        logger.debug(
            f"resources/updated: session {session_id} not local "
            f"(uri={uri}) — caller should persist to pending_notification"
        )
        return False
    try:
        await queue.put({
            "event": "message",
            "data": json.dumps(notification),
        })
        logger.info(
            f"Queued resources/updated for session {session_id} uri={uri}"
        )
        return True
    except Exception:  # noqa: BLE001
        logger.warning(
            f"Failed to push resources/updated to session {session_id}",
            exc_info=True,
        )
        return False


async def broadcast_tools_changed():
    """
    Broadcast tools/list_changed notification to all active SSE sessions
    served by THIS process. MCP 2025-06-18 compliant notification.

    This allows clients to automatically refresh their tools list when
    tools become available (e.g., after server initialization).
    """
    notification = {
        "jsonrpc": "2.0",
        "method": "notifications/tools/list_changed"
    }

    store = get_session_store()
    local_sessions = store.iter_local()
    if not local_sessions:
        logger.debug("No active SSE sessions to notify")
        return

    for session_id, queue in local_sessions:
        try:
            await queue.put({
                "event": "message",
                "data": json.dumps(notification)
            })
            logger.info(f"Queued tools_changed notification for session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to queue notification for {session_id}: {e}")

    logger.info(f"Broadcasted tools/list_changed to {len(local_sessions)} sessions")


async def broadcast_tools_changed_for_user(user_id) -> int:
    """
    Broadcast tools/list_changed notification to SSE sessions of a specific user.

    Unlike broadcast_tools_changed() which notifies ALL sessions, this function
    targets only the sessions belonging to the given user. Used after background
    server startup to notify the user that fresh tools are available.

    Args:
        user_id: User UUID (or string) to target

    Returns:
        Number of sessions notified
    """
    notification = {
        "jsonrpc": "2.0",
        "method": "notifications/tools/list_changed"
    }

    user_id_str = str(user_id)
    notified = 0

    store = get_session_store()
    sids = await store.list_for_user(user_id_str)

    for session_id in sids:
        queue = store.get_local_queue(session_id)
        if queue is None:
            # Session lives in Redis but queue is bound to another process.
            continue
        try:
            await queue.put({
                "event": "message",
                "data": json.dumps(notification)
            })
            notified += 1
            logger.info(f"Queued tools_changed for user {user_id_str} session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to notify session {session_id}: {e}")

    if notified:
        logger.info(f"Sent tools/list_changed to {notified} session(s) for user {user_id_str}")
    else:
        logger.debug(f"No active SSE sessions for user {user_id_str}")

    return notified


async def notify_org_tools_changed(org_id, user_id=None) -> int:
    """
    Notify connected MCP clients that the tool list has changed.

    Spec-compliant flow (MCP 2025-06-18):
      1. Invalidate the org-scoped tool cache.
      2. Push `notifications/tools/list_changed` into every matching session's
         outbound queue. The client receives the notification through its
         existing SSE stream and reissues `tools/list` per the protocol.
      3. Schedule a background refresh so freshly-arriving SSE consumers
         (e.g. a client that just reconnected) get up-to-date data.

    The previous implementation **deleted** the SSE sessions to force a hard
    re-initialization. That worked for Claude Desktop (it always re-inits on
    drop) but broke clients that reconnect SSE without redoing `tools/list`,
    so they kept showing the stale catalog.

    Set `MCP_KILL_SESSION_ON_TOOLS_CHANGED=true` to revert to the legacy
    hard-kill behaviour as an emergency fallback.

    Args:
        org_id: Organization UUID (or string) whose tools changed
        user_id: Optional user UUID — if provided, target only that user.
                 If None, target every session in the org.

    Returns:
        Number of SSE sessions notified (or closed in legacy mode).
    """
    import os
    from uuid import UUID

    org_id_str = str(org_id)
    org_uuid = org_id if isinstance(org_id, UUID) else UUID(org_id_str)
    user_id_str = str(user_id) if user_id else None

    legacy_kill = os.environ.get("MCP_KILL_SESSION_ON_TOOLS_CHANGED", "false").lower() == "true"

    # Step 1: Invalidate cache
    try:
        from ..services.user_tool_cache import get_user_tool_cache
        tool_cache = get_user_tool_cache()
        if user_id:
            await tool_cache.invalidate(UUID(user_id_str))
            logger.info(f"notify_org_tools_changed: invalidated cache for user {user_id_str}")
        else:
            invalidated = await tool_cache.invalidate_organization(org_uuid)
            if invalidated:
                logger.info(
                    f"notify_org_tools_changed: invalidated cache for {invalidated} "
                    f"user(s) in org {org_id_str}"
                )
    except Exception as e:
        logger.warning(f"notify_org_tools_changed: cache invalidation failed: {e}")

    # Step 2: Push the standard `notifications/tools/list_changed` envelope
    # into every matching session's queue. The SSE event_generator drains
    # the queue and forwards the notification on the live stream.
    notification = {
        "jsonrpc": "2.0",
        "method": "notifications/tools/list_changed",
    }

    matched_sessions: list[str] = []
    closed_sessions: list[str] = []

    store = get_session_store()
    local_matches = await store.iter_local_sessions_for_org(org_id_str, user_id_str)

    for session_id, _meta in local_matches:
        matched_sessions.append(session_id)

        if legacy_kill:
            await store.delete(session_id)
            closed_sessions.append(session_id)
            continue

        queue = store.get_local_queue(session_id)
        if queue is None:
            continue
        try:
            await queue.put(
                {"event": "message", "data": json.dumps(notification)}
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"notify_org_tools_changed: failed to enqueue notification "
                f"for {session_id}: {e}"
            )

    scope = f"user {user_id_str}" if user_id_str else f"org {org_id_str}"
    if legacy_kill:
        if closed_sessions:
            logger.info(
                f"notify_org_tools_changed[legacy_kill]: closed {len(closed_sessions)} "
                f"SSE session(s) for {scope}"
            )
        else:
            logger.debug(f"notify_org_tools_changed[legacy_kill]: no SSE sessions for {scope}")
    else:
        if matched_sessions:
            logger.info(
                f"notify_org_tools_changed: queued tools/list_changed on "
                f"{len(matched_sessions)} SSE session(s) for {scope}"
            )
        else:
            logger.debug(
                f"notify_org_tools_changed: no active SSE sessions for {scope} — "
                "background refresh will warm cache for next reconnect"
            )

    # Step 3: Schedule background refresh to warm cache + notify new SSE sessions.
    # Claude Desktop sometimes just reopens SSE without re-initializing (no tools/list).
    # The background refresh detects the tool change, updates the cache, and sends
    # tools/list_changed to any newly created SSE sessions.
    target_user_ids = set()
    if user_id:
        target_user_ids.add(UUID(user_id_str))
    else:
        # Collect all users registered in Redis for the org, plus the
        # `org_active_users` snapshot of recently-active POST clients
        # (Claude Desktop, etc.) that have no live SSE session.
        org_sids = await store.list_for_org(org_id_str)
        for sid in org_sids:
            meta = await store.get_metadata(sid)
            if not meta:
                continue
            uid = meta.get("user_id")
            if uid:
                try:
                    target_user_ids.add(uid if isinstance(uid, UUID) else UUID(str(uid)))
                except Exception:
                    pass
        cutoff = time.time() - ORG_ACTIVE_USER_TTL_SECONDS
        for uid_str, last_active in list(org_active_users.get(org_id_str, {}).items()):
            if last_active >= cutoff:
                try:
                    target_user_ids.add(UUID(uid_str))
                except Exception:
                    pass

    for user_uuid in target_user_ids:
        asyncio.create_task(
            gateway._background_refresh_tools(user_uuid=user_uuid, org_uuid=org_uuid)
        )

    if target_user_ids:
        logger.info(
            f"notify_org_tools_changed: scheduled background refresh for "
            f"{len(target_user_ids)} user(s) in {scope}"
        )

    # In default mode the function returns the count of sessions that
    # received the notification; in legacy_kill mode it returns the number
    # of sessions closed. Callers only use this for log dedup.
    return len(closed_sessions) if legacy_kill else len(matched_sessions)


async def broadcast_resources_changed(org_id=None) -> int:
    """
    Broadcast notifications/resources/list_changed to connected MCP SSE clients.

    Compositions are org-scoped, so the notification targets all sessions
    belonging to the given organization. If org_id is None, all sessions
    are notified (global broadcast).

    MCP 2025-03-26 compliant — fixes the false `resources.listChanged: true`
    capability declaration in initialize().

    Returns:
        Number of SSE sessions notified
    """
    notification = {
        "jsonrpc": "2.0",
        "method": "notifications/resources/list_changed"
    }
    org_id_str = str(org_id) if org_id is not None else None
    notified = 0

    store = get_session_store()

    if org_id_str is None:
        # Global broadcast — every locally-served queue.
        targets = store.iter_local()
    else:
        # Org-scoped — locally-served sessions for that org only.
        scoped = await store.iter_local_sessions_for_org(org_id_str, None)
        targets = [
            (sid, store.get_local_queue(sid))
            for sid, _ in scoped
            if store.get_local_queue(sid) is not None
        ]

    for session_id, queue in targets:
        try:
            await queue.put({
                "event": "message",
                "data": json.dumps(notification)
            })
            notified += 1
        except Exception as e:
            logger.warning(f"Failed to queue resources_changed for session {session_id}: {e}")

    if notified:
        logger.info(f"Broadcasted notifications/resources/list_changed to {notified} session(s)"
                    + (f" in org {org_id_str}" if org_id_str else " (global)"))
    else:
        logger.debug("No active SSE sessions to receive resources/list_changed notification")

    return notified


# NOTE: parse_json_string_arguments, _parse_json_value, _error_response, _normalize_parameters
# have been extracted to mcp_gateway/utils.py and are imported above.


async def _log_tool_call_async(
    *,
    user_id: str,
    organization_id: str,
    session_id: Optional[str],
    tool_name: str,
    duration_ms: int,
    status: str,
    composition_id: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Phase 5: persist a single tool call to ``execution_log``.

    Fire-and-forget — never raises. Used to compute pin suggestions and
    the per-user 30-day preheat overlay over the same ``execution_log``
    table the ``execute`` MCP tool already writes to.
    """
    try:
        from uuid import UUID as _UUID
        from sqlalchemy.exc import SQLAlchemyError
        from ..db.session import AsyncSessionLocal as _Sess
        from ..models.execution_log import ExecutionLog as _ExecLog

        async with _Sess() as db:
            try:
                row = _ExecLog(
                    user_id=_UUID(str(user_id)),
                    organization_id=_UUID(str(organization_id)),
                    session_id=session_id,
                    goal=None,
                    mode="tool_call",
                    shortcut_level=None,
                    duration_ms=duration_ms,
                    status=status,
                    error=error,
                    composition_id=(
                        _UUID(str(composition_id)) if composition_id else None
                    ),
                    tools_called=[tool_name],
                )
                db.add(row)
                await db.commit()
            except SQLAlchemyError as _err:
                logger.warning(f"tool_call execution_log insert failed: {_err}")
                await db.rollback()
    except Exception as _err:  # noqa: BLE001
        logger.debug(f"tool_call execution_log fire-and-forget failed: {_err}")


class MCPUnifiedGateway:
    """
    Unified MCP Gateway implementing complete protocol.

    Handles:
    - Tool discovery and aggregation
    - Tool execution with routing
    - Orchestration capabilities
    - Resource management
    - Session lifecycle
    """

    def __init__(self):
        self.registry = registry
        self.session_store = get_session_store()
        self.orchestration_tools = OrchestrationTools(registry)
        from ..core.config import settings as core_settings
        self.user_server_pool = UserServerPool(
            cleanup_timeout_minutes=core_settings.POOL_CLEANUP_TIMEOUT_MINUTES,
            cleanup_interval_seconds=core_settings.POOL_CLEANUP_INTERVAL_SECONDS,
            max_servers_per_user=core_settings.POOL_MAX_SERVERS_PER_USER,
            max_total_servers=core_settings.POOL_MAX_TOTAL_SERVERS
        )
        # Lock per user to prevent concurrent background refresh tasks
        # Avoids asyncpg connection race conditions when multiple requests
        # trigger background refreshes for the same user simultaneously
        self._user_refresh_locks: Dict[UUID, asyncio.Lock] = {}
        logger.info("MCPUnifiedGateway initialized with UserServerPool")

    async def initialize(self, request_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle initialization request.

        Returns server capabilities and information.
        """
        client_info = params.get("clientInfo", {})
        logger.info(f"Client connecting: {client_info.get('name', 'unknown')}")

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {
                        "listChanged": True  # Dynamic tool list
                    },
                    "resources": {
                        "subscribe": True,
                        "listChanged": True
                    },
                    "prompts": {
                        "listChanged": False  # Static prompts
                    }
                },
                "serverInfo": {
                    "name": "BigMCP",
                    "version": "1.0.0",
                    "description": "Your unified AI tooling platform - Orchestrate MCP tools with intelligence",
                    "icons": [
                        {
                            "src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 64 64'%3E%3Ccircle cx='32' cy='32' r='28' fill='%23D97757'/%3E%3Ccircle cx='32' cy='4' r='3.5' fill='%23fff'/%3E%3Ccircle cx='46' cy='7.75' r='3.5' fill='%23fff'/%3E%3Ccircle cx='56.25' cy='18' r='3.5' fill='%23fff'/%3E%3Ccircle cx='60' cy='32' r='3.5' fill='%23fff'/%3E%3Ccircle cx='56.25' cy='46' r='3.5' fill='%23fff'/%3E%3Ccircle cx='46' cy='56.25' r='3.5' fill='%23fff'/%3E%3Ccircle cx='32' cy='60' r='3.5' fill='%23fff'/%3E%3Ccircle cx='18' cy='56.25' r='3.5' fill='%23fff'/%3E%3Ccircle cx='7.75' cy='46' r='3.5' fill='%23fff'/%3E%3Ccircle cx='4' cy='32' r='3.5' fill='%23fff'/%3E%3Ccircle cx='7.75' cy='18' r='3.5' fill='%23fff'/%3E%3Ccircle cx='18' cy='7.75' r='3.5' fill='%23fff'/%3E%3C/svg%3E",
                            "mimeType": "image/svg+xml"
                        }
                    ]
                },
                "instructions": (
                    "BigMCP aggregates every MCP server the user has connected "
                    "behind a single gateway, with two meta-tools that drive the "
                    "whole flow:\n"
                    "\n"
                    "  • `search(query, mode=append|replace, limit=10)` — load tools "
                    "    relevant to your task into the active session pool. The pool "
                    "    starts EMPTY at every session; call `search` first before "
                    "    `execute` (or before relying on tool/list).\n"
                    "  • `execute(goal | tool_name | composition_id [, params])` — "
                    "    run something. Goal mode orchestrates via LLM; tool_name and "
                    "    composition_id are direct, zero-LLM invocations.\n"
                    "\n"
                    "Saved compositions appear in tools/list as `composition_<name>` "
                    "and are always available — no need to `search` for them.\n"
                    "\n"
                    "Workflow: `search(\"what you want to do\")` → optionally inspect "
                    "the loaded tools via tools/list (a list_changed notification is "
                    "emitted) → `execute(goal=\"...\")` (or call any tool directly). "
                    "If `execute` reports an empty pool, run `search` first."
                )
            }
        }

    # =========================================================================
    # Tool Group & User Management
    # =========================================================================

    async def _get_user_configured_servers(
        self,
        user_id: UUID,
        organization_id: UUID
    ) -> List[UUID]:
        """
        Get list of MCP servers configured for this user/organization.

        Checks:
        - User-level credentials (UserCredential)
        - Organization-level credentials (OrganizationCredential)
        - Enabled MCPServer entries for the organization (for servers without credentials)

        Args:
            user_id: User UUID
            organization_id: Organization UUID

        Returns:
            List of server UUIDs that should be auto-started
        """
        from ..db.database import get_async_session
        from sqlalchemy import select, or_
        from ..models.user_credential import UserCredential, OrganizationCredential
        from ..models.mcp_server import MCPServer
        from ..models.organization import OrganizationMember, UserRole

        try:
            # Get database session
            async for db in get_async_session():
                # Resolve the caller's role in this org for the
                # MCPServer.allowed_roles RBAC filter (N2.3). If they
                # have no membership, treat them as VIEWER for the
                # filter (the most restrictive role).
                role_result = await db.execute(
                    select(OrganizationMember.role).where(
                        OrganizationMember.user_id == user_id,
                        OrganizationMember.organization_id == organization_id,
                    )
                )
                role_row = role_result.scalar_one_or_none()
                user_role_str = (
                    role_row.value if hasattr(role_row, "value") else str(role_row)
                ) if role_row else UserRole.VIEWER.value

                def _role_allowed(allowed_roles: list[str] | None) -> bool:
                    """Apply the same convention as Composition.allowed_roles.

                    - empty list  -> all roles except VIEWER
                    - non-empty   -> user role must appear (case-insensitive)
                    """
                    if not allowed_roles:
                        return user_role_str != UserRole.VIEWER.value
                    lowered = {r.lower() for r in allowed_roles}
                    return user_role_str.lower() in lowered

                # Query user credentials
                user_creds_query = select(UserCredential.server_id).where(
                    UserCredential.user_id == user_id,
                    UserCredential.is_active == True
                )
                user_creds_result = await db.execute(user_creds_query)
                user_server_ids = set(row[0] for row in user_creds_result.fetchall())

                # Query organization credentials
                org_creds_query = select(OrganizationCredential.server_id).where(
                    OrganizationCredential.organization_id == organization_id,
                    OrganizationCredential.is_active == True
                )
                org_creds_result = await db.execute(org_creds_query)
                org_server_ids = set(row[0] for row in org_creds_result.fetchall())

                # Query enabled MCPServer entries for this organization
                # This catches servers without credentials (like Blender, Fetch)
                mcp_servers_query = select(MCPServer.id).where(
                    MCPServer.organization_id == organization_id,
                    MCPServer.enabled == True
                )
                mcp_servers_result = await db.execute(mcp_servers_query)
                mcp_server_ids = set(row[0] for row in mcp_servers_result.fetchall())

                # Filter out Team servers where user has no credentials
                # Team servers require user credentials to be "subscribed"
                # We need to filter BOTH org_server_ids AND mcp_server_ids

                # Get all servers that need filtering (not in user credentials)
                servers_to_check = (org_server_ids | mcp_server_ids) - user_server_ids
                valid_non_user_server_ids = set()
                skipped_team_count = 0

                for server_id in servers_to_check:
                    server = await db.get(MCPServer, server_id)
                    if server:
                        is_team_server = (server.env or {}).get('_IS_TEAM_SERVER') == 'true'
                        if not is_team_server:
                            # Not a Team server - can be started without user credentials
                            valid_non_user_server_ids.add(server_id)
                        else:
                            # Team server without user credentials - user not subscribed
                            logger.info(
                                f"Skipping Team server {server.server_id} for user {user_id} "
                                "(no user credentials = not subscribed)"
                            )
                            skipped_team_count += 1

                # Combine: user servers + valid non-user servers (org + mcp, excluding Team without user creds)
                combined_ids = list(user_server_ids | valid_non_user_server_ids)

                # N2.3 — RBAC filter on MCPServer.allowed_roles. We
                # have to resolve each row to inspect the column;
                # an alternative would be to JOIN above, but the set
                # of candidates is already small.
                final_ids: list[UUID] = []
                rbac_skipped = 0
                for server_id in combined_ids:
                    srv = await db.get(MCPServer, server_id)
                    if srv is None:
                        continue
                    if _role_allowed(srv.allowed_roles):
                        final_ids.append(server_id)
                    else:
                        rbac_skipped += 1
                        logger.info(
                            "RBAC: skipping server %s for user %s (role %s not in %s)",
                            srv.server_id, user_id, user_role_str, srv.allowed_roles,
                        )

                logger.info(
                    f"Found {len(final_ids)} servers to start "
                    f"(user_creds: {len(user_server_ids)}, other_valid: {len(valid_non_user_server_ids)}, "
                    f"skipped_team: {skipped_team_count}, skipped_rbac: {rbac_skipped}) "
                    f"for user {user_id} role={user_role_str}"
                )

                return final_ids

        except Exception as e:
            logger.error(f"Error getting configured servers for user {user_id}: {e}", exc_info=True)
            return []

    async def _get_tools_in_group(self, tool_group_id: str) -> set:
        """
        Get all tools in a ToolGroup as (server_id, tool_name) tuples.

        Used to filter tools when API key is restricted to a specific group.
        Returns tuples instead of tool_ids for reliable matching with runtime tools.

        Args:
            tool_group_id: ToolGroup UUID string

        Returns:
            Set of (server_id_str, tool_name) tuples for tools in the group
        """
        from ..db.database import get_async_session
        from sqlalchemy import select
        from ..models.tool_group import ToolGroupItem, ToolGroupItemType
        from ..models.tool import Tool

        try:
            from uuid import UUID
            group_uuid = UUID(tool_group_id)

            async for db in get_async_session():
                # Query tools with their server_id and tool_name via JOIN
                stmt = (
                    select(Tool.server_id, Tool.tool_name)
                    .join(ToolGroupItem, ToolGroupItem.tool_id == Tool.id)
                    .where(
                        ToolGroupItem.tool_group_id == group_uuid,
                        ToolGroupItem.item_type == ToolGroupItemType.TOOL,
                        ToolGroupItem.tool_id.isnot(None)
                    )
                )
                result = await db.execute(stmt)
                # Return set of (server_uuid_str, tool_name) tuples
                tools_in_group = {(str(row[0]), row[1]) for row in result.fetchall()}

                logger.info(f"ToolGroup {tool_group_id} contains {len(tools_in_group)} tools")
                return tools_in_group

        except Exception as e:
            logger.error(f"Error getting tools in group {tool_group_id}: {e}", exc_info=True)
            return set()

    async def _tool_in_group(self, tool_name: str, tool_group_id: str, all_tools: list) -> bool:
        """
        Check if a tool is in the specified ToolGroup.

        Args:
            tool_name: Name of the tool (prefixed format: server_id__original_name)
            tool_group_id: ToolGroup UUID string
            all_tools: List of all available tools (with metadata)

        Returns:
            True if tool is in group or no group restriction, False otherwise
        """
        if not tool_group_id:
            return True  # No restriction

        try:
            allowed_tools = await self._get_tools_in_group(tool_group_id)
            if not allowed_tools:
                return False  # Empty group means no access

            # Find the tool by prefixed name and check if (server_uuid, original_name) is allowed
            for tool in all_tools:
                if tool.get("name") == tool_name:
                    server_uuid = tool.get("metadata", {}).get("server_uuid") or tool.get("_server_id")
                    original_name = tool.get("metadata", {}).get("original_name") or tool.get("original_name")
                    # Fallback: extract original name from prefixed name
                    if not original_name and "__" in tool_name:
                        original_name = tool_name.split("__", 1)[1]

                    if server_uuid and original_name:
                        if (str(server_uuid), original_name) in allowed_tools:
                            return True
            return False

        except Exception as e:
            logger.error(f"Error checking tool in group: {e}", exc_info=True)
            return True  # On error, allow access for backwards compatibility

    async def _background_refresh_tools(
        self,
        user_uuid: UUID,
        org_uuid: UUID
    ) -> None:
        """
        Background task: start user servers, compare tools with cache, notify if changed.

        This is the proper background refresh that replaces the raw
        ensure_user_pool_started fire-and-forget. It completes the cycle:
        1. Start all configured servers for the user
        2. Get fresh tools from running servers
        3. Compare with cached tools
        4. If tools changed: update cache + send per-user SSE notification

        Uses per-user locking to prevent concurrent refreshes which can cause
        asyncpg connection race conditions (InterfaceError: cannot switch state).

        Args:
            user_uuid: User UUID
            org_uuid: Organization UUID
        """
        # Get or create lock for this user
        if user_uuid not in self._user_refresh_locks:
            self._user_refresh_locks[user_uuid] = asyncio.Lock()
        lock = self._user_refresh_locks[user_uuid]

        # Skip if refresh already in progress for this user
        if lock.locked():
            logger.debug(
                f"Background refresh already in progress for user {user_uuid}, skipping duplicate"
            )
            return

        async with lock:
            try:
                # 1. Start all configured servers
                started = await self.user_server_pool.ensure_configured_servers_started(
                    user_id=user_uuid,
                    organization_id=org_uuid
                )

                # 2. Get fresh tools from running servers
                fresh_tools = await self.user_server_pool.get_user_tools(
                    user_id=user_uuid,
                    organization_id=org_uuid
                )

                # 3. Compare with cached tools (by tool name set — fast and sufficient)
                from ..services.user_tool_cache import get_user_tool_cache
                tool_cache = get_user_tool_cache()
                cached_tools = await tool_cache.get(user_uuid)

                cached_names = {t.get("name") for t in (cached_tools or []) if isinstance(t, dict)}
                fresh_names = {t.get("name") for t in fresh_tools if isinstance(t, dict)}

                tools_changed = cached_names != fresh_names

                if tools_changed:
                    # 4a. Update cache with fresh tools
                    server_ids = {
                        t.get("_server_id") for t in fresh_tools
                        if isinstance(t, dict) and "_server_id" in t
                    }
                    await tool_cache.set(
                        user_id=user_uuid,
                        organization_id=org_uuid,
                        tools=fresh_tools,
                        server_ids=server_ids
                    )

                    # 4b. Close user's SSE sessions to force re-initialization.
                    # Claude Desktop ignores notifications/tools/list_changed but
                    # re-initializes (with fresh tools/list) when SSE drops.
                    closed = 0
                    user_id_str = str(user_uuid)
                    store = get_session_store()
                    for sid in await store.list_for_user(user_id_str):
                        await store.delete(sid)
                        closed += 1

                    added = fresh_names - cached_names
                    removed = cached_names - fresh_names
                    logger.info(
                        f"Background refresh for user {user_uuid}: "
                        f"tools changed ({len(cached_names)}→{len(fresh_names)}, "
                        f"+{len(added)} -{len(removed)}), "
                        f"cache updated, {closed} SSE session(s) closed"
                    )
                else:
                    # Tools unchanged — update cache timestamp but don't notify
                    if fresh_tools:
                        server_ids = {
                            t.get("_server_id") for t in fresh_tools
                            if isinstance(t, dict) and "_server_id" in t
                        }
                        await tool_cache.set(
                            user_id=user_uuid,
                            organization_id=org_uuid,
                            tools=fresh_tools,
                            server_ids=server_ids
                        )
                    logger.info(
                        f"Background refresh for user {user_uuid}: "
                        f"tools unchanged ({len(fresh_names)} tools), cache refreshed"
                    )

            except Exception as e:
                logger.error(
                    f"Background refresh failed for user {user_uuid}: {e}",
                    exc_info=True
                )

    # =========================================================================
    # MCP Protocol Handlers
    # =========================================================================

    async def list_tools(
        self,
        request_id: str,
        params: Dict[str, Any],
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        tool_group_id: Optional[str] = None,
        is_oauth_client: bool = False
    ) -> Dict[str, Any]:
        """
        List all available tools for the authenticated user (aggregated + orchestration + production compositions).

        Auto-starts MCP servers with configured credentials for the user.
        Uses UserServerPool for per-user tool isolation.
        Returns tools in MCP format with JSON Schema parameters.

        If tool_group_id is provided, filters tools to only those in the specified ToolGroup.
        If is_oauth_client is True, filters tools by is_visible_to_oauth_clients flag.

        Args:
            request_id: JSON-RPC request ID
            params: Request parameters
            session_id: Optional session ID (legacy)
            user_id: Optional user ID (preferred - from authentication)
            organization_id: Optional organization ID (preferred - from authentication)
            tool_group_id: Optional ToolGroup ID for filtering tools (from API key)
            is_oauth_client: Whether the client authenticated via OAuth (vs API key)
        """
        try:
            # Priority: use provided user_id/organization_id from auth, fallback to session
            if not user_id and session_id:
                session = await self.session_store.get_metadata(session_id)
                if session:
                    user_id = session.get("user_id")
                    organization_id = session.get("organization_id")

            if user_id:
                logger.info(f"list_tools called for user_id={user_id}, organization_id={organization_id}")
            else:
                logger.warning("list_tools called without user context - will use global registry")

            # Get user-specific tools from UserServerPool
            # OAuth clients only see tools with is_visible_to_oauth_clients=True
            # API key clients see all enabled tools (respecting tool_group_id if set)
            all_tools = []

            if user_id and organization_id:
                from uuid import UUID
                import asyncio
                user_uuid = UUID(str(user_id))
                org_uuid = UUID(str(organization_id))

                # Track this user as recently active in their org so that
                # notify_org_tools_changed can trigger background refresh even
                # when they have no active SSE session (e.g. Claude Desktop).
                org_id_str_track = str(organization_id)
                user_id_str_track = str(user_id)
                if org_id_str_track not in org_active_users:
                    org_active_users[org_id_str_track] = {}
                org_active_users[org_id_str_track][user_id_str_track] = time.time()

                # =====================================================================
                # CACHE CHECK: Return cached tools instantly if available
                # This allows OAuth clients to get immediate response while servers
                # start in background (avoids 35-70 second wait on first connection)
                # =====================================================================
                from ..services.user_tool_cache import get_user_tool_cache
                tool_cache = get_user_tool_cache()
                cached_tools = await tool_cache.get(user_uuid)

                if cached_tools is not None:
                    logger.info(
                        f"🚀 Cache HIT: Returning {len(cached_tools)} cached tools for user {user_id}, "
                        "triggering background refresh with notification"
                    )

                    # Background: start servers, compare tools, update cache, notify via SSE
                    asyncio.create_task(
                        self._background_refresh_tools(
                            user_uuid=user_uuid,
                            org_uuid=org_uuid
                        )
                    )

                    # Use cached tools immediately (client gets instant response)
                    all_tools = cached_tools

                    logger.info(f"Using {len(all_tools)} cached tools, background refresh will notify if changed")

                else:
                    # Cache miss - return DB tools instantly, start servers in background
                    logger.info(f"Cache MISS for user {user_id}, returning DB tools + background server start")

                # Non-blocking cold start (only if cache miss)
                if cached_tools is None:
                    # =====================================================================
                    # INSTANT RESPONSE: Query tools from database (< 50ms)
                    # Tools are persisted to DB when servers start via UserServerPool.
                    # This allows immediate response even when no servers are running.
                    # =====================================================================
                    try:
                        from ..db.database import get_async_session
                        from sqlalchemy import select
                        from ..models.tool import Tool
                        from ..models.mcp_server import MCPServer

                        async for db in get_async_session():
                            # Phase 3: tools that are in the org default pool or
                            # pinned by this user are always visible to OAuth
                            # clients, even when the ephemeral
                            # ``is_visible_to_oauth_clients`` flag is False.
                            # Resolve them up-front so the WHERE clause stays a
                            # simple IN-list rather than a correlated subquery.
                            from ..models.pool_persistent import (
                                OrgDefaultPoolEntry,
                                UserPersistentPoolEntry,
                            )
                            from sqlalchemy import or_

                            persistent_tool_ids: set = set()
                            org_default_rows = (
                                await db.execute(
                                    select(OrgDefaultPoolEntry.tool_id).where(
                                        OrgDefaultPoolEntry.organization_id == org_uuid,
                                        OrgDefaultPoolEntry.tool_id.is_not(None),
                                    )
                                )
                            ).scalars().all()
                            persistent_tool_ids.update(t for t in org_default_rows if t)

                            if user_uuid:
                                user_pin_rows = (
                                    await db.execute(
                                        select(UserPersistentPoolEntry.tool_id).where(
                                            UserPersistentPoolEntry.user_id == user_uuid,
                                            UserPersistentPoolEntry.tool_id.is_not(None),
                                        )
                                    )
                                ).scalars().all()
                                persistent_tool_ids.update(t for t in user_pin_rows if t)

                            # Phase 5: preheat overlay — also expose the user's
                            # top-N tools from the past 30 days, even if they
                            # are not pinned/defaulted. The next agent that
                            # reconnects sees its everyday catalog without
                            # having to call ``search`` first.
                            try:
                                from ..core.config import settings as _ph_cfg
                                if _ph_cfg.MCP_PREHEAT_TOP_N > 0 and user_uuid:
                                    from ..services.usage_analytics import (
                                        top_tools_for_user,
                                        resolve_tool_names_to_ids,
                                    )
                                    top = await top_tools_for_user(
                                        db,
                                        user_id=user_uuid,
                                        organization_id=org_uuid,
                                        days=_ph_cfg.MCP_PREHEAT_DAYS,
                                        limit=_ph_cfg.MCP_PREHEAT_TOP_N,
                                    )
                                    if top:
                                        resolved = await resolve_tool_names_to_ids(
                                            db,
                                            organization_id=org_uuid,
                                            prefixed_names=[t.tool_name for t in top],
                                        )
                                        persistent_tool_ids.update(tid for _, tid in resolved)
                            except Exception as _ph_err:
                                logger.debug(f"preheat overlay skipped: {_ph_err}")

                            # Get all tools for user's org with their server info
                            filters = [
                                Tool.organization_id == org_uuid,
                                MCPServer.enabled == True
                            ]
                            # OAuth clients only see visible tools/servers,
                            # plus anything explicitly persisted in the pool.
                            if is_oauth_client:
                                tool_visibility = (
                                    or_(
                                        Tool.is_visible_to_oauth_clients == True,
                                        Tool.id.in_(persistent_tool_ids),
                                    )
                                    if persistent_tool_ids
                                    else Tool.is_visible_to_oauth_clients == True
                                )
                                server_visibility = (
                                    or_(
                                        MCPServer.is_visible_to_oauth_clients == True,
                                        Tool.id.in_(persistent_tool_ids),
                                    )
                                    if persistent_tool_ids
                                    else MCPServer.is_visible_to_oauth_clients == True
                                )
                                filters.append(tool_visibility)
                                filters.append(server_visibility)
                            stmt = (
                                select(Tool, MCPServer.server_id.label("mcp_server_id"), MCPServer.name.label("mcp_server_name"))
                                .join(MCPServer, Tool.server_id == MCPServer.id)
                                .where(*filters)
                            )
                            result = await db.execute(stmt)
                            rows = result.all()

                            if rows:
                                db_tools = []
                                for tool_row, mcp_server_id, mcp_server_name in rows:
                                    # Use server name (e.g. "Github") as prefix, fallback to server_id
                                    display_name = mcp_server_name or mcp_server_id or ""
                                    safe_prefix = re.sub(r'[^a-zA-Z0-9_]', '_', display_name)
                                    safe_prefix = re.sub(r'_+', '_', safe_prefix).strip('_')
                                    db_tools.append({
                                        "name": f"{safe_prefix}__{tool_row.tool_name}" if safe_prefix else tool_row.tool_name,
                                        "description": tool_row.description or "",
                                        "inputSchema": tool_row.parameters_schema or {},
                                        "_server_id": str(tool_row.server_id),
                                        "metadata": {
                                            "server_id": mcp_server_id,
                                            "server_uuid": str(tool_row.server_id),
                                            "server_display_name": display_name,
                                            "original_tool_name": tool_row.tool_name,
                                            "source": "database"
                                        }
                                    })

                                all_tools = db_tools
                                logger.info(
                                    f"⚡ Instant response: {len(db_tools)} tools from DB for user {user_id} "
                                    "(servers starting in background)"
                                )

                                # Warm the cache with DB tools so next call is a cache HIT
                                server_ids = {t["_server_id"] for t in db_tools}
                                await tool_cache.set(
                                    user_id=user_uuid,
                                    organization_id=org_uuid,
                                    tools=db_tools,
                                    server_ids=server_ids
                                )
                            else:
                                logger.info(f"No tools in DB for user {user_id}, returning empty list")
                            break

                    except Exception as e:
                        logger.error(f"Error querying tools from DB: {e}", exc_info=True)

                    # Background: start servers + refresh cache + notify if tools changed
                    asyncio.create_task(
                        self._background_refresh_tools(
                            user_uuid=user_uuid,
                            org_uuid=org_uuid
                        )
                    )
            else:
                # No user context - return empty list (authentication required)
                logger.error("No user context in session - returning empty tools (authentication required)")
                # NO global registry access without authentication!

            # =====================================================================
            # VISIBILITY FILTER: OAuth clients only see tools currently loaded
            # in the dynamic pool (Tool.is_visible_to_oauth_clients = True).
            # The user_tool_cache stores ALL of a user's tools (shared between
            # API-key clients and OAuth clients), so we MUST re-apply the
            # per-tool visibility flag on every read — otherwise OAuth clients
            # see the entire catalog regardless of pool state.
            # The server-level flag is also enforced as a defence-in-depth
            # layer (a hidden server still hides every tool under it).
            # =====================================================================
            if is_oauth_client and all_tools:
                try:
                    from ..db.database import get_async_session
                    from sqlalchemy import select as sa_select
                    from ..models.mcp_server import MCPServer as MCPServerModel
                    from ..models.tool import Tool as ToolModel

                    visible_server_uuids: set[str] = set()
                    visible_tool_keys: set[tuple[str, str]] = set()
                    async for db in get_async_session():
                        srv_stmt = (
                            sa_select(MCPServerModel.id)
                            .where(
                                MCPServerModel.organization_id == org_uuid,
                                MCPServerModel.enabled == True,
                                MCPServerModel.is_visible_to_oauth_clients == True
                            )
                        )
                        srv_rows = (await db.execute(srv_stmt)).all()
                        visible_server_uuids = {str(row[0]) for row in srv_rows}

                        tool_stmt = (
                            sa_select(ToolModel.server_id, ToolModel.tool_name)
                            .join(MCPServerModel, MCPServerModel.id == ToolModel.server_id)
                            .where(
                                MCPServerModel.organization_id == org_uuid,
                                MCPServerModel.enabled == True,
                                MCPServerModel.is_visible_to_oauth_clients == True,
                                ToolModel.is_visible_to_oauth_clients == True,
                            )
                        )
                        tool_rows = (await db.execute(tool_stmt)).all()
                        visible_tool_keys = {(str(srv_uuid), tname) for srv_uuid, tname in tool_rows}
                        break

                    original_count = len(all_tools)
                    filtered: list = []
                    for t in all_tools:
                        meta = t.get("metadata") or {}
                        srv_uuid = meta.get("server_uuid") or t.get("_server_id")
                        if not srv_uuid or str(srv_uuid) not in visible_server_uuids:
                            continue
                        original_name = (
                            meta.get("original_tool_name")
                            or meta.get("original_name")
                        )
                        # Cache entries built from `UserServerPool.get_user_tools`
                        # carry the prefixed name in `t["name"]` and the raw tool
                        # name in `metadata.original_tool_name`. Cache entries
                        # built from the DB-instant path (line 909) also expose
                        # `original_tool_name`. If neither is set, fall back to
                        # stripping the `Server__` prefix from the unique name.
                        if not original_name:
                            unique_name = t.get("name") or ""
                            if "__" in unique_name:
                                original_name = unique_name.split("__", 1)[1]
                            else:
                                original_name = unique_name
                        if (str(srv_uuid), original_name) in visible_tool_keys:
                            filtered.append(t)

                    all_tools = filtered
                    logger.info(
                        f"OAuth visibility filter: {original_count} -> {len(all_tools)} tools "
                        f"({len(visible_server_uuids)} visible servers, "
                        f"{len(visible_tool_keys)} visible tools in pool)"
                    )
                except Exception as e:
                    logger.error(f"Error in OAuth visibility filter: {e}", exc_info=True)

            # Filter tools by ToolGroup if specified
            if tool_group_id and all_tools:
                try:
                    # Get allowed tools as (server_uuid, tool_name) tuples
                    allowed_tools = await self._get_tools_in_group(tool_group_id)
                    if allowed_tools:
                        # Filter to only tools in the group using (server_uuid, tool_name) matching
                        original_count = len(all_tools)
                        filtered_tools = []
                        for t in all_tools:
                            # Get server_uuid and tool_name from runtime tool metadata
                            server_uuid = t.get("metadata", {}).get("server_uuid")
                            tool_name = t.get("name", "")

                            if server_uuid and tool_name:
                                tool_key = (str(server_uuid), tool_name)
                                if tool_key in allowed_tools:
                                    filtered_tools.append(t)
                                    logger.debug(f"Tool {tool_name} matched in group: {tool_key}")
                                else:
                                    logger.debug(f"Tool {tool_name} NOT in group: {tool_key}")

                        all_tools = filtered_tools
                        logger.info(
                            f"ToolGroup filter applied: {original_count} -> {len(all_tools)} tools "
                            f"(group_id={tool_group_id}, allowed={len(allowed_tools)})"
                        )
                    else:
                        logger.warning(f"ToolGroup {tool_group_id} has no tools - returning empty list")
                        all_tools = []
                except Exception as e:
                    logger.error(f"Error filtering by ToolGroup: {e}", exc_info=True)
                    # On error, return all tools for backwards compatibility
                    # In strict mode, you could instead return empty list

            # Format tools for MCP
            mcp_tools = []

            for tool in all_tools:
                # Ensure parameters are in JSON Schema format
                # MCP protocol uses "inputSchema", not "parameters"
                raw_schema = tool.get("inputSchema") or tool.get("parameters", {})
                parameters = self._normalize_parameters(raw_schema)

                # Get tool name - check if already prefixed by UserServerPool
                tool_name = tool.get("name", "")
                metadata = tool.get("metadata", {})

                # If original_tool_name exists in metadata, the tool was already prefixed
                # by UserServerPool.get_user_tools() - use the name as-is
                if metadata.get("original_tool_name"):
                    # Already prefixed by UserServerPool
                    unique_name = tool_name
                    original_name = metadata["original_tool_name"]
                else:
                    # Not prefixed yet - apply prefix (for backward compatibility)
                    original_name = tool_name

                    # Get server display name for prefix (fallback to server_id)
                    server_prefix = metadata.get("server_display_name") or metadata.get("server_id")
                    if not server_prefix and "server_info" in tool:
                        server_prefix = tool["server_info"].get("server_display_name") or tool["server_info"].get("server_id")

                    # Build unique tool name with server prefix
                    # Format: ServerName__tool_name (double underscore as separator)
                    if server_prefix:
                        # Sanitize for use in tool name (alphanumeric + underscore only)
                        safe_prefix = re.sub(r'[^a-zA-Z0-9_]', '_', server_prefix)
                        safe_prefix = re.sub(r'_+', '_', safe_prefix).strip('_')
                        unique_name = f"{safe_prefix}__{original_name}"
                    else:
                        unique_name = original_name

                # Get server display name for description prefix (fallback to server_id)
                server_display_name = metadata.get("server_display_name") or metadata.get("server_id")

                # Build description with server context using display name
                full_description = tool.get("description", "")
                if server_display_name and not full_description.startswith(f"[{server_display_name}]"):
                    full_description = f"[{server_display_name}] {full_description}"

                # MCP 2025-06-18: Tool requires only `name` + `inputSchema`.
                # `description` and `title` are optional. In compact mode we
                # ship only a 1-line `title` so the LLM can pick the tool
                # without burning ~150 tokens on the verbose description.
                # Full text remains available via the `describe_tool` meta-tool.
                from ..core.config import settings as _cfg
                mcp_tool = {
                    "name": unique_name,
                    "inputSchema": parameters,
                }
                if _cfg.MCP_COMPACT_MODE:
                    # Title = "[Server] tool_name" — enough for tool selection
                    mcp_tool["title"] = (
                        f"[{server_display_name}] {original_name}"
                        if server_display_name
                        else original_name
                    )
                else:
                    mcp_tool["description"] = full_description

                # MCP 2025-06-18: pass through `outputSchema` + `annotations`
                # if the upstream server supplied them. We don't fabricate
                # annotations from the tool name — clients should treat any
                # hint as untrusted, but a wrong "readOnlyHint=true" would
                # be actively misleading. Leave them absent when unknown.
                upstream_output_schema = tool.get("outputSchema")
                if isinstance(upstream_output_schema, dict) and upstream_output_schema:
                    mcp_tool["outputSchema"] = upstream_output_schema
                upstream_annotations = tool.get("annotations")
                if isinstance(upstream_annotations, dict) and upstream_annotations:
                    mcp_tool["annotations"] = upstream_annotations

                # Add service icon if available (MCP protocol support)
                icon_url = tool.get("metadata", {}).get("icon_url")
                logger.debug(f"🎨 Tool {original_name}: icon_url={icon_url}, metadata={tool.get('metadata', {})}")
                if icon_url:
                    # Determine MIME type based on URL extension
                    mime_type = "image/svg+xml" if ".svg" in icon_url.lower() else "image/png"
                    mcp_tool["icons"] = [{
                        "src": icon_url,
                        "mimeType": mime_type
                    }]
                    logger.info(f"🎨 Added icon to tool {unique_name}: {icon_url}")

                # Routing metadata kept in `_meta` (MCP 2025-06-18 standard
                # escape hatch). The legacy `_metadata` alias stays around
                # only as long as no internal consumer reads it; nothing in
                # the gateway reads back from this field today.
                routing_meta = tool.get("metadata", {}).copy() if "metadata" in tool else {}
                routing_meta["original_tool_name"] = original_name
                mcp_tool["_meta"] = routing_meta

                mcp_tools.append(mcp_tool)

            # Surface selection driven by feature flags so we can roll back
            # in production without redeploying:
            #   - LEGACY_POOL_BEHAVIOR=true       → expose ONLY orchestrator_*
            #   - LEGACY_ORCHESTRATOR_TOOLS_VISIBLE=true → also expose
            #     orchestrator_* alongside search/execute (transition mode)
            #   - default                          → only search + execute
            from ..core.config import settings as _settings

            if _settings.LEGACY_POOL_BEHAVIOR:
                mcp_tools.extend(self._get_orchestration_tools())
            else:
                mcp_tools.extend(get_pool_tools())
                if _settings.LEGACY_ORCHESTRATOR_TOOLS_VISIBLE:
                    mcp_tools.extend(self._get_orchestration_tools())

            # Add production compositions as dynamic tools
            # IMPORTANT: Read from DATABASE (not file store) for persistence across restarts
            try:
                from ..db.session import AsyncSessionLocal
                from ..services.composition_service import CompositionService
                from ..models.composition import Composition
                from uuid import UUID

                production_compositions = []

                # Get production compositions from database if user context is available
                if user_id and organization_id:
                    try:
                        user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
                        org_uuid = UUID(organization_id) if isinstance(organization_id, str) else organization_id

                        async with AsyncSessionLocal() as db:
                            service = CompositionService(db)
                            # Get all production compositions for this organization
                            db_compositions = await service.list_compositions(
                                organization_id=org_uuid,
                                user_id=user_uuid,
                                status="production"
                            )
                            # Convert DB models to compatible format
                            for db_comp in db_compositions:
                                production_compositions.append(db_comp)
                                logger.debug(f"Loaded production composition from DB: {db_comp.name} (id={db_comp.id})")

                        logger.info(f"Loaded {len(production_compositions)} production compositions from database")
                    except Exception as db_err:
                        logger.error(f"Error loading compositions from database: {db_err}", exc_info=True)

                for comp in production_compositions:
                    # Get composition ID as string (handles both DB model UUID and file store string)
                    comp_id_str = str(comp.id) if hasattr(comp, 'id') else comp.get('id', '')
                    comp_name = comp.name if hasattr(comp, 'name') else comp.get('name', 'unnamed')

                    # Sanitize name for tool name (alphanumeric + underscore only)
                    safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', comp_name)
                    # Remove consecutive underscores and trim
                    safe_name = re.sub(r'_+', '_', safe_name).strip('_')
                    tool_name = f"composition_{safe_name}"

                    # Use input_schema or create default
                    input_schema = comp.input_schema if comp.input_schema else {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }

                    # Ensure input_schema is proper JSON Schema format
                    if "type" not in input_schema:
                        input_schema["type"] = "object"

                    # Build description with composition name prominently
                    comp_description = comp.description if hasattr(comp, 'description') and comp.description else ''
                    description = f"[Composition: {comp_name}] {comp_description}".strip()

                    # MCP 2025-06-18: in compact mode we drop the verbose
                    # description (the title alone is enough for selection),
                    # full text is fetched on demand via describe_tool. Same
                    # logic as for regular tools.
                    from ..core.config import settings as _cfg
                    mcp_tool = {
                        "name": tool_name,
                        # `title` is the human-friendly display name; `name`
                        # stays the programmatic identifier the client uses
                        # to call the tool.
                        "title": f"Composition: {comp_name}",
                        "inputSchema": input_schema,
                        # `_meta` is the standard escape hatch for non-functional
                        # context. We use it for routing hints the gateway needs
                        # internally; clients are free to ignore it.
                        "_meta": {
                            "is_composition": True,
                            "composition_id": comp_id_str,
                            "composition_name": comp_name,
                            "steps_count": len(comp.steps) if comp.steps else 0
                        },
                        # MCP 2025-06-18: a composition runs an arbitrary
                        # chain of upstream tools, so the safe assumption
                        # is destructive + open-world. Clients that want a
                        # finer signal can inspect the steps via
                        # describe_tool / the REST composition endpoint.
                        "annotations": {
                            "title": f"Composition: {comp_name}",
                            "readOnlyHint": False,
                            "destructiveHint": True,
                            "idempotentHint": False,
                            "openWorldHint": True,
                        },
                    }
                    # Surface output_schema if the composition declares one.
                    comp_output_schema = (
                        comp.output_schema
                        if hasattr(comp, "output_schema") and comp.output_schema
                        else None
                    )
                    if isinstance(comp_output_schema, dict) and comp_output_schema:
                        mcp_tool["outputSchema"] = comp_output_schema
                    if not _cfg.MCP_COMPACT_MODE:
                        mcp_tool["description"] = description

                    mcp_tools.append(mcp_tool)

                if production_compositions:
                    logger.info(f"Added {len(production_compositions)} production compositions as tools")

            except Exception as e:
                logger.error(f"Error loading production compositions: {e}", exc_info=True)
                # Don't fail tools listing if compositions fail to load

            logger.info(f"Returning {len(mcp_tools)} tools to client (including compositions)")

            # MCP 2025-03-26: cursor-based pagination
            from ..core.config import settings as _pg_settings
            cursor = params.get("cursor")
            page_size = max(1, _pg_settings.MCP_TOOLS_PAGE_SIZE)
            offset = 0
            if cursor:
                try:
                    offset = int(cursor)
                except (ValueError, TypeError):
                    offset = 0

            paginated_tools = mcp_tools[offset:offset + page_size]
            next_cursor = str(offset + page_size) if (offset + page_size) < len(mcp_tools) else None

            result_payload: Dict[str, Any] = {"tools": paginated_tools}
            if next_cursor is not None:
                result_payload["nextCursor"] = next_cursor

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result_payload
            }

        except Exception as e:
            logger.error(f"Error listing tools: {e}", exc_info=True)
            return self._error_response(request_id, -32603, f"Internal error: {str(e)}")

    async def call_tool(
        self,
        request_id: str,
        params: Dict[str, Any],
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        tool_group_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a tool (routed to appropriate server, orchestration, or composition).

        Handles aggregated tools, orchestration tools, and production compositions.
        Validates tool access if tool_group_id is specified.

        Args:
            request_id: JSON-RPC request ID
            params: Request parameters
            session_id: Optional session ID (legacy)
            user_id: Optional user ID (preferred - from authentication)
            organization_id: Optional organization ID (preferred - from authentication)
            tool_group_id: Optional ToolGroup ID for access validation (from API key)
        """
        tool_name = params.get("name")
        raw_arguments = params.get("arguments", {})

        # Parse JSON string arguments to native Python types
        # This handles Claude's serialization of complex types as JSON strings
        tool_arguments = parse_json_string_arguments(raw_arguments)

        if not tool_name:
            return self._error_response(request_id, -32602, "Missing 'name' parameter")

        logger.info(f"Calling tool: {tool_name} with args: {tool_arguments}")

        # Phase 5: timestamp for usage tracking. Logged fire-and-forget after
        # the dispatch returns. Meta-tools (search/execute/describe_tool) write
        # their own log rows or are not real usage signals — skip them here.
        import time as _time
        _call_start = _time.time()

        try:
            # Validate tool access if restricted to ToolGroup
            # Skip validation for pool meta-tools (search/execute), orchestration
            # tools, and workflows — these are always allowed.
            if (
                tool_group_id
                and tool_name not in POOL_TOOL_NAMES
                and not tool_name.startswith("orchestrator_")
                and not tool_name.startswith("workflow_")
            ):
                allowed_tool_ids = await self._get_tools_in_group(tool_group_id)
                # For non-grouped tools, we need to check by getting all tools first
                # This is a simplified check - ideally we'd have tool_id in the request
                if allowed_tool_ids:
                    # Log warning but allow for now - full validation would require tool lookup
                    logger.info(f"ToolGroup access check: tool={tool_name}, group={tool_group_id}")
                else:
                    logger.warning(f"ToolGroup {tool_group_id} is empty - denying tool access")
                    return self._error_response(
                        request_id,
                        -32600,
                        f"Tool '{tool_name}' not accessible with this API key (empty ToolGroup)"
                    )

            # New dynamic pool surface (preferred path going forward).
            if tool_name == "search":
                result = await handle_search(
                    tool_arguments,
                    user_id=user_id,
                    organization_id=organization_id,
                )
            elif tool_name == "execute":
                result = await handle_execute(
                    tool_arguments,
                    user_id=user_id,
                    organization_id=organization_id,
                    gateway=self,
                    session_id=session_id,
                )
            elif tool_name == "describe_tool":
                result = await handle_describe_tool(
                    tool_arguments,
                    user_id=user_id,
                    organization_id=organization_id,
                )
            elif tool_name == "composition_status":
                result = await handle_composition_status(
                    tool_arguments,
                    user_id=user_id,
                    organization_id=organization_id,
                )
            # Check if it's an orchestration tool
            elif tool_name.startswith("orchestrator_"):
                result = await self._execute_orchestration_tool(
                    tool_name,
                    tool_arguments,
                    user_id=user_id,
                    organization_id=organization_id,
                    tool_group_id=tool_group_id
                )
            # Check if it's a workflow composition (by ID)
            elif tool_name.startswith("workflow_"):
                # Extract composition ID from tool name (format: workflow_{comp_id})
                composition_id = tool_name.replace("workflow_", "")

                logger.info(f"Executing production composition by ID: {composition_id}")

                # B-0 chunk 6 routing: static analysis decides Pattern A
                # (sync inline, legacy executor) or Pattern C (detached
                # via ResumableExecutor with resource URI return). For
                # B-0 the only suspending step type is _test_suspend
                # (debug-only) so production compositions stay 100% on
                # the legacy sync path — zero regression.
                from ..orchestration.composition_routing import (
                    route_composition_call,
                )
                from uuid import UUID as _UUID
                self.orchestration_tools._user_server_pool = self.user_server_pool
                result = await route_composition_call(
                    composition_id=_UUID(composition_id),
                    tool_arguments=tool_arguments,
                    user_id=_UUID(str(user_id)),
                    organization_id=_UUID(str(organization_id)),
                    legacy_executor=self.orchestration_tools,
                    mcp_session_id=session_id,
                )
            # Check if it's a promoted composition (by name)
            elif tool_name.startswith("composition_"):
                # Extract sanitized name from tool name (format: composition_{safe_name})
                safe_name = tool_name.replace("composition_", "")

                logger.info(f"Executing promoted composition by name: {safe_name}")

                # Look up composition by name from production compositions
                from ..orchestration.composition_store import get_composition_store
                composition_store = get_composition_store()
                production_comps = await composition_store.list_all(status="production")

                # Also load from database for multi-tenant compositions
                from ..db.session import AsyncSessionLocal
                from ..models.composition import Composition
                from sqlalchemy import select
                try:
                    async with AsyncSessionLocal() as db:
                        db_query = select(Composition).where(Composition.status == "production")
                        db_result = await db.execute(db_query)
                        db_comps = db_result.scalars().all()
                        for db_comp in db_comps:
                            production_comps.append(db_comp)
                except Exception as db_err:
                    logger.warning(f"Error loading compositions from DB: {db_err}")

                # Find composition matching the sanitized name
                composition_id = None
                for comp in production_comps:
                    comp_name = comp.name if hasattr(comp, 'name') else comp.get('name', '')
                    # Sanitize name same way as list_tools
                    comp_safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', comp_name)
                    comp_safe_name = re.sub(r'_+', '_', comp_safe_name).strip('_')
                    if comp_safe_name == safe_name:
                        composition_id = str(comp.id) if hasattr(comp, 'id') else comp.get('id')
                        logger.info(f"Found composition '{comp_name}' with ID: {composition_id}")
                        break

                if not composition_id:
                    raise ValueError(f"Composition not found: {tool_name}")

                # B-0 chunk 6 routing — same Pattern A vs C decision as
                # the workflow_ branch above. See route_composition_call
                # for the static analysis. Legacy production compositions
                # have zero suspending step types so they stay sync.
                from ..orchestration.composition_routing import (
                    route_composition_call,
                )
                from uuid import UUID as _UUID
                self.orchestration_tools._user_server_pool = self.user_server_pool
                result = await route_composition_call(
                    composition_id=_UUID(composition_id),
                    tool_arguments=tool_arguments,
                    user_id=_UUID(str(user_id)),
                    organization_id=_UUID(str(organization_id)),
                    legacy_executor=self.orchestration_tools,
                    mcp_session_id=session_id,
                )
            else:
                # Route to appropriate MCP server (with user context)
                result = await self._route_tool_execution(
                    tool_name,
                    tool_arguments,
                    session_id=session_id,
                    user_id=user_id,
                    organization_id=organization_id
                )

            # MCP 2025-06-18: when the underlying handler returned a dict, we
            # ship it both as `structuredContent` (machine-parseable, matches
            # the tool's outputSchema) and as a JSON `text` block (legacy
            # clients that read content[].text still work). For non-dict
            # results we keep only the text path.
            tool_result_payload: Dict[str, Any] = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, ensure_ascii=False, indent=2)
                    }
                ],
                "isError": False
            }
            if isinstance(result, dict):
                tool_result_payload["structuredContent"] = result

            # Phase 5: fire-and-forget tool-call log row used by the
            # usage-analytics service to drive pin suggestions and the
            # 30-day preheat overlay. Skips meta-tools that are not real
            # usage signals or that already write their own row.
            try:
                if (
                    user_id
                    and organization_id
                    and tool_name not in POOL_TOOL_NAMES
                ):
                    _comp_id_for_log = None
                    if tool_name.startswith("composition_") or tool_name.startswith("workflow_"):
                        _comp_id_for_log = locals().get("composition_id")
                    asyncio.create_task(
                        _log_tool_call_async(
                            user_id=str(user_id),
                            organization_id=str(organization_id),
                            session_id=session_id,
                            tool_name=tool_name,
                            duration_ms=int((_time.time() - _call_start) * 1000),
                            status="success",
                            composition_id=_comp_id_for_log,
                        )
                    )
            except Exception:
                pass

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": tool_result_payload
            }

        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
            # Phase 5: log failed tool calls too — they still indicate intent.
            try:
                if (
                    user_id
                    and organization_id
                    and tool_name not in POOL_TOOL_NAMES
                ):
                    asyncio.create_task(
                        _log_tool_call_async(
                            user_id=str(user_id),
                            organization_id=str(organization_id),
                            session_id=session_id,
                            tool_name=tool_name,
                            duration_ms=int((_time.time() - _call_start) * 1000),
                            status="failed",
                            error=str(e),
                            composition_id=None,
                        )
                    )
            except Exception:
                pass
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Error: {str(e)}"
                        }
                    ],
                    "structuredContent": {"error": str(e)},
                    "isError": True
                }
            }

    async def list_resources(
        self,
        request_id: str,
        params: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List available resources (compositions + executions).

        Exposes saved compositions (legacy) AND the calling user's
        ``composition://executions/{id}`` rows (B-0 chunk 7). The
        latter are scoped per-user — a user only sees their own.
        """
        try:
            from ..orchestration.composition_store import get_composition_store
            from ..orchestration.composition_resources import (
                list_user_execution_resources,
            )
            composition_store = get_composition_store()

            # Load all compositions (validated and production)
            validated_comps = await composition_store.list_all(status="validated")
            production_comps = await composition_store.list_all(status="production")

            all_comps = validated_comps + production_comps

            # Format as MCP resources
            resources = []

            for comp in all_comps:
                resource = {
                    "uri": f"composition://{comp.status}/{comp.id}",
                    "name": comp.name,
                    "description": comp.description or f"Workflow composition: {comp.name}",
                    "mimeType": "application/json",
                    "annotations": {
                        "status": comp.status,
                        "steps_count": len(comp.steps),
                        "created_at": comp.created_at,
                        "updated_at": comp.updated_at
                    }
                }

                resources.append(resource)

            # B-0 chunk 7: per-user execution resources
            if user_id:
                from uuid import UUID as _UUID
                try:
                    user_uuid = _UUID(str(user_id))
                    exec_resources = await list_user_execution_resources(
                        user_id=user_uuid
                    )
                    resources.extend(exec_resources)
                except Exception as ee:  # noqa: BLE001
                    logger.warning(
                        f"failed to list execution resources for user {user_id}: {ee}"
                    )

            logger.info(f"Returning {len(resources)} resources (compositions + executions)")

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "resources": resources
                }
            }

        except Exception as e:
            logger.error(f"Error listing resources: {e}", exc_info=True)
            return self._error_response(request_id, -32603, f"Internal error: {str(e)}")

    async def read_resource(
        self,
        request_id: str,
        params: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Read a specific resource (composition details OR execution state).

        URI schemes:
        - ``composition://{status}/{id}`` — saved composition definition
        - ``composition://executions/{id}`` — runtime execution state
          (B-0 chunk 7), per-user scoped (cross-user → 404, no leak)
        """
        uri = params.get("uri")

        if not uri:
            return self._error_response(request_id, -32602, "Missing 'uri' parameter")

        try:
            # B-0 chunk 7: try the execution URI first
            if uri.startswith("composition://executions/"):
                if not user_id:
                    return self._error_response(
                        request_id, -32601,
                        f"Resource not found: {uri}"
                    )
                from ..orchestration.composition_resources import (
                    read_execution_resource,
                )
                from uuid import UUID as _UUID
                try:
                    user_uuid = _UUID(str(user_id))
                except (ValueError, TypeError):
                    return self._error_response(
                        request_id, -32601,
                        f"Resource not found: {uri}"
                    )
                content = await read_execution_resource(
                    uri=uri, user_id=user_uuid
                )
                if content is None:
                    # Same response for non-existent and cross-user
                    # (no info leak about row existence)
                    return self._error_response(
                        request_id, -32601,
                        f"Resource not found: {uri}"
                    )
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"contents": [content]},
                }

            # Legacy composition URI scheme
            if not uri.startswith("composition://"):
                return self._error_response(request_id, -32602, f"Invalid URI format: {uri}")

            # Extract composition ID from URI
            path = uri.replace("composition://", "")
            parts = path.split("/")

            if len(parts) < 2:
                return self._error_response(request_id, -32602, f"Invalid URI format: {uri}")

            status = parts[0]
            composition_id = parts[1]

            # Load composition from store
            from ..orchestration.composition_store import get_composition_store
            composition_store = get_composition_store()

            composition = await composition_store.get(composition_id)

            if not composition:
                return self._error_response(request_id, -32601, f"Composition not found: {composition_id}")

            # Verify status matches
            if composition.status != status:
                logger.warning(f"Status mismatch for {composition_id}: URI has {status}, actual is {composition.status}")

            # Return composition as resource content
            composition_data = composition.to_dict()

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": json.dumps(composition_data, ensure_ascii=False, indent=2)
                        }
                    ]
                }
            }

        except Exception as e:
            logger.error(f"Error reading resource {uri}: {e}", exc_info=True)
            return self._error_response(request_id, -32603, f"Internal error: {str(e)}")

    # B-0 chunk 7: subscribe / unsubscribe handlers

    async def subscribe_resource(
        self,
        request_id: str,
        params: Dict[str, Any],
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """``resources/subscribe`` — track session_id → uri mapping."""
        uri = params.get("uri")
        if not uri:
            return self._error_response(request_id, -32602, "Missing 'uri' parameter")
        if not session_id:
            return self._error_response(
                request_id, -32602, "Subscriptions require an MCP session"
            )
        # Per-user scoping check on execution URIs: only allow the user
        # to subscribe to their own. Same 404 mask as read_resource.
        if uri.startswith("composition://executions/"):
            from ..orchestration.composition_resources import (
                read_execution_resource,
            )
            from uuid import UUID as _UUID
            if not user_id:
                return self._error_response(
                    request_id, -32601, f"Resource not found: {uri}"
                )
            try:
                user_uuid = _UUID(str(user_id))
            except (ValueError, TypeError):
                return self._error_response(
                    request_id, -32601, f"Resource not found: {uri}"
                )
            existence_check = await read_execution_resource(
                uri=uri, user_id=user_uuid
            )
            if existence_check is None:
                return self._error_response(
                    request_id, -32601, f"Resource not found: {uri}"
                )

        from ..orchestration.composition_resources import get_subscription_tracker
        get_subscription_tracker().subscribe(session_id, uri)
        logger.info(f"resource subscribed: session={session_id} uri={uri}")
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    async def unsubscribe_resource(
        self,
        request_id: str,
        params: Dict[str, Any],
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """``resources/unsubscribe``."""
        uri = params.get("uri")
        if not uri:
            return self._error_response(request_id, -32602, "Missing 'uri' parameter")
        if not session_id:
            return self._error_response(
                request_id, -32602, "Subscriptions require an MCP session"
            )
        from ..orchestration.composition_resources import get_subscription_tracker
        removed = get_subscription_tracker().unsubscribe(session_id, uri)
        logger.info(
            f"resource unsubscribe: session={session_id} uri={uri} "
            f"removed={removed}"
        )
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    async def list_prompts(self, request_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        List available prompts (templates for using the gateway).
        """
        prompts = [
            {
                "name": "tool_discovery",
                "description": "Discover tools available in the MCP Gateway and learn how to use them effectively",
                "arguments": []
            },
            {
                "name": "compose_workflow",
                "description": "Guide for composing a multi-step workflow using available tools",
                "arguments": [
                    {
                        "name": "goal",
                        "description": "What you want to accomplish with the workflow",
                        "required": True
                    }
                ]
            },
            {
                "name": "tool_usage",
                "description": "Get detailed usage instructions for a specific tool",
                "arguments": [
                    {
                        "name": "tool_name",
                        "description": "The full name of the tool (e.g., 'github__create_issue')",
                        "required": True
                    }
                ]
            },
            {
                "name": "server_overview",
                "description": "Get an overview of all connected MCP servers and their capabilities",
                "arguments": []
            }
        ]

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "prompts": prompts
            }
        }

    async def get_prompt(self, request_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get a specific prompt template with rendered content.
        """
        prompt_name = params.get("name")
        arguments = params.get("arguments", {})

        if not prompt_name:
            return self._error_response(request_id, -32602, "Missing 'name' parameter")

        # Build prompt content based on name
        if prompt_name == "tool_discovery":
            return await self._get_tool_discovery_prompt(request_id)
        elif prompt_name == "compose_workflow":
            goal = arguments.get("goal", "accomplish a task")
            return await self._get_compose_workflow_prompt(request_id, goal)
        elif prompt_name == "tool_usage":
            tool_name = arguments.get("tool_name")
            if not tool_name:
                return self._error_response(request_id, -32602, "Missing 'tool_name' argument for tool_usage prompt")
            return await self._get_tool_usage_prompt(request_id, tool_name)
        elif prompt_name == "server_overview":
            return await self._get_server_overview_prompt(request_id)
        else:
            return self._error_response(request_id, -32601, f"Prompt not found: {prompt_name}")

    # =========================================================================
    # Built-in Prompts
    # =========================================================================

    async def _get_tool_discovery_prompt(self, request_id: str) -> Dict[str, Any]:
        """Generate tool discovery prompt with current tools."""
        # Get all tools
        tools_response = await self.list_tools(request_id, {})
        tools = tools_response.get("result", {}).get("tools", [])

        # Group tools by server
        servers: Dict[str, List[str]] = {}
        for tool in tools:
            name = tool.get("name", "")
            if "__" in name:
                server_id = name.split("__")[0]
            else:
                server_id = "orchestrator"
            if server_id not in servers:
                servers[server_id] = []
            servers[server_id].append(name)

        # Build discovery message
        content = f"""# MCP Gateway Tool Discovery

You have access to **{len(tools)} tools** across **{len(servers)} services**.

## Available Services

"""
        for server_id, tool_names in sorted(servers.items()):
            content += f"### {server_id}\n"
            content += f"- {len(tool_names)} tools available\n"
            # Show first 5 tools as examples
            examples = tool_names[:5]
            content += f"- Examples: {', '.join(examples)}\n\n"

        content += """## How to Use Tools

1. **Tool Naming Convention**: Tools are named `{server}__{tool_name}` (double underscore separator)
2. **Call a Tool**: Use `tools/call` with the method name and arguments
3. **Find tools by intent**: Call the `search` meta-tool — it loads matched tools into your active session pool and emits `tools/list_changed`
4. **Run a goal**: Call the `execute` meta-tool with `goal=<NL>` (or `tool_name=...` / `composition_id=...` for direct invocations). The dispatcher picks the cheapest level (L0 explicit → L1 single-tool → L2 textual top-1 → L3 full LLM orchestration)

## Example Tool Call

```json
{
  "method": "tools/call",
  "params": {
    "name": "github__list_repos",
    "arguments": {"owner": "anthropics"}
  }
}
```

## Tips

- Use `prompts/get` with `tool_usage` prompt to get detailed instructions for any specific tool
- Most tools require specific parameters — check the tool's `inputSchema` for required fields
- Saved compositions appear in tools/list as `composition_<name>` and can be called directly
- Legacy `orchestrator_*` tools are no longer surfaced in tools/list but their dispatch still works for backward compatibility
"""

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "description": "Tool discovery guide for MCP Gateway",
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": content
                        }
                    }
                ]
            }
        }

    async def _get_compose_workflow_prompt(self, request_id: str, goal: str) -> Dict[str, Any]:
        """Generate workflow composition prompt."""
        content = f"""# Workflow Composition Guide

## Your Goal
{goal}

## Workflow Composition Process

### Step 1: Load relevant tools into the active pool
Call the `search` meta-tool. Matched tools are flagged in your session pool
and you receive a `notifications/tools/list_changed` so the new entries
appear in tools/list.
```json
{{
  "method": "tools/call",
  "params": {{
    "name": "search",
    "arguments": {{"query": "{goal}", "limit": 10}}
  }}
}}
```

### Step 2: Try `execute(goal=...)` first
Often the cheapest path: the dispatcher picks one tool (L1/L2) or builds a
multi-step plan (L3) without you wiring anything by hand.
```json
{{
  "method": "tools/call",
  "params": {{
    "name": "execute",
    "arguments": {{"goal": "{goal}"}}
  }}
}}
```

### Step 3: If you need a reusable saved workflow, create a composition
**IMPORTANT - Tool Naming Convention:**
- Tools are named with format: `serverprefix__toolname` (double underscore)
- Example: `grist_mcp_grist_gouv__list_organizations`, `github_perso__list_issues`
- Use the EXACT full name as shown in the tools list

**Data Flow Between Steps:**
- `${{step_N.field.path}}` - Reference previous step outputs
- `${{step_1.items[0].id}}` - Array index access
- `${{step_1.items[*].id}}` - **WILDCARD**: Extract ALL ids → `["id1", "id2", ...]`
- `${{step_1.workspaces[*].docs[*].id}}` - Nested wildcards auto-flatten

**Object Transformation with _template/_map:**
```json
{{
  "mapped_docs": {{
    "_template": "${{step_1.workspaces[*].docs[*]}}",
    "_map": {{
      "doc_id": "${{_item.id}}",
      "workspace_id": "${{_parent.id}}",
      "synced_at": "${{_now}}"
    }}
  }}
}}
```

**Context Variables in _map:**
- `${{_item}}` - Current iteration item
- `${{_parent}}` - Parent object (for nested wildcards)
- `${{_root}}` - Original step result root
- `${{_index}}` - Current iteration index (0, 1, 2...)
- `${{_now}}` - ISO timestamp

**⚠️ Structured vs prose tools — and the `transform` step:**
Not every tool returns navigable JSON. Many return a single human-readable
TEXT string at `${{step_N.structuredContent.result}}` (e.g. data.gouv.fr
tools: "Found 3 organizations... ID: 5c81..."). For those, a structured path
like `${{step_N.datasets[0].id}}` resolves to NOTHING and the step fails.
To pull a value out of prose, insert a `transform` step — it runs an LLM that
extracts a JSON object conforming to an `output_schema` you provide:
```json
{{
  "step_id": "1b",
  "type": "transform",
  "source": "${{step_1.structuredContent.result}}",
  "output_schema": {{"type":"object","properties":{{
      "datasets":{{"type":"array","items":{{"type":"object",
        "properties":{{"id":{{"type":"string"}}}},"required":["id"]}}}}}},
    "required":["datasets"]}}
}}
```
Rules:
- `source` MUST be the RAW text — almost always
  `${{step_N.structuredContent.result}}`. Never a made-up structured path.
- Reference the transform's output DIRECTLY (no `.structuredContent`):
  `${{step_1b.datasets[0].id}}`.
- Skip `transform` when a tool already returns structured fields — reference
  them directly. Use it only to bridge prose into the data-flow (1 LLM call).
- Unsure of a tool's output shape? Run it once and inspect
  `structuredContent`: a single `result` string ⇒ prose ⇒ needs transform.

**🔁 Fan-out over a list — the `foreach` step:**
When you must run a tool ONCE PER ITEM of a list (e.g. "for each dataset, get
its metrics") and that tool takes a SINGLE value (not an array), do NOT pass a
wildcard list to a single-value param — it fails validation. Use a `foreach`
step: it runs the inner `do` sub-step once per element, exposing the current
element as `${{_item}}` (and `${{_index}}`):
```json
{{
  "step_id": "3",
  "type": "foreach",
  "items": "${{step_2b.datasets[*].id}}",
  "do": {{"tool": "DataGouv__get_metrics", "parameters": {{"dataset_id": "${{_item}}"}}}}
}}
```
Its result is `{{"results": [...], "count": N, "errors": [...]}}`; reference
downstream as `${{step_3.results[*]...}}`. (If the tool itself ACCEPTS an array
param, prefer the `_template/_map` pattern in a single call instead.) Cap: 50
items per foreach.

**Save the workflow via the REST API** (or via the legacy
`orchestrator_create_composition` dispatch — still functional but no longer
exposed in tools/list):
```
POST /api/v1/compositions
{{
  "name": "My Workflow",
  "description": "{goal}",
  "steps": [
    {{"step_id": "1", "tool": "grist_mcp_grist_gouv__list_organizations", "parameters": {{}}}},
    {{"step_id": "2", "tool": "grist_mcp_grist_gouv__list_workspaces", "parameters": {{"org_id": "${{step_1.structuredContent.organizations[0].id}}"}}}}
  ]
}}
(Every step REQUIRES a unique `step_id`; `parameters` not `params`. Extra keys
are rejected.)
```

### Step 4: Execute the saved composition
Once promoted to production, the composition shows up in tools/list as
`composition_<sanitized_name>` and can be called directly.
```json
{{
  "method": "tools/call",
  "params": {{
    "name": "execute",
    "arguments": {{
      "composition_id": "<uuid>",
      "params": {{}}
    }}
  }}
}}
```

## Composition Lifecycle

1. **temporary**: Initial state, can be tested and modified
2. **validated**: Approved for regular use
3. **production**: Stable, production-ready workflow

## Tips

- **Always use full tool names** like `grist_mcp_grist_gouv__list_organizations` (serverprefix__toolname)
- Start with small compositions (2-3 steps) before building complex ones
- Use `search` first (or browse tools/list after a search) to get the exact tool names
- Reference step outputs with `${{step_N.field.path}}` syntax
- Use **wildcards `[*]`** to extract all items from arrays (auto-flattens nested wildcards)
- Use **_template/_map** to transform arrays into objects with enriched data
- The web UI under /app/compositions lists existing workflows you can reuse
- Test compositions in temporary state before promoting them
"""

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "description": f"Workflow composition guide for: {goal}",
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": content
                        }
                    }
                ]
            }
        }

    async def _get_tool_usage_prompt(self, request_id: str, tool_name: str) -> Dict[str, Any]:
        """Generate usage instructions for a specific tool."""
        # Find the tool
        tools_response = await self.list_tools(request_id, {})
        tools = tools_response.get("result", {}).get("tools", [])

        target_tool = None
        for tool in tools:
            if tool.get("name") == tool_name:
                target_tool = tool
                break

        if not target_tool:
            return self._error_response(request_id, -32601, f"Tool not found: {tool_name}")

        # Extract tool info
        name = target_tool.get("name", "")
        description = target_tool.get("description", "No description available")
        schema = target_tool.get("inputSchema", {})
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # Determine server
        if "__" in name:
            server_id = name.split("__")[0]
            short_name = name.split("__", 1)[1]
        else:
            server_id = "orchestrator"
            short_name = name

        # Build usage documentation
        content = f"""# Tool: {name}

## Description
{description}

## Server
{server_id}

## Parameters
"""
        if properties:
            for param_name, param_info in properties.items():
                param_type = param_info.get("type", "any")
                param_desc = param_info.get("description", "No description")
                is_required = "**Required**" if param_name in required else "Optional"
                default = param_info.get("default")
                default_str = f" (default: `{default}`)" if default is not None else ""

                content += f"\n### `{param_name}`\n"
                content += f"- Type: `{param_type}`\n"
                content += f"- {is_required}{default_str}\n"
                content += f"- {param_desc}\n"
        else:
            content += "\nThis tool takes no parameters.\n"

        # Add example call
        example_args = {}
        for param_name in required:
            param_info = properties.get(param_name, {})
            param_type = param_info.get("type", "string")
            if param_type == "string":
                example_args[param_name] = f"<{param_name}>"
            elif param_type == "integer" or param_type == "number":
                example_args[param_name] = 1
            elif param_type == "boolean":
                example_args[param_name] = True
            elif param_type == "object":
                example_args[param_name] = {}
            elif param_type == "array":
                example_args[param_name] = []
            else:
                example_args[param_name] = f"<{param_name}>"

        import json
        args_json = json.dumps(example_args, indent=6)
        content += f"""
## Example Usage

```json
{{
  "method": "tools/call",
  "params": {{
    "name": "{name}",
    "arguments": {args_json}
  }}
}}
```

## Notes

- Always check required parameters before calling
- This tool belongs to the `{server_id}` server
- Use the `search` meta-tool to discover similar tools by intent
"""

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "description": f"Usage instructions for {name}",
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": content
                        }
                    }
                ]
            }
        }

    async def _get_server_overview_prompt(self, request_id: str) -> Dict[str, Any]:
        """Generate server overview prompt."""
        # Get all tools to count by server
        tools_response = await self.list_tools(request_id, {})
        tools = tools_response.get("result", {}).get("tools", [])

        # Group by server with descriptions
        servers: Dict[str, Dict[str, Any]] = {}
        for tool in tools:
            name = tool.get("name", "")
            if "__" in name:
                server_id = name.split("__")[0]
            else:
                server_id = "orchestrator"

            if server_id not in servers:
                servers[server_id] = {
                    "tools": [],
                    "sample_descriptions": []
                }
            servers[server_id]["tools"].append(name)
            if len(servers[server_id]["sample_descriptions"]) < 3:
                servers[server_id]["sample_descriptions"].append(tool.get("description", "")[:100])

        content = f"""# MCP Gateway Server Overview

The MCP Gateway aggregates tools from **{len(servers)} MCP servers** into a unified interface.

## Connected Servers

"""
        for server_id, info in sorted(servers.items()):
            tool_count = len(info["tools"])
            content += f"### {server_id}\n"
            content += f"- **{tool_count} tools** available\n"
            content += f"- Sample tools:\n"
            for tool_name in info["tools"][:5]:
                content += f"  - `{tool_name}`\n"
            content += "\n"

        content += """## Architecture

```
┌─────────────────────────────────────────┐
│           MCP Gateway                    │
│  (Unified tool access & orchestration)  │
├─────────────────────────────────────────┤
│  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ Server1 │ │ Server2 │ │ Server3 │   │
│  │ (tools) │ │ (tools) │ │ (tools) │   │
│  └─────────┘ └─────────┘ └─────────┘   │
└─────────────────────────────────────────┘
```

## Key Features

1. **Unified Access**: All tools accessible through single endpoint
2. **Tool Discovery**: Semantic search across all servers
3. **Workflow Composition**: Chain tools into reusable workflows
4. **Orchestration**: AI-powered intent analysis and execution planning

## Getting Started

1. Call the `search` meta-tool with a natural-language query — matched tools land in your active session pool
2. Inspect `tools/list` to see what was loaded (a `tools/list_changed` notification is emitted on every search)
3. Call `execute` with `goal=<NL>` for orchestrated runs, or `tool_name=<X>` / `composition_id=<id>` for direct invocations
4. Use `prompts/get` with `tool_usage` for specific tool instructions
"""

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "description": "Overview of connected MCP servers",
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": content
                        }
                    }
                ]
            }
        }

    # Helper methods

    def _normalize_parameters(self, parameters: Any) -> Dict[str, Any]:
        """
        Normalize parameters to JSON Schema format.

        Handles multiple input formats:
        - Already JSON Schema (type: object, properties, etc.)
        - Array of parameter definitions
        - Flat dictionary
        """
        if isinstance(parameters, dict):
            # Check if already JSON Schema
            if "type" in parameters and parameters["type"] == "object":
                return parameters

            # If has properties, assume it's schema-like
            if "properties" in parameters:
                return {
                    "type": "object",
                    "properties": parameters.get("properties", {}),
                    "required": parameters.get("required", [])
                }

            # Convert flat dict to schema
            properties = {}
            required = []

            for key, value in parameters.items():
                if isinstance(value, dict):
                    properties[key] = value
                    if value.get("required", False):
                        required.append(key)
                else:
                    properties[key] = {"type": "string", "description": str(value)}

            return {
                "type": "object",
                "properties": properties,
                "required": required
            }

        elif isinstance(parameters, list):
            # Array of parameter objects
            properties = {}
            required = []

            for param in parameters:
                if isinstance(param, dict) and "name" in param:
                    name = param["name"]
                    properties[name] = {
                        "type": param.get("type", "string"),
                        "description": param.get("description", "")
                    }
                    if param.get("required", False):
                        required.append(name)

            return {
                "type": "object",
                "properties": properties,
                "required": required
            }

        # Fallback to empty schema
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    # =========================================================================
    # Orchestration
    # =========================================================================

    def _get_orchestration_tools(self) -> List[Dict[str, Any]]:
        """
        Return orchestration meta-tools.

        These tools provide workflow composition capabilities.
        Delegated to mcp_gateway.orchestration.tools module.
        """
        return get_orchestration_tools()

    async def _execute_orchestration_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        tool_group_id: Optional[str] = None
    ) -> Any:
        """
        Execute an orchestration meta-tool.

        Orchestration tools operate within the same visibility scope as the client:
        - If tool_group_id is set (API Key mode), only tools from that group are visible
        - If tool_group_id is None (OAuth mode), all user's enabled tools are visible
        """
        if tool_name == "orchestrator_search_tools":
            return await self._search_tools(arguments, user_id=user_id, organization_id=organization_id, tool_group_id=tool_group_id)
        elif tool_name == "orchestrator_analyze_intent":
            return await self._analyze_intent(arguments, user_id=user_id, organization_id=organization_id)
        elif tool_name == "orchestrator_execute_composition":
            return await self._execute_composition(arguments, user_id=user_id, organization_id=organization_id)
        elif tool_name == "orchestrator_list_compositions":
            return await self.orchestration_tools.list_compositions(arguments)
        elif tool_name == "orchestrator_get_composition":
            return await self.orchestration_tools.get_composition(arguments)
        elif tool_name == "orchestrator_create_composition":
            # Fetch user tools for validation
            user_tools = []
            if user_id and organization_id:
                try:
                    user_uuid = UUID(user_id)
                    org_uuid = UUID(organization_id)
                    user_tools = await self.user_server_pool.get_user_tools(
                        user_id=user_uuid,
                        organization_id=org_uuid
                    )
                    logger.info(f"Got {len(user_tools)} user tools for composition validation")
                except Exception as e:
                    logger.error(f"Error getting user tools for validation: {e}")

            # Add user context and tools for multi-tenant tracking and validation
            arguments_with_context = {
                **arguments,
                "_user_id": user_id,
                "_organization_id": organization_id,
                "_user_tools": user_tools  # Pass user tools for validation
            }
            return await self.orchestration_tools.create_composition(arguments_with_context)
        elif tool_name == "orchestrator_promote_composition":
            return await self._promote_composition(arguments, user_id=user_id, organization_id=organization_id)
        elif tool_name == "orchestrator_delete_composition":
            return await self._delete_composition(arguments, user_id=user_id, organization_id=organization_id)
        else:
            raise ValueError(f"Unknown orchestration tool: {tool_name}")

    async def _search_tools(
        self,
        arguments: Dict[str, Any],
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        tool_group_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search for tools available to the user using semantic search.

        Uses VectorStore embeddings for natural language understanding.
        Falls back to text-based search if semantic search is unavailable.

        If tool_group_id is set, results are filtered to only include tools
        from that group (same visibility as the client).
        """
        query = arguments.get("query")
        limit = arguments.get("limit", 5)

        if not query:
            return {"error": "Missing 'query' parameter"}

        if not user_id or not organization_id:
            return {
                "error": "User context required for tool search",
                "query": query,
                "results": [],
                "count": 0
            }

        from uuid import UUID
        try:
            user_uuid = UUID(str(user_id))
            org_uuid = UUID(str(organization_id))

            # Get allowed tools if restricted to ToolGroup
            allowed_tools = None
            if tool_group_id:
                allowed_tools = await self._get_tools_in_group(tool_group_id)
                logger.info(f"_search_tools: Filtering by ToolGroup {tool_group_id} ({len(allowed_tools) if allowed_tools else 0} tools)")

            # Try semantic search first (uses VectorStore with embeddings)
            matching_tools = await self.user_server_pool.search_tools_semantic(
                user_id=user_uuid,
                query=query,
                limit=limit * 3 if allowed_tools else limit  # Get more results if filtering
            )

            # Filter by ToolGroup if restricted
            if matching_tools and allowed_tools:
                filtered_tools = []
                for tool in matching_tools:
                    server_uuid = tool.get("metadata", {}).get("server_uuid") or tool.get("server_id")
                    tool_name = tool.get("name", "")
                    if server_uuid and tool_name:
                        tool_key = (str(server_uuid), tool_name)
                        if tool_key in allowed_tools:
                            filtered_tools.append(tool)
                matching_tools = filtered_tools[:limit]
                logger.info(f"_search_tools: After ToolGroup filter: {len(matching_tools)} results")

            # If semantic search returns results, use them
            if matching_tools:
                logger.info(f"_search_tools: Semantic search returned {len(matching_tools)} results for '{query}'")
                return {
                    "query": query,
                    "results": matching_tools,
                    "count": len(matching_tools),
                    "search_type": "semantic",
                    "tool_group_filtered": tool_group_id is not None
                }

            # Fallback to text-based search if no semantic results
            logger.info(f"_search_tools: Falling back to text search for '{query}'")
            all_tools = await self.user_server_pool.get_user_tools(
                user_id=user_uuid,
                organization_id=org_uuid
            )

            # Filter by ToolGroup if restricted
            if allowed_tools:
                filtered_all = []
                for tool in all_tools:
                    server_uuid = tool.get("metadata", {}).get("server_uuid")
                    tool_name = tool.get("name", "")
                    if server_uuid and tool_name:
                        tool_key = (str(server_uuid), tool_name)
                        if tool_key in allowed_tools:
                            filtered_all.append(tool)
                all_tools = filtered_all

            # Simple text-based search as fallback
            query_lower = query.lower()
            text_results = []
            for tool in all_tools:
                tool_name = tool.get("name", "").lower()
                tool_desc = tool.get("description", "").lower()
                if query_lower in tool_name or query_lower in tool_desc:
                    text_results.append(tool)
                    if len(text_results) >= limit:
                        break

            return {
                "query": query,
                "results": text_results,
                "count": len(text_results),
                "total_available": len(all_tools),
                "search_type": "text_fallback",
                "tool_group_filtered": tool_group_id is not None
            }

        except Exception as e:
            logger.error(f"Error in _search_tools: {e}", exc_info=True)
            return {
                "error": str(e),
                "query": query,
                "results": [],
                "count": 0
            }

    async def _analyze_intent(
        self,
        arguments: Dict[str, Any],
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze user intent and propose workflow.
        Passes user's available tools to the intent analyzer.
        """
        # Get user's tools to pass as context
        available_tools = []
        if user_id and organization_id:
            from uuid import UUID
            try:
                user_uuid = UUID(str(user_id))
                org_uuid = UUID(str(organization_id))
                user_tools = await self.user_server_pool.get_user_tools(
                    user_id=user_uuid,
                    organization_id=org_uuid
                )
                available_tools = user_tools
                logger.info(f"_analyze_intent: Using {len(available_tools)} tools for user {user_id}")
            except Exception as e:
                logger.error(f"Error getting user tools for intent analysis: {e}")

        # Add available tools to arguments for the analyzer
        arguments_with_tools = {**arguments, "_available_tools": available_tools}

        # Use the OrchestrationTools analyze_intent method
        return await self.orchestration_tools.analyze_intent(arguments_with_tools)

    async def _execute_composition(
        self,
        arguments: Dict[str, Any],
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a workflow composition with user context for multi-tenant tool execution.
        """
        # Pass user context and server pool for multi-tenant execution
        arguments_with_context = {
            **arguments,
            "_user_id": user_id,
            "_organization_id": organization_id,
            "_user_server_pool": self.user_server_pool
        }

        # Use the OrchestrationTools execute_composition method
        return await self.orchestration_tools.execute_composition(arguments_with_context)

    async def _promote_composition(
        self,
        arguments: Dict[str, Any],
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Promote a composition to a new status.

        When promoted to 'production', the composition becomes a callable tool
        and the user's semantic index is rebuilt to include it.
        """
        composition_id = arguments.get("composition_id")
        target_status = arguments.get("target_status")

        if not composition_id or not target_status:
            return {
                "error": "Missing required parameters: composition_id and target_status"
            }

        try:
            # Get composition from store
            from ..orchestration.composition_store import get_composition_store
            from datetime import datetime
            composition_store = get_composition_store()

            composition = await composition_store.get(composition_id)

            if not composition:
                return {
                    "error": f"Composition not found: {composition_id}"
                }

            # Validate status transition
            current_status = composition.status
            valid_transitions = {
                "temporary": ["validated"],
                "validated": ["production"],
                "production": []
            }

            if target_status not in valid_transitions.get(current_status, []):
                return {
                    "error": f"Invalid status transition: {current_status} -> {target_status}. "
                            f"Valid transitions from {current_status}: {valid_transitions.get(current_status, [])}"
                }

            # For temporary → validated, use existing method
            if current_status == "temporary" and target_status == "validated":
                promoted_comp = await composition_store.promote_to_permanent(composition_id, "validated")
                if not promoted_comp:
                    return {
                        "error": f"Failed to promote composition {composition_id}"
                    }

                logger.info(f"Composition {composition_id} promoted: temporary -> validated")

                # Sync to database for frontend visibility
                db_composition_id = await self._sync_composition_to_database(
                    promoted_comp,
                    user_id=user_id,
                    organization_id=organization_id
                )
                if db_composition_id:
                    logger.info(f"Composition synced to database: {db_composition_id}")

                return {
                    "composition_id": composition_id,
                    "database_id": db_composition_id,
                    "previous_status": "temporary",
                    "new_status": "validated",
                    "message": f"Composition promoted to validated and synced to database"
                }

            # For validated → production
            elif current_status == "validated" and target_status == "production":
                composition.status = "production"
                composition.updated_at = datetime.now().isoformat()

                # Save as permanent with new status
                await composition_store.save_permanent(composition)

                logger.info(f"Composition {composition_id} promoted: validated -> production")

                # Sync to database for frontend visibility
                db_composition_id = await self._sync_composition_to_database(
                    composition,
                    user_id=user_id,
                    organization_id=organization_id
                )
                if db_composition_id:
                    logger.info(f"Composition synced to database: {db_composition_id}")

                # Rebuild user's semantic index to include the new production composition
                if user_id and organization_id:
                    try:
                        user_uuid = UUID(str(user_id))
                        org_uuid = UUID(str(organization_id))
                        await self.user_server_pool.rebuild_user_index(user_uuid, org_uuid)
                        logger.info(f"Semantic index rebuilt after composition promotion for user {user_id}")
                    except Exception as e:
                        logger.error(f"Failed to rebuild index after composition promotion: {e}")

                return {
                    "composition_id": composition_id,
                    "previous_status": "validated",
                    "new_status": "production",
                    "message": f"Composition promoted to production",
                    "note": "Production compositions are now available as directly callable tools"
                }

        except Exception as e:
            logger.error(f"Error promoting composition: {e}", exc_info=True)
            return {
                "error": str(e),
                "composition_id": composition_id
            }

    async def _delete_composition(
        self,
        arguments: Dict[str, Any],
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Delete a composition.

        When deleting a production composition, rebuilds the user's semantic
        index to remove it from search results.
        """
        composition_id = arguments.get("composition_id")
        force = arguments.get("force", False)

        if not composition_id:
            return {
                "error": "Missing required parameter: composition_id"
            }

        try:
            # Get composition from store
            from ..orchestration.composition_store import get_composition_store
            composition_store = get_composition_store()

            composition = await composition_store.get(composition_id)

            if not composition:
                return {
                    "error": f"Composition not found: {composition_id}"
                }

            # Check if production and force flag
            was_production = composition.status == "production"
            if was_production and not force:
                return {
                    "error": f"Cannot delete production composition without force=true flag",
                    "composition_id": composition_id,
                    "status": composition.status
                }

            # Delete composition
            await composition_store.delete(composition_id)

            logger.info(f"Composition {composition_id} deleted (status: {composition.status})")

            # Rebuild user's semantic index if we deleted a production composition
            if was_production and user_id and organization_id:
                try:
                    user_uuid = UUID(str(user_id))
                    org_uuid = UUID(str(organization_id))
                    await self.user_server_pool.rebuild_user_index(user_uuid, org_uuid)
                    logger.info(f"Semantic index rebuilt after composition deletion for user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to rebuild index after composition deletion: {e}")

            return {
                "composition_id": composition_id,
                "status": "deleted",
                "message": f"Composition {composition_id} successfully deleted"
            }

        except Exception as e:
            logger.error(f"Error deleting composition: {e}", exc_info=True)
            return {
                "error": str(e),
                "composition_id": composition_id
            }

    async def _sync_composition_to_database(
        self,
        composition: "CompositionInfo",
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Sync a composition from file store to PostgreSQL database.

        This enables compositions created via MCP/orchestration to be visible
        in the frontend UI which reads from the database.

        Args:
            composition: CompositionInfo from file store
            user_id: User ID (from JWT or composition metadata)
            organization_id: Organization ID (from JWT or composition metadata)

        Returns:
            Database composition UUID if successful, None otherwise
        """
        try:
            from ..db.session import AsyncSessionLocal
            from ..services.composition_service import CompositionService
            from ..models.composition import CompositionStatus, CompositionVisibility
            from uuid import UUID

            # Use user context from composition if available, fallback to parameters
            effective_user_id = composition.created_by or user_id
            effective_org_id = composition.organization_id or organization_id

            if not effective_user_id or not effective_org_id:
                logger.warning(
                    f"Cannot sync composition {composition.id} to database: "
                    f"missing user_id ({effective_user_id}) or organization_id ({effective_org_id})"
                )
                return None

            async with AsyncSessionLocal() as db:
                service = CompositionService(db)

                # Map status
                status_mapping = {
                    "temporary": CompositionStatus.TEMPORARY.value,
                    "validated": CompositionStatus.VALIDATED.value,
                    "production": CompositionStatus.PRODUCTION.value
                }

                # Map visibility
                visibility_mapping = {
                    "private": CompositionVisibility.PRIVATE.value,
                    "organization": CompositionVisibility.ORGANIZATION.value,
                    "public": CompositionVisibility.PUBLIC.value
                }

                # Create composition in database
                db_composition = await service.create_composition(
                    organization_id=UUID(str(effective_org_id)),
                    created_by=UUID(str(effective_user_id)),
                    name=composition.name,
                    description=composition.description or "",
                    visibility=visibility_mapping.get(composition.visibility, "private"),
                    steps=composition.steps,
                    data_mappings=composition.data_mappings,
                    input_schema=composition.input_schema,
                    output_schema=composition.output_schema,
                    server_bindings=composition.server_bindings,
                    allowed_roles=composition.allowed_roles,
                    force_org_credentials=composition.force_org_credentials,
                    status=status_mapping.get(composition.status, "validated"),
                    ttl=composition.ttl,
                    extra_metadata={
                        "file_store_id": composition.id,
                        "creation_method": composition.metadata.get("creation_method", "orchestrator"),
                        **composition.metadata
                    }
                )

                logger.info(
                    f"✅ Composition synced to database: {composition.id} -> {db_composition.id}"
                )

                return str(db_composition.id)

        except Exception as e:
            logger.error(f"Failed to sync composition to database: {e}", exc_info=True)
            return None

    # =========================================================================
    # Tool Routing & Execution
    # =========================================================================

    async def _route_tool_execution(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None
    ) -> Any:
        """
        Route tool execution to appropriate MCP server with user-specific credentials.

        This method:
        1. Finds which server provides the tool
        2. Gets user context from auth params or session
        3. Uses UserServerPool to execute with user's credentials

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            session_id: Optional session ID (legacy)
            user_id: Optional user ID (preferred - from authentication)
            organization_id: Optional organization ID (preferred - from authentication)
        """
        # Get tool metadata from UserServerPool (multi-tenant) - NOT from global registry
        all_tools = []
        if user_id and organization_id:
            from uuid import UUID
            try:
                user_uuid = UUID(str(user_id))
                org_uuid = UUID(str(organization_id))
                all_tools = await self.user_server_pool.get_user_tools(
                    user_id=user_uuid,
                    organization_id=org_uuid
                )
                logger.info(f"_route_tool_execution: Got {len(all_tools)} tools for user {user_id}")

                # Auto-recovery: trigger when the REQUESTED tool isn't among the
                # currently-running servers' tools — not only when the pool is
                # totally empty. A direct execute(tool_name=...) for a server
                # that simply hasn't been started yet (other servers may be
                # running) must still resolve + start that server, mirroring the
                # L3 orchestration path. Strategy:
                #   1. Check cache for tool routing info → start ONLY the needed server
                #   2. Fallback: start ALL configured servers if cache miss
                def _tool_present(tools: list) -> bool:
                    if any(t.get("name") == tool_name for t in tools):
                        return True
                    if "__" in tool_name:
                        pfx, orig = tool_name.split("__", 1)
                        for t in tools:
                            md = t.get("metadata", {}) or {}
                            if md.get("original_tool_name") != orig:
                                continue
                            disp = re.sub(r'[^a-zA-Z0-9_]', '_', md.get("server_display_name", ""))
                            disp = re.sub(r'_+', '_', disp).strip('_')
                            if disp == pfx:
                                return True
                    return False

                if not _tool_present(all_tools):
                    from ..services.user_tool_cache import get_user_tool_cache
                    tool_cache = get_user_tool_cache()

                    target_server_id = None

                    # Most reliable resolution: map the display-name prefix to a
                    # server UUID via the DB — the SAME mechanism the L3
                    # orchestration path uses. Works even when the server has
                    # never run this session and isn't in the tool cache yet.
                    try:
                        resolved = await self.orchestration_tools.composition_executor._resolve_server_from_prefix(
                            tool_name, str(user_uuid), str(org_uuid), self.user_server_pool, {}
                        )
                        if resolved:
                            target_server_id = resolved[0]
                            logger.info(
                                f"_route_tool_execution: resolved '{tool_name}' to server "
                                f"{target_server_id} via DB prefix map"
                            )
                    except Exception as e:
                        logger.warning(f"_route_tool_execution: prefix→DB resolution failed: {e}")

                    cached_tools = await tool_cache.get(user_uuid) if target_server_id is None else None
                    if target_server_id is None and cached_tools:
                        # Find the requested tool in cache to get its server_id
                        for ct in cached_tools:
                            ct_name = ct.get("name", "")
                            if ct_name == tool_name:
                                target_server_id = ct.get("_server_id") or ct.get("metadata", {}).get("server_uuid")
                                break
                            # Also check prefixed tool names (ServerName__tool_name)
                            if "__" in tool_name:
                                prefix, original = tool_name.split("__", 1)
                                ct_original = ct.get("metadata", {}).get("original_tool_name", "")
                                ct_server_prefix = ct.get("metadata", {}).get("server_display_name", "").replace("-", "_")
                                ct_server_prefix = re.sub(r'[^a-zA-Z0-9_]', '_', ct_server_prefix)
                                ct_server_prefix = re.sub(r'_+', '_', ct_server_prefix).strip('_')
                                if ct_original == original and ct_server_prefix == prefix:
                                    target_server_id = ct.get("_server_id") or ct.get("metadata", {}).get("server_uuid")
                                    break

                    if target_server_id:
                        # Fast path: start only the specific server needed for this tool
                        logger.info(
                            f"_route_tool_execution: 0 live tools for user {user_id}, "
                            f"cache hit → starting server {target_server_id} for tool {tool_name}"
                        )
                        try:
                            await self.user_server_pool.get_or_start_server(
                                user_id=user_uuid,
                                server_id=UUID(str(target_server_id)),
                                organization_id=org_uuid
                            )
                        except Exception as e:
                            logger.warning(
                                f"Fast path failed for server {target_server_id}: {e}, "
                                "falling back to starting all configured servers"
                            )
                            # Fallback to slow path: server may have been deleted/disabled
                            try:
                                await self.user_server_pool.ensure_configured_servers_started(
                                    user_id=user_uuid,
                                    organization_id=org_uuid
                                )
                            except Exception as e2:
                                logger.error(f"Slow path fallback also failed: {e2}")
                    else:
                        # Slow path: no cache or tool not found in cache, start all servers
                        logger.info(
                            f"_route_tool_execution: 0 tools for user {user_id}, "
                            "no cache match → starting all configured servers"
                        )
                        await self.user_server_pool.ensure_configured_servers_started(
                            user_id=user_uuid,
                            organization_id=org_uuid
                        )

                    # Retry getting tools after server startup
                    all_tools = await self.user_server_pool.get_user_tools(
                        user_id=user_uuid,
                        organization_id=org_uuid
                    )
                    logger.info(
                        f"_route_tool_execution: After auto-recovery, got {len(all_tools)} tools "
                        f"for user {user_id}"
                    )
            except Exception as e:
                logger.error(f"Error getting user tools for routing: {e}")

        tool_info = None

        # Try exact name match first
        for tool in all_tools:
            if tool.get("name") == tool_name:
                tool_info = tool
                break

        # If not found, try parsing prefixed tool name
        # Format: server_id__tool_name (double underscore as separator from list_tools)
        if not tool_info and "__" in tool_name:
            # Split on double underscore (our standard separator)
            parts = tool_name.split("__", 1)
            if len(parts) == 2:
                server_prefix = parts[0]
                original_tool_name = parts[1]
                logger.info(f"Parsing prefixed tool: prefix={server_prefix}, original={original_tool_name}")

                # Find tool by original name AND matching server prefix.
                # The prefix is the sanitized SERVER DISPLAY NAME — exactly how
                # get_user_tools builds the prefixed `name` (NOT the server_id).
                # Handles multi-instance scenarios (e.g., github_perso vs github_work).
                for tool in all_tools:
                    tool_metadata = tool.get("metadata", {})
                    tool_original = tool_metadata.get("original_tool_name", "")
                    disp = tool_metadata.get("server_display_name", "")
                    tool_prefix = re.sub(r'[^a-zA-Z0-9_]', '_', disp)
                    tool_prefix = re.sub(r'_+', '_', tool_prefix).strip('_')

                    # Match by BOTH original name AND server prefix
                    if tool_original == original_tool_name and tool_prefix == server_prefix:
                        tool_info = tool
                        logger.info(f"✅ Found tool: {original_tool_name} (server: {disp})")
                        break

                # Fallback: if no exact server match, try just tool name (single server scenario)
                if not tool_info:
                    for tool in all_tools:
                        if tool.get("name") == original_tool_name:
                            tool_info = tool
                            logger.info(f"✅ Found tool by name only: {original_tool_name}")
                            break

        # Legacy fallback: try dot separator (server.tool format)
        if not tool_info and "." in tool_name:
            parts = tool_name.rsplit(".", 1)
            if len(parts) == 2:
                potential_name = parts[1]
                logger.info(f"Trying legacy format: {potential_name} (from {tool_name})")
                for tool in all_tools:
                    if tool.get("name") == potential_name:
                        tool_info = tool
                        logger.info(f"✅ Found tool using legacy name: {potential_name}")
                        break

        if not tool_info:
            available_names = [t.get('name') for t in all_tools[:20]]
            logger.error(f"Tool not found: {tool_name}. Available tools ({len(all_tools)}): {available_names}")
            raise ValueError(f"Tool not found: {tool_name}")

        logger.debug(f"Found tool: {tool_name}, id={tool_info.get('id')}, server_id={tool_info.get('server_id')}")

        # Extract server UUID with multiple fallbacks
        # Priority: UUID fields first, then string-based fallbacks
        metadata = tool_info.get("metadata", {})

        # Fallback 1: _server_id (UUID string added by UserServerPool.get_user_tools)
        server_id = tool_info.get("_server_id")

        # Fallback 2: metadata.server_uuid (UUID string for routing)
        if not server_id:
            server_id = metadata.get("server_uuid")

        # Fallback 3: server_info.id (added by _enrich_tool_metadata)
        if not server_id:
            server_info = tool_info.get("server_info", {})
            server_id = server_info.get("id")

        # Fallback 4: tool_info.server_id (might be UUID or string)
        if not server_id:
            server_id = tool_info.get("server_id")

        # Fallback 5: extract from tool ID (format: server_id.tool_name)
        if not server_id:
            tool_full_id = tool_info.get("id", "")
            if "." in tool_full_id:
                server_id = tool_full_id.split(".", 1)[0]

        if not server_id:
            logger.error(f"Cannot extract server_id for tool: {tool_name}. tool_info: {tool_info}")
            raise ValueError(f"No server_id found for tool: {tool_name}")

        # Extract original tool name (may differ from tool_name if aliased)
        metadata = tool_info.get("metadata", {})
        # Use the actual tool name found, not the input tool_name which may include server_id prefix
        original_tool_name = metadata.get("original_tool_name", tool_info.get("name", tool_name))

        logger.debug(f"Extracted server_id: {server_id}, original_tool_name: {original_tool_name}")

        # Get user context: Priority to provided params, fallback to session
        if not user_id and session_id:
            session = await self.session_store.get_metadata(session_id)
            if session:
                user_id = session.get("user_id")
                organization_id = session.get("organization_id")

        if not user_id:
            # No user context - fallback to global servers (insecure, legacy behavior)
            logger.warning(f"No user context for tool execution, using global servers (INSECURE!)")
            result = await self.registry.execute_tool(server_id, original_tool_name, arguments)
            return result

        logger.info(f"Executing tool {tool_name} for user {user_id} on server {server_id}")

        # Execute tool with user-specific credentials via UserServerPool
        from uuid import UUID
        result = await self.user_server_pool.execute_tool(
            user_id=UUID(str(user_id)),
            server_id=UUID(str(server_id)),
            tool_name=original_tool_name,
            parameters=arguments,
            organization_id=UUID(str(organization_id)) if organization_id else None
        )

        return result

    def _error_response(self, request_id: str, code: int, message: str) -> Dict[str, Any]:
        """
        Create JSON-RPC error response.
        """
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message
            }
        }


# Gateway instance
gateway = MCPUnifiedGateway()


# SSE Endpoint
@router.get("/sse")
async def mcp_sse_endpoint(
    request: Request,
    auth: tuple = Depends(get_current_user)
):
    """
    Primary SSE endpoint for MCP protocol (MCP 2025-03-26).

    Accepts: MCPHub API Key (mcphub_sk_*) or OAuth JWT access token
    Format: Authorization: Bearer <token>

    Implements Server-Sent Events stream for server→client notifications.
    Supports:
    - Tool discovery notifications (notifications/tools/list_changed)
    - Session management
    - Keepalive pings
    """
    user, api_key = auth  # get_current_user returns (user, api_key|None)

    # MCP 2025-06-18 §6.3.1: clients may pass `Mcp-Session-Id` to resume an
    # existing session. We honour that when the metadata is still in Redis
    # (e.g. after a backend restart) so reconnecting clients keep their
    # session_id and don't have to redo `initialize`. Otherwise allocate a
    # fresh UUID — the new id is published back via the SSE response headers.
    requested_sid = request.headers.get("mcp-session-id") or request.headers.get("X-Session-ID")
    store = get_session_store()
    resumed = False
    if requested_sid:
        existing = await store.get_metadata(requested_sid)
        if existing and str(existing.get("user_id")) == str(user.id):
            session_id = requested_sid
            resumed = True
        else:
            session_id = str(uuid.uuid4())
    else:
        session_id = str(uuid.uuid4())

    # Resolve organization_id for both API Key and OAuth JWT clients.
    # API Key: organization is fixed by the key.
    # OAuth JWT: extracted from token org_id claim, or single-org fallback.
    # This mirrors the pattern used in handle_mcp_message for POST requests.
    organization_id = None
    if api_key:
        organization_id = api_key.organization_id
    else:
        # OAuth client: use _resolve_organization (handles JWT org_id claim + single-org fallback)
        try:
            _, organization_id = _resolve_organization(request, user, None)
        except HTTPException:
            # Last-resort fallback: single membership (avoids rejecting valid single-org OAuth users)
            if user.organization_memberships:
                organization_id = user.organization_memberships[0].organization_id

    auth_info = f"API Key: {api_key.name}" if api_key else "OAuth token"
    logger.info(
        f"Authenticated MCP connection - User: {user.email}, {auth_info}, "
        f"Session: {session_id}{' (resumed)' if resumed else ''}"
    )

    async def event_generator() -> AsyncGenerator[Dict[str, Any], None]:
        """Generate SSE events for the client."""

        # Create or rebind the session.
        # - Fresh session: persist metadata in Redis (TTL-bounded) and bind a queue.
        # - Resumed session (post-restart reconnect): metadata already in Redis,
        #   we just attach a fresh in-process queue.
        if resumed:
            queue = await store.attach_local_queue(session_id)
            if queue is None:
                # Race: metadata expired between the GET handler and here.
                # Fall back to a brand-new session.
                queue = await store.create(session_id, {
                    "user_id": user.id,
                    "organization_id": organization_id,
                    "api_key_id": api_key.id if api_key else None,
                    "user_email": user.email,
                    "tool_group_id": api_key.tool_group_id if api_key else None,
                })
        else:
            queue = await store.create(session_id, {
                "user_id": user.id,
                "organization_id": organization_id,
                "api_key_id": api_key.id if api_key else None,
                "user_email": user.email,
                "tool_group_id": api_key.tool_group_id if api_key else None,
            })

        session_started_at = time.time()
        logger.info(f"New SSE connection: {session_id}")

        try:
            # Send keepalive pings
            last_ping = time.time()
            last_touch = time.time()

            while True:
                # Check for client disconnect
                if await request.is_disconnected():
                    logger.info(f"Client disconnected: {session_id}")
                    break

                # Detect external session deletion (e.g. legacy_kill, DELETE /,
                # or background refresh closing the session). The local queue
                # is removed by `store.delete()`, so its absence is the signal.
                if not store.has_local_queue(session_id):
                    logger.warning(f"Session {session_id} no longer registered, ending SSE stream")
                    break

                # Hard upper bound on a single SSE connection — TTL refresh
                # in Redis happens via `touch()` below, so the session itself
                # can outlive any individual SSE socket.
                session_age = time.time() - session_started_at
                if session_age > SESSION_TIMEOUT_SECONDS:
                    logger.info(
                        f"Session {session_id} reached SSE keepalive ceiling after "
                        f"{session_age:.0f}s (limit: {SESSION_TIMEOUT_SECONDS}s)"
                    )
                    break

                # Check message queue for notifications (NON-BLOCKING)
                try:
                    # Non-blocking check for queued messages
                    message = queue.get_nowait()
                    yield message
                    logger.info(f"Sent notification to session {session_id}")
                except asyncio.QueueEmpty:
                    pass  # No messages waiting, continue

                # Send keepalive ping
                now = time.time()
                if now - last_ping >= KEEPALIVE_INTERVAL_SECONDS:
                    yield {
                        "event": "ping",
                        "data": json.dumps({
                            "type": "ping",
                            "timestamp": datetime.now().isoformat()
                        })
                    }
                    last_ping = now

                # Refresh Redis TTL on the metadata roughly once per keepalive
                # interval so live SSE streams keep their session metadata
                # warm without flooding Redis on every loop tick.
                if now - last_touch >= KEEPALIVE_INTERVAL_SECONDS:
                    try:
                        await store.touch(session_id)
                    except Exception as e:  # noqa: BLE001
                        logger.debug(f"session_store.touch failed for {session_id}: {e}")
                    last_touch = now

                # Wait a bit before next iteration
                await asyncio.sleep(1)

        finally:
            # Cleanup: drop both metadata + local queue. A subsequent reconnect
            # with the same Mcp-Session-Id falls through to a brand new session.
            try:
                await store.delete(session_id)
                logger.info(f"Session cleaned up: {session_id}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"session_store.delete failed for {session_id}: {e}")

    return EventSourceResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Session-ID": session_id,
            "Mcp-Session-Id": session_id
        }
    )


# Internal handler for MCP messages (shared logic)
async def handle_mcp_message(request: Request, auth: Optional[tuple]):
    """
    Internal handler for JSON-RPC 2.0 messages from MCP clients.

    This function contains the actual message handling logic and can be called
    from both the /mcp/message endpoint and the / proxy endpoint.

    Args:
        request: FastAPI Request object
        auth: Tuple of (user, api_key) from authentication, or None for unauthenticated

    Returns:
        JSONResponse with JSON-RPC 2.0 formatted response
    """
    # Peek at the method before auth check so initialize always works
    try:
        body_peek = await request.json()
        peek_method = body_peek.get("method")
    except Exception:
        body_peek = None
        peek_method = None

    # initialize is allowed without auth (MCP spec: announces capabilities)
    if auth is None and peek_method != "initialize":
        # Re-raise proper OAuth discovery 401 for authenticated methods
        from ..api.dependencies import get_current_user as _require_auth
        scheme = request.headers.get("x-forwarded-proto", "https")
        host = request.headers.get("host", "localhost")
        base_url = f"{scheme}://{host}"
        resource_metadata_url = f"{base_url}/.well-known/oauth-protected-resource"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "unauthorized",
                "error_description": "Authentication required",
                "oauth_discovery": f"{base_url}/.well-known/oauth-authorization-server",
                "authorization_endpoint": f"{base_url}/api/v1/oauth/authorize",
                "token_endpoint": f"{base_url}/api/v1/oauth/token",
            },
            headers={"WWW-Authenticate": f'Bearer resource_metadata="{resource_metadata_url}"'},
        )

    # Extract authenticated user (may be None only for initialize)
    user = api_key = None
    if auth is not None:
        user, api_key = auth
        logger.info(f"✅ MCP message from authenticated user: {user.email} (user_id={user.id})")

    # Get organization context
    organization_id = None
    if user and user.organization_memberships:
        from ..api.dependencies import _resolve_organization
        try:
            _, organization_id = _resolve_organization(request, user, api_key)
        except HTTPException:
            # MCP gateway fallback: single-org users still work
            if len(user.organization_memberships) == 1:
                organization_id = user.organization_memberships[0].organization_id
        logger.info(f"User organization_id={organization_id}")

    # Re-use body already parsed during auth peek (avoids double read of request stream)
    body = body_peek
    try:
        if body is None:
            body = await request.json()

        # Extract JSON-RPC fields
        jsonrpc = body.get("jsonrpc")
        request_id = body.get("id")
        method = body.get("method")
        params = body.get("params", {})

        # Extract session ID from Mcp-Session-Id header (MCP 2025-03-26 spec)
        # Fall back to X-Session-ID for backward compatibility
        session_id = request.headers.get("mcp-session-id") or request.headers.get("X-Session-ID")

        if jsonrpc != "2.0":
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32600,
                    "message": "Invalid JSON-RPC version"
                }
            })

        # Route to appropriate handler
        if method == "initialize":
            response = await gateway.initialize(request_id, params)
            # MCP 2025-03-26: re-use the client-supplied Mcp-Session-Id
            # if one is present (handshake on reconnect) so any queued
            # notifications/resources/updated for that session can flush.
            # Otherwise, mint a fresh one.
            initialize_session_id = session_id or str(uuid.uuid4())
            # B-0 chunk 9: drain pending_notification rows for this
            # session_id. Background task — never blocks the
            # initialize response. The push helper's bool return tells
            # flush whether to delete the row or leave it for later.
            try:
                from ..orchestration.composition_resources import (
                    flush_pending_notifications,
                )
                asyncio.create_task(
                    flush_pending_notifications(
                        initialize_session_id,
                        live_pusher=push_resource_updated_to_session,
                    )
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "failed to schedule pending_notification flush",
                    exc_info=True,
                )
            return JSONResponse(
                response,
                headers={"Mcp-Session-Id": initialize_session_id}
            )
        elif method == "tools/list":
            # Pass user context from authenticated user
            # Include tool_group_id from API key for filtering
            tool_group_id = str(api_key.tool_group_id) if api_key and api_key.tool_group_id else None
            # OAuth client = no API key (authenticated via OAuth token)
            is_oauth = api_key is None
            response = await gateway.list_tools(
                request_id,
                params,
                session_id=session_id,
                user_id=str(user.id),
                organization_id=str(organization_id) if organization_id else None,
                tool_group_id=tool_group_id,
                is_oauth_client=is_oauth
            )
        elif method == "tools/call":
            # Pass user context from authenticated user
            # Include tool_group_id from API key for access validation
            tool_group_id = str(api_key.tool_group_id) if api_key and api_key.tool_group_id else None
            response = await gateway.call_tool(
                request_id,
                params,
                session_id=session_id,
                user_id=str(user.id),
                organization_id=str(organization_id) if organization_id else None,
                tool_group_id=tool_group_id
            )
        elif method == "resources/list":
            response = await gateway.list_resources(
                request_id, params,
                user_id=str(user.id) if user else None,
            )
        elif method == "resources/read":
            response = await gateway.read_resource(
                request_id, params,
                user_id=str(user.id) if user else None,
            )
        elif method == "resources/subscribe":
            response = await gateway.subscribe_resource(
                request_id, params,
                session_id=session_id,
                user_id=str(user.id) if user else None,
            )
        elif method == "resources/unsubscribe":
            response = await gateway.unsubscribe_resource(
                request_id, params,
                session_id=session_id,
            )
        elif method == "prompts/list":
            response = await gateway.list_prompts(request_id, params)
        elif method == "prompts/get":
            response = await gateway.get_prompt(request_id, params)
        elif method == "ping":
            # MCP 2025-03-26: ping health check — respond with empty result
            response = {"jsonrpc": "2.0", "id": request_id, "result": {}}
        elif method and method.startswith("notifications/"):
            # MCP 2025-03-26 / JSON-RPC 2.0: client notifications have no 'id'
            # and MUST NOT receive a JSON-RPC response.
            # Accept silently and return HTTP 202 Accepted (no body).
            if method == "notifications/initialized":
                logger.info(f"Client initialization acknowledged (session: {session_id})")
            else:
                logger.debug(f"Received client notification: {method}")
            return Response(status_code=202)
        else:
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }

        # MCP 2025-03-26: echo Mcp-Session-Id in all responses
        resp_headers = {}
        if session_id:
            resp_headers["Mcp-Session-Id"] = session_id

        # MCP 2025-03-26 §6.3.2 Streamable HTTP: if the client accepts SSE on POST,
        # we can send the JSON-RPC response AND any pending notifications in the same
        # stream. Claude Desktop uses per-request short-lived SSE sessions, so this
        # is the only reliable way to deliver tools/list_changed notifications to it.
        accept_header = request.headers.get("accept", "")
        logger.info(
            f"POST /{method} — Accept: '{accept_header}' | "
            f"pending_notification: {pending_org_notifications.get(str(organization_id), False)}"
        )
        if "text/event-stream" in accept_header and user and organization_id:
            org_id_str = str(organization_id)
            # Atomically drain the pending flag (asyncio single-threaded → no race)
            has_pending_notification = pending_org_notifications.pop(org_id_str, False)

            if has_pending_notification:
                logger.info(
                    f"Streamable HTTP SSE: delivering tools/list_changed inline with "
                    f"{method} response for user {user.email} (org {org_id_str})"
                )

            async def _sse_stream(
                _response=response,
                _notification=has_pending_notification,
                _method=method,
                _org=org_id_str,
                _user_email=user.email if user else "unknown",
            ) -> AsyncGenerator:
                # Event 1: the actual JSON-RPC response
                yield {"event": "message", "data": json.dumps(_response)}
                # Event 2 (conditional): pending tools/list_changed notification
                if _notification:
                    tools_changed = {
                        "jsonrpc": "2.0",
                        "method": "notifications/tools/list_changed"
                    }
                    yield {"event": "message", "data": json.dumps(tools_changed)}
                    logger.debug(
                        f"Streamable HTTP SSE: tools/list_changed delivered for "
                        f"user {_user_email} (org {_org})"
                    )

            return EventSourceResponse(_sse_stream(), headers=resp_headers)

        return JSONResponse(response, headers=resp_headers)

    except json.JSONDecodeError:
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": -32700,
                "message": "Parse error: Invalid JSON"
            }
        }, status_code=400)

    except ClientDisconnect:
        # Client disconnected before we could read the body - this is normal
        logger.debug("Client disconnected before request was processed")
        return Response(status_code=499)  # Client Closed Request

    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": body.get("id") if isinstance(body, dict) else None,
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }
        }, status_code=500)
# Message Handler - FastAPI endpoint wrapper
@router.post("/message")
async def mcp_message_handler(
    request: Request,
    auth: Optional[tuple] = Depends(get_current_user_optional)
):
    """
    Handle JSON-RPC 2.0 messages from MCP clients.

    The 'initialize' method is allowed without authentication (MCP spec compliance).
    All other methods require valid authentication (JWT or MCPHub API Key).

    This endpoint wraps the internal handler to enable FastAPI dependency injection.
    The internal handler (handle_mcp_message) can be called from both this endpoint
    and the root POST proxy endpoint (/).

    Authentication:
    - JWT Bearer token (from OAuth 2.0 flow)
    - MCPHub API Key (in Authorization: Bearer header)

    Supports:
    - initialize: Initialize MCP session
    - tools/list: List available tools for user
    - tools/call: Execute a tool
    - ping: Health check
    """
    return await handle_mcp_message(request, auth)


# Health check
@router.get("/health")
async def mcp_health_check():
    """
    Health check endpoint for monitoring.

    Returns:
    - Gateway status
    - Active sessions count
    - Tools count
    - Servers count
    - User server pool stats
    """
    try:
        servers_count = len(registry.servers)
        tools_count = len(registry.tools)
        sessions_count = get_session_store().local_count()
        pool_stats = gateway.user_server_pool.get_stats()

        return {
            "status": "healthy",
            "version": "1.0.0",
            "protocol_version": MCP_PROTOCOL_VERSION,
            "stats": {
                "active_sessions": sessions_count,
                "registered_servers": servers_count,
                "available_tools": tools_count,
                "user_server_pool": {
                    "total_users": pool_stats["total_users"],
                    "total_servers": pool_stats["total_servers"]
                }
            },
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# Pool statistics endpoint (admin only)
@router.get("/pool/stats")
async def pool_stats(
    auth: tuple = Depends(get_current_user_api_key)
):
    """
    Get detailed statistics about the UserServerPool.

    Requires: Valid MCPHub API Key in Authorization header

    Returns:
    - Per-user server counts
    - Last used timestamps
    - Total stats
    """
    api_key, user = auth

    # Get full stats from pool
    stats = gateway.user_server_pool.get_stats()

    return {
        "pool_stats": stats,
        "timestamp": datetime.now().isoformat()
    }
