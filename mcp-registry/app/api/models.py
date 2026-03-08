"""
Pydantic models for the MCP Registry API.
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class ServerInfo(BaseModel):
    """MCP server information."""
    id: str
    name: str
    url: str
    description: Optional[str] = ""
    last_update: Optional[datetime] = None
    tools_count: int = 0

class ToolParameter(BaseModel):
    """MCP tool parameter."""
    name: str
    description: Optional[str] = ""
    type: Optional[str] = "string"
    required: bool = False

class ToolInfo(BaseModel):
    """MCP tool information."""
    id: Optional[str] = None
    name: Optional[str] = None
    server_id: Optional[str] = None
    server_url: Optional[str] = None
    description: Optional[str] = ""
    parameters: Optional[Dict[str, Any]] = None

    class Config:
        """Configuration to allow extra fields."""
        extra = "allow"

class SearchQuery(BaseModel):
    """Tool search query."""
    query: str
    limit: int = Field(5, ge=1, le=100)

class ExecuteToolRequest(BaseModel):
    """Tool execution request."""
    server_id: str
    tool_id: str
    parameters: Dict[str, Any] = Field(default_factory=dict)

class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    message: Optional[str] = None

class ApiInfo(BaseModel):
    """API information."""
    name: str
    version: str
    description: str 