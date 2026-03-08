"""
Pydantic schemas for MCP Server API.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, validator

from ..models.mcp_server import InstallType, ServerStatus


class MCPServerCreate(BaseModel):
    """Schema for creating an MCP server."""

    server_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique identifier for the server within organization"
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable name"
    )
    description: Optional[str] = Field(
        None,
        description="Optional description"
    )

    # Installation configuration
    install_type: InstallType = Field(
        ...,
        description="Installation method"
    )
    install_package: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Package name or repository URL"
    )
    version: Optional[str] = Field(
        None,
        max_length=50,
        description="Specific version (null = latest)"
    )

    # Runtime configuration
    command: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Command to execute"
    )
    args: List[str] = Field(
        default_factory=list,
        description="Command arguments"
    )
    env: Dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables"
    )

    auto_start: bool = Field(
        default=False,
        description="Whether to start the server immediately after creation"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "server_id": "grist-mcp",
                "name": "Grist MCP Server",
                "description": "MCP server for Grist integration",
                "install_type": "pip",
                "install_package": "grist-mcp",
                "version": "1.0.0",
                "command": "python",
                "args": ["-m", "grist_mcp"],
                "env": {
                    "GRIST_API_KEY": "your-api-key",
                    "GRIST_BASE_URL": "https://docs.getgrist.com"
                },
                "auto_start": True
            }
        }


class MCPServerUpdate(BaseModel):
    """Schema for updating an MCP server."""

    command: Optional[str] = Field(
        None,
        min_length=1,
        max_length=500,
        description="New command (requires server stop)"
    )
    args: Optional[List[str]] = Field(
        None,
        description="New arguments (requires server stop)"
    )
    env: Optional[Dict[str, str]] = Field(
        None,
        description="New environment variables (can update while running)"
    )
    enabled: Optional[bool] = Field(
        None,
        description="Enable/disable server"
    )
    is_visible_to_oauth_clients: Optional[bool] = Field(
        None,
        description="Show/hide server from OAuth clients (still available for API keys)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "env": {
                    "GRIST_API_KEY": "new-api-key"
                }
            }
        }


class MCPServerResponse(BaseModel):
    """Schema for MCP server response."""

    id: UUID
    organization_id: UUID
    server_id: str
    name: str
    description: Optional[str]

    # Installation
    install_type: InstallType
    install_package: str
    version: Optional[str]

    # Runtime
    command: str
    args: List[str]
    env: Dict[str, str]

    # Status
    status: ServerStatus
    enabled: bool
    is_visible_to_oauth_clients: bool
    last_connected_at: Optional[datetime]
    error_message: Optional[str]

    # Statistics
    total_requests: int
    failed_requests: int

    # Metadata
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "organization_id": "123e4567-e89b-12d3-a456-426614174001",
                "server_id": "grist-mcp",
                "name": "Grist MCP Server",
                "description": "MCP server for Grist integration",
                "install_type": "pip",
                "install_package": "grist-mcp",
                "version": "1.0.0",
                "command": "python",
                "args": ["-m", "grist_mcp"],
                "env": {
                    "GRIST_API_KEY": "***",
                    "GRIST_BASE_URL": "https://docs.getgrist.com"
                },
                "status": "running",
                "enabled": True,
                "last_connected_at": "2024-01-15T10:30:00Z",
                "error_message": None,
                "total_requests": 1234,
                "failed_requests": 5,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-15T10:30:00Z"
            }
        }


class MCPServerListResponse(BaseModel):
    """Schema for list of MCP servers."""

    servers: List[MCPServerResponse]
    total: int

    class Config:
        json_schema_extra = {
            "example": {
                "servers": [
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "server_id": "grist-mcp",
                        "name": "Grist MCP Server",
                        "status": "running",
                        "enabled": True
                    }
                ],
                "total": 1
            }
        }
