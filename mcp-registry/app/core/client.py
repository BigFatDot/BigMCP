"""
Client for interacting with Model Context Protocol (MCP) servers.
"""

import asyncio
import aiohttp
import json
import logging
from typing import Dict, List, Any, Optional

# Logging configuration
logger = logging.getLogger("mcp_registry.client")

class MCPClient:
    """Client for interacting with a Model Context Protocol server."""

    def __init__(self, server_id: str, server_url: str, headers: Dict[str, str] = None):
        """
        Initialize the MCP client.

        Args:
            server_id: Server identifier
            server_url: MCP server URL
            headers: Optional HTTP headers for requests
        """
        self.server_id = server_id
        self.server_url = server_url.rstrip('/')
        self.headers = headers or {}
        
    async def get_schema(self) -> Dict:
        """
        Retrieve the MCP server schema.

        Returns:
            Schema of available tools
        """
        try:
            logger.info(f"Retrieving MCP schema from {self.server_url}/schema")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.server_url}/schema",
                    headers=self.headers,
                    timeout=10
                ) as response:
                    if response.status == 200:
                        schema = await response.json()
                        logger.info(f"Schema retrieved successfully for {self.server_id}")
                        return schema
                    else:
                        error_text = await response.text()
                        logger.error(f"Error retrieving schema: {response.status} - {error_text}")
                        return {"error": f"Error {response.status}", "message": error_text}
        except asyncio.TimeoutError:
            logger.error(f"Timeout retrieving schema for {self.server_id}")
            return {"error": "Timeout", "message": "Request timed out"}
        except Exception as e:
            logger.exception(f"Exception retrieving schema for {self.server_id}: {str(e)}")
            return {"error": str(e)}
            
    def extract_tools_from_schema(self, schema: Dict) -> List[Dict]:
        """
        Extract and enrich the list of tools from an MCP schema.

        Args:
            schema: Complete MCP schema

        Returns:
            List of enriched available tools
        """
        tools = []

        # Standard tool extraction
        raw_tools = []
        if "tools" in schema:
            raw_tools = schema["tools"]
        elif "functions" in schema:
            raw_tools = schema["functions"]

        # Enrich each tool with server ID and URL
        for tool in raw_tools:
            enriched_tool = dict(tool)
            enriched_tool["server_id"] = self.server_id
            enriched_tool["server_url"] = self.server_url
            tools.append(enriched_tool)

        return tools
        
    async def run_tool(self, tool_id: str, parameters: Dict[str, Any]) -> Dict:
        """
        Execute a specific tool.

        Args:
            tool_id: Identifier of the tool to execute
            parameters: Parameters to pass to the tool

        Returns:
            Execution result
        """
        try:
            logger.info(f"Executing tool {tool_id} on {self.server_id} with parameters: {parameters}")

            async with aiohttp.ClientSession() as session:
                # Payload format according to MCP protocol
                payload = {
                    "name": tool_id,
                    "parameters": parameters
                }

                async with session.post(
                    f"{self.server_url}/run",
                    headers=self.headers,
                    json=payload,
                    timeout=60  # Longer timeout for execution
                ) as response:
                    if response.status >= 200 and response.status < 300:
                        result = await response.json()
                        logger.info(f"Tool {tool_id} executed successfully on {self.server_id}")
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(f"Error executing tool: {response.status} - {error_text}")
                        return {"error": f"Error {response.status}", "message": error_text}
        except asyncio.TimeoutError:
            logger.error(f"Timeout executing tool {tool_id} on {self.server_id}")
            return {"error": "Timeout", "message": "Request timed out"}
        except Exception as e:
            logger.exception(f"Exception executing tool {tool_id} on {self.server_id}: {str(e)}")
            return {"error": str(e)} 