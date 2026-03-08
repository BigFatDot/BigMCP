"""
MCP Client module for interacting with MCP servers.

This module provides functionality to discover, connect to, and interact with
Model Context Protocol (MCP) servers.
"""

import asyncio
import json
import logging
import os
import base64
from typing import Any, Dict, List, Optional, Union

import aiohttp
from pydantic import BaseModel, Field, ValidationError

from ..config.settings import ServerConfig

logger = logging.getLogger(__name__)


class ServerDiscoveryError(Exception):
    """Exception raised when server discovery fails."""
    pass


class ServerConnectionError(Exception):
    """Exception raised when connection to a server fails."""
    pass


class ToolExecutionError(Exception):
    """Exception raised when tool execution fails."""
    pass


class MCPServer(BaseModel):
    """MCP Server information model."""
    
    id: str
    name: str
    description: Optional[str] = None
    url: str
    version: Optional[str] = None
    status: str = "unknown"
    tools_count: int = 0
    
    class Config:
        arbitrary_types_allowed = True


class MCPTool(BaseModel):
    """MCP Tool information model."""
    
    id: str
    server_id: str
    name: str
    description: Optional[str] = None
    parameters: Optional[Union[List[Dict[str, Any]], Dict[str, Any]]] = Field(default_factory=list)
    
    class Config:
        arbitrary_types_allowed = True


