"""
Orchestration Tools - Meta-tool definitions for workflow composition.

Extracted from mcp_unified.py for better modularity.

These tools provide workflow composition capabilities:
- Search tools semantically
- Analyze user intent
- Create/manage compositions
- Execute workflows
"""

from typing import Any, Dict, List


def get_orchestration_tools() -> List[Dict[str, Any]]:
    """
    Return orchestration meta-tools.

    These tools provide workflow composition capabilities.
    """
    return [
        {
            "name": "orchestrator_search_tools",
            "description": "Search for tools using semantic search. Find tools based on natural language description of what you want to do.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language description of what you want to do (e.g., 'create a document', 'analyze data')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of tools to return",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        },
        {
            "name": "orchestrator_analyze_intent",
            "description": "Analyze a user request and propose an orchestrated workflow to accomplish it. Returns a detailed execution plan.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "User request in natural language"
                    },
                    "context": {
                        "type": "object",
                        "description": "Additional context (previous interactions, preferences)"
                    }
                },
                "required": ["query"]
            }
        },
        {
            "name": "orchestrator_execute_composition",
            "description": "Execute a workflow composition. Two modes: (1) saved: pass composition_id (UUID from orchestrator_create_composition or orchestrator_list_compositions); (2) inline: pass composition (full definition object). Never pass the literal string 'inline' as composition_id.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "composition_id": {
                        "type": "string",
                        "description": "UUID of a saved composition. Obtain from orchestrator_create_composition or orchestrator_list_compositions. Mutually exclusive with 'composition'."
                    },
                    "composition": {
                        "type": "object",
                        "description": "Inline composition definition to execute directly without saving first. Mutually exclusive with 'composition_id'. Must have 'name', 'steps', and optionally 'data_mappings'."
                    },
                    "parameters": {
                        "type": "object",
                        "description": "Input parameters for the composition"
                    }
                },
                "required": ["parameters"]
            }
        },
        {
            "name": "orchestrator_list_compositions",
            "description": "List all available workflow compositions. Filter by status (temporary, validated, production) or search text.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": "Text to search in composition names and descriptions"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["temporary", "validated", "production"],
                        "description": "Filter by composition status"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results",
                        "default": 20
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Pagination offset",
                        "default": 0
                    }
                },
                "required": []
            }
        },
        {
            "name": "orchestrator_get_composition",
            "description": "Get detailed information about a specific workflow composition including steps, parameters, and execution metrics.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "composition_id": {
                        "type": "string",
                        "description": "ID of the composition to retrieve"
                    },
                    "include_metrics": {
                        "type": "boolean",
                        "description": "Include execution statistics and metrics",
                        "default": True
                    }
                },
                "required": ["composition_id"]
            }
        },
        {
            "name": "orchestrator_create_composition",
            "description": """Create a new reusable workflow composition.

TOOL FORMAT: Use EXACTLY the prefixed tool name: 'prefix__toolname' (e.g., 'grist_mcp_grist_gouv__list_organizations').

DATA REFERENCES:
- ${input.param_name} - Composition input parameter
- ${step_N.field.path} - Previous step output (N = 1, 2, 3...)
- ${step_1.items[0].id} - Array index access
- ${step_1.items[*].id} - WILDCARD: Extract ALL ids → ["id1", "id2", ...]
- ${step_1.workspaces[*].docs[*].id} - Nested wildcards auto-flatten

TEMPLATE/MAP for object transformation:
{
  "_template": "${step_1.workspaces[*].docs[*]}",
  "_map": {
    "doc_id": "${_item.id}",
    "workspace_id": "${_parent.id}",
    "source": "${_root.metadata.source}",
    "index": "${_index}",
    "synced_at": "${_now}"
  }
}

Context variables in _map:
- ${_item} - Current iteration item
- ${_parent} - Parent object (for nested wildcards)
- ${_root} - Original step result root
- ${_index} - Current iteration index (0, 1, 2...)
- ${_now} - ISO timestamp
- ${_comment} - Ignored (for documentation)""",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Human-readable name for the composition"
                    },
                    "description": {
                        "type": "string",
                        "description": "What this workflow accomplishes"
                    },
                    "steps": {
                        "type": "array",
                        "description": "Ordered list of workflow steps",
                        "items": {
                            "type": "object",
                            "required": ["tool", "parameters"],
                            "properties": {
                                "tool": {
                                    "type": "string",
                                    "description": "EXACT prefixed tool name from tools list: 'prefix__toolname' (e.g., 'grist_mcp_grist_gouv__list_organizations'). Copy the name exactly as shown."
                                },
                                "parameters": {
                                    "type": "object",
                                    "description": "Tool parameters. Supports: ${input.x}, ${step_N.path}, ${step_N.items[*].id} for wildcards, and {\"_template\": \"...\", \"_map\": {...}} for object transformation."
                                }
                            }
                        }
                    },
                    "input_schema": {
                        "type": "object",
                        "description": "JSON Schema with 'type': 'object', 'required': [...], 'properties': {...} defining composition input parameters"
                    },
                    "output_schema": {
                        "type": "object",
                        "description": "Optional JSON Schema for expected output structure"
                    }
                },
                "required": ["name", "description", "steps"]
            }
        },
        {
            "name": "orchestrator_promote_composition",
            "description": "Promote a composition through lifecycle stages: temporary -> validated -> production. Production compositions become directly callable tools.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "composition_id": {
                        "type": "string",
                        "description": "ID of the composition to promote"
                    },
                    "target_status": {
                        "type": "string",
                        "enum": ["validated", "production"],
                        "description": "Target status to promote to"
                    }
                },
                "required": ["composition_id", "target_status"]
            }
        },
        {
            "name": "orchestrator_delete_composition",
            "description": "Delete a workflow composition. Cannot delete production compositions without force flag.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "composition_id": {
                        "type": "string",
                        "description": "ID of the composition to delete"
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Force deletion even for production compositions",
                        "default": False
                    }
                },
                "required": ["composition_id"]
            }
        }
    ]


# Backwards compatibility - can be imported as constant
ORCHESTRATION_TOOLS = get_orchestration_tools()
