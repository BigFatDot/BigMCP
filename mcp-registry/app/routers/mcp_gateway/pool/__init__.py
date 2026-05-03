"""
Dynamic Tool Pool module.

Implements the new BigMCP MCP surface: only two tools (`search` and `execute`)
are exposed to OAuth clients. The pool of "natively visible" tools is managed
dynamically per-user via the `search` MCP tool, eliminating the need to
manually toggle tool visibility from the web UI.

- definitions.py: MCP tool definitions (`search`, `execute`)
- search_handler.py: server-side logic for `search`
- execute_handler.py: server-side logic for `execute` with 4-level routing
"""

from .definitions import get_pool_tools, POOL_TOOL_NAMES
from .search_handler import handle_search
from .execute_handler import handle_execute

__all__ = [
    "get_pool_tools",
    "POOL_TOOL_NAMES",
    "handle_search",
    "handle_execute",
]
