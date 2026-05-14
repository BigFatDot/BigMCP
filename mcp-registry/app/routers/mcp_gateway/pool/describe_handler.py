"""
Server-side handler for the `describe_tool` MCP tool.

Returns the full description (and metadata) of a tool or composition
currently in the user's searchable pool. Used by the LLM in compact
mode (``MCP_COMPACT_MODE=true``) when ``tools/list`` ships only the
1-line title and the LLM needs the verbose description before deciding
whether to invoke the tool.

Cost model:
- ``tools/list`` in compact mode = ~30 tokens/tool × N tools
- ``describe_tool`` = ~150 tokens once per tool the LLM is hesitant on
- Net win as long as the LLM doesn't need to describe more than ~25%
  of the catalog per session, which is the typical pattern.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ....db.session import AsyncSessionLocal
from .pool_loader import load_searchable_pool

logger = logging.getLogger("describe_tool")


async def handle_describe_tool(
    arguments: Dict[str, Any],
    *,
    user_id: str,
    organization_id: str,
    db: Optional[AsyncSession] = None,
) -> Dict[str, Any]:
    """Resolve a tool/composition name to its full description.

    Returns ``found=False`` instead of raising when the name is unknown,
    so the LLM can recover gracefully (typically by calling ``search``).

    ``db`` is an optional dependency-injected session — only useful in
    tests where the searchable pool lives in an in-memory SQLite that
    differs from the app's ``AsyncSessionLocal``.
    """
    name = (arguments or {}).get("name", "").strip()
    if not name:
        return {
            "structuredContent": {
                "name": "",
                "found": False,
                "description": "",
                "kind": "tool",
                "input_schema": {},
            },
            "content": [{"type": "text", "text": "Missing 'name' argument."}],
            "isError": True,
        }

    if not organization_id:
        return {
            "structuredContent": {
                "name": name,
                "found": False,
                "description": "",
                "kind": "tool",
                "input_schema": {},
            },
            "content": [
                {"type": "text", "text": "No organization context for this session."}
            ],
            "isError": True,
        }

    org_uuid = UUID(organization_id)

    if db is not None:
        entries = await load_searchable_pool(db, org_uuid)
    else:
        async with AsyncSessionLocal() as session:
            entries = await load_searchable_pool(session, org_uuid)

    match = next((e for e in entries if e.name == name), None)
    if match is None:
        body = {
            "name": name,
            "found": False,
            "kind": "tool",
            "title": None,
            "description": "",
            "server": None,
            "input_schema": {},
        }
        text = (
            f"Tool '{name}' not found in your searchable pool. Try `search` "
            f"first to load matching tools, or check the spelling."
        )
        return {
            "structuredContent": body,
            "content": [{"type": "text", "text": text}],
        }

    title = (
        f"Composition: {match.raw_composition.name}"
        if match.kind == "composition" and match.raw_composition
        else (
            f"[{match.server_name}] {match.raw_tool.tool_name}"
            if match.kind == "tool" and match.server_name and match.raw_tool
            else None
        )
    )
    body = {
        "name": match.name,
        "found": True,
        "kind": match.kind,
        "title": title,
        "description": match.description,
        "server": match.server_name,
        "input_schema": match.parameters_schema,
    }
    text = f"{title or match.name}\n\n{match.description}".strip()
    return {
        "structuredContent": body,
        "content": [{"type": "text", "text": text}],
    }
