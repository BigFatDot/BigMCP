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
from ..api.dependencies import get_current_user_api_key, get_current_user, get_current_user_optional
from ..orchestration.tools import OrchestrationTools
from ..core.user_server_pool import UserServerPool

# Import utilities from modular structure
from .mcp_gateway.utils import (
    parse_json_string_arguments,
    _parse_json_value,
    _error_response,
    _normalize_parameters,
)
from .mcp_gateway.orchestration import get_orchestration_tools

# Configure logging
logger = logging.getLogger("mcp_unified")

# Create router
router = APIRouter(
    prefix="/mcp",
    tags=["MCP Unified Gateway"]
)

# Get the shared registry instance
registry = get_registry()

# Session management
mcp_sessions: Dict[str, Dict[str, Any]] = {}
SESSION_TIMEOUT_SECONDS = 600  # 10 minutes
KEEPALIVE_INTERVAL_SECONDS = 30

# Protocol version
MCP_PROTOCOL_VERSION = "2025-03-26"


async def broadcast_tools_changed():
    """
    Broadcast tools/list_changed notification to all active SSE sessions.
    MCP 2024-11-05 compliant notification.

    This allows clients to automatically refresh their tools list when
    tools become available (e.g., after server initialization).
    """
    notification = {
        "jsonrpc": "2.0",
        "method": "notifications/tools/list_changed"
    }

    active_sessions = list(mcp_sessions.items())
    if not active_sessions:
        logger.debug("No active SSE sessions to notify")
        return

    for session_id, session in active_sessions:
        try:
            queue = session.get("message_queue")
            if queue:
                await queue.put({
                    "event": "message",
                    "data": json.dumps(notification)
                })
                logger.info(f"Queued tools_changed notification for session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to queue notification for {session_id}: {e}")

    logger.info(f"Broadcasted tools/list_changed to {len(active_sessions)} sessions")


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

    for session_id, session in list(mcp_sessions.items()):
        session_user_id = session.get("user_id")
        if str(session_user_id) == user_id_str:
            try:
                queue = session.get("message_queue")
                if queue:
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


