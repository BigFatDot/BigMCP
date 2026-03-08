"""
User Server Pool - Maintains MCP server instances per user.

This module provides per-user MCP server isolation, ensuring that each user's
tool executions use their own credentials stored in the database.

Features:
- Per-user MCP server processes with credential isolation
- Semantic search via per-user VectorStore index
- Event-driven index rebuild (on server add/remove, composition promotion)
"""

import logging
import asyncio
import re
from typing import Dict, List, Optional
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ..services.mcp_server_service import MCPServerService
from ..services.credential_service import CredentialService
from .mcp_wrapper import MCPServerWrapper, StdioMCPWrapper, HttpMCPWrapper, create_wrapper
from .mcp_installer import MCPInstaller
from .vector_store import VectorStore
from ..config.settings import settings
from ..db.database import get_db, async_session_maker
from ..models.mcp_server import MCPServer, ServerStatus
from ..models.tool import Tool
from sqlalchemy import select

logger = logging.getLogger(__name__)


class UserServerPool:
    """
    Manages MCP server instances per user.

    Architecture:
    - Each user gets their own MCP server processes
    - Servers are started on-demand (lazy loading)
    - Credentials are resolved hierarchically (user > org > server default)
    - Servers are cleaned up after inactivity timeout

    Example:
        pool = UserServerPool()

        # Execute a tool with user's credentials
        result = await pool.execute_tool(
            user_id=alice_id,
            server_id=grist_server_id,
            tool_name="grist_create_record",
            parameters={"table": "Tasks", "fields": {...}}
        )
    """

    def __init__(
        self,
        cleanup_timeout_minutes: int = 5,
        cleanup_interval_seconds: int = 30,
        max_servers_per_user: int = 5,
        max_total_servers: int = 50
    ):
        """
        Initialize the user server pool.

        Args:
            cleanup_timeout_minutes: Minutes of inactivity before server cleanup
            cleanup_interval_seconds: Seconds between cleanup checks
            max_servers_per_user: Maximum concurrent servers per user (LRU eviction)
            max_total_servers: Maximum total servers across all users (LRU eviction)
        """
        # Structure: {user_id: {server_id: {"wrapper": ..., "last_used": ...}}}
        self._servers: Dict[UUID, Dict[UUID, Dict]] = {}
        self._cleanup_timeout = timedelta(minutes=cleanup_timeout_minutes)
        self._cleanup_interval = cleanup_interval_seconds
        self._max_servers_per_user = max_servers_per_user
        self._max_total_servers = max_total_servers
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        self._installer = MCPInstaller()

        # Lock to prevent concurrent server starts for the same user-server combination
        self._start_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        # Lock to prevent concurrent ensure_configured_servers_started per user
        # Prevents asyncpg connection race conditions
        self._ensure_locks: Dict[UUID, asyncio.Lock] = {}

        # Semantic search: per-user VectorStore cache (event-driven rebuild)
        self._vector_stores: Dict[UUID, VectorStore] = {}
        self._user_tools_cache: Dict[UUID, List[Dict]] = {}  # Cached tools for search result mapping
        self._user_org_cache: Dict[UUID, UUID] = {}  # Cache user -> org mapping for rebuild

        logger.info(
            f"UserServerPool initialized (timeout: {cleanup_timeout_minutes}min, "
            f"interval: {cleanup_interval_seconds}s, "
            f"max/user: {max_servers_per_user}, max/total: {max_total_servers})"
        )

    async def start(self):
        """Start the background cleanup task."""
        if self._running:
            logger.warning("UserServerPool already running")
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("UserServerPool cleanup task started")

    async def stop(self):
        """Stop the pool and cleanup all servers."""
        logger.info("Stopping UserServerPool...")
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Cleanup all user servers
        for user_id in list(self._servers.keys()):
            await self.cleanup_user_servers(user_id)

        logger.info("UserServerPool stopped")

    async def _get_or_create_lock(self, user_id: UUID, server_id: UUID) -> asyncio.Lock:
        """Get or create a lock for a specific user-server combination."""
        lock_key = f"{user_id}:{server_id}"
        async with self._global_lock:
            if lock_key not in self._start_locks:
                self._start_locks[lock_key] = asyncio.Lock()
            return self._start_locks[lock_key]

    async def get_or_start_server(
        self,
        user_id: UUID,
        server_id: UUID,
        organization_id: Optional[UUID] = None,
        db: Optional[AsyncSession] = None,
        skip_rebuild: bool = False
    ) -> MCPServerWrapper:
        """
        Get an existing server wrapper or start a new one for this user.

        Args:
            user_id: User ID
            server_id: MCP Server ID
            organization_id: Optional organization ID for credential resolution
            db: Optional database session (will create one if not provided)
            skip_rebuild: If True, skip rebuild_user_index (caller will do it)

        Returns:
            MCPServerWrapper instance with user's credentials

        Raises:
            Exception: If server startup fails
        """
        # Get lock for this user-server combination to prevent concurrent starts
        lock = await self._get_or_create_lock(user_id, server_id)

        async with lock:
            # Check if user already has this server running (inside lock to prevent race)
            if user_id in self._servers and server_id in self._servers[user_id]:
                server_info = self._servers[user_id][server_id]

                # Check if wrapper is still alive
                wrapper = server_info["wrapper"]
                if await self._is_server_healthy(wrapper):
                    # Update last used timestamp
                    server_info["last_used"] = datetime.utcnow()
                    logger.debug(f"Reusing server {server_id} for user {user_id}")
                    return wrapper
                else:
                    # Server died, remove it
                    logger.warning(f"Server {server_id} for user {user_id} is unhealthy, restarting")
                    await self._remove_user_server(user_id, server_id, rebuild_index=not skip_rebuild)

            # LRU eviction: per-user limit
            user_servers = self._servers.get(user_id, {})
            if len(user_servers) >= self._max_servers_per_user:
                await self._evict_lru_server(user_id, skip_rebuild=skip_rebuild)

            # LRU eviction: global limit
            total = sum(len(s) for s in self._servers.values())
            if total >= self._max_total_servers:
                await self._evict_lru_server_global(skip_rebuild=skip_rebuild)

            # Start new server for this user
            logger.info(f"Starting new server {server_id} for user {user_id}")

            # Create a new DB session for this operation to avoid concurrent session issues
            from ..db.database import async_session_maker
            async with async_session_maker() as db_session:
                try:
                    return await self._start_server_internal(
                        user_id=user_id,
                        server_id=server_id,
                        organization_id=organization_id,
                        db=db_session,
                        skip_rebuild=skip_rebuild
                    )
                except Exception as e:
                    logger.error(f"Failed to start server {server_id} for user {user_id}: {e}", exc_info=True)
                    raise

    async def _start_server_internal(
        self,
        user_id: UUID,
        server_id: UUID,
        organization_id: Optional[UUID],
        db: AsyncSession,
        skip_rebuild: bool = False
    ) -> MCPServerWrapper:
        """Internal method to start a server (called within lock)."""
        # 1. Get server configuration from database
        stmt = select(MCPServer).where(MCPServer.id == server_id)
        result = await db.execute(stmt)
        server = result.scalar_one_or_none()

        if not server:
            raise ValueError(f"Server {server_id} not found")

        # Note: 'enabled' controls visibility to Claude MCP clients, not ability to run.
        # A server can be running but hidden from Claude (for API-only or Tool Group access).
        if not server.enabled:
            logger.info(f"Starting server {server.server_id} (hidden from Claude - API/Tool Groups only)")

        logger.info(f"Found server config: {server.server_id} (command: {server.command})")

        # 2. Ensure server package is installed (pip, npm, github, etc.)
        server_config = {
            "install": {
                "type": server.install_type,
                "package": server.install_package
            },
            "command": server.command,
            "args": server.args or [],
            "env": server.env or {}
        }

        install_success = await self._installer.ensure_server_installed(
            server.server_id,
            server_config
        )
        if not install_success:
            raise RuntimeError(f"Failed to install server package for {server.server_id}")

        logger.info(f"Server {server.server_id} package installed/verified")

        # 3. Build environment with system env + server env
        import os
        env = os.environ.copy()
        env.update(server.env or {})

        # 4. Resolve credentials based on server type
        # Team servers: merge org + user credentials
        # Personal servers: use only user credentials
        if user_id:
            credential_service = CredentialService(db)
            org_id = organization_id or server.organization_id

            # Check if this is a Team server (has _IS_TEAM_SERVER flag)
            is_team_server = (server.env or {}).get('_IS_TEAM_SERVER') == 'true'

            if is_team_server:
                # Team server: merge org credentials (base) + user credentials (overlay)
                credentials = await credential_service.resolve_credentials_merged(
                    user_id=user_id,
                    server_id=server_id,
                    organization_id=org_id
                )
                logger.info(f"Team server: resolved {len(credentials) if credentials else 0} merged credentials for user {user_id}")
            else:
                # Personal server: use ONLY user credentials
                user_cred = await credential_service._get_user_credential(user_id, server_id)
                credentials = user_cred.credentials if user_cred and user_cred.is_active else None
                logger.info(f"Personal server: resolved {len(credentials) if credentials else 0} user-only credentials for user {user_id}")

            if credentials:
                env.update(credentials)
                # Normalize env var aliases: GITLAB_URL → GITLAB_API_URL
                # The @modelcontextprotocol/server-gitlab package reads GITLAB_API_URL,
                # but the marketplace form field is named GITLAB_URL.
                if "GITLAB_URL" in env and "GITLAB_API_URL" not in env:
                    env["GITLAB_API_URL"] = env["GITLAB_URL"]
                logger.info(f"Applied credentials keys: {list(credentials.keys())}")
            else:
                logger.warning(f"No credentials found for user {user_id} and server {server.server_id}")

        # 5. Create appropriate wrapper based on server configuration
        wrapper_config = {
            "command": server.command,
            "args": server.args or [],
            "env": env  # Use the merged environment
        }

        wrapper = create_wrapper(str(server.server_id), wrapper_config)
        logger.info(f"Created {type(wrapper).__name__} for {server.server_id}")

        # 6. Initialize the wrapper (starts the process and handshake)
        await wrapper.initialize()
        logger.info(f"Wrapper initialized for {server.server_id}")

        # 7. Update server status in database
        server.status = ServerStatus.RUNNING
        await db.commit()

        # 7b. Sync tools to database (for frontend tool groups)
        # Use a fresh session to avoid concurrent session issues after commit
        try:
            async with async_session_maker() as sync_db:
                await self._sync_tools_to_db(server.id, server.organization_id, wrapper, sync_db)
        except Exception as e:
            logger.warning(f"Tool sync failed for {server.server_id}: {e}")

        # 8. Get icon from marketplace cache using _MARKETPLACE_SERVER_ID
        icon_url = None
        marketplace_id = (server.env or {}).get("_MARKETPLACE_SERVER_ID")
        logger.info(f"🎨 Icon lookup for {server.server_id}: marketplace_id={marketplace_id}, env={server.env}")
        if marketplace_id:
            try:
                from ..services.marketplace_service import get_marketplace_service
                marketplace = get_marketplace_service()
                icon_urls = marketplace.get_server_icon(marketplace_id)
                logger.info(f"🎨 Icon lookup result for {marketplace_id}: {icon_urls}")
                if icon_urls:
                    icon_url = icon_urls.get("primary") or icon_urls.get("fallback")
                    logger.info(f"🎨 Using icon for {marketplace_id}: {icon_url}")
            except Exception as e:
                logger.warning(f"Failed to get icon for {marketplace_id}: {e}")

        # 9. Store in pool
        if user_id not in self._servers:
            self._servers[user_id] = {}

        # Build display name for tool prefixing: "ServerName (alias)" or just "ServerName"
        server_display_name = server.name
        if hasattr(server, 'alias') and server.alias:
            server_display_name = f"{server.name} ({server.alias})"

        self._servers[user_id][server_id] = {
            "wrapper": wrapper,
            "last_used": datetime.utcnow(),
            "server": server,
            "server_id_str": server.server_id,  # Technical ID for internal routing
            "server_display_name": server_display_name,  # User-friendly name for tool display
            "icon_url": icon_url  # Service icon for tool display
        }

        logger.info(f"Server {server_display_name} ({server.server_id}) started successfully for user {user_id}")

        # Rebuild semantic index after adding a new server (event-driven)
        # Skip if caller will batch rebuild (e.g., ensure_configured_servers_started)
        if not skip_rebuild:
            org_id = organization_id or server.organization_id
            if org_id:
                try:
                    await self.rebuild_user_index(user_id, org_id)
                except Exception as e:
                    logger.error(f"Failed to rebuild index after server start: {e}")

        return wrapper

    async def execute_tool(
        self,
        user_id: UUID,
        server_id: UUID,
        tool_name: str,
        parameters: dict,
        organization_id: Optional[UUID] = None,
        db: Optional[AsyncSession] = None
    ) -> dict:
        """
        Execute a tool with user-specific credentials.

        Args:
            user_id: User ID
            server_id: MCP Server ID providing the tool
            tool_name: Name of the tool to execute
            parameters: Tool parameters
            organization_id: Optional organization ID
            db: Optional database session

        Returns:
            Tool execution result

        Raises:
            Exception: If tool execution fails
        """
        logger.info(f"Executing tool {tool_name} on server {server_id} for user {user_id}")

        # Get or start the server for this user
        wrapper = await self.get_or_start_server(
            user_id=user_id,
            server_id=server_id,
            organization_id=organization_id,
            db=db
        )

        # Execute the tool
        try:
            result = await wrapper.call_tool(tool_name, parameters)

            # Check if result contains an error from the MCP server
            if isinstance(result, dict):
                if result.get("isError"):
                    error_content = result.get("content", [])
                    error_msg = error_content[0].get("text", str(result)) if error_content else str(result)
                    logger.warning(f"Tool {tool_name} returned error for user {user_id}: {error_msg[:500]}")
                elif "error" in result:
                    logger.warning(f"Tool {tool_name} returned error for user {user_id}: {result.get('error')}")
                else:
                    logger.info(f"Tool {tool_name} executed successfully for user {user_id}")
            else:
                logger.info(f"Tool {tool_name} executed successfully for user {user_id}")

            return result
        except Exception as e:
            logger.error(f"Tool execution failed for {tool_name} (user {user_id}): {e}", exc_info=True)
            raise

    async def get_user_tools(
        self,
        user_id: UUID,
        organization_id: UUID,
        include_hidden: bool = False
    ) -> list:
        """
        Get all available tools from user's running servers.

        This method ensures multi-tenant isolation by only returning tools
        from servers that are currently running for this specific user.

        Args:
            user_id: User ID
            organization_id: Organization ID
            include_hidden: If True, include tools from servers with is_visible_to_oauth_clients=False
                          (used for composition execution where hidden servers should be accessible)

        Returns:
            List of tools from all user's running servers
        """
        logger.info(f"Getting tools for user {user_id} from UserServerPool (include_hidden={include_hidden})")

        all_tools = []

        # Check if user has any running servers
        if user_id not in self._servers:
            logger.info(f"No running servers found for user {user_id}")
            return all_tools

        # Get current visibility status from database for all servers
        visible_server_ids = set()
        if not include_hidden:
            try:
                async with async_session_maker() as db:
                    from sqlalchemy import select
                    from ..models.mcp_server import MCPServer
                    stmt = select(MCPServer.id).where(
                        MCPServer.id.in_([sid for sid in self._servers[user_id].keys()]),
                        MCPServer.is_visible_to_oauth_clients == True
                    )
                    result = await db.execute(stmt)
                    visible_server_ids = {row[0] for row in result.all()}
            except Exception as e:
                logger.warning(f"Could not check server visibility, showing all: {e}")
                visible_server_ids = set(self._servers[user_id].keys())
        else:
            # Include all running servers (hidden + visible)
            visible_server_ids = set(self._servers[user_id].keys())
            logger.info(f"Including hidden servers: {len(visible_server_ids)} total servers")

        # Iterate through user's running servers
        for server_id, server_info in self._servers[user_id].items():
            # Skip hidden servers only if include_hidden=False
            if server_id not in visible_server_ids:
                logger.debug(f"Skipping hidden server {server_id} for user {user_id}")
                continue

            wrapper = server_info["wrapper"]
            # Get the string server_id from server_info (set during _start_server_internal)
            server_id_str = server_info.get("server_id_str", "unknown")
            # Get the user-friendly display name for tool prefixing
            server_display_name = server_info.get("server_display_name", server_id_str)
            # Get the service icon URL (set during _start_server_internal)
            icon_url = server_info.get("icon_url")

            try:
                # Check if server is healthy
                if await self._is_server_healthy(wrapper):
                    # Get tools from this server
                    tools = await wrapper.list_tools()

                    # Add server metadata to each tool for routing
                    for tool in tools:
                        if isinstance(tool, dict):
                            tool["_server_id"] = str(server_id)  # UUID for internal routing
                            # Add metadata for unique tool naming and icon
                            if "metadata" not in tool:
                                tool["metadata"] = {}

                            # Store original tool name before prefixing
                            original_name = tool.get("name", "")
                            tool["metadata"]["original_tool_name"] = original_name
                            tool["metadata"]["server_id"] = server_id_str  # Technical ID for routing
                            tool["metadata"]["server_display_name"] = server_display_name  # For display
                            tool["metadata"]["server_uuid"] = str(server_id)
                            if icon_url:
                                tool["metadata"]["icon_url"] = icon_url  # Service icon

                            # Prefix tool name with display name for user-friendly naming
                            # Format: ServerName__tool_name (sanitized for valid identifier)
                            safe_prefix = re.sub(r'[^a-zA-Z0-9_]', '_', server_display_name)
                            safe_prefix = re.sub(r'_+', '_', safe_prefix).strip('_')
                            tool["name"] = f"{safe_prefix}__{original_name}"

                            all_tools.append(tool)

                    logger.debug(f"Retrieved {len(tools)} tools from server {server_display_name} ({server_id_str})")

                    # Update last used timestamp
                    server_info["last_used"] = datetime.utcnow()
                else:
                    logger.warning(f"Server {server_id} for user {user_id} is unhealthy, skipping")
            except Exception as e:
                logger.error(f"Error getting tools from server {server_id} for user {user_id}: {e}")
                # Continue to next server instead of failing completely

        logger.info(f"Retrieved total of {len(all_tools)} tools for user {user_id}")
        return all_tools

    async def ensure_configured_servers_started(
        self,
        user_id: UUID,
        organization_id: UUID
    ) -> int:
        """
        Ensure all servers with configured credentials are started.

        This method mirrors the auto-start logic used in MCPUnifiedGateway.list_tools()
        to ensure that when compositions execute, all necessary servers are running.

        Optimizations:
        - Limits to max_servers_per_user to avoid LRU eviction ping-pong
        - Prioritizes already-running servers
        - Defers rebuild_user_index to ONE call at the end (skip_rebuild=True)
        - Per-user lock prevents concurrent calls (avoids asyncpg connection race)

        Args:
            user_id: User UUID
            organization_id: Organization UUID

        Returns:
            Number of servers successfully started
        """
        # Get or create lock for this user
        if user_id not in self._ensure_locks:
            self._ensure_locks[user_id] = asyncio.Lock()
        lock = self._ensure_locks[user_id]

        # Skip if already in progress for this user
        if lock.locked():
            logger.debug(
                f"ensure_configured_servers_started already in progress for user {user_id}, skipping"
            )
            # Return count of currently running servers instead of 0
            return len(self._servers.get(user_id, {}))

        async with lock:
            from sqlalchemy import select
            from ..models.user_credential import UserCredential, OrganizationCredential

            try:
                async with async_session_maker() as db:
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

                    # For Team servers, user must have credentials to be "subscribed"
                    # Org-only credentials without user credentials = user opted out
                    org_only_server_ids = org_server_ids - user_server_ids

                    # Filter out Team servers where user has no credentials
                    valid_org_server_ids = set()
                    for server_id in org_only_server_ids:
                        server = await db.get(MCPServer, server_id)
                        if server:
                            is_team_server = (server.env or {}).get('_IS_TEAM_SERVER') == 'true'
                            if not is_team_server:
                                # Not a Team server - org credentials alone are fine
                                valid_org_server_ids.add(server_id)
                            else:
                                # Team server without user credentials - user not subscribed
                                logger.info(
                                    f"Skipping Team server {server.server_id} for user {user_id} "
                                    "(no user credentials = not subscribed)"
                                )

                    # Combine user servers + valid org-only servers
                    all_server_ids = list(user_server_ids | valid_org_server_ids)

                    # Separate already-running vs needs-start for logging
                    running_servers = self._servers.get(user_id, {})
                    already_running = [sid for sid in all_server_ids if sid in running_servers]
                    needs_start = [sid for sid in all_server_ids if sid not in running_servers]

                    # Process ALL servers (already-running first, then new starts).
                    # LRU eviction in get_or_start_server handles the limit naturally.
                    # With skip_rebuild=True, evictions are fast (no intermediate rebuilds).
                    servers_to_process = already_running + needs_start

                    logger.info(
                        f"Found {len(all_server_ids)} configured servers "
                        f"(user: {len(user_server_ids)}, org-only: {len(valid_org_server_ids)}, "
                        f"skipped Team: {len(org_only_server_ids) - len(valid_org_server_ids)}) "
                        f"for user {user_id}. "
                        f"Processing: {len(already_running)} running + {len(needs_start)} to start"
                    )

                    if not servers_to_process:
                        return 0

                    # Start each server with skip_rebuild=True to defer index rebuild
                    started_count = 0
                    any_new_started = False
                    for server_id in servers_to_process:
                        try:
                            was_running = server_id in running_servers
                            await self.get_or_start_server(
                                user_id=user_id,
                                server_id=server_id,
                                organization_id=organization_id,
                                skip_rebuild=True  # Defer rebuild to end
                            )
                            started_count += 1
                            if not was_running:
                                any_new_started = True
                        except Exception as e:
                            logger.warning(
                                f"⚠️ Failed to start server {server_id} for user {user_id}: {e}"
                            )
                            # Continue with other servers even if one fails

                    # ONE rebuild at the end (only if new servers were started)
                    if any_new_started:
                        try:
                            await self.rebuild_user_index(user_id, organization_id)
                        except Exception as e:
                            logger.error(f"Failed to rebuild index after ensure_configured: {e}")

                    logger.info(
                        f"ensure_configured_servers_started: {started_count}/{len(servers_to_process)} "
                        f"servers running for user {user_id}"
                    )

                    return started_count

            except Exception as e:
                logger.error(f"Error ensuring servers started: {e}", exc_info=True)
                return 0

    async def ensure_user_pool_started(
        self,
        user_id: str,
        org_id: str
    ) -> None:
        """
        Ensure user's server pool is started (fire-and-forget).

        Used by OAuth tools endpoint to trigger async server startup
        while returning cached tools immediately.

        Args:
            user_id: User ID (string, will be converted to UUID)
            org_id: Organization ID (string, will be converted to UUID)
        """
        from uuid import UUID

        try:
            user_uuid = UUID(user_id)
            org_uuid = UUID(org_id)

            # Call ensure_configured_servers_started without waiting
            await self.ensure_configured_servers_started(
                user_id=user_uuid,
                organization_id=org_uuid
            )

            logger.info(f"User pool startup triggered for user {user_id}")

        except Exception as e:
            logger.error(f"Error ensuring user pool started: {e}", exc_info=True)

    # =========================================================================
    # Semantic Search (Event-driven VectorStore per user)
    # =========================================================================

    async def rebuild_user_index(
        self,
        user_id: UUID,
        organization_id: UUID
    ) -> None:
        """
        Rebuild the semantic search index for a user.

        Called automatically when:
        - A server is started for the user
        - A server is removed for the user
        - A composition is promoted to production
        - A production composition is deleted

        Args:
            user_id: User ID
            organization_id: Organization ID
        """
        logger.info(f"Rebuilding semantic index for user {user_id}")

        # Cache org_id for future rebuilds
        self._user_org_cache[user_id] = organization_id

        # Get ALL tools for this user (including hidden - compositions need access to all)
        tools = await self.get_user_tools(user_id, organization_id, include_hidden=True)

        if not tools:
            # No tools - remove index from cache
            self._vector_stores.pop(user_id, None)
            self._user_tools_cache.pop(user_id, None)
            logger.info(f"No tools for user {user_id}, index cleared")
            return

        # Prepare tools for indexing (add unique ID if missing)
        indexed_tools = []
        for i, tool in enumerate(tools):
            tool_copy = tool.copy()
            # Create unique ID: server_id.tool_name or just index
            tool_id = f"{tool.get('_server_id', 'unknown')}.{tool.get('name', f'tool_{i}')}"
            tool_copy["id"] = tool_id
            indexed_tools.append(tool_copy)

        # Create or update VectorStore
        if user_id not in self._vector_stores:
            self._vector_stores[user_id] = VectorStore(settings.embedding)

        # Build the index
        self._vector_stores[user_id].build_index(indexed_tools)

        # Cache tools for result mapping
        self._user_tools_cache[user_id] = indexed_tools

        logger.info(f"Semantic index rebuilt for user {user_id}: {len(indexed_tools)} tools indexed")

    async def search_tools_semantic(
        self,
        user_id: UUID,
        query: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        Semantic search for tools using the user's VectorStore index.

        Args:
            user_id: User ID
            query: Natural language search query
            limit: Maximum number of results

        Returns:
            List of matching tools sorted by semantic relevance
        """
        if user_id not in self._vector_stores:
            logger.warning(f"No semantic index for user {user_id}, returning empty results")
            return []

        if user_id not in self._user_tools_cache:
            logger.warning(f"No tools cache for user {user_id}")
            return []

        try:
            # Search in VectorStore
            vector_store = self._vector_stores[user_id]
            tool_ids = vector_store.search(query, limit=limit)

            if not tool_ids:
                logger.info(f"Semantic search for '{query}' returned no results for user {user_id}")
                return []

            # Map tool IDs back to full tool objects
            tools_cache = self._user_tools_cache[user_id]
            tools_by_id = {t.get("id"): t for t in tools_cache}

            results = []
            for tool_id in tool_ids:
                if tool_id in tools_by_id:
                    results.append(tools_by_id[tool_id])

            logger.info(f"Semantic search for '{query}': {len(results)} results for user {user_id}")
            return results

        except Exception as e:
            logger.error(f"Error in semantic search for user {user_id}: {e}", exc_info=True)
            return []

    def invalidate_user_index(self, user_id: UUID) -> None:
        """
        Invalidate (remove) the semantic index for a user.

        Called when all servers are cleaned up for a user.

        Args:
            user_id: User ID
        """
        self._vector_stores.pop(user_id, None)
        self._user_tools_cache.pop(user_id, None)
        self._user_org_cache.pop(user_id, None)
        logger.info(f"Semantic index invalidated for user {user_id}")

    async def stop_user_server(
        self,
        user_id: UUID,
        server_id: UUID
    ) -> bool:
        """
        Stop a specific server for a user.

        Args:
            user_id: User ID
            server_id: Server UUID

        Returns:
            True if server was stopped, False if not found
        """
        logger.info(f"Stopping server {server_id} for user {user_id}")

        # Check if server is running for this user
        if user_id not in self._servers or server_id not in self._servers[user_id]:
            logger.warning(f"Server {server_id} not running for user {user_id}")
            return False

        # Remove from pool (stops the process)
        await self._remove_user_server(user_id, server_id)

        # Update database status
        async with async_session_maker() as db:
            stmt = select(MCPServer).where(MCPServer.id == server_id)
            result = await db.execute(stmt)
            server = result.scalar_one_or_none()
            if server:
                server.status = ServerStatus.STOPPED
                await db.commit()
                logger.info(f"Server {server.server_id} stopped and status updated")

        return True

    async def restart_user_server(
        self,
        user_id: UUID,
        server_id: UUID,
        db: Optional[AsyncSession] = None
    ) -> bool:
        """
        Restart a specific server for a user with fresh credentials.

        This is called when user/org credentials are updated to ensure
        the server picks up the new credential values.

        Args:
            user_id: User ID
            server_id: Server UUID
            db: Optional database session

        Returns:
            True if server was restarted, False if not found or failed
        """
        logger.info(f"Restarting server {server_id} for user {user_id} to refresh credentials")

        # Check if server is running for this user
        if user_id not in self._servers or server_id not in self._servers[user_id]:
            logger.info(f"Server {server_id} not running for user {user_id}, no restart needed")
            return False

        # Stop the server first
        await self._remove_user_server(user_id, server_id, rebuild_index=False)

        # Start it again with fresh credentials
        try:
            if db:
                await self.get_or_start_server(user_id, server_id, db)
            else:
                async with async_session_maker() as fresh_db:
                    await self.get_or_start_server(user_id, server_id, fresh_db)

            logger.info(f"Server {server_id} restarted successfully for user {user_id}")

            # Rebuild semantic index with new tools
            await self._rebuild_semantic_index(user_id)

            return True
        except Exception as e:
            logger.error(f"Failed to restart server {server_id} for user {user_id}: {e}")
            return False

    async def restart_servers_for_credential(
        self,
        user_id: UUID,
        server_id_str: str,
        organization_id: UUID
    ) -> int:
        """
        Restart all running servers that use a specific credential.

        Called when a user or org credential is created/updated/deleted.

        Args:
            user_id: User who owns/triggered the credential change
            server_id_str: The server_id string (e.g., "grist") that the credential is for
            organization_id: Organization ID for org-wide restarts

        Returns:
            Number of servers restarted
        """
        restarted = 0

        # Find all running servers matching this server_id_str
        if user_id in self._servers:
            for srv_uuid, srv_info in list(self._servers[user_id].items()):
                if srv_info.get("server_id_str") == server_id_str:
                    if await self.restart_user_server(user_id, srv_uuid):
                        restarted += 1

        logger.info(f"Restarted {restarted} servers for credential {server_id_str}")
        return restarted

    async def restart_servers_for_org_credential(
        self,
        server_id_str: str,
        organization_id: UUID
    ) -> int:
        """
        Restart servers across ALL users in an organization when org credential changes.

        Called when an organization credential is created/updated/deleted.
        This ensures all connected users pick up the new credential values.

        Args:
            server_id_str: The server_id string (e.g., "grist") that the credential is for
            organization_id: Organization ID

        Returns:
            Number of servers restarted across all users
        """
        restarted = 0

        # Iterate over all users with running servers
        for user_id in list(self._servers.keys()):
            for srv_uuid, srv_info in list(self._servers.get(user_id, {}).items()):
                # Check if this server matches the credential's server_id
                if srv_info.get("server_id_str") == server_id_str:
                    # Verify server belongs to the same organization
                    server = srv_info.get("server")
                    if server and server.organization_id == organization_id:
                        if await self.restart_user_server(user_id, srv_uuid):
                            restarted += 1

        logger.info(f"Restarted {restarted} servers across org {organization_id} for credential {server_id_str}")
        return restarted

    async def cleanup_user_servers(self, user_id: UUID):
        """
        Cleanup all servers for a specific user.

        Args:
            user_id: User ID
        """
        if user_id not in self._servers:
            return

        logger.info(f"Cleaning up servers for user {user_id}")

        server_ids = list(self._servers[user_id].keys())
        for server_id in server_ids:
            # Don't rebuild index for each server removal during full cleanup
            await self._remove_user_server(user_id, server_id, rebuild_index=False)

        # Remove user entry
        del self._servers[user_id]

        # Invalidate the semantic index for this user
        self.invalidate_user_index(user_id)

        logger.info(f"All servers cleaned up for user {user_id}")

    async def _remove_user_server(self, user_id: UUID, server_id: UUID, rebuild_index: bool = True):
        """Remove and cleanup a specific server for a user."""
        if user_id not in self._servers or server_id not in self._servers[user_id]:
            return

        server_info = self._servers[user_id][server_id]
        wrapper = server_info["wrapper"]

        try:
            # Close the wrapper (stops the server process)
            await wrapper.close()
            logger.info(f"Closed wrapper for server {server_id} for user {user_id}")
        except Exception as e:
            logger.error(f"Error closing wrapper for server {server_id} for user {user_id}: {e}")
        finally:
            # Remove from pool
            del self._servers[user_id][server_id]

        # Rebuild semantic index after removing a server (event-driven)
        # Skip if rebuild_index=False (e.g., during full user cleanup)
        if rebuild_index and user_id in self._user_org_cache:
            org_id = self._user_org_cache[user_id]
            try:
                await self.rebuild_user_index(user_id, org_id)
            except Exception as e:
                logger.error(f"Failed to rebuild index after server removal: {e}")

    async def _is_server_healthy(self, wrapper: MCPServerWrapper) -> bool:
        """
        Check if a server wrapper is still healthy.

        Args:
            wrapper: MCPServerWrapper to check

        Returns:
            True if healthy, False otherwise
        """
        try:
            # Check if the underlying process is still running
            if hasattr(wrapper, '_process') and wrapper._process:
                return wrapper._process.returncode is None

            # Check if wrapper is initialized
            if hasattr(wrapper, '_initialized'):
                return wrapper._initialized

            # For HTTP wrappers, could implement a health check
            # For now, assume healthy if wrapper exists
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def get_user_server_status(
        self,
        user_id: UUID,
        organization_id: UUID,
        db: Optional[AsyncSession] = None
    ) -> list:
        """
        Get connection status for all servers of a user.

        Returns the status of all servers (both running and not running)
        for display in the web interface.

        Args:
            user_id: User ID
            organization_id: Organization ID
            db: Optional database session

        Returns:
            List of server status dictionaries with:
            - server_id: MCPServer UUID
            - is_connected: True if server is running and healthy
            - has_credentials: True if user has credentials stored
            - connection_error: Error message if any
        """
        logger.info(f"Getting server status for user {user_id}")

        status_list = []

        # Get database session
        from ..db.database import async_session_maker
        from ..services.mcp_server_service import MCPServerService

        async with async_session_maker() as session:
            mcp_service = MCPServerService(session)

            servers = await mcp_service.list_servers(
                organization_id=organization_id,
                include_disabled=True
            )

            for server in servers:
                server_uuid = server.id
                is_running = False
                is_healthy = False
                connection_error = None
                server_info = None

                # Check if server is running in user pool
                if user_id in self._servers and server_uuid in self._servers[user_id]:
                    server_info = self._servers[user_id][server_uuid]
                    wrapper = server_info.get("wrapper")
                    is_running = True

                    # Check health
                    try:
                        is_healthy = await self._is_server_healthy(wrapper)
                    except Exception as e:
                        connection_error = str(e)
                        is_healthy = False

                # Check for credentials
                has_credentials = bool(server.env) and any(
                    k not in ("_MARKETPLACE_SERVER_ID",) for k in (server.env or {}).keys()
                )

                status_list.append({
                    "server_id": str(server_uuid),
                    "server_name": server.name,
                    "is_connected": is_running and is_healthy,
                    "has_credentials": has_credentials,
                    "enabled": server.enabled,
                    "connection_error": connection_error,
                    "last_connection_at": server_info.get("last_used").isoformat() if server_info and server_info.get("last_used") else None
                })

        logger.info(f"Returning status for {len(status_list)} servers for user {user_id}")
        return status_list

    async def _evict_lru_server(self, user_id: UUID, skip_rebuild: bool = False) -> None:
        """
        Evict the least recently used server for a specific user.

        Called when user reaches max_servers_per_user limit.
        """
        user_servers = self._servers.get(user_id, {})
        if not user_servers:
            return

        # Find the LRU server (oldest last_used)
        lru_server_id = min(
            user_servers.keys(),
            key=lambda sid: user_servers[sid]["last_used"]
        )

        lru_name = user_servers[lru_server_id].get("server_display_name", str(lru_server_id))
        logger.info(
            f"LRU eviction (per-user): removing server '{lru_name}' "
            f"for user {user_id} (limit: {self._max_servers_per_user})"
        )
        await self._remove_user_server(user_id, lru_server_id, rebuild_index=not skip_rebuild)

    async def _evict_lru_server_global(self, skip_rebuild: bool = False) -> None:
        """
        Evict the globally least recently used server.

        Called when total servers reach max_total_servers limit.
        """
        oldest_time = None
        oldest_user_id = None
        oldest_server_id = None

        for user_id, user_servers in self._servers.items():
            for server_id, server_info in user_servers.items():
                last_used = server_info["last_used"]
                if oldest_time is None or last_used < oldest_time:
                    oldest_time = last_used
                    oldest_user_id = user_id
                    oldest_server_id = server_id

        if oldest_user_id and oldest_server_id:
            oldest_name = self._servers[oldest_user_id][oldest_server_id].get(
                "server_display_name", str(oldest_server_id)
            )
            logger.info(
                f"LRU eviction (global): removing server '{oldest_name}' "
                f"for user {oldest_user_id} (limit: {self._max_total_servers})"
            )
            await self._remove_user_server(oldest_user_id, oldest_server_id, rebuild_index=not skip_rebuild)

    def get_pool_stats(self) -> Dict:
        """
        Get pool statistics for monitoring.

        Returns:
            Dict with pool metrics
        """
        total_servers = sum(len(s) for s in self._servers.values())
        users_with_servers = len(self._servers)

        per_user = {}
        for user_id, user_servers in self._servers.items():
            per_user[str(user_id)[:8]] = len(user_servers)

        return {
            "total_users": users_with_servers,
            "total_servers": total_servers,
            "max_servers_per_user": self._max_servers_per_user,
            "max_total_servers": self._max_total_servers,
            "cleanup_timeout_minutes": self._cleanup_timeout.total_seconds() / 60,
            "cleanup_interval_seconds": self._cleanup_interval,
            "servers_per_user": per_user,
            "active_locks": len(self._start_locks),
            "vector_stores_cached": len(self._vector_stores),
        }

    async def _cleanup_loop(self):
        """Background task to cleanup inactive servers."""
        logger.info(f"Starting cleanup loop (interval: {self._cleanup_interval}s)")

        while self._running:
            try:
                await asyncio.sleep(self._cleanup_interval)

                now = datetime.utcnow()
                users_to_cleanup = []

                # --- Orphan detection: collect all server UUIDs currently in pool ---
                all_pool_server_ids: set = set()
                for user_servers in self._servers.values():
                    all_pool_server_ids.update(user_servers.keys())

                existing_server_ids: set = set()
                if all_pool_server_ids:
                    try:
                        async with async_session_maker() as db:
                            from sqlalchemy import select as sa_select
                            from ..models.mcp_server import MCPServer as MCPServerModel
                            stmt = sa_select(MCPServerModel.id).where(
                                MCPServerModel.id.in_(all_pool_server_ids)
                            )
                            result = await db.execute(stmt)
                            existing_server_ids = {row[0] for row in result.all()}
                    except Exception as e:
                        logger.warning(f"Orphan check DB query failed, skipping: {e}")
                        existing_server_ids = all_pool_server_ids  # safe fallback: keep all

                orphaned_server_ids = all_pool_server_ids - existing_server_ids
                if orphaned_server_ids:
                    logger.info(
                        f"Detected {len(orphaned_server_ids)} orphaned server(s) "
                        f"(deleted from DB but still in pool): {orphaned_server_ids}"
                    )
                # -------------------------------------------------------------------

                for user_id, user_servers in self._servers.items():
                    servers_to_remove = []

                    for server_id, server_info in user_servers.items():
                        # Stop servers deleted from the database (orphaned)
                        if server_id in orphaned_server_ids:
                            logger.info(
                                f"Removing orphaned server {server_id} for user {user_id} "
                                f"(no longer in database)"
                            )
                            servers_to_remove.append(server_id)
                            continue

                        last_used = server_info["last_used"]
                        inactive_time = now - last_used

                        if inactive_time > self._cleanup_timeout:
                            logger.info(
                                f"Server {server_id} for user {user_id} "
                                f"inactive for {inactive_time}, cleaning up"
                            )
                            servers_to_remove.append(server_id)

                    # Remove inactive and orphaned servers
                    for server_id in servers_to_remove:
                        await self._remove_user_server(user_id, server_id)

                    # If user has no servers left, mark for cleanup
                    if not self._servers.get(user_id):
                        users_to_cleanup.append(user_id)

                # Remove empty user entries and cleanup caches
                for user_id in users_to_cleanup:
                    if user_id in self._servers:
                        del self._servers[user_id]
                        logger.debug(f"Removed empty server entry for user {user_id}")

                    # Cleanup VectorStore cache for users with no servers
                    if user_id in self._vector_stores:
                        del self._vector_stores[user_id]
                        logger.debug(f"Removed VectorStore cache for user {user_id}")

                    # Cleanup tools cache
                    if user_id in self._user_tools_cache:
                        del self._user_tools_cache[user_id]
                        logger.debug(f"Removed tools cache for user {user_id}")

                    # Cleanup org mapping cache
                    if user_id in self._user_org_cache:
                        del self._user_org_cache[user_id]
                        logger.debug(f"Removed org cache for user {user_id}")

                # Cleanup locks for inactive users (lock key format: "user_id:server_id")
                async with self._global_lock:
                    active_user_ids = set(str(uid) for uid in self._servers.keys())
                    locks_to_remove = []

                    for lock_key in self._start_locks.keys():
                        user_id_str = lock_key.split(":")[0]
                        if user_id_str not in active_user_ids:
                            locks_to_remove.append(lock_key)

                    for lock_key in locks_to_remove:
                        del self._start_locks[lock_key]
                        logger.debug(f"Removed unused lock: {lock_key}")

                if users_to_cleanup or locks_to_remove:
                    logger.info(
                        f"Cleanup completed: {len(users_to_cleanup)} users, "
                        f"{len(locks_to_remove)} locks removed"
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}", exc_info=True)

        logger.info("Cleanup loop stopped")

    def get_stats(self) -> dict:
        """
        Get statistics about the server pool.

        Returns:
            Dictionary with pool statistics
        """
        total_servers = sum(len(servers) for servers in self._servers.values())

        return {
            "total_users": len(self._servers),
            "total_servers": total_servers,
            "users": {
                str(user_id): {
                    "server_count": len(servers),
                    "servers": [
                        {
                            "server_id": str(server_id),
                            "last_used": info["last_used"].isoformat(),
                        }
                        for server_id, info in servers.items()
                    ]
                }
                for user_id, servers in self._servers.items()
            }
        }

    async def _sync_tools_to_db(
        self,
        server_id: UUID,
        organization_id: UUID,
        wrapper,
        db: AsyncSession
    ):
        """
        Sync discovered tools from MCP server to the database.

        This ensures tools are available for Tool Groups and the frontend.
        Reuses the same logic as MCPServerService._create_or_update_tool.

        Args:
            server_id: MCPServer UUID
            organization_id: Organization UUID
            wrapper: MCP server wrapper
            db: Database session
        """
        try:
            # Get tools from the running server
            runtime_tools = await wrapper.list_tools()
            logger.info(f"🔧 Syncing {len(runtime_tools)} tools for server {server_id}")

            if not runtime_tools:
                logger.info(f"No tools to sync for server {server_id}")
                return

            synced_count = 0
            for tool_data in runtime_tools:
                if not isinstance(tool_data, dict):
                    continue

                tool_name = tool_data.get("name", "")
                if not tool_name:
                    continue

                # Check if tool exists
                stmt = select(Tool).where(
                    Tool.server_id == server_id,
                    Tool.tool_name == tool_name
                )
                result = await db.execute(stmt)
                tool = result.scalar_one_or_none()

                if tool:
                    # Update existing tool
                    tool.description = tool_data.get("description")
                    tool.parameters_schema = tool_data.get("inputSchema", {})
                    tool.returns_schema = tool_data.get("outputSchema")
                else:
                    # Create new tool
                    tool = Tool(
                        server_id=server_id,
                        organization_id=organization_id,
                        tool_name=tool_name,
                        display_name=tool_data.get("displayName", tool_name),
                        description=tool_data.get("description"),
                        parameters_schema=tool_data.get("inputSchema", {}),
                        returns_schema=tool_data.get("outputSchema"),
                        tags=tool_data.get("tags", []),
                        category=tool_data.get("category"),
                        meta=tool_data.get("metadata", {})
                    )
                    db.add(tool)

                synced_count += 1

            await db.commit()
            logger.info(f"✅ Synced {synced_count} tools for server {server_id}")

        except Exception as e:
            logger.error(f"Failed to sync tools for server {server_id}: {e}", exc_info=True)
            try:
                await db.rollback()
            except:
                pass
