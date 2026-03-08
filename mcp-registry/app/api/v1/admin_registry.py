"""
Instance Admin Registry API endpoints.

Provides endpoints for managing the marketplace sources:
- CRUD operations on servers in mcp_servers.json (custom servers) and bigmcp_source.json (curated)
- Source management (enable/disable sources, priority ordering)
- Server visibility toggles
"""

import json
import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..dependencies import require_instance_admin
from ...models.user import User
from ...services.marketplace_service import (
    get_marketplace_service,
    MarketplaceSyncService,
    ServerSource
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/registry", tags=["Instance Admin - Registry"])

# Path to local registry (custom servers only)
CUSTOM_SERVERS_PATH = Path(__file__).parent.parent.parent.parent / "conf" / "mcp_servers.json"
CURATED_PATH = Path(__file__).parent.parent.parent.parent / "conf" / "bigmcp_source.json"
SOURCE_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "conf" / "source_config.json"


# ============================================================================
# Pydantic Models
# ============================================================================

class CredentialDefinition(BaseModel):
    """Definition of a credential required by an MCP server."""
    name: str = Field(..., description="Environment variable name")
    description: str = Field(..., description="Human-readable description")
    required: bool = Field(default=True)
    type: str = Field(default="string", description="Type: string, secret, url, path, paths, oauth, connection_string")
    default: Optional[str] = None
    example: Optional[str] = None
    documentationUrl: Optional[str] = None
    # URL validation options
    allow_localhost: Optional[bool] = Field(default=True, description="Allow localhost/127.0.0.1 URLs")
    allow_private_ip: Optional[bool] = Field(default=True, description="Allow private IP ranges")


class InstallDefinition(BaseModel):
    """Installation definition for an MCP server."""
    type: str = Field(..., description="Installation type: npm, pip, github, docker, local, remote")
    package: Optional[str] = Field(None, description="Package name (npm/pip) or repository URL (github)")
    # For remote/SSE servers
    url: Optional[str] = Field(None, description="SSE endpoint URL (for remote type)")
    # For local scripts/binaries
    binary_path: Optional[str] = Field(None, description="Path to local binary/script (for local type)")


class LocalServerCreate(BaseModel):
    """
    Request model to create a custom MCP server.

    Supports multiple installation types:
    - npm: Install from npm registry (package required)
    - pip: Install from PyPI (package required)
    - github: Clone from GitHub (package = repo URL)
    - docker: Run as Docker container (package = image)
    - local: Run local script/binary (binary_path or command required)
    - remote: Connect to existing SSE endpoint (url required)
    """
    id: str = Field(..., description="Unique server identifier (e.g., 'my-server')")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="Server description")
    author: Optional[str] = None
    repository: Optional[str] = None
    category: str = Field(default="custom")
    tags: List[str] = Field(default=[])
    install: InstallDefinition
    # Command execution (for local/npm/pip types)
    command: Optional[str] = Field(None, description="Command to run (e.g., 'npx', 'python', '/usr/local/bin/my-mcp')")
    args: List[str] = Field(default=[])
    # Environment and credentials
    env: Optional[dict] = Field(default=None, description="Environment variables to set")
    credentials: List[CredentialDefinition] = Field(default=[])
    toolsPreview: List[str] = Field(default=[])
    popularity: int = Field(default=50, ge=0, le=100)
    verified: bool = Field(default=False)
    # Visibility options
    visible_in_marketplace: bool = Field(default=True, description="Show in marketplace listing")
    saas_compatible: bool = Field(default=False, description="Can run in cloud/SaaS mode (False for local servers)")


class LocalServerUpdate(BaseModel):
    """Request model to update a server in local registry."""
    name: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None
    repository: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    install: Optional[InstallDefinition] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[dict] = None
    credentials: Optional[List[CredentialDefinition]] = None
    toolsPreview: Optional[List[str]] = None
    popularity: Optional[int] = None
    verified: Optional[bool] = None
    visible_in_marketplace: Optional[bool] = None
    saas_compatible: Optional[bool] = None
    icon_url: Optional[str] = None


class LocalServerResponse(BaseModel):
    """Response model for a local registry server."""
    id: str
    name: str
    description: str
    author: Optional[str] = None
    repository: Optional[str] = None
    category: str
    tags: List[str] = []
    install: dict
    command: Optional[str] = None
    args: List[str] = []
    env: Optional[dict] = None
    credentials: List[dict] = []
    toolsPreview: List[str] = []
    popularity: int = 50
    verified: bool = False
    visible_in_marketplace: bool = True
    saas_compatible: bool = False
    icon_url: Optional[str] = None


class SourceInfo(BaseModel):
    """Information about a marketplace source."""
    id: str
    name: str
    description: str
    enabled: bool
    priority: int
    server_count: int = 0


class SourceToggleRequest(BaseModel):
    """Request to toggle a source."""
    enabled: bool


class AdminServerInfo(BaseModel):
    """Server info for admin listing with full display fields."""
    id: str
    name: str
    source: str
    category: Optional[str] = None
    visible_in_marketplace: bool = True
    verified: bool = False
    popularity: int = 0
    credentials_count: int = 0
    saas_compatible: bool = True
    # Additional fields for full ServerCard display
    description: Optional[str] = None
    author: Optional[str] = None
    tags: List[str] = []
    tools_preview: List[str] = []
    tools_count: int = 0
    install_type: Optional[str] = None
    is_official: bool = False
    requires_local_access: bool = False
    icon_url: Optional[str] = None
    icon_urls: List[str] = []


class ServerVisibilityUpdate(BaseModel):
    """Request to update server visibility."""
    visible_in_marketplace: bool


# ============================================================================
# Helper Functions
# ============================================================================

