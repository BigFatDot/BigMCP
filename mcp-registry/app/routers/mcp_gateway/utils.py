"""
MCP Gateway Utilities - Standalone helper functions.

Extracted from mcp_unified.py for better modularity.
These functions have no external dependencies and can be safely reused.
"""

import json
import logging
from typing import Any, Dict

logger = logging.getLogger("mcp_unified")


def _parse_json_value(value: Any) -> Any:
    """
    Parse a single value, converting JSON strings to native types.

    Args:
        value: Any value to potentially parse

    Returns:
        Parsed value or original if not a JSON string
    """
    if isinstance(value, str):
        stripped = value.strip()
        # Only attempt parsing if it looks like JSON
        if stripped in ('true', 'false', 'null') or (
            stripped and stripped[0] in '[{' and stripped[-1] in ']}'
        ):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
    return value


def parse_json_string_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pre-process tool arguments to parse JSON strings into native Python types.

    Claude (and other LLMs) may serialize complex values (lists, dicts, booleans)
    as JSON strings when sending tool parameters. This function converts them back
    to native types for proper Pydantic validation.

    Example:
        Input:  {"items": "[]", "enabled": "true", "config": "{\"key\": \"value\"}"}
        Output: {"items": [], "enabled": True, "config": {"key": "value"}}

    Args:
        arguments: Tool arguments dictionary

    Returns:
        Arguments with JSON strings parsed to native types
    """
    if not isinstance(arguments, dict):
        return arguments

    parsed = {}
    for key, value in arguments.items():
        if isinstance(value, str):
            parsed_value = _parse_json_value(value)
            if parsed_value != value:
                logger.debug(f"Parsed JSON string argument '{key}': {value!r} -> {parsed_value!r}")
            parsed[key] = parsed_value
        elif isinstance(value, dict):
            # Recursively process nested dicts
            parsed[key] = parse_json_string_arguments(value)
        elif isinstance(value, list):
            # Recursively process list elements
            parsed[key] = [
                parse_json_string_arguments(item) if isinstance(item, dict)
                else _parse_json_value(item)
                for item in value
            ]
        else:
            # Keep other types as-is (int, float, None, etc.)
            parsed[key] = value

    return parsed


def _error_response(request_id: str, code: int, message: str) -> Dict[str, Any]:
    """
    Create a JSON-RPC 2.0 error response.

    Args:
        request_id: Original request ID
        code: Error code (negative for JSON-RPC standard errors)
        message: Human-readable error message

    Returns:
        JSON-RPC 2.0 compliant error response dict
    """
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message
        }
    }


def _normalize_parameters(params: Any) -> Dict[str, Any]:
    """
    Normalize parameters from various formats to a consistent dict.

    MCP clients may send parameters in different formats:
    - As a dict: {"name": "value"}
    - As None or missing
    - As other types (rare)

    Args:
        params: Raw parameters from request

    Returns:
        Normalized parameters dict
    """
    if params is None:
        return {}
    if isinstance(params, dict):
        return params
    # Fallback for unexpected types
    return {"_raw": params}
