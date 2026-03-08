"""
Universal MCP Server Wrapper Module

This module provides a universal interface for communicating with MCP servers
regardless of their transport mode (STDIO, HTTP, SSE, etc.)
"""

import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import aiohttp

logger = logging.getLogger(__name__)


class MCPServerWrapper(ABC):
    """
    Abstract base class for MCP server wrappers.

    Provides a unified interface for communicating with MCP servers
    regardless of their underlying transport mechanism.
    """

    def __init__(self, server_id: str, url: str):
        """
        Initialize the wrapper.

        Args:
            server_id: Unique identifier for the server
            url: Server URL or endpoint
        """
        self.server_id = server_id
        self.url = url
        self._initialized = False
        self._server_info = None

    @abstractmethod
    async def initialize(self) -> Dict[str, Any]:
        """
        Initialize connection with the MCP server.

        Returns:
            Server information from initialize response
        """
        pass

    @abstractmethod
    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        Get list of available tools from the server.

        Returns:
            List of tool definitions
        """
        pass

    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Execute a tool on the server.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the connection to the server."""
        pass

    @property
    def is_initialized(self) -> bool:
        """Check if the wrapper is initialized."""
        return self._initialized

    @property
    def server_info(self) -> Optional[Dict[str, Any]]:
        """Get server information."""
        return self._server_info


