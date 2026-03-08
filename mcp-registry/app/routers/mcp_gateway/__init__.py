"""
MCP Gateway Module - Unified MCP protocol handling.

This module is being incrementally refactored from a monolithic
mcp_unified.py (66KB, 3004 lines) into smaller, focused modules.

Current structure:
- utils.py: Helper functions (extracted)
- gateway.py: MCPUnifiedGateway class (planned)
- handlers/: MCP protocol handlers (planned)
- orchestration/: AI orchestration logic (planned)
- endpoints.py: FastAPI router endpoints (planned)

IMPORTANT: Due to circular import constraints, imports from mcp_unified.py
are done lazily. Use the get_* functions or import directly from mcp_unified.py.
"""

# Import from new modular structure (Phase 2) - no circular dependency
from .utils import (
    parse_json_string_arguments,
    _parse_json_value,
    _error_response,
    _normalize_parameters,
)


def get_gateway():
    """Lazy import to avoid circular dependency."""
    from ..mcp_unified import gateway
    return gateway


def get_mcp_sessions():
    """Lazy import to avoid circular dependency."""
    from ..mcp_unified import mcp_sessions
    return mcp_sessions


def get_router():
    """Lazy import to avoid circular dependency."""
    from ..mcp_unified import router
    return router


__all__ = [
    # Lazy accessors (to avoid circular imports)
    "get_gateway",
    "get_mcp_sessions",
    "get_router",
    # Utilities (from utils.py - safe, no circular dependency)
    "parse_json_string_arguments",
    "_parse_json_value",
    "_error_response",
    "_normalize_parameters",
]
