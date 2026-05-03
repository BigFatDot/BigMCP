"""
Server-side handler for the `search` MCP tool.

Loads tools (and surfaces production compositions) into the user's active
session pool. The pool is materialized for tools via the
`Tool.is_visible_to_oauth_clients` flag — flipping it on makes the tool
appear in the next `tools/list` response. Production compositions are
*always* visible in `tools/list`, so they are reported in the search
response for discoverability but do not require any DB mutation.

Notifications and cache invalidation reuse the existing hooks already in
place for the legacy visibility toggle endpoint.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy import select, update

from ....db.database import async_session_maker
from ....models.mcp_server import MCPServer
from ....models.tool import Tool
from .pool_loader import (
    PoolEntry,
    load_searchable_pool,
    score_entry,
)

logger = logging.getLogger(__name__)


_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


# Backward-compat shim used by tests written before the loader refactor.
def _score_tool(query_tokens: List[str], tool: Any, server_name: str) -> int:
    """Score a SQLAlchemy Tool against query tokens (test helper)."""
    if not query_tokens:
        return 0
    parts = [
        getattr(tool, "tool_name", "") or "",
        getattr(tool, "display_name", "") or "",
        getattr(tool, "description", "") or "",
        getattr(tool, "category", "") or "",
        server_name or "",
    ]
    tags = getattr(tool, "tags", None) or []
    parts.extend(tags)
    haystack = " ".join(parts).lower()
    name_lower = (getattr(tool, "tool_name", "") or "").lower()
    score = 0
    for token in query_tokens:
        if not token:
            continue
        if token in name_lower:
            score += 2
        if token in haystack:
            score += 1
    return score


async def handle_search(
    arguments: Dict[str, Any],
    user_id: Optional[str],
    organization_id: Optional[str],
) -> Dict[str, Any]:
    """Handle the `search` MCP tool call."""
    query: Optional[str] = arguments.get("query")
    mode: str = arguments.get("mode", "append")
    try:
        limit: int = int(arguments.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
    limit = max(1, min(50, limit))

    if not query or not isinstance(query, str) or not query.strip():
        return {"error": "Missing or empty 'query' parameter"}
    if mode not in ("append", "replace"):
        return {"error": f"Invalid mode '{mode}'. Must be 'append' or 'replace'."}
    if not user_id or not organization_id:
        return {"error": "Authentication required: missing user/organization context"}

    try:
        org_uuid = UUID(str(organization_id))
        user_uuid = UUID(str(user_id))
    except (TypeError, ValueError):
        return {"error": "Invalid user_id or organization_id"}

    query_tokens = _tokenize(query)

    async with async_session_maker() as db:
        candidates = await load_searchable_pool(db, org_uuid)
        scored: List[Tuple[int, PoolEntry]] = []
        for entry in candidates:
            s = score_entry(query_tokens, entry)
            if s > 0:
                scored.append((s, entry))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        matched = scored[:limit]

        # Tool-side mutations only (compositions are always visible).
        matched_tool_uuids: Set[UUID] = {
            UUID(e.id) for _, e in matched if e.kind == "tool"
        }
        matched_server_uuids: Set[UUID] = {
            UUID(e.server_id) for _, e in matched
            if e.kind == "tool" and e.server_id
        }

        previous_visible_tool_ids: Set[UUID] = set()
        prev_stmt = select(Tool.id).where(
            Tool.organization_id == org_uuid,
            Tool.is_visible_to_oauth_clients.is_(True),
        )
        for (tid,) in (await db.execute(prev_stmt)).all():
            previous_visible_tool_ids.add(tid)

        if mode == "replace":
            await db.execute(
                update(Tool)
                .where(
                    Tool.organization_id == org_uuid,
                    Tool.is_visible_to_oauth_clients.is_(True),
                )
                .values(is_visible_to_oauth_clients=False)
            )

        if matched_tool_uuids:
            await db.execute(
                update(Tool)
                .where(Tool.id.in_(matched_tool_uuids))
                .values(is_visible_to_oauth_clients=True)
            )
            await db.execute(
                update(MCPServer)
                .where(
                    # Defence-in-depth: explicit org scope even though
                    # matched_server_uuids was derived from an org-scoped query.
                    MCPServer.organization_id == org_uuid,
                    MCPServer.id.in_(matched_server_uuids),
                    MCPServer.is_visible_to_oauth_clients.is_(False),
                )
                .values(is_visible_to_oauth_clients=True)
            )

        await db.commit()

    async with async_session_maker() as db:
        size_stmt = select(Tool.id).where(
            Tool.organization_id == org_uuid,
            Tool.is_visible_to_oauth_clients.is_(True),
        )
        final_pool_size = len((await db.execute(size_stmt)).all())

    await _invalidate_and_notify(org_uuid, user_uuid)

    loaded_summary: List[Dict[str, Any]] = []
    for score, entry in matched:
        was_in_pool = (
            entry.kind == "composition"
            or (entry.kind == "tool" and UUID(entry.id) in previous_visible_tool_ids)
        )
        loaded_summary.append(
            {
                "kind": entry.kind,
                "name": entry.name,
                "server": entry.server_name,
                "description": (entry.description or "")[:200],
                "score": score,
                "was_already_in_pool": was_in_pool,
            }
        )

    composition_count = sum(1 for _, e in matched if e.kind == "composition")
    tool_count = len(matched) - composition_count

    return {
        "query": query,
        "mode": mode,
        "loaded": loaded_summary,
        "loaded_count": len(loaded_summary),
        "tool_count": tool_count,
        "composition_count": composition_count,
        "pool_size": final_pool_size,
        "hint": (
            "Call `execute` with a natural-language goal now, or with tool_name/params "
            "for a direct invocation."
            if final_pool_size > 0 or composition_count > 0
            else "No tools matched. Try a broader query or check that you have "
            "connected MCP servers in your account."
        ),
    }


async def _invalidate_and_notify(org_uuid: UUID, user_uuid: UUID) -> None:
    """Invalidate caches and emit `tools/list_changed` for the user."""
    try:
        from ....services.organization_tool_cache import tool_cache

        await tool_cache.invalidate_organization(org_uuid)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"search_handler: org tool_cache invalidation failed: {e}")

    try:
        from ....services.user_tool_cache import get_user_tool_cache

        user_cache = get_user_tool_cache()
        await user_cache.invalidate_organization(org_uuid)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"search_handler: user_tool_cache invalidation failed: {e}")

    try:
        from ...mcp_unified import notify_org_tools_changed

        import asyncio as _asyncio

        _asyncio.create_task(notify_org_tools_changed(org_uuid, user_id=user_uuid))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"search_handler: notification scheduling failed: {e}")