def load_custom_servers() -> dict:
    """Load custom MCP servers from mcp_servers.json."""
    if not CUSTOM_SERVERS_PATH.exists():
        return {"mcpServers": {}}

    with open(CUSTOM_SERVERS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_custom_servers(data: dict):
    """Save custom MCP servers to mcp_servers.json."""
    # Ensure the structure is correct
    if "mcpServers" not in data:
        data = {"mcpServers": data}

    with open(CUSTOM_SERVERS_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_visibility_config() -> dict:
    """Load server visibility configuration from curated registry."""
    visibility_path = CURATED_PATH.parent / "server_visibility.json"
    if not visibility_path.exists():
        return {}

    with open(visibility_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_visibility_config(config: dict):
    """Save server visibility configuration."""
    visibility_path = CURATED_PATH.parent / "server_visibility.json"

    with open(visibility_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def load_source_config() -> dict:
    """Load source configuration."""
    if not SOURCE_CONFIG_PATH.exists():
        # Default configuration
        return {
            "sources": {
                "bigmcp": {"enabled": True, "priority": 0},
                "official": {"enabled": True, "priority": 1},
                "npm": {"enabled": True, "priority": 2},
                "github": {"enabled": True, "priority": 3},
                "glama": {"enabled": False, "priority": 4},
                "smithery": {"enabled": False, "priority": 5},
                "custom": {"enabled": True, "priority": 6},
            }
        }

    with open(SOURCE_CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_source_config(config: dict):
    """Save source configuration."""
    config["last_updated"] = datetime.now().isoformat()

    with open(SOURCE_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ============================================================================
# Local Registry CRUD Endpoints
# ============================================================================

@router.get("/servers", response_model=List[LocalServerResponse])
async def list_local_servers(
    admin_user: User = Depends(require_instance_admin)
):
    """
    List all custom MCP servers in the local registry.

    **Requires: Instance Admin privileges**

    Returns servers from mcp_servers.json only (custom servers added by admin).
    """
    try:
        data = load_custom_servers()
        servers = []

        for server_id, server_data in data.get("mcpServers", {}).items():
            # Build response from MCP server config format
            response_data = {
                "id": server_id,
                "name": server_data.get("_metadata", {}).get("name", server_id),
                "description": server_data.get("_metadata", {}).get("description", ""),
                "author": server_data.get("_metadata", {}).get("author"),
                "repository": server_data.get("_metadata", {}).get("repository"),
                "category": server_data.get("_metadata", {}).get("category", "custom"),
                "tags": server_data.get("_metadata", {}).get("tags", []),
                "install": server_data.get("_metadata", {}).get("install", {"type": "local"}),
                "command": server_data.get("command"),
                "args": server_data.get("args", []),
                "env": server_data.get("env"),
                "credentials": server_data.get("_metadata", {}).get("credentials", []),
                "toolsPreview": server_data.get("_metadata", {}).get("toolsPreview", []),
                "popularity": server_data.get("_metadata", {}).get("popularity", 50),
                "verified": server_data.get("_metadata", {}).get("verified", False),
                "visible_in_marketplace": server_data.get("_metadata", {}).get("visible_in_marketplace", True),
                "saas_compatible": server_data.get("_metadata", {}).get("saas_compatible", False),
                "icon_url": server_data.get("_metadata", {}).get("iconUrl"),
            }
            servers.append(LocalServerResponse(**response_data))

        return servers
    except Exception as e:
        logger.error(f"Error listing local servers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/servers/{server_id}", response_model=LocalServerResponse)
async def get_local_server(
    server_id: str,
    admin_user: User = Depends(require_instance_admin)
):
    """
    Get a specific custom server from the local registry.

    **Requires: Instance Admin privileges**
    """
    try:
        data = load_custom_servers()

        if server_id not in data.get("mcpServers", {}):
            raise HTTPException(status_code=404, detail=f"Server not found: {server_id}")

        server_data = data["mcpServers"][server_id]
        response_data = {
            "id": server_id,
            "name": server_data.get("_metadata", {}).get("name", server_id),
            "description": server_data.get("_metadata", {}).get("description", ""),
            "author": server_data.get("_metadata", {}).get("author"),
            "repository": server_data.get("_metadata", {}).get("repository"),
            "category": server_data.get("_metadata", {}).get("category", "custom"),
            "tags": server_data.get("_metadata", {}).get("tags", []),
            "install": server_data.get("_metadata", {}).get("install", {"type": "local"}),
            "command": server_data.get("command"),
            "args": server_data.get("args", []),
            "env": server_data.get("env"),
            "credentials": server_data.get("_metadata", {}).get("credentials", []),
            "toolsPreview": server_data.get("_metadata", {}).get("toolsPreview", []),
            "popularity": server_data.get("_metadata", {}).get("popularity", 50),
            "verified": server_data.get("_metadata", {}).get("verified", False),
            "visible_in_marketplace": server_data.get("_metadata", {}).get("visible_in_marketplace", True),
            "saas_compatible": server_data.get("_metadata", {}).get("saas_compatible", False),
            "icon_url": server_data.get("_metadata", {}).get("iconUrl"),
        }
        return LocalServerResponse(**response_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting local server {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/servers", response_model=LocalServerResponse)
async def create_local_server(
    server: LocalServerCreate,
    admin_user: User = Depends(require_instance_admin)
):
    """
    Add a custom MCP server to the local registry.

    **Requires: Instance Admin privileges**

    Supports multiple server types:

    **npm/pip packages:**
    ```json
    {
      "id": "my-npm-server",
      "name": "My NPM Server",
      "install": {"type": "npm", "package": "@company/mcp-server"},
      "command": "npx",
      "args": ["-y", "@company/mcp-server"]
    }
    ```

    **Local script/binary:**
    ```json
    {
      "id": "my-local-server",
      "name": "My Local Server",
      "install": {"type": "local", "binary_path": "/opt/mcp/server.py"},
      "command": "python",
      "args": ["/opt/mcp/server.py"]
    }
    ```

    **Remote SSE endpoint:**
    ```json
    {
      "id": "my-remote-server",
      "name": "My Remote Server",
      "install": {"type": "remote", "url": "http://localhost:9000/sse"}
    }
    ```
    """
    try:
        data = load_custom_servers()

        if server.id in data.get("mcpServers", {}):
            raise HTTPException(status_code=400, detail=f"Server already exists: {server.id}")

        # Validate based on install type
        install_type = server.install.type
        if install_type in ("npm", "pip", "github", "docker"):
            if not server.install.package:
                raise HTTPException(
                    status_code=400,
                    detail=f"'package' is required for {install_type} install type"
                )
        elif install_type == "local":
            if not server.command and not server.install.binary_path:
                raise HTTPException(
                    status_code=400,
                    detail="Either 'command' or 'install.binary_path' is required for local install type"
                )
        elif install_type == "remote":
            if not server.install.url:
                raise HTTPException(
                    status_code=400,
                    detail="'install.url' is required for remote install type (SSE endpoint)"
                )

        # Build install object with only relevant fields
        install_data = {"type": install_type}
        if server.install.package:
            install_data["package"] = server.install.package
        if server.install.url:
            install_data["url"] = server.install.url
        if server.install.binary_path:
            install_data["binary_path"] = server.install.binary_path

        # Convert credentials to proper format
        credentials_list = [
            cred.model_dump() if hasattr(cred, 'model_dump') else cred
            for cred in server.credentials
        ]

        # Build MCP server config format (compatible with mcp.json)
        mcp_server_config = {
            "command": server.command,
            "args": server.args,
            "_metadata": {
                "name": server.name,
                "description": server.description,
                "author": server.author,
                "repository": server.repository,
                "category": server.category,
                "tags": server.tags,
                "install": install_data,
                "credentials": credentials_list,
                "toolsPreview": server.toolsPreview,
                "popularity": server.popularity,
                "verified": server.verified,
                "visible_in_marketplace": server.visible_in_marketplace,
                "saas_compatible": server.saas_compatible,
            }
        }

        # Add env if provided
        if server.env:
            mcp_server_config["env"] = server.env

        # Remove None values from _metadata
        mcp_server_config["_metadata"] = {
            k: v for k, v in mcp_server_config["_metadata"].items() if v is not None
        }

        # Add to registry
        if "mcpServers" not in data:
            data["mcpServers"] = {}
        data["mcpServers"][server.id] = mcp_server_config

        save_custom_servers(data)

        # Add server directly to marketplace cache (no full resync needed)
        marketplace_service = get_marketplace_service()
        await marketplace_service.add_custom_server_to_cache(server.id)

        logger.info(f"Admin {admin_user.email} created custom server: {server.id} (type={install_type})")

        # Return response
        return LocalServerResponse(
            id=server.id,
            name=server.name,
            description=server.description,
            author=server.author,
            repository=server.repository,
            category=server.category,
            tags=server.tags,
            install=install_data,
            command=server.command,
            args=server.args,
            env=server.env,
            credentials=credentials_list,
            toolsPreview=server.toolsPreview,
            popularity=server.popularity,
            verified=server.verified,
            visible_in_marketplace=server.visible_in_marketplace,
            saas_compatible=server.saas_compatible,
            icon_url=mcp_server_config["_metadata"].get("iconUrl"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating local server: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/servers/{server_id}", response_model=LocalServerResponse)
async def update_local_server(
    server_id: str,
    update: LocalServerUpdate,
    admin_user: User = Depends(require_instance_admin)
):
    """
    Update a custom server in the local registry.

    **Requires: Instance Admin privileges**
    """
    try:
        data = load_custom_servers()

        if server_id not in data.get("mcpServers", {}):
            raise HTTPException(status_code=404, detail=f"Server not found: {server_id}")

        server_data = data["mcpServers"][server_id]
        metadata = server_data.get("_metadata", {})

        # Update only provided fields
        update_dict = update.model_dump(exclude_unset=True)

        for key, value in update_dict.items():
            if value is not None:
                if key in ("command", "args", "env"):
                    # Direct MCP config fields
                    server_data[key] = value
                elif key == "install" and value:
                    # Install goes in metadata
                    install_data = {"type": value["type"]}
                    if value.get("package"):
                        install_data["package"] = value["package"]
                    if value.get("url"):
                        install_data["url"] = value["url"]
                    if value.get("binary_path"):
                        install_data["binary_path"] = value["binary_path"]
                    metadata["install"] = install_data
                elif key == "credentials" and value:
                    metadata["credentials"] = [
                        cred if isinstance(cred, dict) else cred.model_dump()
                        for cred in value
                    ]
                elif key == "icon_url":
                    # Map snake_case to camelCase for metadata storage
                    metadata["iconUrl"] = value
                else:
                    # Other fields go in metadata
                    metadata[key] = value

        server_data["_metadata"] = metadata
        data["mcpServers"][server_id] = server_data
        save_custom_servers(data)

        # Update server in marketplace cache (no full resync needed)
        marketplace_service = get_marketplace_service()
        await marketplace_service.add_custom_server_to_cache(server_id)

        logger.info(f"Admin {admin_user.email} updated local server: {server_id}")

        # Build response
        return LocalServerResponse(
            id=server_id,
            name=metadata.get("name", server_id),
            description=metadata.get("description", ""),
            author=metadata.get("author"),
            repository=metadata.get("repository"),
            category=metadata.get("category", "custom"),
            tags=metadata.get("tags", []),
            install=metadata.get("install", {"type": "local"}),
            command=server_data.get("command"),
            args=server_data.get("args", []),
            env=server_data.get("env"),
            credentials=metadata.get("credentials", []),
            toolsPreview=metadata.get("toolsPreview", []),
            popularity=metadata.get("popularity", 50),
            verified=metadata.get("verified", False),
            visible_in_marketplace=metadata.get("visible_in_marketplace", True),
            saas_compatible=metadata.get("saas_compatible", False),
            icon_url=metadata.get("iconUrl"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating local server {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/servers/{server_id}")
async def delete_local_server(
    server_id: str,
    admin_user: User = Depends(require_instance_admin)
):
    """
    Remove a custom server from the local registry.

    **Requires: Instance Admin privileges**

    This only removes from the local registry (mcp_servers.json) - servers from
    other sources (npm, github, curated) are not affected.
    """
    try:
        data = load_custom_servers()

        if server_id not in data.get("mcpServers", {}):
            raise HTTPException(status_code=404, detail=f"Server not found: {server_id}")

        del data["mcpServers"][server_id]
        save_custom_servers(data)

        # Remove server directly from marketplace cache (no full resync needed)
        marketplace_service = get_marketplace_service()
        marketplace_service.remove_server_from_cache(server_id)

        logger.info(f"Admin {admin_user.email} deleted local server: {server_id}")

        return {"success": True, "message": f"Server {server_id} removed from local registry"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting local server {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Raw MCP Config Endpoints (for LocalRegistryManager)
# ============================================================================

class MCPConfigCreate(BaseModel):
    """Request to create a server from raw MCP config."""
    server_id: str = Field(..., description="Server ID (key in mcpServers)")
    config: dict = Field(..., description="Raw MCP config (command, args, env, or url)")
    metadata: Optional[dict] = Field(None, description="Optional metadata (name, description, category)")


class MCPConfigUpdate(BaseModel):
    """Request to update a server's raw MCP config and metadata."""
    config: dict = Field(..., description="Raw MCP config (command, args, env, url) with optional _metadata")


def detect_install_type(config: dict) -> tuple[str, Optional[str]]:
    """Detect install type and package from MCP config."""
    if config.get("url"):
        return "remote", None

    command = config.get("command", "").lower()
    args = config.get("args", [])

    if command in ("npx", "npm"):
        # Extract package from args
        for arg in args:
            if arg.startswith("@") or arg.startswith("mcp-server-") or "/" in arg:
                if arg != "-y":
                    return "npm", arg
        return "npm", None
    elif command in ("uvx", "pip", "python", "python3"):
        for arg in args:
            if "mcp" in arg.lower():
                return "pip", arg
        return "pip", None
    elif command == "docker":
        return "docker", None
    else:
        return "local", None


def extract_credentials_from_env(env: dict) -> List[dict]:
    """Extract credential definitions from env variables."""
    credentials = []
    if not env:
        return credentials

    for key, value in env.items():
        if isinstance(value, str):
            # Check for ${VAR} pattern or empty value
            if "${" in value or value == "":
                credentials.append({
                    "name": key,
                    "description": f"Value for {key}",
                    "required": True,
                })
    return credentials


def detect_saas_compatible(config: dict, install_type: str) -> bool:
    """
    Detect if a server config is likely SaaS compatible.

    SaaS compatible means it can run in cloud WITHOUT needing local resources.
    This is about LOCAL ACCESS requirements, not remote API connectivity.

    Returns False (NOT SaaS compatible) if:
    - Has local-only patterns (filesystem paths, docker, local sockets, etc.)

    Returns True (SaaS compatible) if:
    - Remote SSE server (always SaaS compatible)
    - No local access patterns detected (default)
    """
    # Remote SSE servers are always SaaS compatible
    if install_type == "remote" or config.get("url"):
        return True

    env = config.get("env", {})
    args = config.get("args", [])

    # Patterns indicating LOCAL resource access (NOT SaaS compatible)
    local_env_patterns = [
        "_PATH", "_DIR", "_FILE", "_FOLDER", "DOCKER_", "LOCAL_",
        "FILESYSTEM", "_SOCKET", "WORKSPACE", "PROJECT_"
    ]

    # Patterns indicating localhost/local network (NOT SaaS compatible)
    localhost_patterns = ["localhost", "127.0.0.1", "0.0.0.0"]

    # Check env vars for local patterns (in keys)
    for key in env.keys():
        key_upper = key.upper()
        for pattern in local_env_patterns:
            if pattern in key_upper:
                return False  # Needs local access

    # Check env var VALUES for localhost patterns
    for value in env.values():
        if isinstance(value, str):
            value_lower = value.lower()
            for pattern in localhost_patterns:
                if pattern in value_lower:
                    return False  # Points to local server

    # Check args for filesystem paths and localhost
    for arg in args:
        if isinstance(arg, str):
            arg_lower = arg.lower()
            # Check for localhost patterns
            for pattern in localhost_patterns:
                if pattern in arg_lower:
                    return False  # Points to local server
            # Absolute paths like /home, /tmp, C:\, etc.
            if arg.startswith("/") and not arg.startswith("/-"):
                return False
            if len(arg) > 2 and arg[1] == ":" and arg[2] == "\\":
                return False  # Windows path like C:\
            # Common path indicators
            if "filesystem" in arg_lower or "local" in arg_lower:
                return False

    # Default: SaaS compatible (no local access detected)
    return True


@router.post("/servers/from-config", response_model=LocalServerResponse)
async def create_server_from_config(
    request: MCPConfigCreate,
    admin_user: User = Depends(require_instance_admin)
):
    """
    Create a server from raw MCP config JSON.

    **Requires: Instance Admin privileges**

    This endpoint accepts raw MCP config format (command/args/env or url)
    and automatically detects the install type and credentials.

    Example request:
    ```json
    {
      "server_id": "my-server",
      "config": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
        "env": { "API_KEY": "${API_KEY}" }
      },
      "metadata": {
        "name": "My Server",
        "description": "A custom MCP server"
      }
    }
    ```
    """
    try:
        data = load_custom_servers()

        if request.server_id in data.get("mcpServers", {}):
            raise HTTPException(status_code=400, detail=f"Server already exists: {request.server_id}")

        config = request.config
        metadata = request.metadata or {}

        # Detect install type
        install_type, package = detect_install_type(config)

        # Build install data
        install_data = {"type": install_type}
        if package:
            install_data["package"] = package
        if config.get("url"):
            install_data["url"] = config["url"]

        # Extract credentials from env
        credentials = extract_credentials_from_env(config.get("env", {}))

        # Build MCP server config
        mcp_server_config = {}

        if config.get("command"):
            mcp_server_config["command"] = config["command"]
        if config.get("args"):
            mcp_server_config["args"] = config["args"]
        if config.get("env"):
            mcp_server_config["env"] = config["env"]

        # Detect SaaS compatibility from config
        is_saas_compatible = detect_saas_compatible(config, install_type)

        # Add metadata
        mcp_server_config["_metadata"] = {
            "name": metadata.get("name", request.server_id),
            "description": metadata.get("description", ""),
            "category": metadata.get("category", "custom"),
            "install": install_data,
            "credentials": credentials,
            "visible_in_marketplace": True,
            "saas_compatible": is_saas_compatible,
        }

        # Add icon_url if provided (use camelCase for storage consistency)
        if metadata.get("icon_url"):
            mcp_server_config["_metadata"]["iconUrl"] = metadata["icon_url"]

        # Add to registry
        if "mcpServers" not in data:
            data["mcpServers"] = {}
        data["mcpServers"][request.server_id] = mcp_server_config

        save_custom_servers(data)

        # Add server directly to marketplace cache (no full resync needed)
        marketplace_service = get_marketplace_service()
        await marketplace_service.add_custom_server_to_cache(request.server_id)

        logger.info(f"Admin {admin_user.email} created server from config: {request.server_id} (type={install_type})")

        # Return response
        return LocalServerResponse(
            id=request.server_id,
            name=metadata.get("name", request.server_id),
            description=metadata.get("description", ""),
            category=metadata.get("category", "custom"),
            install=install_data,
            command=config.get("command"),
            args=config.get("args", []),
            env=config.get("env"),
            credentials=credentials,
            visible_in_marketplace=True,
            saas_compatible=is_saas_compatible,
            icon_url=metadata.get("iconUrl"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating server from config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/servers/{server_id}/config", response_model=LocalServerResponse)
async def update_server_config(
    server_id: str,
    request: MCPConfigUpdate,
    admin_user: User = Depends(require_instance_admin)
):
    """
    Update a server's raw MCP config.

    **Requires: Instance Admin privileges**

    This endpoint updates the core MCP config (command, args, env, url)
    while preserving existing metadata.
    """
    try:
        data = load_custom_servers()

        if server_id not in data.get("mcpServers", {}):
            raise HTTPException(status_code=404, detail=f"Server not found: {server_id}")

        config = request.config
        server_data = data["mcpServers"][server_id]
        metadata = server_data.get("_metadata", {})

        # Update core config fields
        if config.get("command"):
            server_data["command"] = config["command"]
        elif "command" in server_data and config.get("url"):
            # Switching to remote - remove command
            del server_data["command"]

        if config.get("args"):
            server_data["args"] = config["args"]
        elif "args" in server_data and config.get("url"):
            del server_data["args"]

        if config.get("env"):
            server_data["env"] = config["env"]
        elif "env" in config:
            server_data["env"] = config["env"]

        # Handle _metadata updates from config (full JSON editing)
        config_metadata = config.get("_metadata", {})
        if config_metadata:
            # Update metadata fields from config._metadata
            if "name" in config_metadata:
                metadata["name"] = config_metadata["name"]
            if "description" in config_metadata:
                metadata["description"] = config_metadata["description"]
            if "category" in config_metadata:
                metadata["category"] = config_metadata["category"]
            if "iconUrl" in config_metadata:
                metadata["iconUrl"] = config_metadata["iconUrl"]
            if "visible_in_marketplace" in config_metadata:
                metadata["visible_in_marketplace"] = config_metadata["visible_in_marketplace"]
            if "saas_compatible" in config_metadata:
                metadata["saas_compatible"] = config_metadata["saas_compatible"]
            if "credentials" in config_metadata:
                # Use credentials from config._metadata if provided
                metadata["credentials"] = config_metadata["credentials"]

        # Re-detect install type
        install_type, package = detect_install_type(config)
        install_data = {"type": install_type}
        if package:
            install_data["package"] = package
        if config.get("url"):
            install_data["url"] = config["url"]

        metadata["install"] = install_data

        # Only re-extract credentials if not provided in _metadata
        if "credentials" not in config_metadata:
            metadata["credentials"] = extract_credentials_from_env(config.get("env", {}))

        # Only re-detect SaaS compatibility if not explicitly set in _metadata
        if "saas_compatible" not in config_metadata:
            metadata["saas_compatible"] = detect_saas_compatible(config, install_type)

        server_data["_metadata"] = metadata
        data["mcpServers"][server_id] = server_data

        save_custom_servers(data)

        # Update server in marketplace cache (no full resync needed)
        marketplace_service = get_marketplace_service()
        await marketplace_service.add_custom_server_to_cache(server_id)

        logger.info(f"Admin {admin_user.email} updated server config: {server_id}")

        return LocalServerResponse(
            id=server_id,
            name=metadata.get("name", server_id),
            description=metadata.get("description", ""),
            category=metadata.get("category", "custom"),
            install=install_data,
            command=server_data.get("command"),
            args=server_data.get("args", []),
            env=server_data.get("env"),
            credentials=metadata.get("credentials", []),
            visible_in_marketplace=metadata.get("visible_in_marketplace", True),
            saas_compatible=metadata.get("saas_compatible", False),
            icon_url=metadata.get("iconUrl"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating server config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Server Curation Preview
# ============================================================================

class CurationPreviewRequest(BaseModel):
    """Request model for curation preview."""
    server_id: str = Field(..., description="Server identifier")
    config: dict = Field(..., description="Raw MCP config (command, args, env, url)")
    metadata: Optional[dict] = Field(None, description="Optional initial metadata (name, description)")


class CurationPreviewResponse(BaseModel):
    """Response model for curation preview."""
    server_id: str
    name: str
    description: str
    service_id: Optional[str] = None
    service_display_name: Optional[str] = None
    author: Optional[str] = None
    category: str = "custom"
    tags: List[str] = []
    icon_url: Optional[str] = None
    icon_hint: Optional[str] = None
    credentials: List[dict] = []
    tools_preview: List[str] = []
    tool_descriptions: List[dict] = []  # LLM-generated descriptions for tools without descriptions
    summary: Optional[str] = None
    use_cases: List[str] = []
    quality_score: int = 50
    install: dict
    # Status
    curated: bool = False
    curation_source: str = "basic"  # "llm", "static", "basic"


@router.post("/servers/curate-preview", response_model=CurationPreviewResponse)
async def curate_server_preview(
    request: CurationPreviewRequest,
    marketplace: MarketplaceSyncService = Depends(get_marketplace_service),
    admin_user: User = Depends(require_instance_admin)
):
    """
    Preview LLM curation results for a server config without saving.

    **Requires: Instance Admin privileges**

    This endpoint takes a raw MCP config and runs it through the curation
    pipeline (static analysis + LLM) to generate metadata suggestions.
    The admin can then review and modify the results before saving.

    Returns curated metadata including:
    - service_id and service_display_name (for deduplication)
    - icon_url and icon_hint (validated against CDNs)
    - category and tags
    - credentials (filtered and validated)
    - summary and use_cases
    - quality_score
    """
    from ...services.marketplace_service import MarketplaceServer, InstallationType, ServerSource

    try:
        config = request.config
        metadata = request.metadata or {}

        # Detect install type from config
        install_type, package = detect_install_type(config)
        install_data = {"type": install_type}
        if package:
            install_data["package"] = package
        if config.get("url"):
            install_data["url"] = config["url"]

        # Try to parse install type enum
        try:
            install_type_enum = InstallationType(install_type)
        except ValueError:
            install_type_enum = InstallationType.LOCAL

        # Create a temporary MarketplaceServer for curation
        temp_server = MarketplaceServer(
            id=request.server_id,
            name=metadata.get("name", request.server_id),
            description=metadata.get("description", ""),
            install_type=install_type_enum,
            install_package=package or config.get("url", ""),
            command=config.get("command"),
            args=config.get("args", []),
            source=ServerSource.CUSTOM,
            category=metadata.get("category", "custom"),
            tags=metadata.get("tags", []),
        )

        # Run curation (this will use LLM if available, else static analysis)
        curation_result = await marketplace._curate_server_with_llm(temp_server)

        # PRIORITY: Credentials declared in env config (with ${VAR} pattern)
        # These are the authoritative credentials the user explicitly declared
        env_declared_creds = extract_credentials_from_env(config.get("env", {}))
        env_cred_names = {c["name"] for c in env_declared_creds}

        # Curation credentials from LLM/static analysis
        curation_creds = curation_result.get("credentials", [])

        # Merge: Start with env-declared credentials, enrich with curation info
        final_credentials = []
        for env_cred in env_declared_creds:
            # Find matching curation credential to get better description
            matching_curation = next(
                (c for c in curation_creds if c.get("name") == env_cred["name"]),
                None
            )
            if matching_curation:
                # Use curation's richer description but keep required=True from env
                final_credentials.append({
                    "name": env_cred["name"],
                    "description": matching_curation.get("description", env_cred["description"]),
                    "required": True,  # Declared in env = required
                    "type": matching_curation.get("type", "secret"),
                    "example": matching_curation.get("example"),
                    "documentation_url": matching_curation.get("documentation_url"),
                })
            else:
                final_credentials.append(env_cred)

        # Optionally add curation-only credentials as OPTIONAL (not declared in env)
        # Only if they look like real credentials (not generic params)
        SKIP_GENERIC_PARAMS = {"PATH", "DIR", "FILE", "PORT", "HOST", "URL", "DEBUG", "LOG_LEVEL"}
        for curation_cred in curation_creds:
            cred_name = curation_cred.get("name", "")
            if cred_name not in env_cred_names:
                # Skip generic config params that aren't real credentials
                if any(generic in cred_name.upper() for generic in SKIP_GENERIC_PARAMS):
                    continue
                # Add as optional credential (discovered by analysis but not declared)
                final_credentials.append({
                    "name": cred_name,
                    "description": curation_cred.get("description", f"Optional: {cred_name}"),
                    "required": False,  # Not in env = optional
                    "type": curation_cred.get("type", "string"),
                    "example": curation_cred.get("example"),
                    "documentation_url": curation_cred.get("documentation_url"),
                })

        # Build response
        return CurationPreviewResponse(
            server_id=request.server_id,
            name=curation_result.get("service_display_name") or metadata.get("name") or request.server_id,
            description=curation_result.get("summary") or metadata.get("description", ""),
            service_id=curation_result.get("service_id"),
            service_display_name=curation_result.get("service_display_name"),
            author=curation_result.get("author"),
            category=curation_result.get("category", "custom"),
            tags=curation_result.get("tags", []),
            icon_url=curation_result.get("icon_url"),
            icon_hint=curation_result.get("icon_hint"),
            credentials=final_credentials,
            tools_preview=curation_result.get("tools_preview", []),
            tool_descriptions=curation_result.get("tool_descriptions", []),
            summary=curation_result.get("summary"),
            use_cases=curation_result.get("use_cases", []),
            quality_score=curation_result.get("quality_score", 50),
            install=install_data,
            curated=True,
            curation_source=curation_result.get("curated_by", "basic")
        )

    except Exception as e:
        logger.error(f"Error in curation preview: {e}", exc_info=True)
        # Return basic response on error
        install_type, package = detect_install_type(request.config)
        install_data = {"type": install_type}
        if package:
            install_data["package"] = package
        if request.config.get("url"):
            install_data["url"] = request.config["url"]

        return CurationPreviewResponse(
            server_id=request.server_id,
            name=request.metadata.get("name", request.server_id) if request.metadata else request.server_id,
            description=request.metadata.get("description", "") if request.metadata else "",
            category="custom",
            tags=[],
            credentials=extract_credentials_from_env(request.config.get("env", {})),
            install=install_data,
            curated=False,
            curation_source="error"
        )


# ============================================================================
# Source Management Endpoints
# ============================================================================

SOURCE_DESCRIPTIONS = {
    "bigmcp": "BigMCP curated source (bigmcp_source.json) - verified MCP servers with full metadata",
    "official": "Official modelcontextprotocol organization servers",
    "npm": "npm registry packages (@modelcontextprotocol/*, mcp-server-*)",
    "github": "GitHub repositories from modelcontextprotocol/servers",
    "glama": "Glama.ai MCP server registry",
    "smithery": "Smithery.ai marketplace",
    "custom": "Custom MCP servers (mcp_servers.json)",
}

SOURCE_NAMES = {
    "bigmcp": "BigMCP",
    "official": "Official MCP",
    "npm": "npm Registry",
    "github": "GitHub Discovery",
    "glama": "Glama.ai",
    "smithery": "Smithery",
    "custom": "Custom",
}


@router.get("/sources", response_model=List[SourceInfo])
async def list_sources(
    marketplace: MarketplaceSyncService = Depends(get_marketplace_service),
    admin_user: User = Depends(require_instance_admin)
):
    """
    List all marketplace sources with their status.

    **Requires: Instance Admin privileges**
    """
    try:
        config = load_source_config()
        sources = []

        for source_id, source_config in config.get("sources", {}).items():
            sources.append(SourceInfo(
                id=source_id,
                name=SOURCE_NAMES.get(source_id, source_id.replace("_", " ").title()),
                description=SOURCE_DESCRIPTIONS.get(source_id, ""),
                enabled=source_config.get("enabled", True),
                priority=source_config.get("priority", 99),
                server_count=0  # Will be populated by frontend if needed
            ))

        # Sort by priority
        sources.sort(key=lambda s: s.priority)

        return sources
    except Exception as e:
        logger.error(f"Error listing sources: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/sources/{source_id}")
async def toggle_source(
    source_id: str,
    request: SourceToggleRequest,
    admin_user: User = Depends(require_instance_admin)
):
    """
    Enable or disable a marketplace source.

    **Requires: Instance Admin privileges**

    Disabling a source will exclude its servers from the marketplace.
    Changes take effect on next sync.
    """
    try:
        config = load_source_config()

        if source_id not in config.get("sources", {}):
            raise HTTPException(status_code=404, detail=f"Unknown source: {source_id}")

        config["sources"][source_id]["enabled"] = request.enabled
        save_source_config(config)

        action = "enabled" if request.enabled else "disabled"
        logger.info(f"Admin {admin_user.email} {action} source: {source_id}")

        return {
            "success": True,
            "message": f"Source {source_id} {action}",
            "source": source_id,
            "enabled": request.enabled
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling source {source_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class SourcePrioritiesUpdate(BaseModel):
    """Request to update source priorities (from drag & drop)."""
    priorities: dict[str, int] = Field(..., description="Map of source_id -> priority")


@router.put("/sources/priorities")
async def update_source_priorities(
    request: SourcePrioritiesUpdate,
    admin_user: User = Depends(require_instance_admin)
):
    """
    Update priorities for all sources at once (for drag & drop reordering).

    **Requires: Instance Admin privileges**

    Request body example:
    ```json
    {
      "priorities": {
        "bigmcp": 0,
        "official": 1,
        "npm": 2,
        "github": 3,
        "glama": 4,
        "smithery": 5,
        "custom": 6
      }
    }
    ```
    """
    try:
        config = load_source_config()

        for source_id, priority in request.priorities.items():
            if source_id in config.get("sources", {}):
                config["sources"][source_id]["priority"] = priority

        save_source_config(config)

        logger.info(f"Admin {admin_user.email} updated source priorities: {request.priorities}")

        return {
            "success": True,
            "message": "Source priorities updated",
            "priorities": request.priorities
        }
    except Exception as e:
        logger.error(f"Error updating source priorities: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Server Visibility Management
# ============================================================================

@router.get("/all-servers", response_model=List[AdminServerInfo])
async def list_all_servers_for_admin(
    source: Optional[str] = Query(None, description="Filter by source"),
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search in name/description"),
    visible_only: bool = Query(False, description="Only show visible servers"),
    marketplace: MarketplaceSyncService = Depends(get_marketplace_service),
    admin_user: User = Depends(require_instance_admin)
):
    """
    List ALL servers from all sources for admin management.

    **Requires: Instance Admin privileges**

    Returns servers with visibility status for toggling.
    """
    try:
        # Get all servers from marketplace (bypass visibility filter for admin view)
        result = await marketplace.list_servers(
            category=category,
            search=search,
            source=ServerSource(source) if source else None,
            respect_visibility=False,  # Admin sees ALL servers
            limit=1000  # Get all
        )

        # Load visibility config
        visibility_config = load_visibility_config()

        servers = []
        for server in result["servers"]:
            # Get visibility (default True)
            is_visible = visibility_config.get(server["id"], {}).get("visible", True)

            if visible_only and not is_visible:
                continue

            # Get tools preview and count
            tools_preview = server.get("tools_preview", [])
            tools_count = server.get("tools_count", len(tools_preview))

            # Handle icon_urls - can be a dict or list, filter to only strings
            raw_icon_urls = server.get("icon_urls", [])
            if isinstance(raw_icon_urls, dict):
                icon_urls = [v for v in raw_icon_urls.values() if isinstance(v, str)]
            elif isinstance(raw_icon_urls, list):
                icon_urls = [v for v in raw_icon_urls if isinstance(v, str)]
            else:
                icon_urls = []

            servers.append(AdminServerInfo(
                id=server["id"],
                name=server.get("name", server["id"]),
                source=server.get("source", "unknown"),
                category=server.get("category"),
                visible_in_marketplace=is_visible,
                verified=server.get("verified", False),
                popularity=server.get("popularity", 0),
                credentials_count=len(server.get("credentials", [])),
                saas_compatible=not server.get("requires_local_access", False),
                # Additional fields for full ServerCard display
                description=server.get("description", ""),
                author=server.get("author", "Community"),
                tags=server.get("tags", []),
                tools_preview=tools_preview[:5] if tools_preview else [],
                tools_count=tools_count,
                install_type=server.get("install_type", "npm"),
                is_official=server.get("is_official", False),
                requires_local_access=server.get("requires_local_access", False),
                icon_url=server.get("icon_url"),
                icon_urls=icon_urls,
            ))

        return servers
    except Exception as e:
        logger.error(f"Error listing admin servers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/servers/{server_id}/visibility")
async def update_server_visibility(
    server_id: str,
    update: ServerVisibilityUpdate,
    admin_user: User = Depends(require_instance_admin)
):
    """
    Toggle a server's visibility in the marketplace.

    **Requires: Instance Admin privileges**

    Hidden servers won't appear in marketplace listings but can still
    be installed manually by knowing their ID.
    """
    try:
        visibility_config = load_visibility_config()

        if server_id not in visibility_config:
            visibility_config[server_id] = {}

        visibility_config[server_id]["visible"] = update.visible_in_marketplace
        visibility_config[server_id]["updated_at"] = datetime.now().isoformat()
        visibility_config[server_id]["updated_by"] = admin_user.email

        save_visibility_config(visibility_config)

        action = "visible" if update.visible_in_marketplace else "hidden"
        logger.info(f"Admin {admin_user.email} set server {server_id} to {action}")

        return {
            "success": True,
            "message": f"Server {server_id} is now {action}",
            "server_id": server_id,
            "visible": update.visible_in_marketplace
        }
    except Exception as e:
        logger.error(f"Error updating visibility for {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class BulkVisibilityUpdate(BaseModel):
    """Request to update visibility for multiple servers."""
    server_ids: List[str] = Field(..., description="List of server IDs to update")
    visible: bool = Field(..., description="Visibility to set for all servers")


@router.post("/servers/bulk-visibility")
async def update_bulk_visibility(
    update: BulkVisibilityUpdate,
    admin_user: User = Depends(require_instance_admin)
):
    """
    Toggle visibility for multiple servers at once.

    **Requires: Instance Admin privileges**

    Useful for batch operations like:
    - Show/hide all servers from a source
    - Toggle visibility for a selection of servers
    """
    try:
        visibility_config = load_visibility_config()
        updated = []

        for server_id in update.server_ids:
            if server_id not in visibility_config:
                visibility_config[server_id] = {}

            visibility_config[server_id]["visible"] = update.visible
            visibility_config[server_id]["updated_at"] = datetime.now().isoformat()
            visibility_config[server_id]["updated_by"] = admin_user.email
            updated.append(server_id)

        save_visibility_config(visibility_config)

        action = "visible" if update.visible else "hidden"
        logger.info(f"Admin {admin_user.email} set {len(updated)} servers to {action}")

        return {
            "success": True,
            "message": f"{len(updated)} servers are now {action}",
            "updated_count": len(updated),
            "visible": update.visible
        }
    except Exception as e:
        logger.error(f"Error updating bulk visibility: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/servers/{server_id}/credentials")
async def update_server_credentials_config(
    server_id: str,
    credentials: List[CredentialDefinition],
    admin_user: User = Depends(require_instance_admin)
):
    """
    Update credential configuration for a server.

    **Requires: Instance Admin privileges**

    Allows customizing which credentials are required/optional,
    and setting URL validation options.
    """
    try:
        # Check if server exists in local registry
        registry = load_custom_servers()

        if server_id in registry.get("mcpServers", {}):
            # Update local registry — credentials are stored in _metadata
            server_data = registry["mcpServers"][server_id]
            if "_metadata" not in server_data:
                server_data["_metadata"] = {}
            server_data["_metadata"]["credentials"] = [
                cred.model_dump() for cred in credentials
            ]
            save_custom_servers(registry)
            source = "local"
        else:
            # Store in separate credential config for external servers
            config_path = CURATED_PATH.parent / "credential_overrides.json"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    overrides = json.load(f)
            else:
                overrides = {}

            overrides[server_id] = {
                "credentials": [cred.model_dump() for cred in credentials],
                "updated_at": datetime.now().isoformat(),
                "updated_by": admin_user.email
            }

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(overrides, f, indent=2, ensure_ascii=False)

            source = "override"

        logger.info(f"Admin {admin_user.email} updated credentials for {server_id}")

        return {
            "success": True,
            "message": f"Credentials updated for {server_id}",
            "server_id": server_id,
            "credentials_count": len(credentials),
            "source": source
        }
    except Exception as e:
        logger.error(f"Error updating credentials for {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Categories Management
# ============================================================================

@router.get("/categories")
async def list_categories(
    admin_user: User = Depends(require_instance_admin)
):
    """
    List all categories in the local registry.

    **Requires: Instance Admin privileges**
    """
    try:
        registry = load_custom_servers()
        return registry.get("categories", {})
    except Exception as e:
        logger.error(f"Error listing categories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/categories/{category_id}")
async def create_or_update_category(
    category_id: str,
    name: str = Query(..., description="Category display name"),
    description: str = Query("", description="Category description"),
    icon: str = Query("folder", description="Icon name"),
    admin_user: User = Depends(require_instance_admin)
):
    """
    Create or update a category in the local registry.

    **Requires: Instance Admin privileges**
    """
    try:
        registry = load_custom_servers()

        if "categories" not in registry:
            registry["categories"] = {}

        registry["categories"][category_id] = {
            "name": name,
            "description": description,
            "icon": icon
        }

        save_custom_servers(registry)

        logger.info(f"Admin {admin_user.email} updated category: {category_id}")

        return {
            "success": True,
            "message": f"Category {category_id} saved",
            "category": registry["categories"][category_id]
        }
    except Exception as e:
        logger.error(f"Error updating category {category_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
