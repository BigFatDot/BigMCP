"""
MCP Server Service - Dynamic server lifecycle management.

Handles installation, starting, stopping, and tool discovery for MCP servers.
Replaces static mcp_servers.json with database-driven configuration.
"""

import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import async_session_maker
from ..models.mcp_server import MCPServer, InstallType, ServerStatus
from ..models.tool import Tool
from ..models.organization import Organization


logger = logging.getLogger(__name__)


class MCPServerService:
    """
    Service for managing MCP server lifecycle and operations.

    Responsibilities:
    - Install MCP servers based on InstallType
    - Start/stop/restart server processes
    - Discover tools from running servers
    - Track server status and health
    - Manage server configuration
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._running_processes: Dict[str, asyncio.subprocess.Process] = {}

    async def create_server(
        self,
        organization_id: UUID,
        server_id: str,
        name: str,
        install_type: InstallType,
        install_package: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        version: Optional[str] = None,
        auto_start: bool = False
    ) -> MCPServer:
        """
        Create a new MCP server configuration.

        Args:
            organization_id: Organization owning the server
            server_id: Unique identifier for the server
            name: Human-readable name
            install_type: Installation method (pip, npm, github, docker, local)
            install_package: Package name or path
            command: Command to run the server
            args: Command arguments
            env: Environment variables
            version: Package version (optional)
            auto_start: Whether to start the server immediately

        Returns:
            Created MCPServer instance

        Raises:
            ValueError: If server_id already exists for organization
        """
        # Check if server_id already exists
        stmt = select(MCPServer).where(
            MCPServer.organization_id == organization_id,
            MCPServer.server_id == server_id
        )
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none():
            raise ValueError(f"Server '{server_id}' already exists for this organization")

        # Verify organization exists
        org_stmt = select(Organization).where(Organization.id == organization_id)
        org_result = await self.db.execute(org_stmt)
        org = org_result.scalar_one_or_none()
        if not org:
            raise ValueError(f"Organization {organization_id} not found")

        # Create server
        server = MCPServer(
            organization_id=organization_id,
            server_id=server_id,
            name=name,
            install_type=install_type,
            install_package=install_package,
            command=command,
            args=args or [],
            env=env or {},
            version=version,
            status=ServerStatus.STOPPED
        )

        self.db.add(server)
        await self.db.commit()
        await self.db.refresh(server)

        logger.info(f"Created MCP server: {server_id} for org {organization_id}")

        # Auto-install and start if requested
        if auto_start:
            await self.install(server.id)
            await self.start(server.id)

        return server

    async def install(self, server_id: UUID) -> MCPServer:
        """
        Install an MCP server based on its install_type.

        Args:
            server_id: Server UUID

        Returns:
            Updated server with installation status

        Raises:
            ValueError: If server not found
            RuntimeError: If installation fails
        """
        # Fetch server info and extract all needed data upfront
        server = await self._get_server(server_id)

        # Extract values we need for installation (avoid holding DB connection)
        install_type = server.install_type
        install_package = server.install_package
        version = server.version
        server_id_str = server.server_id

        logger.info(f"Installing MCP server: {server_id_str} ({install_type})")

        try:
            # Perform installation based on type
            # These operations can take several minutes for npm/pip
            # We don't hold the DB connection during this time
            if install_type == InstallType.PIP:
                await self._install_pip_standalone(install_package, version)
            elif install_type == InstallType.NPM:
                await self._install_npm_standalone(install_package, version)
            elif install_type == InstallType.GITHUB:
                await self._install_github_standalone(install_package, version, server_id_str)
            elif install_type == InstallType.DOCKER:
                await self._install_docker_standalone(install_package, version)
            elif install_type == InstallType.LOCAL:
                # Local servers don't need installation
                logger.info(f"Server {server_id_str} is local, skipping installation")

            logger.info(f"Successfully installed: {server_id_str}")

            # Fetch fresh server object with new session for return
            async with async_session_maker() as fresh_db:
                stmt = select(MCPServer).where(MCPServer.id == server_id)
                result = await fresh_db.execute(stmt)
                return result.scalar_one()

        except Exception as e:
            logger.error(f"Failed to install {server_id_str}: {e}")
            # Use fresh session to update error status (original may have timed out)
            async with async_session_maker() as fresh_db:
                stmt = select(MCPServer).where(MCPServer.id == server_id)
                result = await fresh_db.execute(stmt)
                server = result.scalar_one_or_none()
                if server:
                    server.status = ServerStatus.ERROR
                    server.error_message = str(e)
                    await fresh_db.commit()
            raise RuntimeError(f"Installation failed: {e}")

    async def _install_pip_standalone(
        self,
        install_package: str,
        version: Optional[str]
    ):
        """
        Install Python package via pip (standalone version).

        Does not require MCPServer object, just the package info.
        Used for long-running installations where DB connection may timeout.
        """
        package = install_package
        if version:
            package = f"{package}=={version}"

        cmd = ["pip", "install", package]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(f"pip install failed: {stderr.decode()}")

    async def _install_npm_standalone(
        self,
        install_package: str,
        version: Optional[str]
    ):
        """
        Install Node.js package via npm (standalone version).

        NPM packages are auto-installed by npx -y at runtime — no global install needed.
        Global npm install (npm install -g) requires root access to /usr/lib/node_modules/
        which is not available when running as unprivileged user (bigmcp UID 999).
        """
        package = install_package
        if version:
            package = f"{package}@{version}"
        # NPM packages are cached automatically by npx -y on first run.
        # Skipping npm install -g (requires root, not available after privilege drop).
        logger.info(
            f"Server type npm: skipping global install of '{package}', "
            f"npx handles installation automatically at runtime"
        )

    async def _install_github_standalone(
        self,
        install_package: str,
        version: Optional[str],
        server_id_str: str
    ):
        """
        Clone and install from GitHub repository (standalone version).

        Does not require MCPServer object, just the package info.
        Used for long-running installations where DB connection may timeout.
        """
        repo_url = install_package

        # Create temp directory for cloning
        clone_dir = Path(f"/tmp/mcp_install_{server_id_str}")
        clone_dir.mkdir(parents=True, exist_ok=True)

        # Clone repository
        cmd = ["git", "clone", repo_url, str(clone_dir)]
        if version:
            cmd.extend(["--branch", version])

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(f"git clone failed: {stderr.decode()}")

        # Check for setup.py or package.json and install
        if (clone_dir / "setup.py").exists():
            install_cmd = ["pip", "install", "-e", str(clone_dir)]
        elif (clone_dir / "package.json").exists():
            install_cmd = ["npm", "install", "-g", str(clone_dir)]
        else:
            raise RuntimeError("No setup.py or package.json found in repository")

        process = await asyncio.create_subprocess_exec(
            *install_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(f"Installation failed: {stderr.decode()}")

    async def _install_docker_standalone(
        self,
        install_package: str,
        version: Optional[str]
    ):
        """
        Pull Docker image (standalone version).

        Does not require MCPServer object, just the package info.
        Used for long-running installations where DB connection may timeout.
        """
        image = install_package
        if version:
            image = f"{image}:{version}"

        cmd = ["docker", "pull", image]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(f"docker pull failed: {stderr.decode()}")

    async def start(
        self,
        server_id: UUID,
        user_id: Optional[UUID] = None,
        organization_id: Optional[UUID] = None
    ) -> MCPServer:
        """
        Start an MCP server process.

        Uses a fresh DB session to avoid connection timeout issues when called
        after long-running operations like install().

        Args:
            server_id: Server UUID
            user_id: Optional user UUID for credential resolution
            organization_id: Optional organization UUID for credential resolution (overrides server.organization_id)

        Returns:
            Updated server with running status

        Raises:
            ValueError: If server not found
            RuntimeError: If server already running or start fails
        """
        import os

        # Use fresh session to avoid timeout issues after long install operations
        async with async_session_maker() as db:
            # Fetch server
            stmt = select(MCPServer).where(MCPServer.id == server_id)
            result = await db.execute(stmt)
            server = result.scalar_one_or_none()

            if not server:
                raise ValueError(f"Server {server_id} not found")

            if server.status == ServerStatus.RUNNING:
                raise RuntimeError(f"Server {server.server_id} is already running")

            if not server.enabled:
                raise RuntimeError(f"Server {server.server_id} is disabled")

            # Extract all needed values from server object
            server_uuid = server.id
            server_id_str = server.server_id
            server_org_id = server.organization_id
            server_command = server.command
            server_args = server.args
            server_env = server.env or {}
            is_team_server = server_env.get('_IS_TEAM_SERVER') == 'true'

            logger.info(f"Starting MCP server: {server_id_str}")

            try:
                # Update status to STARTING
                server.status = ServerStatus.STARTING
                await db.commit()

                # Build environment from server config
                # Start with os.environ to preserve PATH and other system variables
                env = {**os.environ, **server_env}

                # Resolve credentials based on server type
                # Team servers: merge org + user credentials
                # Personal servers: use only user credentials
                if user_id:
                    from .credential_service import CredentialService
                    credential_service = CredentialService(db)

                    # Use provided organization_id or fall back to server's organization_id
                    org_id = organization_id or server_org_id

                    if is_team_server:
                        # Team server: merge org credentials (base) + user credentials (overlay)
                        # Essential for Team Services where admin pre-configures some credentials
                        # and users provide the remaining ones
                        credentials = await credential_service.resolve_credentials_merged(
                            user_id=user_id,
                            server_id=server_uuid,
                            organization_id=org_id
                        )
                        logger.info(f"Team server: using merged credentials for {server_id_str}")
                    else:
                        # Personal server: use ONLY user credentials (no merge with org)
                        user_cred = await credential_service._get_user_credential(user_id, server_uuid)
                        credentials = user_cred.credentials if user_cred and user_cred.is_active else None
                        logger.info(f"Personal server: using user-only credentials for {server_id_str}")

                    if credentials:
                        # Merge credentials into environment (credentials override server.env)
                        env.update(credentials)
                        # Normalize env var aliases: GITLAB_URL → GITLAB_API_URL
                        # The @modelcontextprotocol/server-gitlab package reads GITLAB_API_URL,
                        # but the marketplace form field is named GITLAB_URL.
                        if "GITLAB_URL" in env and "GITLAB_API_URL" not in env:
                            env["GITLAB_API_URL"] = env["GITLAB_URL"]
                        logger.info(f"Applied credentials keys: {list(credentials.keys())}")
                    else:
                        logger.warning(
                            f"No credentials found for user {user_id} and server {server_id_str}. "
                            f"Using server default environment."
                        )

                # Start process
                process = await asyncio.create_subprocess_exec(
                    server_command,
                    *server_args,
                    env=env,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                # Store process reference
                process_key = f"{server_org_id}:{server_id_str}"
                self._running_processes[process_key] = process

                # Update status to RUNNING
                server.status = ServerStatus.RUNNING
                server.error_message = None
                await db.commit()

                logger.info(f"Started MCP server: {server_id_str} (PID: {process.pid})")

                # Discover tools from running server (uses its own fresh session)
                asyncio.create_task(self._discover_tools_async(server_uuid, server_id_str, server_org_id))

                # Refresh server object to load all attributes for serialization
                await db.refresh(server)

                return server

            except Exception as e:
                logger.error(f"Failed to start {server_id_str}: {e}")
                # Update error status with fresh query to handle any connection issues
                try:
                    stmt = select(MCPServer).where(MCPServer.id == server_id)
                    result = await db.execute(stmt)
                    server = result.scalar_one_or_none()
                    if server:
                        server.status = ServerStatus.ERROR
                        server.error_message = str(e)
                        await db.commit()
                except Exception as db_error:
                    logger.error(f"Failed to update error status: {db_error}")
                raise RuntimeError(f"Failed to start server: {e}")

    async def stop(self, server_id: UUID) -> MCPServer:
        """
        Stop a running MCP server.

        Args:
            server_id: Server UUID

        Returns:
            Updated server with stopped status
        """
        server = await self._get_server(server_id)

        if server.status != ServerStatus.RUNNING:
            raise RuntimeError(f"Server {server.server_id} is not running")

        logger.info(f"Stopping MCP server: {server.server_id}")

        try:
            process_key = f"{server.organization_id}:{server.server_id}"
            process = self._running_processes.get(process_key)

            if process:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()

                del self._running_processes[process_key]

            server.status = ServerStatus.STOPPED
            await self.db.commit()

            logger.info(f"Stopped MCP server: {server.server_id}")

            # Refresh server object to load all attributes for serialization
            await self.db.refresh(server)

            return server

        except Exception as e:
            logger.error(f"Failed to stop {server.server_id}: {e}")
            raise RuntimeError(f"Failed to stop server: {e}")

    async def restart(self, server_id: UUID, user_id: Optional[UUID] = None) -> MCPServer:
        """Restart an MCP server."""
        await self.stop(server_id)
        return await self.start(server_id, user_id=user_id)

    async def delete_server(self, server_id: UUID) -> None:
        """
        Delete an MCP server configuration.

        Stops the server if running and removes from database.
        Cascade delete removes associated tools and bindings.

        Args:
            server_id: Server UUID
        """
        server = await self._get_server(server_id)

        # Stop if running
        if server.status == ServerStatus.RUNNING:
            await self.stop(server_id)

        # Delete from database (cascade deletes tools and bindings)
        await self.db.delete(server)
        await self.db.commit()

        logger.info(f"Deleted MCP server: {server.server_id}")

    async def update_config(
        self,
        server_id: UUID,
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        enabled: Optional[bool] = None,
        is_visible_to_oauth_clients: Optional[bool] = None
    ) -> MCPServer:
        """
        Update server configuration.

        Server must be stopped to update command/args.
        Environment variables can be updated while running.

        Args:
            server_id: Server UUID
            command: New command (requires stop)
            args: New arguments (requires stop)
            env: New environment variables
            enabled: Enable/disable server
            is_visible_to_oauth_clients: Show/hide from OAuth clients

        Returns:
            Updated server

        Raises:
            RuntimeError: If trying to update command/args while running
        """
        server = await self._get_server(server_id)

        if server.status == ServerStatus.RUNNING and (command or args):
            raise RuntimeError(
                "Cannot update command/args while server is running. Stop server first."
            )

        if command:
            server.command = command
        if args is not None:
            server.args = args
        if env is not None:
            server.env = env
        if enabled is not None:
            server.enabled = enabled

        # Handle visibility changes
        if is_visible_to_oauth_clients is not None:
            old_visible = server.is_visible_to_oauth_clients
            server.is_visible_to_oauth_clients = is_visible_to_oauth_clients

            from .tool_service import ToolService
            from .organization_tool_cache import tool_cache

            tool_service = ToolService(self.db)

            # If hiding server, cascade hide all its tools
            if old_visible and not is_visible_to_oauth_clients:
                count = await tool_service.bulk_update_tool_visibility(
                    server_id=server.id,
                    is_visible=False,
                    user_id=None  # System action
                )
                logger.info(f"Cascaded hide to {count} tools for server {server.server_id}")

            # If showing server, cascade show all its tools
            elif not old_visible and is_visible_to_oauth_clients:
                count = await tool_service.bulk_update_tool_visibility(
                    server_id=server.id,
                    is_visible=True,
                    user_id=None  # System action
                )
                logger.info(f"Cascaded show to {count} tools for server {server.server_id}")

            # Invalidate caches for this organization
            await tool_cache.invalidate_organization(server.organization_id)

            # Also invalidate user tool cache (OAuth clients)
            from .user_tool_cache import get_user_tool_cache
            user_cache = get_user_tool_cache()
            invalidated = await user_cache.invalidate_organization(server.organization_id)
            logger.info(f"Invalidated caches for organization {server.organization_id} ({invalidated} user caches)")

        await self.db.commit()
        await self.db.refresh(server)

        logger.info(f"Updated MCP server config: {server.server_id}")
        return server

    async def list_servers(
        self,
        organization_id: UUID,
        include_disabled: bool = False
    ) -> List[MCPServer]:
        """
        List all MCP servers for an organization.

        Args:
            organization_id: Organization UUID
            include_disabled: Whether to include disabled servers

        Returns:
            List of MCP servers
        """
        stmt = select(MCPServer).where(
            MCPServer.organization_id == organization_id
        )

        if not include_disabled:
            stmt = stmt.where(MCPServer.enabled == True)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_server_by_server_id(
        self,
        organization_id: UUID,
        server_id: str
    ) -> Optional[MCPServer]:
        """
        Get server by server_id within organization.

        Args:
            organization_id: Organization UUID
            server_id: Server identifier string

        Returns:
            MCPServer or None
        """
        stmt = select(MCPServer).where(
            MCPServer.organization_id == organization_id,
            MCPServer.server_id == server_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_server_by_uuid(
        self,
        organization_id: UUID,
        server_uuid: UUID
    ) -> Optional[MCPServer]:
        """
        Get server by its UUID within organization.

        Args:
            organization_id: Organization UUID
            server_uuid: Server UUID

        Returns:
            MCPServer or None
        """
        stmt = select(MCPServer).where(
            MCPServer.organization_id == organization_id,
            MCPServer.id == server_uuid
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_server(
        self,
        organization_id: UUID,
        identifier: str
    ) -> Optional[MCPServer]:
        """
        Get server by UUID or server_id string.

        Tries UUID first, falls back to string server_id.

        Args:
            organization_id: Organization UUID
            identifier: Server UUID or server_id string

        Returns:
            MCPServer or None
        """
        # Try to parse as UUID first
        try:
            server_uuid = UUID(identifier)
            server = await self.get_server_by_uuid(organization_id, server_uuid)
            if server:
                return server
        except ValueError:
            pass  # Not a UUID, try as string server_id

        # Fall back to string server_id
        return await self.get_server_by_server_id(organization_id, identifier)

    async def _discover_tools_async(
        self,
        server_id: UUID,
        server_id_str: str,
        organization_id: UUID
    ):
        """
        Discover tools from a running MCP server (async task version).

        Uses MCP protocol to list available tools and store them in database.
        Called as an async task with pre-extracted values to avoid session issues.

        Args:
            server_id: MCPServer UUID
            server_id_str: Server ID string (e.g., 'grist-mcp')
            organization_id: Organization UUID
        """
        try:
            logger.info(f"Discovering tools from {server_id_str}")

            process_key = f"{organization_id}:{server_id_str}"
            process = self._running_processes.get(process_key)

            if not process:
                logger.warning(f"No process found for {server_id_str}")
                return

            # Send MCP list_tools request
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {}
            }

            process.stdin.write(json.dumps(request).encode() + b'\n')
            await process.stdin.drain()

            # Read response
            response_line = await asyncio.wait_for(
                process.stdout.readline(),
                timeout=10.0
            )
            response = json.loads(response_line.decode())

            if "result" in response and "tools" in response["result"]:
                tools_data = response["result"]["tools"]

                # Store discovered tools using a fresh session
                async with async_session_maker() as db:
                    for tool_data in tools_data:
                        await self._create_or_update_tool_in_session(
                            db, server_id, organization_id, tool_data
                        )
                    await db.commit()

                logger.info(
                    f"Discovered {len(tools_data)} tools from {server_id_str}"
                )

        except asyncio.TimeoutError:
            logger.warning(f"Timeout discovering tools from {server_id_str}")
        except Exception as e:
            logger.error(f"Error discovering tools from {server_id_str}: {e}")

    async def _create_or_update_tool(self, server: MCPServer, tool_data: Dict[str, Any]):
        """
        Create or update a tool from discovery data.

        Args:
            server: MCPServer that provides the tool
            tool_data: Tool metadata from MCP protocol
        """
        tool_name = tool_data["name"]

        # Check if tool exists
        stmt = select(Tool).where(
            Tool.server_id == server.id,
            Tool.tool_name == tool_name
        )
        result = await self.db.execute(stmt)
        tool = result.scalar_one_or_none()

        if tool:
            # Update existing tool
            tool.description = tool_data.get("description")
            tool.parameters_schema = tool_data.get("inputSchema", {})
            tool.returns_schema = tool_data.get("outputSchema")
        else:
            # Create new tool
            tool = Tool(
                server_id=server.id,
                organization_id=server.organization_id,
                tool_name=tool_name,
                display_name=tool_data.get("displayName", tool_name),
                description=tool_data.get("description"),
                parameters_schema=tool_data.get("inputSchema", {}),
                returns_schema=tool_data.get("outputSchema"),
                tags=tool_data.get("tags", []),
                category=tool_data.get("category"),
                meta=tool_data.get("metadata", {})
            )
            self.db.add(tool)

        await self.db.commit()

    async def _create_or_update_tool_in_session(
        self,
        db: AsyncSession,
        server_id: UUID,
        organization_id: UUID,
        tool_data: Dict[str, Any]
    ):
        """
        Create or update a tool from discovery data using provided session.

        Args:
            db: Database session to use
            server_id: MCPServer UUID
            organization_id: Organization UUID
            tool_data: Tool metadata from MCP protocol
        """
        tool_name = tool_data["name"]

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

    async def _get_server(self, server_id: UUID) -> MCPServer:
        """Get server by UUID or raise ValueError."""
        stmt = select(MCPServer).where(MCPServer.id == server_id)
        result = await self.db.execute(stmt)
        server = result.scalar_one_or_none()

        if not server:
            raise ValueError(f"Server {server_id} not found")

        return server
