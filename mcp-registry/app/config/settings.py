"""
Configuration module for the MCP Registry.
Loads settings from YAML file and environment variables.
"""

import os
import yaml
from typing import Dict, Any, List, Optional
from pathlib import Path
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class AppConfig(BaseModel):
    """Application configuration."""
    name: str = "MCP Registry Service"
    version: str = "1.0.0"
    description: str = "MCP server management service"
    host: str = "0.0.0.0"
    port: int = 8000

class EmbeddingConfig(BaseModel):
    """Embedding configuration."""
    model: str = "mistral-embed"
    dimension: int = 1536  # Max dimension (OpenAI=1536), smaller dims are zero-padded
    cache_dir: str = "./embeddings_cache"

class ServerConfig(BaseModel):
    """MCP server configuration."""
    id: str
    name: str
    description: str = ""
    url: str
    headers: Dict[str, str] = Field(default_factory=dict)

class DatabaseConfig(BaseModel):
    """Database configuration."""
    url: str = "postgresql+asyncpg://postgres:postgres@db:5432/mcphub"
    echo: bool = False  # SQL query logging
    pool_size: int = 5
    max_overflow: int = 10
    pool_pre_ping: bool = True

class RegistryConfig(BaseModel):
    """MCP registry configuration."""
    discovery_interval: int = 3600
    discovery_enabled: bool = True
    cache_ttl: int = 86400
    server_urls: Optional[List[str]] = None
    discovery_urls: Optional[List[str]] = None
    auth_token: Optional[str] = None
    timeout: int = 30
    manage_servers: bool = False  # Option to manage MCP servers
    # SSE configurations
    sse_ping_interval: int = 30  # Ping interval in seconds
    sse_timeout: int = 600  # Timeout in seconds

class Settings(BaseModel):
    """Global configuration."""
    app: AppConfig = Field(default_factory=AppConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    registry: RegistryConfig = Field(default_factory=RegistryConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    servers: List[ServerConfig] = Field(default_factory=list)

def get_config_path() -> Path:
    """Get the configuration file path."""
    env_path = os.getenv("MCP_CONFIG_PATH")
    if env_path:
        return Path(env_path)

    # Search in standard paths
    paths = [
        Path("./conf/config.yaml"),
        Path("../conf/config.yaml"),
        Path("/etc/mcp-registry/config.yaml"),
    ]

    for path in paths:
        if path.exists():
            return path

    # Use default configuration
    return Path("./conf/config.yaml")

def load_config() -> Settings:
    """Load configuration from YAML file and environment variables."""
    config_path = get_config_path()
    config_dict = {}

    # Load YAML configuration if it exists
    if config_path.exists():
        with open(config_path, "r") as f:
            config_dict = yaml.safe_load(f)

    # Replace values with environment variables if defined
    if os.getenv("DATABASE_URL"):
        config_dict.setdefault("database", {})["url"] = os.getenv("DATABASE_URL")

    if os.getenv("MCP_APP_PORT"):
        config_dict.setdefault("app", {})["port"] = int(os.getenv("MCP_APP_PORT"))

    if os.getenv("MCP_DISCOVERY_INTERVAL"):
        config_dict.setdefault("registry", {})["discovery_interval"] = int(os.getenv("MCP_DISCOVERY_INTERVAL"))
    
    if os.getenv("MCP_DISCOVERY_ENABLED"):
        config_dict.setdefault("registry", {})["discovery_enabled"] = os.getenv("MCP_DISCOVERY_ENABLED").lower() in ("true", "1", "yes")
    
    if os.getenv("MCP_MANAGE_SERVERS"):
        config_dict.setdefault("registry", {})["manage_servers"] = os.getenv("MCP_MANAGE_SERVERS").lower() in ("true", "1", "yes")
    
    # SSE variables
    if os.getenv("MCP_SSE_PING_INTERVAL"):
        config_dict.setdefault("registry", {})["sse_ping_interval"] = int(os.getenv("MCP_SSE_PING_INTERVAL"))

    if os.getenv("MCP_SSE_TIMEOUT"):
        config_dict.setdefault("registry", {})["sse_timeout"] = int(os.getenv("MCP_SSE_TIMEOUT"))

    # Process servers defined in environment variables
    # Format: MCP_SERVER_<ID>_URL=<url>
    # Format: MCP_SERVER_<ID>_NAME=<n>
    # Format: MCP_SERVER_<ID>_DESC=<description>

    env_servers = []
    for key, value in os.environ.items():
        if key.startswith("MCP_SERVER_") and key.endswith("_URL"):
            server_id = key[11:-4].lower()  # Extract server ID
            server_url = value
            server_name = os.getenv(f"MCP_SERVER_{server_id.upper()}_NAME", server_id.title())
            server_desc = os.getenv(f"MCP_SERVER_{server_id.upper()}_DESC", "")

            env_servers.append({
                "id": server_id,
                "name": server_name,
                "description": server_desc,
                "url": server_url,
            })

    # Add servers defined in environment variables
    if env_servers:
        config_dict.setdefault("servers", []).extend(env_servers)

    return Settings(**config_dict)

# Global configuration instance
settings = load_config() 