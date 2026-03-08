"""
MCP Server Manager Module.

This module provides functionalities to start, monitor, and stop
MCP servers based on a configuration similar to Claude Desktop.
"""

import json
import logging
import os
import shlex
import subprocess
import sys
import time
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any

from .mcp_installer import MCPInstaller
from .mcp_wrapper import create_wrapper, MCPServerWrapper

logger = logging.getLogger(__name__)

class MCPServerManager:
    """
    MCP Server Manager.

    This class allows starting, monitoring, and stopping MCP servers
    based on a configuration similar to Claude Desktop.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the MCP server manager.

        Args:
            config_path: Path to the MCP servers configuration file.
                If None, searches in standard locations.
        """
        self.config_path = config_path
        self.config = {}
        self.servers = {}
        self.installer = MCPInstaller()
        self._load_config()
        
    def _load_config(self) -> None:
        """Load the MCP servers configuration."""
        if not self.config_path:
            # Search in standard locations
            paths = [
                Path("./conf/mcp_servers.json"),
                Path("../conf/mcp_servers.json"),
                Path("/etc/mcp-registry/mcp_servers.json"),
                Path(os.path.expanduser("~/.config/claude-desktop/claude_desktop_config.json")),
            ]
            
            for path in paths:
                if path.exists():
                    self.config_path = str(path)
                    break
        
        if not self.config_path or not os.path.exists(self.config_path):
            logger.warning("No MCP configuration file found")
            return
            
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                
            if "mcpServers" in config:
                self.config = config["mcpServers"]
            else:
                self.config = config
                
            logger.info(f"MCP configuration loaded from {self.config_path}")
        except Exception as e:
            logger.error(f"Error loading MCP configuration: {str(e)}")
    
    async def start_servers(self) -> Dict[str, Any]:
        """
        Start all MCP servers defined in the configuration.
        Automatically installs servers if necessary.

        Returns:
            Dictionary of started servers with their status
        """
        results = {}

        for server_id, server_config in self.config.items():
            try:
                # Step 1: Automatic installation
                logger.info(f"Verifying installation of server '{server_id}'")
                install_success = await self.installer.ensure_server_installed(server_id, server_config)

                if not install_success:
                    logger.error(f"Unable to install server '{server_id}', aborting startup")
                    results[server_id] = {"status": "error", "error": "Installation failed"}
                    continue

                # Step 2: Start the server
                result = await self.start_server(server_id, server_config)
                results[server_id] = result

            except Exception as e:
                logger.error(f"Error starting MCP server {server_id}: {str(e)}")
                results[server_id] = {"status": "error", "error": str(e)}

        return results
        
    async def start_server(self, server_id: str, server_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Start a specific MCP server using the universal wrapper.

        Args:
            server_id: Server identifier
            server_config: Server configuration

        Returns:
            Server startup status
        """
        if server_id in self.servers and self.servers[server_id].get("wrapper") and self.servers[server_id]["wrapper"].is_initialized:
            logger.info(f"MCP server {server_id} is already running")
            return {"status": "already_running"}

        command = server_config.get("command")
        args = server_config.get("args", [])

        if not command:
            logger.error(f"Command not specified for MCP server {server_id}")
            return {"status": "error", "error": "Command not specified"}

        logger.info(f"Creating wrapper for MCP server {server_id}")

        try:
            # Create the appropriate wrapper (STDIO or HTTP) based on configuration
            wrapper = create_wrapper(server_id, server_config)

            # Initialize the MCP server via the wrapper
            logger.info(f"Initializing MCP server {server_id} via wrapper")
            server_info = await wrapper.initialize()

            # Store server information with the wrapper
            self.servers[server_id] = {
                "wrapper": wrapper,
                "config": server_config,
                "start_time": time.time(),
                "server_info": server_info
            }

            logger.info(f"✅ MCP server {server_id} initialized: {server_info.get('name', 'Unknown')}")
            return {"status": "success", "server_info": server_info}

        except Exception as e:
            logger.error(f"❌ Error starting MCP server {server_id}: {str(e)}")
            return {"status": "error", "error": str(e)}
    
    async def stop_server(self, server_id: str) -> Dict[str, Any]:
        """
        Stop a specific MCP server.

        Args:
            server_id: Server identifier

        Returns:
            Server shutdown status
        """
        if server_id not in self.servers or not self.servers[server_id].get("wrapper"):
            logger.warning(f"MCP server {server_id} is not running")
            return {"status": "not_running"}

        wrapper = self.servers[server_id]["wrapper"]

        try:
            # Close the wrapper properly
            await wrapper.close()

            logger.info(f"MCP server {server_id} stopped")

            # Clean up server information
            del self.servers[server_id]

            return {"status": "success"}

        except Exception as e:
            logger.error(f"Error stopping MCP server {server_id}: {str(e)}")
            return {"status": "error", "error": str(e)}
    
    async def stop_all_servers(self) -> Dict[str, Any]:
        """
        Stop all running MCP servers.

        Returns:
            Server shutdown status
        """
        results = {}

        for server_id in list(self.servers.keys()):
            results[server_id] = await self.stop_server(server_id)

        return results
    
    def is_server_running(self, server_id: str) -> bool:
        """
        Check if an MCP server is running.

        Args:
            server_id: Server identifier

        Returns:
            True if the server is running, False otherwise
        """
        if server_id not in self.servers or not self.servers[server_id].get("wrapper"):
            return False

        wrapper = self.servers[server_id]["wrapper"]
        return wrapper.is_initialized
    
    def get_server_status(self, server_id: str) -> Dict[str, Any]:
        """
        Get the status of an MCP server.

        Args:
            server_id: Server identifier

        Returns:
            Server status
        """
        if server_id not in self.servers:
            return {"status": "unknown"}

        server_info = self.servers[server_id]
        wrapper = server_info.get("wrapper")

        if not wrapper:
            return {"status": "stopped"}

        if wrapper.is_initialized:
            uptime = time.time() - server_info.get("start_time", time.time())
            return {
                "status": "running",
                "uptime": int(uptime),
                "server_info": wrapper.server_info,
                "url": wrapper.url
            }
        else:
            return {"status": "stopped"}
    
    def get_all_servers_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get the status of all MCP servers.

        Returns:
            Status of all servers
        """
        results = {}

        # Currently managed servers
        for server_id in self.servers.keys():
            results[server_id] = self.get_server_status(server_id)

        # Servers defined in configuration but not yet started
        for server_id in self.config.keys():
            if server_id not in results:
                results[server_id] = {"status": "not_started"}

        return results
    
    def get_server_url(self, server_id: str) -> Optional[str]:
        """
        Get the URL of an MCP server based on heuristics.

        Args:
            server_id: Server identifier

        Returns:
            Server URL or None if undetermined
        """
        # For now, using simple heuristics based on server name
        # Eventually, this should be configured or auto-discovered

        if server_id == "grist-mcp":
            return "http://localhost:8083/mcp"
        elif server_id == "filesystem":
            return "http://localhost:3000/mcp/"
        elif server_id == "github":
            return "http://localhost:3000/mcp/"
        elif server_id == "n8n":
            return "http://localhost:5678/mcp/nextcloud_tools/"

        return None

    async def get_server_tools(self, server_id: str) -> List[Dict[str, Any]]:
        """
        Get the tools of an MCP server via its wrapper.

        Args:
            server_id: Server identifier

        Returns:
            List of server tools
        """
        if server_id not in self.servers:
            logger.warning(f"Server {server_id} not found")
            return []

        wrapper = self.servers[server_id].get("wrapper")
        if not wrapper or not wrapper.is_initialized:
            logger.warning(f"Wrapper for {server_id} not initialized")
            return []

        try:
            tools = await wrapper.list_tools()
            logger.info(f"✅ {len(tools)} tools retrieved from {server_id} via wrapper")
            return tools
        except Exception as e:
            logger.error(f"❌ Error retrieving tools from {server_id}: {e}")
            return []

    async def get_all_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all tools from all managed servers.

        Returns:
            Dictionary {server_id: [tools]}
        """
        all_tools = {}

        logger.info(f"🔧 get_all_tools called - {len(self.servers)} servers in self.servers: {list(self.servers.keys())}")

        for server_id in self.servers.keys():
            is_running = self.is_server_running(server_id)
            logger.info(f"  → Server {server_id}: is_running={is_running}")

            if is_running:
                tools = await self.get_server_tools(server_id)
                if tools:
                    all_tools[server_id] = tools
                    logger.info(f"    ✅ {len(tools)} tools retrieved")
                else:
                    logger.warning(f"    ⚠️  get_server_tools returned empty")
            else:
                logger.warning(f"    ❌ Server marked as not-running")

        logger.info(f"📦 get_all_tools completed: {len(all_tools)} servers with tools")
        return all_tools 