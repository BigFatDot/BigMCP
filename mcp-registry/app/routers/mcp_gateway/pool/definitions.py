"""
MCP tool definitions for the dynamic pool surface.

These are the only two tools BigMCP exposes to OAuth clients in the new UX:
- `search`: load tools (and saved composed tools) into the user's active pool
- `execute`: run a goal in natural language using the loaded pool, with
  intelligent shortcut routing (no LLM when goal is unambiguous).
"""

from typing import Any, Dict, List


POOL_TOOL_NAMES = frozenset({"search", "execute", "describe_tool"})


def get_pool_tools() -> List[Dict[str, Any]]:
    """Return the MCP tool definitions for the dynamic pool surface."""
    return [
        {
            "name": "search",
            "title": "Search & load tools into the active pool",
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
            },
            # MCP 2025-06-18: declare a JSON Schema for the response so clients
            # parse `structuredContent` deterministically instead of regexing
            # the text body. Keeps the legacy text content for backward compat.
            "outputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "mode": {"type": "string"},
                    "loaded_count": {"type": "integer"},
                    "tool_count": {"type": "integer"},
                    "composition_count": {"type": "integer"},
                    "pool_size": {"type": "integer"},
                    "loaded": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": ["tool", "composition"]},
                                "name": {"type": "string"},
                                "server": {"type": ["string", "null"]},
                                "description": {"type": "string"},
                                "score": {"type": "integer"},
                                "was_already_in_pool": {"type": "boolean"}
                            },
                            "required": ["kind", "name"]
                        }
                    },
                    "hint": {"type": "string"}
                },
                "required": ["loaded_count", "pool_size"]
            },
            # MCP 2025-06-18: behavior hints. ``search`` only mutates the
            # internal pool selection — no external side-effect — and is
            # NOT idempotent because successive calls accumulate matches.
            "annotations": {
                "title": "Search & load tools",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False,
            },
        },
        {
            "name": "execute",
            "title": "Execute a goal, tool, or composition",
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
            },
            # MCP 2025-06-18: structured output. The shape is a thin envelope
            # whose `result` carries the underlying tool/composition payload —
            # callers get a stable hook on `level` / `composition` / `tool` /
            # `error` without parsing the text body.
            "outputSchema": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "string",
                        "description": (
                            "Routing level chosen by the dispatcher: "
                            "L0_tool, L0_composition, L1_or_L2_tool_direct, "
                            "L1_or_L2_tool_via_intent, "
                            "L1_or_L2_composition_direct, "
                            "L1_or_L2_composition_via_intent, L3_orchestrated, "
                            "or one of the *_failed variants."
                        )
                    },
                    "tool": {"type": ["string", "null"]},
                    "composition_id": {"type": ["string", "null"]},
                    "composition_name": {"type": ["string", "null"]},
                    "extracted_params": {"type": ["object", "null"]},
                    "result": {"type": ["object", "null"]},
                    "error": {"type": ["string", "null"]}
                }
            },
            # MCP 2025-06-18: ``execute`` may invoke ANY underlying tool —
            # the safe assumption is destructive + open-world. Clients can
            # still inspect the resolved tool's own annotations via
            # ``describe_tool`` if they need a tighter signal.
            "annotations": {
                "title": "Execute a goal, tool, or composition",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": True,
            },
        },
        {
            "name": "describe_tool",
            "title": "Get the full description of a tool",
            "description": (
                "Return the verbose description (and optional usage hints) of "
                "any tool or composition currently in the pool. Useful when "
                "tools/list ships only a 1-line title (compact mode) and you "
                "need the full text before deciding to call it. Costs ~150 "
                "tokens once instead of N×150 for every tools/list response."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Exact tool name as advertised in tools/list (e.g., 'GitHub__create_issue' or 'composition_my_workflow').",
                    }
                },
                "required": ["name"],
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "kind": {"type": "string", "enum": ["tool", "composition"]},
                    "title": {"type": ["string", "null"]},
                    "description": {"type": "string"},
                    "server": {"type": ["string", "null"]},
                    "input_schema": {"type": "object"},
                    "found": {"type": "boolean"},
                },
                "required": ["name", "found"],
            },
            # MCP 2025-06-18: pure metadata read — fully read-only and
            # idempotent. No external service calls (the catalog lives in
            # our own DB).
            "annotations": {
                "title": "Describe a tool or composition",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        },
    ]