async def notify_org_tools_changed(org_id) -> int:
    """
    Notify all connected MCP clients in an organization that tools have changed.

    Called after visibility changes (server or tool level) to ensure MCP clients
    (Claude Desktop, etc.) get updated tool lists.

    Strategy:
    1. ALWAYS invalidate the Redis cache for the org — so any client (SSE or
       Streamable HTTP POST) gets fresh tools on its next tools/list request.
    2. For users with active SSE sessions: also schedule a background refresh
       so the cache is warm before they re-list, and push tools/list_changed.

    Args:
        org_id: Organization UUID (or string) whose tools changed

    Returns:
        Number of SSE users scheduled for background refresh
    """
    from uuid import UUID
    org_id_str = str(org_id)
    org_uuid = org_id if isinstance(org_id, UUID) else UUID(org_id_str)

    # Step 1: ALWAYS invalidate the org cache (works for all client types,
    # including Streamable HTTP POST clients that have no SSE session).
    try:
        from ..services.user_tool_cache import get_user_tool_cache
        tool_cache = get_user_tool_cache()
        invalidated = await tool_cache.invalidate_organization(org_uuid)
        if invalidated:
            logger.info(
                f"notify_org_tools_changed: invalidated cache for {invalidated} "
                f"user(s) in org {org_id_str}"
            )
        else:
            logger.debug(f"notify_org_tools_changed: no cache entries to invalidate for org {org_id_str}")
    except Exception as e:
        logger.warning(f"notify_org_tools_changed: cache invalidation failed for org {org_id_str}: {e}")

    # Step 2: Find SSE-connected users and trigger background refresh + notification
    user_ids = set()
    for session in mcp_sessions.values():
        if str(session.get("organization_id")) == org_id_str:
            user_id = session.get("user_id")
            if user_id:
                user_ids.add(user_id)

    if not user_ids:
        logger.debug(
            f"notify_org_tools_changed: no active SSE sessions for org {org_id_str} "
            f"(cache was still invalidated above)"
        )
        return 0

    for user_id in user_ids:
        user_uuid = user_id if isinstance(user_id, UUID) else UUID(str(user_id))
        asyncio.create_task(
            gateway._background_refresh_tools(
                user_uuid=user_uuid,
                org_uuid=org_uuid
            )
        )

    logger.info(
        f"notify_org_tools_changed: org {org_id_str} — "
        f"scheduled background refresh for {len(user_ids)} SSE user(s)"
    )
    return len(user_ids)


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

    for session_id, session in list(mcp_sessions.items()):
        if org_id_str is not None:
            if str(session.get("organization_id")) != org_id_str:
                continue
        try:
            queue = session.get("message_queue")
            if queue:
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
        self.sessions = mcp_sessions
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
                    "This gateway aggregates tools from multiple MCP servers "
                    "and provides intelligent orchestration capabilities. "
                    "Use orchestrator_* tools for workflow composition."
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

        try:
            # Get database session
            async for db in get_async_session():
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
                all_server_ids = list(user_server_ids | valid_non_user_server_ids)

                logger.info(
                    f"Found {len(all_server_ids)} servers to start "
                    f"(user_creds: {len(user_server_ids)}, other_valid: {len(valid_non_user_server_ids)}, "
                    f"skipped_team: {skipped_team_count}) for user {user_id}"
                )

                return all_server_ids

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

                    # 4b. Notify this user's SSE sessions
                    notified = await broadcast_tools_changed_for_user(user_uuid)

                    added = fresh_names - cached_names
                    removed = cached_names - fresh_names
                    logger.info(
                        f"Background refresh for user {user_uuid}: "
                        f"tools changed ({len(cached_names)}→{len(fresh_names)}, "
                        f"+{len(added)} -{len(removed)}), "
                        f"cache updated, {notified} session(s) notified"
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
            if not user_id and session_id and session_id in self.sessions:
                session = self.sessions[session_id]
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
                            # Get all tools for user's org with their server info
                            filters = [
                                Tool.organization_id == org_uuid,
                                MCPServer.enabled == True
                            ]
                            # OAuth clients only see visible tools/servers
                            if is_oauth_client:
                                filters.append(Tool.is_visible_to_oauth_clients == True)
                                filters.append(MCPServer.is_visible_to_oauth_clients == True)
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
            # VISIBILITY FILTER: OAuth clients only see visible tools/servers
            # Cache contains ALL tools (shared across auth methods),
            # so we filter by querying visible server UUIDs from DB.
            # This covers both cache HIT and background refresh paths.
            # =====================================================================
            if is_oauth_client and all_tools:
                try:
                    from ..db.database import get_async_session
                    from sqlalchemy import select as sa_select
                    from ..models.mcp_server import MCPServer as MCPServerModel

                    visible_server_uuids = set()
                    async for db in get_async_session():
                        stmt = (
                            sa_select(MCPServerModel.id)
                            .where(
                                MCPServerModel.organization_id == org_uuid,
                                MCPServerModel.enabled == True,
                                MCPServerModel.is_visible_to_oauth_clients == True
                            )
                        )
                        result = await db.execute(stmt)
                        visible_server_uuids = {str(row[0]) for row in result.all()}
                        break

                    original_count = len(all_tools)
                    all_tools = [
                        t for t in all_tools
                        if t.get("metadata", {}).get("server_uuid") in visible_server_uuids
                        or t.get("_server_id") in visible_server_uuids
                    ]
                    logger.info(
                        f"OAuth visibility filter: {original_count} -> {len(all_tools)} tools "
                        f"({len(visible_server_uuids)} visible servers)"
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
                description = tool.get("description", "")
                if server_display_name and not description.startswith(f"[{server_display_name}]"):
                    description = f"[{server_display_name}] {description}"

                mcp_tool = {
                    "name": unique_name,
                    "description": description,
                    "inputSchema": parameters
                }

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

                # Add metadata as custom field (for internal routing)
                metadata = tool.get("metadata", {}).copy() if "metadata" in tool else {}
                # Store original tool name for routing
                metadata["original_tool_name"] = original_name
                # server_id should already be in metadata from UserServerPool
                mcp_tool["_metadata"] = metadata

                mcp_tools.append(mcp_tool)

            # Add orchestration tools
            orchestration_tools = self._get_orchestration_tools()
            mcp_tools.extend(orchestration_tools)

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

                    mcp_tool = {
                        "name": tool_name,
                        "description": description,
                        "inputSchema": input_schema,
                        "_metadata": {
                            "is_composition": True,
                            "composition_id": comp_id_str,
                            "composition_name": comp_name,
                            "display_name": f"Composition: {comp_name}",
                            "steps_count": len(comp.steps) if comp.steps else 0
                        }
                    }

                    mcp_tools.append(mcp_tool)

                if production_compositions:
                    logger.info(f"Added {len(production_compositions)} production compositions as tools")

            except Exception as e:
                logger.error(f"Error loading production compositions: {e}", exc_info=True)
                # Don't fail tools listing if compositions fail to load

            logger.info(f"Returning {len(mcp_tools)} tools to client (including compositions)")

            # MCP 2025-03-26: cursor-based pagination
            cursor = params.get("cursor")
            page_size = 100
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

        try:
            # Validate tool access if restricted to ToolGroup
            # Skip validation for orchestration tools (always allowed) and workflows
            if tool_group_id and not tool_name.startswith("orchestrator_") and not tool_name.startswith("workflow_"):
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

            # Check if it's an orchestration tool
            if tool_name.startswith("orchestrator_"):
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

                # Execute via orchestration tools with user context for multi-tenant execution
                result = await self.orchestration_tools.execute_composition({
                    "composition_id": composition_id,
                    "parameters": tool_arguments,
                    "_user_id": user_id,
                    "_organization_id": organization_id,
                    "_user_server_pool": self.user_server_pool
                })
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

                # Execute via orchestration tools with user context for multi-tenant execution
                result = await self.orchestration_tools.execute_composition({
                    "composition_id": composition_id,
                    "parameters": tool_arguments,
                    "_user_id": user_id,
                    "_organization_id": organization_id,
                    "_user_server_pool": self.user_server_pool
                })
            else:
                # Route to appropriate MCP server (with user context)
                result = await self._route_tool_execution(
                    tool_name,
                    tool_arguments,
                    session_id=session_id,
                    user_id=user_id,
                    organization_id=organization_id
                )

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, ensure_ascii=False, indent=2)
                        }
                    ],
                    "isError": False
                }
            }

        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
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
                    "isError": True
                }
            }

    async def list_resources(self, request_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        List available resources (compositions).

        Exposes saved compositions as MCP resources.
        """
        try:
            from ..orchestration.composition_store import get_composition_store
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

            logger.info(f"Returning {len(resources)} composition resources")

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

    async def read_resource(self, request_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Read a specific resource (composition details).
        """
        uri = params.get("uri")

        if not uri:
            return self._error_response(request_id, -32602, "Missing 'uri' parameter")

        try:
            # Parse URI: composition://{status}/{id}
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
3. **Search Tools**: Use `orchestrator_search_tools` to find tools by natural language description
4. **Compose Workflows**: Use `orchestrator_analyze_intent` to plan multi-step operations

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
- Most tools require specific parameters - check the tool's `inputSchema` for required fields
- Orchestrator tools help you compose complex workflows from simple tools
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

### Step 1: Analyze Intent
Use `orchestrator_analyze_intent` to analyze what you want to accomplish:
```json
{{
  "method": "tools/call",
  "params": {{
    "name": "orchestrator_analyze_intent",
    "arguments": {{"query": "{goal}"}}
  }}
}}
```

### Step 2: Search for Relevant Tools
Find tools that can help accomplish parts of your goal:
```json
{{
  "method": "tools/call",
  "params": {{
    "name": "orchestrator_search_tools",
    "arguments": {{"query": "{goal}", "limit": 10}}
  }}
}}
```

### Step 3: Create a Composition
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

**Example Composition:**
```json
{{
  "method": "tools/call",
  "params": {{
    "name": "orchestrator_create_composition",
    "arguments": {{
      "name": "My Workflow",
      "description": "{goal}",
      "steps": [
        {{"tool": "grist_mcp_grist_gouv__list_organizations", "parameters": {{}}}},
        {{"tool": "grist_mcp_grist_gouv__list_workspaces", "parameters": {{"org_id": "${{step_1.structuredContent.organizations[0].id}}"}}}}
      ]
    }}
  }}
}}
```

### Step 4: Execute the Composition
```json
{{
  "method": "tools/call",
  "params": {{
    "name": "orchestrator_execute_composition",
    "arguments": {{
      "composition_id": "<id>",
      "parameters": {{}}
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
- Use `orchestrator_search_tools` first to get the exact tool names
- Reference step outputs with `${{step_N.field.path}}` syntax
- Use **wildcards `[*]`** to extract all items from arrays (auto-flattens nested wildcards)
- Use **_template/_map** to transform arrays into objects with enriched data
- Use `orchestrator_list_compositions` to see existing workflows you can reuse
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
- Use `orchestrator_search_tools` to find similar tools
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

1. Use `tools/list` to see all available tools
2. Use `prompts/get` with `tool_discovery` for discovery guide
3. Use `orchestrator_search_tools` to find tools by description
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

                # Auto-recovery: if 0 tools, servers may have been cleaned up after
                # inactivity, or list_tools() returned cached tools while servers
                # are still starting in background (race condition).
                # Strategy:
                #   1. Check cache for tool routing info → start ONLY the needed server
                #   2. Fallback: start ALL configured servers if cache miss
                if not all_tools:
                    from ..services.user_tool_cache import get_user_tool_cache
                    tool_cache = get_user_tool_cache()
                    cached_tools = await tool_cache.get(user_uuid)

                    target_server_id = None
                    if cached_tools:
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

                # Find tool by original name AND matching server prefix
                # This handles multi-instance scenarios (e.g., github_perso vs github_work)
                for tool in all_tools:
                    tool_original_name = tool.get("name")
                    tool_metadata = tool.get("metadata", {})
                    tool_server_id = tool_metadata.get("server_id", "")
                    # Sanitize server_id same way as list_tools (- to _)
                    tool_server_prefix = tool_server_id.replace("-", "_")

                    # Match by BOTH original name AND server prefix
                    if tool_original_name == original_tool_name and tool_server_prefix == server_prefix:
                        tool_info = tool
                        logger.info(f"✅ Found tool: {original_tool_name} (server: {tool_server_id})")
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
        if not user_id and session_id and session_id in self.sessions:
            session = self.sessions[session_id]
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
    auth: tuple = Depends(get_current_user_api_key)
):
    """
    Primary SSE endpoint for MCP protocol.

    Requires: Valid MCPHub API Key in Authorization header
    Format: Authorization: Bearer mcphub_sk_xxx

    Implements Server-Sent Events stream for real-time communication.
    Supports:
    - Tool discovery
    - Tool execution
    - Resource management
    - Session management
    """
    api_key, user = auth
    session_id = str(uuid.uuid4())

    # Log authenticated connection
    logger.info(f"Authenticated MCP connection - User: {user.email}, API Key: {api_key.name}, Session: {session_id}")

    async def event_generator() -> AsyncGenerator[Dict[str, Any], None]:
        """Generate SSE events for the client."""

        # Create session with auth context
        mcp_sessions[session_id] = {
            "created_at": time.time(),
            "last_activity": time.time(),
            "message_queue": asyncio.Queue(),
            "user_id": user.id,
            "organization_id": api_key.organization_id,
            "api_key_id": api_key.id,
            "user_email": user.email,
            "tool_group_id": api_key.tool_group_id  # For filtering tools if restricted
        }

        logger.info(f"New SSE connection: {session_id}")

        try:
            # Send keepalive pings
            last_ping = time.time()

            while True:
                # Check for client disconnect
                if await request.is_disconnected():
                    logger.info(f"Client disconnected: {session_id}")
                    break

                # Check session timeout (fix: SESSION_TIMEOUT_SECONDS was defined but unused)
                session_data = mcp_sessions.get(session_id)
                if not session_data:
                    logger.warning(f"Session {session_id} not found, ending SSE stream")
                    break

                session_age = time.time() - session_data["created_at"]
                if session_age > SESSION_TIMEOUT_SECONDS:
                    logger.info(
                        f"Session {session_id} timed out after {session_age:.0f}s "
                        f"(limit: {SESSION_TIMEOUT_SECONDS}s)"
                    )
                    break

                # Check message queue for notifications (NON-BLOCKING)
                queue = session_data.get("message_queue")
                if queue:
                    try:
                        # Non-blocking check for queued messages
                        message = queue.get_nowait()
                        yield message
                        # Update activity timestamp on message delivery
                        session_data["last_activity"] = time.time()
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

                # Wait a bit before next iteration
                await asyncio.sleep(1)

        finally:
            # Cleanup session
            if session_id in mcp_sessions:
                del mcp_sessions[session_id]
                logger.info(f"Session cleaned up: {session_id}")

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
            # MCP 2025-03-26: generate session ID and return in Mcp-Session-Id header
            session_id = str(uuid.uuid4())
            return JSONResponse(
                response,
                headers={"Mcp-Session-Id": session_id}
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
            response = await gateway.list_resources(request_id, params)
        elif method == "resources/read":
            response = await gateway.read_resource(request_id, params)
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
        sessions_count = len(mcp_sessions)
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
