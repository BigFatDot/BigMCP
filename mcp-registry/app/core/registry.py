"""
MCP Registry module, serving as interface between clients and MCP servers.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any
import os
import uuid
import httpx
from fastapi import HTTPException

from ..config.settings import settings
from .vector_store import VectorStore
from .mcp_client import MCPClient
from .server_manager import MCPServerManager

logger = logging.getLogger(__name__)


def _to_dict(obj: Any) -> Dict[str, Any]:
    """
    Convert Pydantic model to dict, supporting both v1 and v2.

    Args:
        obj: Pydantic model instance or dict

    Returns:
        Dictionary representation
    """
    if hasattr(obj, 'model_dump'):  # Pydantic v2
        return obj.model_dump()
    elif hasattr(obj, 'dict'):  # Pydantic v1
        return obj.dict()
    elif isinstance(obj, dict):  # Already a dict
        return obj
    else:
        return {}


class MCPRegistry:
    """
    MCP Registry. Enables discovery and management of MCP servers.

    This class is the core of the service, managing:
    - Discovery and addition of MCP servers
    - Tool indexing with FAISS
    - Semantic tool search
    - Tool execution
    """

    def __init__(self):
        """
        Initialize the MCP Registry.
        """
        self.vector_store = VectorStore(
            config=settings.embedding
        )
        
        self.mcp_client = MCPClient(
            config=settings.registry
        )
        
        self.server_manager = MCPServerManager()
        
        self.servers = {}
        self.tools = {}
        self.last_update = 0
        self.is_running = False
        self.discovery_task = None
        
        # Support for standard MCP features
        self.supported_features = {
            "resources": True,  # Support for resources
            "prompts": True,    # Support for prompts
            "tools": True,      # Already supported
            "sampling": False   # Not yet implemented
        }
        
    async def start(self) -> None:
        """
        Start the MCP registry service.

        - Start configured MCP servers
        - Discover servers
        - Build search index
        - Launch periodic discovery task
        """
        if self.is_running:
            logger.warning("MCP registry is already running")
            return

        logger.info("Starting MCP registry")

        # Start servers if configured
        if settings.registry.manage_servers:
            logger.info("Starting configured MCP servers")
            server_results = await self.server_manager.start_servers()
            for server_id, result in server_results.items():
                if result.get("status") in ["success", "already_running"]:
                    logger.info(f"MCP server {server_id} started or already running")
                else:
                    logger.error(f"Error starting MCP server {server_id}: {result}")
        
        # Retrieve tools directly from managed server wrappers
        if settings.registry.manage_servers:
            logger.info("Retrieving tools from managed servers")
            managed_tools = await self.server_manager.get_all_tools()

            for server_id, tools in managed_tools.items():
                # Create or update server entry in registry
                if server_id not in self.servers:
                    server_info = self.server_manager.get_server_status(server_id)
                    self.servers[server_id] = {
                        "id": server_id,
                        "name": server_info.get("server_info", {}).get("name", server_id),
                        "url": server_info.get("url", ""),
                        "version": server_info.get("server_info", {}).get("version", "1.0.0"),
                        "status": "available"
                    }

                # Add tools to registry
                for tool in tools:
                    tool_id = f"{server_id}.{tool.get('name', 'unknown')}"
                    self.tools[tool_id] = {
                        "id": tool_id,
                        "name": tool.get("name", "unknown"),
                        "description": tool.get("description", ""),
                        "server_id": server_id,
                        "input_schema": tool.get("inputSchema", {}),
                        **tool
                    }

                logger.info(f"✅ {len(tools)} tools registered from {server_id}")

        # Add URLs of started servers for additional discovery
        for server_id, server_info in self.server_manager.get_all_servers_status().items():
            if server_info.get("status") in ["running", "already_running"]:
                url = self.server_manager.get_server_url(server_id)
                if url:
                    logger.info(f"Adding MCP server URL {server_id}: {url}")
                    settings.registry.server_urls = settings.registry.server_urls or []
                    if url not in settings.registry.server_urls:
                        settings.registry.server_urls.append(url)

        # Discover additional servers (unmanaged)
        await self.discover_servers()

        # Build the index
        self.build_vector_index()

        # Update cache timestamp
        self.last_update = time.time()

        # Start periodic discovery task if configured
        if settings.registry.discovery_enabled and settings.registry.discovery_interval > 0:
            self.discovery_task = asyncio.create_task(self._discovery_loop())
            logger.info(f"Periodic discovery task started (interval: {settings.registry.discovery_interval}s)")

        self.is_running = True
        logger.info(f"✅ MCP Registry started - {len(self.tools)} tools loaded, last_update={self.last_update}")

        # Notify any clients that connected during startup
        self._notify_tools_changed()

    def _notify_tools_changed(self) -> None:
        """
        Notify connected SSE clients that the tools list has changed.
        Uses asyncio.create_task to avoid blocking the current operation.
        """
        try:
            from ..routers.mcp_unified import broadcast_tools_changed
            asyncio.create_task(broadcast_tools_changed())
            logger.debug("Scheduled tools/list_changed notification broadcast")
        except ImportError:
            logger.warning("Could not import broadcast_tools_changed - notifications disabled")
        except Exception as e:
            logger.warning(f"Failed to broadcast tools notification: {e}")

    async def stop(self) -> None:
        """
        Stop the MCP registry service and associated servers.
        """
        logger.info("Stopping MCP registry")

        self.is_running = False

        # Stop the discovery task
        if self.discovery_task:
            self.discovery_task.cancel()
            try:
                await self.discovery_task
            except asyncio.CancelledError:
                pass
            self.discovery_task = None
            
        # Close client connections
        await self.mcp_client.close()

        # Stop servers if necessary
        if settings.registry.manage_servers:
            logger.info("Stopping MCP servers")
            self.server_manager.stop_all_servers()

        logger.info("MCP registry stopped")
        
    async def discover_servers(self) -> List[Dict[str, Any]]:
        """
        Discover available MCP servers.

        Returns:
            List of discovered servers
        """
        logger.info(f"🔍 Discovering MCP servers - Current state: {len(self.tools)} tools in self.tools")

        try:
            # Discover servers via MCP client
            servers = await self.mcp_client.discover_servers()

            if not servers:
                logger.warning(f"No MCP server discovered - {len(self.tools)} tools still present")
                return []

            logger.info(f"{len(servers)} MCP servers discovered")

            # Update known servers
            for server in servers:
                self.servers[server.id] = server

            # Retrieve tools from servers
            await self.refresh_tools()

            # Update last update time
            self.last_update = time.time()

            return [server.dict() for server in servers]

        except Exception as e:
            logger.error(f"Error discovering MCP servers: {str(e)}")
            return []
            
    async def refresh_tools(self) -> List[Dict[str, Any]]:
        """
        Refresh the list of available tools from all servers.

        Returns:
            List of updated tools
        """
        logger.info(f"🔄 Refreshing MCP tools - Current state: {len(self.tools)} tools")

        try:
            # Priority 1: Use servers managed by server_manager (STDIO)
            if settings.registry.manage_servers and self.server_manager:
                logger.info("Retrieving tools from managed servers (STDIO)")
                managed_tools = await self.server_manager.get_all_tools()
                logger.info(f"📦 managed_tools retrieved: {len(managed_tools)} servers, {sum(len(tools) for tools in managed_tools.values())} tools total")

                # Build new tools in temporary dictionary
                # WITHOUT destroying existing tools
                new_tools = {}

                for server_id, tools in managed_tools.items():
                    for tool_dict in tools:
                        # Convert to ToolInfo and add to registry
                        from ..api.models import ToolInfo

                        # Add server_id if missing
                        if "server_id" not in tool_dict:
                            tool_dict["server_id"] = server_id

                        # Create unique ID for tool (format: server_id.tool_name)
                        tool_id = f"{server_id}.{tool_dict.get('name', tool_dict.get('id', ''))}"
                        if "id" not in tool_dict:
                            tool_dict["id"] = tool_id

                        tool = ToolInfo(**tool_dict)
                        new_tools[tool.id] = tool

                # Only update self.tools if we actually retrieved new tools
                if new_tools:
                    self.tools = new_tools

                    # Rebuild vector index
                    self.build_vector_index()

                    # Update timestamp
                    self.last_update = time.time()

                    logger.info(f"{len(self.tools)} MCP tools updated from {len(managed_tools)} managed servers")

                    # Notify connected clients that tools have changed
                    self._notify_tools_changed()

                    return [_to_dict(tool) for tool in self.tools.values()]
                else:
                    # If no new tools found, keep existing tools
                    logger.warning("No new tools retrieved, keeping existing tools")
                    if self.tools:
                        return [_to_dict(tool) for tool in self.tools.values()]
                    return []

            # Priority 2: Fallback to legacy HTTP discovery system
            else:
                logger.info("Attempting tool discovery via HTTP (fallback)")
                tools = await self.mcp_client.get_tools(refresh=True)

                if not tools:
                    logger.warning("No MCP tool found via HTTP")
                    # Keep existing tools
                    if self.tools:
                        return [_to_dict(tool) for tool in self.tools.values()]
                    return []

                # Update tools
                self.tools = {tool.id: tool for tool in tools}

                # Rebuild vector index
                self.build_vector_index()

                # Update timestamp
                self.last_update = time.time()

                logger.info(f"{len(tools)} MCP tools updated via HTTP")

                # Notify connected clients that tools have changed
                self._notify_tools_changed()

                return [_to_dict(tool) for tool in tools]

        except Exception as e:
            logger.error(f"Error refreshing MCP tools: {str(e)}")
            # In case of error, return existing tools if they exist
            if self.tools:
                logger.info(f"Error during refresh, keeping {len(self.tools)} existing tools")
                return [_to_dict(tool) for tool in self.tools.values()]
            return []

    def _enrich_tool_metadata(self, tool: Any) -> Dict[str, Any]:
        """
        Enrich tool with server metadata.

        Used by both get_tools() and search_tools() to ensure consistency.

        Args:
            tool: Tool object (ToolInfo) or dict

        Returns:
            Enriched tool dictionary
        """
        # Convert to dict if needed
        tool_dict = tool.dict() if hasattr(tool, 'dict') else (tool if isinstance(tool, dict) else {})

        # Get server info
        srv_id = tool_dict.get("server_id", "")

        # Build servers_dict from self.servers
        servers_dict = {}
        for server in self.servers.values():
            if isinstance(server, dict):
                servers_dict[server.get("id", "")] = server
            else:
                servers_dict[getattr(server, "id", "")] = server

        server_info = servers_dict.get(srv_id, {})
        if not isinstance(server_info, dict):
            # Convert to dict if it's an object
            server_info = server_info.dict() if hasattr(server_info, 'dict') else {}

        # Add enriched metadata
        tool_dict["server_info"] = {
            "id": srv_id,
            "name": server_info.get("name", ""),
            "description": server_info.get("description", ""),
            "url": server_info.get("url", "")
        }

        # Add registry identifiers
        registry_id = "mcp-registry"
        tool_dict["registry_id"] = registry_id
        tool_dict["unique_id"] = f"{registry_id}:{srv_id}:{tool_dict.get('id', '')}"

        return tool_dict

    def build_vector_index(self) -> None:
        """
        Build the vector index of MCP tools with enriched metadata.
        """
        if not self.tools:
            logger.warning("No MCP tool to index")
            return

        try:
            logger.info(f"Building vector index for {len(self.tools)} MCP tools")

            # Retrieve servers to enrich indexing
            servers_dict = {}
            for server in self.servers.values():
                servers_dict[server["id"]] = server

            # Convert tools to dictionaries for indexing
            tools_list = []

            for tool in self.tools.values():
                # Convert tool to dict if it's a Pydantic model
                if isinstance(tool, dict):
                    tool_dict = tool
                else:
                    # Support both Pydantic v1 (.dict()) and v2 (.model_dump())
                    tool_dict = tool.model_dump() if hasattr(tool, 'model_dump') else tool.dict()

                server_id = tool_dict.get("server_id", "")
                server_info = servers_dict.get(server_id, {})

                # Create enriched index text including:
                # 1. Tool name and description
                # 2. Origin server name and description
                # 3. Parameters description

                # Base tool text
                index_text = f"{tool_dict.get('name', '')} - {tool_dict.get('description', '')}"

                # Add server information
                server_name = server_info.get("name", "")
                server_desc = server_info.get("description", "")
                if server_name:
                    index_text += f" - Server: {server_name}"
                if server_desc:
                    index_text += f" - {server_desc}"

                # Add parameter information
                params = tool_dict.get("parameters", {})
                if params and isinstance(params, dict):
                    if "properties" in params:
                        properties = params.get("properties", {})
                        param_texts = []
                        for name, prop in properties.items():
                            desc = prop.get("description", "")
                            if desc:
                                param_texts.append(f"{name}: {desc}")

                        if param_texts:
                            index_text += f" - Parameters: {' | '.join(param_texts)}"

                # Store enriched index text
                tool_dict["_index_text"] = index_text
                tools_list.append(tool_dict)

            # Build the index
            self.vector_store.build_index(tools_list)

            logger.info("Vector index built successfully")

        except Exception as e:
            logger.error(f"Error building vector index: {str(e)}")
            
    async def search_tools(self, query: str, limit: int = 5):
        """
        Search for tools that best match the query.

        Args:
            query: Search query
            limit: Maximum number of results to return

        Returns:
            List of tools sorted by relevance
        """
        # Ensure we have up-to-date tools
        await self.update_tools()

        if not self.tools:
            logger.warning("No tool available for search")
            return []

        # Convert tools to a list
        tools_list = list(self.tools.values())

        # Define maximum number of tools to retrieve initially
        # We retrieve all available tools for reranking
        max_initial_tools = len(tools_list)

        # If vector search is available, use it
        try:
            if self.vector_store:
                # Retrieve all tools via vector search
                tool_ids = self.vector_store.search(
                    query=query,
                    limit=max_initial_tools
                )

                # Retrieve matching tools
                all_tool_results = []
                for tool_id in tool_ids:
                    if tool_id in self.tools:
                        all_tool_results.append(self.tools[tool_id])

                # If we have results, apply reranking with LLM API
                if all_tool_results:
                    # Convert tools to dictionaries for reranking
                    rerank_tools = []
                    for tool in all_tool_results:
                        if hasattr(tool, 'dict'):
                            tool_dict = tool.dict()
                        else:
                            # Fallback if not an object with dict() method
                            tool_dict = vars(tool) if hasattr(tool, "__dict__") else {"id": str(tool)}

                        # Create rich text for reranking
                        name = tool_dict.get("name", "")
                        description = tool_dict.get("description", "")

                        # Include parameter information
                        params_info = ""
                        params = tool_dict.get("parameters", {})
                        if params and isinstance(params, dict) and "properties" in params:
                            properties = params.get("properties", {})
                            params_info = ", ".join([
                                f"{name}: {prop.get('description', '')}"
                                for name, prop in properties.items()
                            ])

                        # Full text for reranking
                        rerank_text = f"{name}: {description}"
                        if params_info:
                            rerank_text += f". Parameters: {params_info}"

                        rerank_tools.append({
                            "id": tool_dict.get("id", ""),
                            "text": rerank_text,
                            "tool": tool  # Keep reference to original tool
                        })
                    
                    # Retrieve LLM API configuration from environment variables
                    llm_api_url = os.environ.get("LLM_API_URL", "https://api.mistral.ai/v1")
                    llm_api_key = os.environ.get("LLM_API_KEY", "")

                    if llm_api_key:
                        try:
                            import requests

                            # Chunk tools in batches of 64 (standard limit)
                            BATCH_SIZE = 64
                            all_ranked_results = []

                            # Call reranking API by batch
                            headers = {
                                "Authorization": f"Bearer {llm_api_key}",
                                "Content-Type": "application/json"
                            }

                            for batch_start in range(0, len(rerank_tools), BATCH_SIZE):
                                batch_end = min(batch_start + BATCH_SIZE, len(rerank_tools))
                                batch_tools = rerank_tools[batch_start:batch_end]

                                # Prepare data for reranking API
                                rerank_data = {
                                    "model": "rerank-small",
                                    "prompt": query,
                                    "input": [item["text"] for item in batch_tools]
                                }

                                rerank_url = f"{llm_api_url}/rerank" if "/v1" in llm_api_url else f"{llm_api_url}/v1/rerank"
                                response = requests.post(
                                    rerank_url,
                                    headers=headers,
                                    json=rerank_data
                                )

                                if response.status_code == 200:
                                    # Process reranking results
                                    rerank_results = response.json()

                                    # Response format contains list of results with index and score
                                    for result in rerank_results.get("results", []):
                                        batch_index = result.get("index")
                                        relevance_score = result.get("relevance_score", 0)

                                        if batch_index is not None:
                                            # Convert batch index to global index
                                            global_index = batch_start + batch_index
                                            all_ranked_results.append((global_index, relevance_score))
                                else:
                                    logger.warning(f"Reranking API call failed for batch {batch_start}-{batch_end}: {response.status_code} - {response.text}")

                            if all_ranked_results:
                                # Sort all results by relevance score descending
                                all_ranked_results.sort(key=lambda x: x[1], reverse=True)

                                # Rebuild tool list in reranking order with enriched metadata
                                reranked_tools = []
                                for idx, score in all_ranked_results:
                                    if idx < len(rerank_tools):
                                        tool = rerank_tools[idx]["tool"]
                                        # Enrich with server_info, registry_id metadata, etc.
                                        tool_dict = self._enrich_tool_metadata(tool)
                                        # Add reranking score
                                        tool_dict['relevance_score'] = score
                                        reranked_tools.append(tool_dict)

                                # Limit to requested results
                                return reranked_tools[:limit]
                            else:
                                logger.warning("No reranking result obtained")
                        except Exception as e:
                            logger.error(f"Error during reranking with LLM API: {str(e)}")

                # If reranking failed or unavailable, enrich and return original results
                enriched_results = [self._enrich_tool_metadata(tool) for tool in all_tool_results[:limit]]
                return enriched_results
        except Exception as e:
            logger.error(f"Error during vector search: {str(e)}")

        # Fallback text-based search if vector search fails
        results = []
        query_lower = query.lower()

        # Function to evaluate tool relevance to the query
        def score_tool(tool):
            score = 0
            name = tool.name.lower()
            description = tool.description.lower() if tool.description else ""

            # Bonus for exact match in name
            if query_lower == name:
                score += 100
            # Bonus for word present in name
            elif query_lower in name:
                score += 50
            # Bonus for query words present in name
            else:
                for word in query_lower.split():
                    if word in name:
                        score += 10

            # Bonus for query words present in description
            for word in query_lower.split():
                if word in description:
                    score += 5

            return score

        # Calculate scores for all tools
        scored_tools = [(tool, score_tool(tool)) for tool in tools_list]

        # Sort by score and take the best
        scored_tools.sort(key=lambda x: x[1], reverse=True)
        results = [tool for tool, score in scored_tools[:limit] if score > 0]

        # If no relevant result, take the first tools
        if not results and tools_list:
            results = tools_list[:limit]

        return results
        
    async def update_tools(self) -> List[Dict[str, Any]]:
        """
        Update the list of available tools.

        This method ensures that the tool list and vector index
        are up-to-date before a search or analysis operation.

        Returns:
            List of updated tools
        """
        # Check if cache is expired
        cache_expired = time.time() - self.last_update > settings.registry.cache_ttl

        if not self.tools or cache_expired:
            logger.info("Updating MCP tools")

            try:
                # Use refresh_tools for complete update
                result = await self.refresh_tools()
                return result
            except Exception as e:
                logger.error(f"Error updating MCP tools: {str(e)}")

                # In case of error, return existing tools
                if self.tools:
                    return [tool.dict() if hasattr(tool, 'dict') else tool for tool in self.tools.values()]
                return []

        # If tools are already up-to-date, simply return them
        return [tool.dict() if hasattr(tool, 'dict') else tool for tool in self.tools.values()]
        
    async def analyze_intent(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze user intent to determine the best server/tool to use.

        Args:
            tool_name: Requested tool name
            parameters: Provided parameters

        Returns:
            Dictionary with recommended server, tool and parameters
        """
        # Ensure we have up-to-date tools
        await self.update_tools()

        # By default, we will search by exact tool name
        server_id = None
        matched_tool = None

        # Search for tool by exact name
        for tool_id, tool in self.tools.items():
            if tool.name == tool_name:
                server_id = tool.server_id
                matched_tool = tool
                break

        # If no exact tool found, try similar search
        if not server_id:
            search_query = tool_name
            # Add parameters to query to improve search
            if parameters:
                param_str = " ".join(f"{k}:{v}" for k, v in parameters.items() if isinstance(v, (str, int, float, bool)))
                search_query = f"{search_query} {param_str}"

            results = await self.search_tools(search_query, limit=1)
            if results:
                matched_tool = results[0]
                server_id = matched_tool.server_id

        # If we found a tool, verify parameters are valid
        if matched_tool:
            # TODO: Implement parameter validation according to tool schema
            pass

        return {
            "server_id": server_id,
            "tool_name": tool_name,
            "parameters": parameters,
            "matched_tool": matched_tool.dict() if matched_tool else None
        }
        
    async def get_servers(self, refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Retrieve the list of MCP servers.

        Args:
            refresh: Force server rediscovery

        Returns:
            List of servers
        """
        # If cache is expired or refresh is requested, rediscover servers
        cache_expired = time.time() - self.last_update > settings.registry.cache_ttl

        if not self.servers or cache_expired or refresh:
            await self.discover_servers()

        return list(self.servers.values())
        
    async def get_tools(self, server_id: Optional[str] = None,
                  refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Retrieve the list of MCP tools with enriched metadata.

        Args:
            server_id: Server ID (optional to filter by server)
            refresh: Force tool refresh

        Returns:
            List of tools with enriched metadata
        """
        # Check if cache is expired or refresh is requested
        cache_expired = time.time() - self.last_update > settings.registry.cache_ttl

        if not self.tools or cache_expired or refresh:
            await self.refresh_tools()

        # Retrieve servers to enrich metadata
        servers_dict = {}
        for server in self.servers.values():
            servers_dict[server["id"]] = server

        # Filter by server if necessary
        if server_id:
            tools = [tool for tool in self.tools.values()
                   if tool.server_id == server_id]
        else:
            tools = list(self.tools.values())

        # Enrich metadata for each tool
        enriched_tools = []
        for tool in tools:
            tool_dict = _to_dict(tool)

            # Get server information
            srv_id = tool_dict.get("server_id", "")
            server_info = servers_dict.get(srv_id, {})

            # Add enriched metadata
            tool_dict["server_info"] = {
                "id": srv_id,
                "name": server_info.get("name", ""),
                "description": server_info.get("description", ""),
                "url": server_info.get("url", "")
            }

            # Use constant value for registry_id instead of settings.app.id which doesn't exist
            registry_id = "mcp-registry"
            tool_dict["registry_id"] = registry_id
            tool_dict["unique_id"] = f"{registry_id}:{srv_id}:{tool_dict.get('id', '')}"

            enriched_tools.append(tool_dict)

        # If no tool found, log a warning
        if not enriched_tools:
            logger.warning(f"No tool found for server {server_id if server_id else 'all servers'}")

        return enriched_tools

    async def get_all_tools(self, refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Retrieve all available tools.

        Alias for get_tools without server_id for router compatibility.

        Args:
            refresh: Force tool refresh

        Returns:
            List of all tools
        """
        tools = await self.get_tools(server_id=None, refresh=refresh)

        if not tools:
            logger.warning("No tool found in get_all_tools()")

            # Ensure cache is updated with current time
            # to avoid repeated calls if tools are actually empty
            self.last_update = time.time()

            # Return empty list rather than None
            return []

        return tools
        
    async def get_tool(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve details of a specific MCP tool.

        Args:
            tool_id: Tool ID

        Returns:
            Tool details or None if not found
        """
        if tool_id in self.tools:
            return self.tools[tool_id].dict()
        return None
        
    async def execute_tool(self, server_id: str, tool_id: str, parameters: Dict[str, Any]) -> Any:
        """
        Execute a specific MCP tool via the server wrapper.

        Args:
            server_id: ID of the server to use
            tool_id: ID of the tool to execute
            parameters: Parameters for the tool

        Returns:
            Tool execution result

        Raises:
            HTTPException: If tool is not found or there is an execution error
        """
        logger.info(f"Executing tool {tool_id} on server {server_id} with parameters: {parameters}")

        try:
            # Verify server exists in server_manager
            if not self.server_manager.is_server_running(server_id):
                logger.error(f"Server {server_id} not found or not started")
                raise HTTPException(
                    status_code=404,
                    detail=f"Server {server_id} not found or not started"
                )

            # Retrieve server wrapper from server_manager
            server_info = self.server_manager.servers.get(server_id)
            if not server_info or "wrapper" not in server_info:
                logger.error(f"Wrapper not found for server {server_id}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Wrapper not available for server {server_id}"
                )

            wrapper = server_info["wrapper"]

            # Extract tool name from tool_id (format: server_id.tool_name)
            # The wrapper expects just the tool name, not the full tool_id
            if "." in tool_id:
                tool_name = tool_id.split(".", 1)[1]  # Split on first dot only
            else:
                tool_name = tool_id

            # Execute tool via wrapper
            logger.info(f"Calling tool {tool_name} via wrapper {server_id}")
            result = await wrapper.call_tool(tool_name, parameters)

            logger.info(f"✅ Tool {tool_id} executed successfully")
            return result

        except HTTPException:
            # Re-raise HTTP exceptions directly
            raise

        except Exception as e:
            logger.error(f"❌ Error executing tool {tool_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Execution error: {str(e)}"
            )

    async def get_tool_by_id(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a tool by its complete ID.

        This method is an alias of get_tool for router compatibility.

        Args:
            tool_id: Complete tool ID

        Returns:
            Tool details or None if not found
        """
        return await self.get_tool(tool_id)

    async def _discovery_loop(self) -> None:
        """
        Periodic discovery loop for MCP servers.
        """
        while self.is_running:
            try:
                # Execute discovery
                await self.discover_servers()

                # Also try to discover from MCP client configurations
                await self._discover_from_mcp_client_configs()

            except Exception as e:
                logger.error(f"Error in discovery loop: {str(e)}")

            # Wait for configured interval
            await asyncio.sleep(settings.registry.discovery_interval)

    async def _discover_from_mcp_client_configs(self) -> None:
        """Discover MCP servers from standard MCP client configurations"""
        from pathlib import Path
        import json

        # Standard paths for MCP client configurations
        config_paths = [
            # Claude Desktop
            Path.home() / ".config" / "claude" / "servers.json",
            # Windows - Claude Desktop
            Path.home() / "AppData" / "Roaming" / "Claude" / "servers.json",
            # VS Code settings
            Path.home() / ".config" / "Code" / "User" / "settings.json",
            # Cursor
            Path.home() / ".cursor" / "mcp" / "servers.json"
        ]

        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path, "r") as f:
                        data = json.load(f)

                    # Different formats depending on clients
                    servers = []
                    if isinstance(data, list):  # Claude Desktop format
                        servers = data
                    elif isinstance(data, dict):
                        # VS Code format
                        if "mcp.servers" in data:
                            servers = data["mcp.servers"]
                        # Cursor format
                        elif "servers" in data:
                            servers = data["servers"]

                    # Process each server
                    for server in servers:
                        if "url" in server and "id" in server:
                            # Add to URL list to explore
                            settings.registry.server_urls = settings.registry.server_urls or []
                            if server["url"] not in settings.registry.server_urls:
                                settings.registry.server_urls.append(server["url"])

                except Exception as e:
                    logger.warning(f"Error reading {config_path}: {str(e)}")
                    
    async def get_info(self) -> Dict[str, Any]:
        """
        Return MCP Registry information according to MCP standard.

        Returns:
            MCP Registry information
        """
        # Collect server information
        servers = await self.get_servers()
        server_count = len(servers)

        # Collect tool information
        tools = await self.get_tools()
        tool_count = len(tools)

        # Create response according to standard format
        return {
            "name": "BigMCP Registry",
            "description": "Centralized MCP Gateway with automatic server discovery",
            "version": "1.0.0",
            "contact": {
                "name": "BigMCP Team"
            },
            "supported_features": self.supported_features,
            "metrics": {
                "servers": server_count,
                "tools": tool_count,
                "last_update": int(self.last_update)
            },
            "authentication": {
                "required": False,
                "types": ["bearer"]
            }
        }

    async def get_servers_info(self) -> List[Dict[str, Any]]:
        """
        Return information about registered MCP servers.

        Returns:
            List of servers in standard format
        """
        result = []
        for server_id, server in self.servers.items():
            # Convert to dict if necessary
            if hasattr(server, 'dict'):
                server_dict = server.dict()
            else:
                server_dict = server

            # Structure according to standard format
            result.append({
                "id": server_id,
                "name": server_dict.get("name", server_id),
                "description": server_dict.get("description", ""),
                "url": server_dict.get("url", ""),
                "features": server_dict.get("features", {"tools": True}),
                "version": server_dict.get("version", "1.0.0"),
                "tools_count": server_dict.get("tools_count", 0)
            })

        return result

    async def get_tools_for_query(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieve tools matching a search query.

        Alias for search_tools for router compatibility.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching tools
        """
        tools = await self.search_tools(query, limit=limit)

        if not tools:
            logger.warning(f"No tool found for query: {query}")

            # If no tool is found, we don't make assumptions about the specific service
            # the user is looking for. It's up to the orchestrator to handle this case.
            return []

        return tools 