class StdioMCPWrapper(MCPServerWrapper):
    """
    Wrapper for MCP servers using STDIO transport.

    Manages a persistent subprocess with stdin/stdout communication.
    Supports concurrent requests from multiple clients (laptop + mobile) via
    request ID matching and proper response routing.
    """

    def __init__(self, server_id: str, command: str, args: List[str], env: Dict[str, str]):
        """
        Initialize STDIO wrapper.

        Args:
            server_id: Unique identifier for the server
            command: Command to start the server
            args: Command arguments
            env: Environment variables
        """
        super().__init__(server_id, "stdio://localhost")
        self.command = command
        self.args = args
        self.env = env
        self._process = None
        self._request_id = 0
        self._reader_task = None

        # Response routing: dict of {request_id: asyncio.Future}
        # Each request creates a Future and waits for the reader to resolve it
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._pending_lock = asyncio.Lock()

        # Queue for notifications (messages without ID or non-response messages)
        self._notification_queue = asyncio.Queue()

        # Lock to serialize request SENDING only (not waiting for response)
        self._send_lock = asyncio.Lock()

    async def _start_process(self) -> None:
        """Start the MCP server process."""
        if self._process is not None:
            return

        try:
            logger.info(f"🚀 Starting STDIO server {self.server_id}: {self.command} {' '.join(self.args)}")

            # Merge server env with system env to preserve PATH
            import os
            env = os.environ.copy()
            env.update(self.env)

            # Start process with pipes
            # Note: Default buffer limit is 64KB, which may be too small for large responses
            # We increase it later in _read_responses using a custom StreamReader
            self._process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                limit=10 * 1024 * 1024  # 10MB buffer limit for large JSON responses
            )

            # Check if process crashed immediately (missing shebang issue)
            # Give it a moment to potentially fail
            await asyncio.sleep(0.3)

            if self._process.returncode is not None:
                # Process exited - check if it's a missing shebang issue
                stderr_data = await self._process.stderr.read()
                stderr_text = stderr_data.decode('utf-8', errors='ignore')

                # Pattern: "import: not found" or "syntax error" indicates JS executed as shell
                is_shebang_issue = (
                    "import: not found" in stderr_text or
                    "syntax error near unexpected token" in stderr_text or
                    "node: not found" not in stderr_text  # Exclude actual missing node
                )

                if is_shebang_issue and self.command == "npx":
                    logger.warning(f"⚠️ Process {self.server_id} failed (missing shebang?), trying node fallback...")
                    # Try fallback with node via npx --node-arg
                    self._process = await self._start_with_npx_node_fallback(env)
                else:
                    raise RuntimeError(
                        f"Process exited immediately with code {self._process.returncode}. "
                        f"Stderr: {stderr_text[:500]}"
                    )

            # Start background task to read responses
            self._reader_task = asyncio.create_task(self._read_responses())

            logger.info(f"✅ STDIO process {self.server_id} started (PID: {self._process.pid})")

        except Exception as e:
            logger.error(f"❌ Error starting STDIO process {self.server_id}: {e}")
            raise

    async def _start_with_npx_node_fallback(self, env: dict) -> asyncio.subprocess.Process:
        """
        Fallback for npx packages with missing shebang.

        Some npm packages have bin scripts without #!/usr/bin/env node shebang,
        causing the OS to try to execute JavaScript as shell script.

        This fallback uses: npx -p <package> -c 'node "$(readlink -f $(which <bin>))"'
        which resolves the real path to the entry file and runs it with node explicitly.
        """
        # Extract package name from npx args
        # Typical pattern: npx -y @scope/package-name or npx -y package-name
        package_name = None
        for i, arg in enumerate(self.args):
            if arg == "-y" and i + 1 < len(self.args):
                package_name = self.args[i + 1]
                break
            elif not arg.startswith("-"):
                package_name = arg
                break

        if not package_name:
            raise RuntimeError(f"Could not extract package name from npx args: {self.args}")

        # Derive bin name from package name
        # @scope/package-name -> package-name
        # package-name -> package-name
        if "/" in package_name:
            bin_name = package_name.split("/")[-1]
        else:
            bin_name = package_name

        logger.info(f"🔄 Fallback: explicit node execution for {package_name} (bin: {bin_name})")

        # Use npx with -p to install package, then -c to run node with resolved bin path
        # readlink -f resolves symlinks to get the actual JS file
        # This works around missing shebang by having node execute the file directly
        fallback_command = "npx"
        fallback_args = [
            "-y",
            "-p", package_name,
            "-c", f'node "$(readlink -f $(which {bin_name}))"'
        ]

        process = await asyncio.create_subprocess_exec(
            fallback_command,
            *fallback_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            limit=10 * 1024 * 1024
        )

        # Give it a moment to start
        await asyncio.sleep(0.5)

        if process.returncode is not None:
            stderr_data = await process.stderr.read()
            stderr_text = stderr_data.decode('utf-8', errors='ignore')
            raise RuntimeError(
                f"Fallback failed for {package_name}. "
                f"Stderr: {stderr_text[:500]}"
            )

        logger.info(f"✅ Node fallback successful for {self.server_id}")
        return process

    async def _read_responses(self) -> None:
        """
        Background task to read JSON-RPC responses from stdout.

        Routes responses to the correct pending request based on ID.
        Notifications (messages without ID) go to the notification queue.
        """
        try:
            while self._process and self._process.stdout:
                line = await self._process.stdout.readline()
                if not line:
                    logger.warning(f"EOF from {self.server_id} stdout, process may have exited")
                    break

                try:
                    message = json.loads(line.decode('utf-8'))

                    # Check if this is a response (has 'id' field)
                    msg_id = message.get("id")

                    if msg_id is not None:
                        # This is a response to a request - route to the correct Future
                        async with self._pending_lock:
                            future = self._pending_requests.get(msg_id)
                            if future and not future.done():
                                future.set_result(message)
                                logger.debug(f"Routed response ID={msg_id} for {self.server_id}")
                            else:
                                logger.warning(
                                    f"Received response ID={msg_id} but no pending request "
                                    f"for {self.server_id} (orphaned response)"
                                )
                    else:
                        # This is a notification (no ID) - queue it
                        await self._notification_queue.put(message)
                        method = message.get("method", "unknown")
                        logger.debug(f"Received notification '{method}' from {self.server_id}")

                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from {self.server_id}: {line.decode('utf-8', errors='ignore')[:200]}")

        except asyncio.CancelledError:
            logger.info(f"Reader task cancelled for {self.server_id}")
            raise
        except Exception as e:
            logger.error(f"Error reading from {self.server_id}: {e}")

        # When reader exits, fail all pending requests
        async with self._pending_lock:
            for req_id, future in self._pending_requests.items():
                if not future.done():
                    future.set_exception(RuntimeError(f"Process exited for {self.server_id}"))
            self._pending_requests.clear()

    async def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send a JSON-RPC request and wait for response.

        Supports concurrent requests from multiple clients by:
        1. Using a unique request ID for each request
        2. Creating a Future that the reader task will resolve
        3. Only locking during the send phase, not during wait

        Args:
            method: JSON-RPC method name
            params: Method parameters

        Returns:
            Response data
        """
        if not self._process or not self._process.stdin:
            raise RuntimeError(f"Process not started for {self.server_id}")

        # Create a Future for this request's response
        loop = asyncio.get_event_loop()
        response_future = loop.create_future()

        # Generate unique request ID and register the Future
        async with self._send_lock:
            self._request_id += 1
            request_id = self._request_id

            # Register the Future BEFORE sending (to avoid race condition)
            async with self._pending_lock:
                self._pending_requests[request_id] = response_future

            request = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or {}
            }

            # Send request
            try:
                request_json = json.dumps(request) + "\n"
                self._process.stdin.write(request_json.encode('utf-8'))
                await self._process.stdin.drain()
                logger.debug(f"Sent request ID={request_id} method={method} to {self.server_id}")
            except Exception as e:
                # Clean up Future on send failure
                async with self._pending_lock:
                    self._pending_requests.pop(request_id, None)
                raise RuntimeError(f"Failed to send request to {self.server_id}: {e}")

        # Wait for response (outside the send lock - allows concurrent waiting)
        try:
            # 120s timeout to allow for first-time package downloads (uvx, pip, npm)
            response = await asyncio.wait_for(response_future, timeout=120.0)

            if "error" in response:
                error = response["error"]
                error_msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
                raise RuntimeError(f"MCP Error from {self.server_id}: {error_msg}")

            return response.get("result", {})

        except asyncio.TimeoutError:
            logger.error(f"Timeout waiting for response ID={request_id} method={method} from {self.server_id}")
            raise RuntimeError(f"Timeout waiting for response from {self.server_id} (method={method})")
        finally:
            # Clean up the pending request
            async with self._pending_lock:
                self._pending_requests.pop(request_id, None)

    async def initialize(self) -> Dict[str, Any]:
        """Initialize the STDIO MCP server."""
        if self._initialized:
            return self._server_info

        # Start process
        await self._start_process()

        # Send initialize request - may fail if process crashes (e.g., missing shebang)
        try:
            result = await self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "MCPHub",
                        "version": "1.0.0"
                    }
                }
            )
        except RuntimeError as e:
            # Check if this is a shebang issue that we can retry with fallback
            if "Process exited" in str(e) and self.command == "npx":
                stderr_text = ""
                if self._process and self._process.stderr:
                    try:
                        stderr_data = await asyncio.wait_for(
                            self._process.stderr.read(),
                            timeout=1.0
                        )
                        stderr_text = stderr_data.decode('utf-8', errors='ignore')
                    except asyncio.TimeoutError:
                        pass

                is_shebang_issue = (
                    "import: not found" in stderr_text or
                    "syntax error near unexpected token" in stderr_text or
                    ("Syntax error" in stderr_text and "import" in stderr_text.lower())
                )

                if is_shebang_issue:
                    logger.warning(f"⚠️ Process {self.server_id} failed (missing shebang), trying fallback...")

                    # Clean up failed process
                    await self._cleanup_process()

                    # Merge env
                    import os
                    env = os.environ.copy()
                    env.update(self.env)

                    # Retry with fallback
                    self._process = await self._start_with_npx_node_fallback(env)
                    self._reader_task = asyncio.create_task(self._read_responses())

                    # Retry initialize request
                    result = await self._send_request(
                        "initialize",
                        {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {
                                "name": "MCPHub",
                                "version": "1.0.0"
                            }
                        }
                    )
                else:
                    logger.error(f"Process crashed but not shebang issue. Stderr: {stderr_text[:500]}")
                    raise
            else:
                raise

        self._server_info = result.get("serverInfo", {})
        self._initialized = True

        logger.info(f"✅ STDIO server {self.server_id} initialized: {self._server_info.get('name')}")

        return self._server_info

    async def _cleanup_process(self) -> None:
        """Clean up a failed process."""
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    self._process.kill()
                except ProcessLookupError:
                    pass
            self._process = None

        async with self._pending_lock:
            self._pending_requests.clear()

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Get tools from STDIO server."""
        if not self._initialized:
            await self.initialize()

        result = await self._send_request("tools/list", {})
        return result.get("tools", [])

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool on STDIO server."""
        if not self._initialized:
            await self.initialize()

        result = await self._send_request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments
            }
        )

        return result

    async def close(self) -> None:
        """Close the STDIO connection and cleanup all pending requests."""
        logger.info(f"Closing STDIO wrapper for {self.server_id}")

        # Cancel all pending requests first
        async with self._pending_lock:
            for req_id, future in self._pending_requests.items():
                if not future.done():
                    future.set_exception(RuntimeError(f"Connection closed for {self.server_id}"))
            self._pending_requests.clear()

        # Cancel the reader task
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        # Terminate the process
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()

            logger.info(f"🔌 STDIO server {self.server_id} closed")

        self._initialized = False
        self._process = None


class HttpMCPWrapper(MCPServerWrapper):
    """
    Wrapper for MCP servers using HTTP-based transport (streamable-http, SSE).

    Starts the server process and maintains a persistent HTTP session.
    """

    def __init__(self, server_id: str, url: str, command: str, args: List[str], env: Dict[str, str], timeout: int = 30):
        """
        Initialize HTTP wrapper.

        Args:
            server_id: Unique identifier for the server
            url: Server base URL
            command: Command to start the server
            args: Command arguments
            env: Environment variables
            timeout: Request timeout in seconds
        """
        super().__init__(server_id, url)
        self.command = command
        self.args = args
        self.env = env
        self._session = None
        self._timeout = timeout
        self._session_id = None
        self._process = None

    async def _start_process(self) -> None:
        """Start the HTTP MCP server process."""
        if self._process is not None:
            return

        try:
            logger.info(f"🚀 Starting HTTP server {self.server_id}: {self.command} {' '.join(self.args)}")

            # Merge server env with system env to preserve PATH
            import os
            env = os.environ.copy()
            env.update(self.env)

            # Start process
            self._process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            # Wait for server to be ready (give it a few seconds to start listening)
            logger.info(f"⏳ Waiting for HTTP server {self.server_id} to start...")
            await asyncio.sleep(3)

            # Check if process is still running
            if self._process.returncode is not None:
                stderr = await self._process.stderr.read()
                stdout = await self._process.stdout.read()
                raise RuntimeError(
                    f"Server process exited prematurely with code {self._process.returncode}. "
                    f"Stderr: {stderr.decode('utf-8', errors='ignore')}"
                )

            logger.info(f"✅ HTTP process {self.server_id} started (PID: {self._process.pid})")

        except Exception as e:
            logger.error(f"❌ Error starting HTTP process {self.server_id}: {e}")
            raise

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout),
                cookie_jar=aiohttp.CookieJar()
            )
            logger.info(f"📡 HTTP session created for {self.server_id}")
        return self._session

    async def _send_jsonrpc_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send JSON-RPC request over HTTP.

        Args:
            method: JSON-RPC method
            params: Method parameters

        Returns:
            Result data
        """
        session = await self._get_session()

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {}
        }

        # Add session ID if we have one
        if self._session_id:
            # Try adding session ID in BOTH top-level and params
            payload["sessionId"] = self._session_id  # Top-level for streamable-http
            payload["params"]["sessionId"] = self._session_id  # In params as well
            logger.info(f"📤 Sending session ID for {self.server_id}: {self._session_id}")

        url = self.url.rstrip('/')

        async with session.post(url, headers=headers, json=payload) as response:
            if response.status != 200:
                text = await response.text()
                raise RuntimeError(f"HTTP {response.status}: {text}")

            content_type = response.headers.get("Content-Type", "")

            # Log response headers for debugging session management
            logger.debug(f"🔍 Response headers for {self.server_id}: {dict(response.headers)}")

            # Handle SSE response
            if "text/event-stream" in content_type:
                text_content = await response.text()
                logger.debug(f"🔍 SSE Response for {self.server_id}/{method}: {text_content[:500]}")

                for line in text_content.split('\n'):
                    line_str = line.strip()
                    if line_str.startswith('data: '):
                        data_json = line_str[6:]
                        try:
                            data = json.loads(data_json)
                            if "result" in data:
                                result = data["result"]

                                # Try to extract session ID from multiple possible locations
                                session_id = None

                                # Check in result.sessionId
                                if "sessionId" in result:
                                    session_id = result["sessionId"]
                                # Check in result._meta.sessionId
                                elif "_meta" in result and "sessionId" in result["_meta"]:
                                    session_id = result["_meta"]["sessionId"]
                                # Check in top-level data
                                elif "sessionId" in data:
                                    session_id = data["sessionId"]

                                if session_id:
                                    self._session_id = session_id
                                    logger.info(f"📝 Session ID captured for {self.server_id}: {self._session_id}")
                                elif method == "initialize":
                                    # For initialize, log the full response to understand the structure
                                    logger.warning(f"⚠️  No session ID in {method} response for {self.server_id}")
                                    logger.info(f"🔍 Full response: {json.dumps(result, indent=2)}")

                                return result
                            elif "error" in data:
                                raise RuntimeError(f"MCP Error: {data['error']}")
                        except json.JSONDecodeError:
                            continue

                raise RuntimeError("No valid response in SSE stream")

            # Handle regular JSON response
            else:
                data = await response.json()
                logger.debug(f"🔍 JSON Response for {self.server_id}/{method}: {json.dumps(data, indent=2)[:500]}")

                if "result" in data:
                    result = data["result"]

                    # Try to extract session ID from multiple possible locations
                    session_id = None

                    # Check in result.sessionId
                    if "sessionId" in result:
                        session_id = result["sessionId"]
                    # Check in result._meta.sessionId
                    elif "_meta" in result and "sessionId" in result["_meta"]:
                        session_id = result["_meta"]["sessionId"]
                    # Check in top-level data
                    elif "sessionId" in data:
                        session_id = data["sessionId"]

                    if session_id:
                        self._session_id = session_id
                        logger.info(f"📝 Session ID captured for {self.server_id}: {self._session_id}")
                    elif method == "initialize":
                        # For initialize, log the full response to understand the structure
                        logger.warning(f"⚠️  No session ID in {method} response for {self.server_id}")
                        logger.info(f"🔍 Full response: {json.dumps(result, indent=2)}")

                    return result
                elif "error" in data:
                    raise RuntimeError(f"MCP Error: {data['error']}")
                else:
                    raise RuntimeError(f"Invalid JSON-RPC response: {data}")

    async def initialize(self) -> Dict[str, Any]:
        """Initialize HTTP MCP server."""
        if self._initialized:
            return self._server_info

        # Start the HTTP server process first
        await self._start_process()

        # Generate session ID before initialize for servers that need it in the request
        if not self._session_id:
            self._session_id = str(uuid.uuid4())
            logger.info(f"🔑 Client-side session ID generated for {self.server_id}: {self._session_id}")

        result = await self._send_jsonrpc_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "MCPHub",
                    "version": "1.0.0"
                }
            }
        )

        self._server_info = result.get("serverInfo", {})
        self._initialized = True

        logger.info(f"✅ HTTP server {self.server_id} initialized: {self._server_info.get('name')}")

        return self._server_info

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Get tools from HTTP server."""
        if not self._initialized:
            await self.initialize()

        result = await self._send_jsonrpc_request("tools/list", {})
        return result.get("tools", [])

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool on HTTP server."""
        if not self._initialized:
            await self.initialize()

        result = await self._send_jsonrpc_request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments
            }
        )

        return result

    async def close(self) -> None:
        """Close HTTP session and stop server process."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info(f"🔌 HTTP session {self.server_id} closed")

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()

            logger.info(f"🔌 HTTP server {self.server_id} closed")

        self._initialized = False
        self._session = None
        self._process = None


def create_wrapper(server_id: str, config: Dict[str, Any]) -> MCPServerWrapper:
    """
    Factory function to create the appropriate wrapper for a server.

    Args:
        server_id: Server identifier
        config: Server configuration from mcp_servers.json

    Returns:
        Appropriate MCPServerWrapper instance
    """
    # Determine transport mode from args or config
    command = config.get("command", "python")
    args = config.get("args", [])
    env = config.get("env", {})

    # Check if it's HTTP-based transport
    if "--transport" in args:
        transport_idx = args.index("--transport") + 1
        if transport_idx < len(args):
            transport = args[transport_idx]
            if transport in ["streamable-http", "sse", "http"]:
                # Extract host and port
                host = "localhost"
                port = 8080

                if "--host" in args:
                    host_idx = args.index("--host") + 1
                    if host_idx < len(args):
                        host = args[host_idx]

                if "--port" in args:
                    port_idx = args.index("--port") + 1
                    if port_idx < len(args):
                        port = int(args[port_idx])

                url = f"http://{host}:{port}/mcp"

                logger.info(f"🔧 Creating HTTP wrapper for {server_id} at {url}")
                return HttpMCPWrapper(server_id, url, command, args, env)

    # Default to STDIO wrapper
    logger.info(f"🔧 Creating STDIO wrapper for {server_id}")
    return StdioMCPWrapper(server_id, command, args, env)
