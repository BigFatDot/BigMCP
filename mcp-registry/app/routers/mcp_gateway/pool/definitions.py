"""
MCP tool definitions for the dynamic pool surface.

These are the only two tools BigMCP exposes to OAuth clients in the new UX:
- `search`: load tools (and saved composed tools) into the user's active pool
- `execute`: run a goal in natural language using the loaded pool, with
  intelligent shortcut routing (no LLM when goal is unambiguous).
"""

from typing import Any, Dict, List


POOL_TOOL_NAMES = frozenset({"search", "execute"})


def get_pool_tools() -> List[Dict[str, Any]]:
    """Return the MCP tool definitions for the dynamic pool surface."""
    return [
        {
            "name": "search",
            "description": (
                "Load tools relevant to your current task into your active pool. "
                "Your pool starts EMPTY at session start; call `search` first before "
                "trying `execute`. Subsequent `search` calls add to the pool by default "
                "(use mode='replace' to reset). Searches across every tool the user has "
                "connected (including saved composed tools) — not only what is currently "
                "visible to you."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language description of what you want to do (e.g., 'send an email', 'create a github issue', 'lookup DNS records')."
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["append", "replace"],
                        "default": "append",
                        "description": "append (default): add matched tools to the existing pool. replace: clear pool first, then load matches."
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                        "description": "Maximum number of tools to load. Keep small (5-15) to avoid context bloat."
                    }
                },
                "required": ["query"]
            }
        },
        {
            "name": "execute",
            "description": (
                "Execute a goal using the tools currently loaded in your pool. "
                "Routes intelligently: direct call if you pass tool_name or composition_id, "
                "single-tool execution when one tool clearly matches, full LLM orchestration "
                "for multi-step goals. The pool must be non-empty — call `search` first if it "
                "is empty."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "Natural-language description of what to achieve. Required unless tool_name or composition_id is set."
                    },
                    "tool_name": {
                        "type": "string",
                        "description": "Optional: bypass orchestration and call this exact tool from the pool. Use when you already know which tool to call."
                    },
                    "composition_id": {
                        "type": "string",
                        "description": "Optional: run a saved composed tool by its UUID. Mutually exclusive with tool_name/goal-orchestration."
                    },
                    "params": {
                        "type": "object",
                        "description": "Optional: explicit parameters. Required when using tool_name or composition_id; optional for goal-mode (will be inferred from the goal)."
                    }
                }
            }
        }
    ]
