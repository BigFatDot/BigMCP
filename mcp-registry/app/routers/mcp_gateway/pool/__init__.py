"""
Dynamic Tool Pool module.

Implements the BigMCP MCP surface meta-tools exposed to OAuth clients:
``search``, ``execute``, ``describe_tool``, and ``composition_status``
(B-0 chunk 8). The pool of "natively visible" tools is managed
dynamically per-user via the `search` MCP tool, with descriptions
fetched on demand via `describe_tool` when compact mode is on.

- definitions.py: MCP tool definitions (`search`, `execute`,
  `describe_tool`, `composition_status`)
- search_handler.py: server-side logic for `search`
- execute_handler.py: server-side logic for `execute` with 4-level routing
- describe_handler.py: server-side logic for `describe_tool`
- composition_status_handler.py: per-user execution status polling
"""

from .definitions import get_pool_tools, POOL_TOOL_NAMES
from .search_handler import handle_search
from .execute_handler import handle_execute
from .describe_handler import handle_describe_tool
from .composition_status_handler import handle_composition_status

__all__ = [
    "get_pool_tools",
    "POOL_TOOL_NAMES",
    "handle_search",
    "handle_execute",
    "handle_describe_tool",
    "handle_composition_status",
]