class MCPClient:
    """
    Client for interacting with MCP servers.
    
    This class provides methods to discover and interact with MCP servers,
    retrieve available tools, and execute tools with parameters.
    """
    
    def __init__(self, config: ServerConfig):
        """
        Initialize the MCP client with the given configuration.

        Args:
            config: Server configuration for MCP
        """
        self.config = config
        self.servers: Dict[str, MCPServer] = {}
        self.tools: Dict[str, MCPTool] = {}
        self._session = None
        self._server_sessions: Dict[str, aiohttp.ClientSession] = {}  # Session per MCP server
        self._additional_server_urls = set()
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            )
        return self._session

    async def _get_server_session(self, server_url: str) -> aiohttp.ClientSession:
        """
        Get or create a dedicated session for a specific MCP server.

        This ensures all requests to the same server share the same HTTP session,
        which is required for MCP streamable-http protocol session management.

        Args:
            server_url: The base URL of the MCP server

        Returns:
            A dedicated aiohttp ClientSession for this server
        """
        # Normalize URL to use as key
        server_key = server_url.rstrip('/')

        # Create session if it doesn't exist or is closed
        if server_key not in self._server_sessions or self._server_sessions[server_key].closed:
            self._server_sessions[server_key] = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
                cookie_jar=aiohttp.CookieJar()  # Enable cookie handling for session management
            )
            logger.info(f"📡 HTTP session created for {server_key}")

        return self._server_sessions[server_key]

    async def close(self) -> None:
        """Close any open connections."""
        # Close global session
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

        # Close all server-specific sessions
        for server_url, session in list(self._server_sessions.items()):
            if not session.closed:
                await session.close()
                logger.info(f"📡 HTTP session closed for {server_url}")
        self._server_sessions.clear()
            
    async def add_server_url(self, url: str) -> None:
        """
        Add a server URL to explore during next discovery.

        Args:
            url: MCP server URL
        """
        if url and url.strip():
            self._additional_server_urls.add(url.strip())
            logger.debug(f"Server URL added for discovery: {url}")
            
    async def discover_servers(self) -> List[MCPServer]:
        """
        Discover available MCP servers from the configured server list or discovery endpoints.
        
        Returns:
            List of discovered MCP servers
        
        Raises:
            ServerDiscoveryError: If server discovery fails
        """
        discovered_servers = []
        
        # Combine configured URLs and additional URLs
        all_urls = set(self.config.server_urls or [])
        all_urls.update(self._additional_server_urls)

        # Use static server list if provided
        for url in all_urls:
            try:
                # Try first with standard MCP /info URL
                info_url = f"{url.rstrip('/')}/info"
                logger.debug(f"Attempting discovery via standard endpoint: {info_url}")

                session = await self._get_session()
                async with session.get(info_url) as response:
                    if response.status == 200:
                        server_info = await response.json()

                        # Check for required fields
                        if "id" in server_info:
                            server_id = server_info["id"]
                            server = MCPServer(
                                id=server_id,
                                name=server_info.get("name", server_id),
                                description=server_info.get("description", ""),
                                url=url,
                                version=server_info.get("version", "1.0.0"),
                                status="available",
                                tools_count=server_info.get("tools_count", 0)
                            )

                            discovered_servers.append(server)
                            self.servers[server_id] = server

                            # Retrieve server tools
                            await self._fetch_tools(server)

                            logger.info(f"Standard MCP server discovered: {server.name} ({server.url})")
                            continue

                # If that fails, try with legacy method
                server = await self._fetch_server_info(url.strip())
                if server:
                    discovered_servers.append(server)
                    continue

                # If all fails, try Claude MCP compatibility mode
                server = await self._try_claude_mcp_discovery(url.strip())
                if server:
                    discovered_servers.append(server)
                    continue
                    
            except Exception as e:
                logger.warning(f"Connection error for server {url}: {str(e)}")
                    
        # Use discovery endpoints if provided
        if self.config.discovery_urls:
            for discovery_url in self.config.discovery_urls:
                try:
                    servers = await self._discover_from_endpoint(discovery_url.strip())
                    discovered_servers.extend(servers)
                except Exception as e:
                    logger.warning(f"Failed to discover MCP servers from {discovery_url}: {str(e)}")
        
        # Update internal server registry
        for server in discovered_servers:
            self.servers[server.id] = server
            
        if not discovered_servers and (self.config.server_urls or self.config.discovery_urls or self._additional_server_urls):
            logger.warning("No MCP servers discovered")
            
        return discovered_servers
        
    async def _try_claude_mcp_discovery(self, url: str) -> Optional[MCPServer]:
        """
        Try to discover an MCP server compatible with Claude format.

        Args:
            url: MCP server URL

        Returns:
            Server information or None if unavailable
        """
        try:
            # Minimal configuration for Claude MCP
            config = {
                "client_id": "mcp-registry-client",
                "client_version": "1.0.0"
            }

            # Encode configuration in base64
            config_base64 = base64.b64encode(json.dumps(config).encode()).decode()

            # Build full URL
            full_url = f"{url.rstrip('/')}?config={config_base64}"

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            session = await self._get_session()

            # Attempt connection with Claude MCP format
            async with session.post(full_url, json={"type": "init", "body": {}}, headers=headers) as response:
                if response.status == 200:
                    # Read first line to extract tools
                    async for line in response.content:
                        try:
                            data = json.loads(line.decode())
                            if data.get("type") == "tools" and "body" in data:
                                tools = data.get("body", [])

                                # Create placeholder server with discovered tools
                                server_id = f"claude-mcp-{url.replace('://', '-').replace('/', '-').replace(':', '-')}"

                                server = MCPServer(
                                    id=server_id,
                                    name=f"Claude MCP ({url})",
                                    description="Claude-compatible MCP server",
                                    url=url,
                                    version="1.0.0",
                                    status="available",
                                    tools_count=len(tools)
                                )

                                # Register server
                                self.servers[server_id] = server

                                # Add tools
                                for tool in tools:
                                    if "name" in tool:
                                        tool_id = f"{server_id}:{tool['name']}"
                                        tool_obj = MCPTool(
                                            id=tool_id,
                                            server_id=server_id,
                                            name=tool["name"],
                                            description=tool.get("description", ""),
                                            parameters=tool.get("parameters", [])
                                        )
                                        self.tools[tool_id] = tool_obj

                                logger.info(f"Claude MCP server discovered: {server.name} ({url}) with {len(tools)} tools")
                                return server
                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            logger.debug(f"Error parsing line: {str(e)}")

                        # Only read first line
                        break

        except Exception as e:
            logger.debug(f"Claude MCP format discovery failed for {url}: {str(e)}")
            
        return None
        
    async def _discover_from_endpoint(self, discovery_url: str) -> List[MCPServer]:
        """
        Discover MCP servers from a discovery endpoint.
        
        Args:
            discovery_url: URL of the discovery endpoint
            
        Returns:
            List of discovered servers
        """
        session = await self._get_session()
        
        try:
            async with session.get(discovery_url) as response:
                if response.status != 200:
                    logger.warning(f"Discovery endpoint {discovery_url} returned status {response.status}")
                    return []
                    
                data = await response.json()
                
                if not isinstance(data, list):
                    logger.warning(f"Discovery endpoint {discovery_url} returned invalid data format")
                    return []
                    
                servers = []
                for server_data in data:
                    try:
                        url = server_data.get("url")
                        if url:
                            server = await self._fetch_server_info(url)
                            if server:
                                servers.append(server)
                    except Exception as e:
                        logger.warning(f"Failed to process server from discovery: {str(e)}")
                        
                return servers
                
        except Exception as e:
            logger.error(f"Error connecting to discovery endpoint {discovery_url}: {str(e)}")
            return []
            
    async def _fetch_server_info(self, server_url: str) -> Optional[MCPServer]:
        """
        Fetch information about an MCP server.

        Args:
            server_url: URL of the MCP server

        Returns:
            Server information or None if unavailable
        """
        # Use dedicated session for this server to maintain MCP session context
        session = await self._get_server_session(server_url)
        
        # Normalize URL
        if not server_url.endswith("/"):
            server_url += "/"
            
        try:
            headers = {
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json"
            }
            if self.config.auth_token:
                headers["Authorization"] = f"Bearer {self.config.auth_token}"

            # For MCP streamable-http servers, try POST with initialize first
            init_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "MCPRegistry", "version": "1.0.0"}
                }
            }

            server_url_no_slash = server_url.rstrip("/")
            data = None

            # Attempt 1: POST with initialize (MCP streamable-http)
            try:
                async with session.post(server_url_no_slash, headers=headers, json=init_payload) as response:
                    if response.status == 200:
                        # Read SSE response
                        content_type = response.headers.get("Content-Type", "")
                        if "text/event-stream" in content_type:
                            # Parse SSE response - read as text stream
                            text_content = await response.text()
                            for line in text_content.split('\n'):
                                line_str = line.strip()
                                if line_str.startswith('data: '):
                                    data_json = line_str[6:]  # Remove "data: " prefix
                                    try:
                                        data = json.loads(data_json)
                                        if "result" in data:
                                            # Extract server info from initialize response
                                            result = data["result"]
                                            server_info = result.get("serverInfo", {})
                                            data = {
                                                "name": server_info.get("name", "Unknown"),
                                                "version": server_info.get("version", "1.0.0"),
                                                "capabilities": result.get("capabilities", {}),
                                                "protocolVersion": result.get("protocolVersion", "2024-11-05")
                                            }
                                            logger.info(f"✅ MCP server discovered: {data['name']} v{data['version']} at {server_url}")
                                            break
                                    except json.JSONDecodeError as je:
                                        logger.warning(f"Failed to parse SSE data JSON: {je}")
                                        continue
                        else:
                            # Regular JSON response
                            data = await response.json()
                            if "result" in data:
                                result = data["result"]
                                server_info = result.get("serverInfo", {})
                                data = {
                                    "name": server_info.get("name", "Unknown"),
                                    "version": server_info.get("version", "1.0.0"),
                                    "capabilities": result.get("capabilities", {})
                                }
                                logger.info(f"✅ MCP server discovered: {data['name']} v{data['version']} at {server_url}")
            except Exception as e:
                logger.warning(f"POST initialize failed for {server_url}: {str(e)}")

            # Attempt 2: Classic GET if POST failed
            if data is None:
                async with session.get(server_url, headers=headers) as response:
                    if response.status != 200:
                        logger.warning(f"Server {server_url} returned status {response.status}")
                        return None

                    data = await response.json()

            # If no data retrieved, return None
            if data is None:
                logger.warning(f"No data retrieved from {server_url}")
                return None

            # Basic validation
            if not isinstance(data, dict):
                logger.warning(f"Server {server_url} returned invalid data format")
                return None

            # Extract server ID and name, with default values
            server_id = data.get("id", os.path.basename(server_url.rstrip("/")))
            server_name = data.get("name", f"MCP Server {server_id}")

            # Create server object
            server = MCPServer(
                id=server_id,
                name=server_name,
                description=data.get("description", "MCP Server"),
                url=server_url,
                version=data.get("version", "1.0.0"),
                status="available"
            )

            # Try to get tools count
            try:
                tools = await self._fetch_tools(server)
                server.tools_count = len(tools)
            except Exception as e:
                logger.warning(f"Could not fetch tools from {server_url}: {str(e)}")

            return server
                
        except aiohttp.ClientError as e:
            logger.warning(f"Connection error for server {server_url}: {str(e)}")
            return None
        except Exception as e:
            logger.warning(f"Error processing server {server_url}: {str(e)}")
            return None
            
    async def get_tools(self, server_id: Optional[str] = None, 
                        refresh: bool = False) -> List[MCPTool]:
        """
        Get available tools from MCP servers.
        
        Args:
            server_id: Optional server ID to filter tools by server
            refresh: Whether to refresh the tools cache
            
        Returns:
            List of available tools
        """
        if refresh or not self.tools:
            await self.refresh_tools()
            
        if server_id:
            return [tool for tool in self.tools.values() if tool.server_id == server_id]
        else:
            return list(self.tools.values())
            
    async def refresh_tools(self) -> None:
        """
        Refresh the tools cache by fetching tools from all known servers.
        """
        # Discover servers if none are known
        if not self.servers:
            await self.discover_servers()
            
        all_tools = {}
        
        # Fetch tools from each server
        for server in self.servers.values():
            try:
                tools = await self._fetch_tools(server)
                for tool in tools:
                    all_tools[tool.id] = tool
            except Exception as e:
                logger.warning(f"Failed to fetch tools from server {server.id}: {str(e)}")
                
        self.tools = all_tools
        
    async def _fetch_tools(self, server: MCPServer) -> List[MCPTool]:
        """
        Fetch available tools from an MCP server.

        Args:
            server: The server to fetch tools from

        Returns:
            List of available tools
        """
        # Use dedicated session for this server to reuse MCP session context from initialize
        session = await self._get_server_session(server.url)

        server_url_no_slash = server.url.rstrip("/")

        try:
            headers = {
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json"
            }
            if self.config.auth_token:
                headers["Authorization"] = f"Bearer {self.config.auth_token}"

            # MCP JSON-RPC 2.0 tools/list request
            tools_payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {}
            }

            tools_list = []
            data = None

            logger.info(f"🔧 Attempting to retrieve tools from {server.id} ({server_url_no_slash})")

            # First attempt: POST with tools/list (MCP streamable-http)
            try:
                async with session.post(server_url_no_slash, headers=headers, json=tools_payload) as response:
                    logger.info(f"POST tools/list status: {response.status}")
                    if response.status == 200:
                        # Read SSE response
                        content_type = response.headers.get("Content-Type", "")
                        if "text/event-stream" in content_type:
                            # Parse SSE response
                            text_content = await response.text()
                            for line in text_content.split('\n'):
                                line_str = line.strip()
                                if line_str.startswith('data: '):
                                    data_json = line_str[6:]
                                    try:
                                        data = json.loads(data_json)
                                        if "result" in data and "tools" in data["result"]:
                                            tools_list = data["result"]["tools"]
                                            logger.info(f"✅ {len(tools_list)} tools found for {server.id}")
                                            break
                                    except json.JSONDecodeError as je:
                                        logger.warning(f"Failed to parse tools SSE data: {je}")
                                        continue
                        else:
                            # Regular JSON response
                            data = await response.json()
                            if "result" in data and "tools" in data["result"]:
                                tools_list = data["result"]["tools"]
                                logger.info(f"✅ {len(tools_list)} tools found for {server.id}")
            except Exception as e:
                logger.warning(f"POST tools/list failed for {server_url_no_slash}: {str(e)}")

            # Second attempt: GET on /tools if POST failed (fallback REST)
            if not tools_list:
                tools_url = f"{server_url_no_slash}/tools"
                async with session.get(tools_url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Process according to response format
                        # Format 1: Direct tool list
                        if isinstance(data, list):
                            tools_list = data
                        # Format 2: {"tools": [...]}
                        elif isinstance(data, dict) and "tools" in data:
                            tools_list = data["tools"]
                        # Format 3: Response wrapper
                        elif isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                            tools_list = data["data"]
                        else:
                            logger.warning(f"Unknown data format received from {server.url}")

            # Process tools_list if tools were found (POST or GET)
            if tools_list:
                # Create MCPTool objects
                tools = []
                for tool_data in tools_list:
                    try:
                        if "name" not in tool_data:
                            logger.warning(f"Tool without name received from {server.url}")
                            continue

                        tool_id = f"{server.id}:{tool_data['name']}"

                        # Parameter standardization
                        parameters = tool_data.get("parameters", [])

                        # Standard format: {"parameters": {"properties": {...}, "required": [...]}}
                        if isinstance(parameters, dict):
                            # Nothing to do, already correct format
                            pass
                        # List format: [{"name": "x", "type": "string", ...}, ...]
                        elif isinstance(parameters, list):
                            # Convert to standard JSONSchema format
                            properties = {}
                            required = []

                            for param in parameters:
                                if "name" in param:
                                    param_name = param["name"]
                                    properties[param_name] = {
                                        "type": param.get("type", "string"),
                                        "description": param.get("description", "")
                                    }

                                    if param.get("required", False):
                                        required.append(param_name)

                            parameters = {
                                "properties": properties,
                                "required": required
                            }

                        # Create tool with standardized parameters
                        tool = MCPTool(
                            id=tool_id,
                            server_id=server.id,
                            name=tool_data["name"],
                            description=tool_data.get("description", ""),
                            parameters=parameters
                        )
                        tools.append(tool)

                        # Register tool in cache
                        self.tools[tool_id] = tool

                    except Exception as e:
                        logger.warning(f"Error processing tool from {server.id}: {str(e)}")

                logger.info(f"Retrieved {len(tools)} tools from {server.url}")
                return tools

            # Second attempt: /schema endpoint (Claude Desktop, VSCode, etc.)
            schema_url = f"{server.url.rstrip('/')}/schema"
            async with session.get(schema_url, headers=headers) as response:
                if response.status == 200:
                    schema = await response.json()

                    # Extract tools from schema
                    tools_list = []
                    if "tools" in schema:
                        tools_list = schema["tools"]
                    elif "functions" in schema:
                        # Format used by OpenAI and some clients
                        tools_list = schema["functions"]

                    # Create MCPTool objects
                    tools = []
                    for tool_data in tools_list:
                        try:
                            if "name" not in tool_data:
                                continue

                            tool_id = f"{server.id}:{tool_data['name']}"

                            # Extract parameters from schema
                            parameters = {}
                            if "parameters" in tool_data:
                                parameters = tool_data["parameters"]

                            tool = MCPTool(
                                id=tool_id,
                                server_id=server.id,
                                name=tool_data["name"],
                                description=tool_data.get("description", ""),
                                parameters=parameters
                            )
                            tools.append(tool)

                            # Register tool in cache
                            self.tools[tool_id] = tool

                        except Exception as e:
                            logger.warning(f"Error processing tool from {server.id}: {str(e)}")

                    logger.info(f"Retrieved {len(tools)} tools from schema of {server.url}")
                    return tools

            logger.warning(f"No tool found for server {server.id}")
            return []

        except aiohttp.ClientError as e:
            logger.error(f"Connection error retrieving tools from {server.url}: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error retrieving tools from {server.url}: {str(e)}")
            return []
            
    async def execute_tool(self, server_id: str, tool_name: str, 
                          parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool on an MCP server with the given parameters.
        
        Args:
            server_id: ID of the server to execute the tool on
            tool_name: Name of the tool to execute
            parameters: Parameters to pass to the tool
            
        Returns:
            Tool execution result
        
        Raises:
            ServerConnectionError: If the server connection fails
            ToolExecutionError: If tool execution fails
        """
        # Get server information
        server = self.servers.get(server_id)
        if not server:
            try:
                await self.discover_servers()
                server = self.servers.get(server_id)
            except Exception as e:
                raise ServerConnectionError(f"Failed to discover server {server_id}: {str(e)}")
                
        if not server:
            raise ServerConnectionError(f"Unknown server ID: {server_id}")

        # Use dedicated session for this server to maintain MCP session context
        session = await self._get_server_session(server.url)

        # Normalize server URL
        server_url = server.url.rstrip("/")

        # Try multiple execution endpoint formats
        endpoints_to_try = [
            # Standard MCP format
            {
                "url": f"{server_url}/execute",
                "payload": {
                    "name": tool_name,
                    "parameters": parameters
                }
            },
            # Claude Desktop alternative format
            {
                "url": f"{server_url}/tools/{tool_name}/execute",
                "payload": parameters
            },
            # VSCode alternative format
            {
                "url": f"{server_url}/run",
                "payload": {
                    "name": tool_name,
                    "parameters": parameters
                }
            },
            # OpenAI format
            {
                "url": f"{server_url}/v1/functions/{tool_name}",
                "payload": parameters
            }
        ]

        # Common headers
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json"
        }

        if self.config.auth_token:
            headers["Authorization"] = f"Bearer {self.config.auth_token}"

        # Try each endpoint until one works
        last_error = None
        for endpoint in endpoints_to_try:
            try:
                logger.debug(f"Attempting execution of {tool_name} on {endpoint['url']}")

                async with session.post(
                    endpoint["url"],
                    headers=headers,
                    json=endpoint["payload"],
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    # Check if response is valid
                    if response.status >= 200 and response.status < 300:
                        try:
                            response_data = await response.json()
                            logger.info(f"Successful execution of {tool_name} on {server_id}")
                            return response_data
                        except json.JSONDecodeError:
                            # Try reading as text if not JSON
                            text = await response.text()
                            if text:
                                return {"result": text}
                    else:
                        error_text = await response.text()
                        last_error = f"HTTP status {response.status}: {error_text}"
                        logger.debug(f"Failed with endpoint {endpoint['url']}: {last_error}")

            except aiohttp.ClientError as e:
                last_error = f"Connection error: {str(e)}"
                logger.debug(f"Connection error with {endpoint['url']}: {last_error}")
            except Exception as e:
                last_error = str(e)
                logger.debug(f"Exception with {endpoint['url']}: {last_error}")

        # If all endpoints failed, raise exception
        error_msg = f"Tool execution failed for {tool_name} on {server_id}: {last_error}"
        logger.error(error_msg)
        raise ToolExecutionError(error_msg) 