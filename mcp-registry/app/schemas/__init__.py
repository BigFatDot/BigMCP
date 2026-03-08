"""
Pydantic schemas for API request/response validation.

Schemas define the contract between API clients and the server,
providing type safety and automatic validation.
"""

from .mcp_server import (
    MCPServerCreate,
    MCPServerUpdate,
    MCPServerResponse,
    MCPServerListResponse
)
from .context import (
    ContextCreate,
    ContextUpdate,
    ContextResponse,
    ContextTreeResponse
)
from .tool_binding import (
    ToolBindingCreate,
    ToolBindingUpdate,
    ToolBindingResponse,
    ToolBindingExecute,
    ToolBindingExecuteResponse
)
from .tool import (
    ToolResponse,
    ToolUpdateVisibility,
    ToolListResponse
)

__all__ = [
    # MCP Server schemas
    "MCPServerCreate",
    "MCPServerUpdate",
    "MCPServerResponse",
    "MCPServerListResponse",

    # Context schemas
    "ContextCreate",
    "ContextUpdate",
    "ContextResponse",
    "ContextTreeResponse",

    # Tool Binding schemas
    "ToolBindingCreate",
    "ToolBindingUpdate",
    "ToolBindingResponse",
    "ToolBindingExecute",
    "ToolBindingExecuteResponse",

    # Tool schemas
    "ToolResponse",
    "ToolUpdateVisibility",
    "ToolListResponse",
]
