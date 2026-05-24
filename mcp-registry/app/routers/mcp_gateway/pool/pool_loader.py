"""
Pool entries loader — unifies Tool and Composition into a single shape.

A user's pool conceptually contains two kinds of items:
- "tool"        : an MCP tool from a connected server, gated by the dynamic
                  visibility flag `Tool.is_visible_to_oauth_clients`.
- "composition" : a saved composed tool with status='production'. These are
                  always available (not gated by the dynamic visibility flag)
                  so creating a production composition makes it permanently
                  invokable through `execute`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....models.composition import Composition
from ....models.mcp_server import MCPServer
from ....models.tool import Tool


@dataclass(frozen=True)
class PoolEntry:
    kind: str  # "tool" | "composition"
    id: str
    name: str  # MCP-facing name (prefixed for tools, "composition_<safe>" for comps)
    description: str
    parameters_schema: Dict[str, Any]
    server_name: Optional[str]
    server_id: Optional[str]
    raw_tool: Optional[Tool] = None
    raw_composition: Optional[Composition] = None
    raw_server: Optional[MCPServer] = None

    @property
    def haystack(self) -> str:
        parts = [self.name, self.description, self.server_name or ""]
        if self.kind == "tool" and self.raw_tool is not None:
            if self.raw_tool.tool_name:
                parts.append(self.raw_tool.tool_name)
            if self.raw_tool.display_name:
                parts.append(self.raw_tool.display_name)
            if self.raw_tool.category:
                parts.append(self.raw_tool.category)
            if self.raw_tool.tags:
                parts.extend(self.raw_tool.tags)
        elif self.kind == "composition" and self.raw_composition is not None:
            meta = self.raw_composition.extra_metadata or {}
            tags = meta.get("tags") or []
            if isinstance(tags, list):
                parts.extend(str(t) for t in tags)
        return " ".join(parts).lower()


def _sanitize_prefix(text: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", text or "")
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe


def _tool_to_entry(tool: Tool, server: MCPServer) -> PoolEntry:
    prefix = _sanitize_prefix(server.name or "")
    prefixed = f"{prefix}__{tool.tool_name}" if prefix else tool.tool_name
    return PoolEntry(
        kind="tool",
        id=str(tool.id),
        name=prefixed,
        description=tool.description or "",
        parameters_schema=tool.parameters_schema or {"type": "object"},
        server_name=server.name,
        server_id=str(server.id),
        raw_tool=tool,
        raw_server=server,
    )


def _composition_to_entry(comp: Composition) -> PoolEntry:
    safe = _sanitize_prefix(comp.name or "")
    return PoolEntry(
        kind="composition",
        id=str(comp.id),
        name=f"composition_{safe}" if safe else f"composition_{comp.id}",
        description=comp.description or "",
        parameters_schema=comp.input_schema or {"type": "object"},
        server_name=None,
        server_id=None,
        raw_composition=comp,
    )


async def load_visible_pool(
    db: AsyncSession,
    organization_id: UUID,
    user_id: Optional[UUID] = None,
) -> List[PoolEntry]:
    """Tools currently in the dynamic pool + all production compositions.

    Three layers UNIONed (deduplicated by tool/composition id):

    1. **Ephemeral session pool** — tools where
       ``is_visible_to_oauth_clients=True`` for this org. Mutated by
       ``search`` calls; reset at session end (depends on caller).

    2. **Org default pool** (Phase 3) — admin-curated entries every
       user of the org inherits at MCP-connect time. Solves the cold
       start: agents see a non-empty catalog on first ``tools/list``
       without having to call ``search`` first.

    3. **User-persistent pinned entries** (Phase 3) — per-user
       favorites that survive across sessions. Optional, applied only
       when ``user_id`` is passed.

    Plus production compositions for the org (visibility=ORGANIZATION
    is implicit in pool exposure; PRIVATE compositions stay private).
    """
    from ....models.pool_persistent import (
        OrgDefaultPoolEntry,
        UserPersistentPoolEntry,
    )

    entries: List[PoolEntry] = []
    seen_tool_ids: set[UUID] = set()
    seen_composition_ids: set[UUID] = set()

    # ---------- Layer 1: ephemeral session pool ----------
    tool_stmt = (
        select(Tool, MCPServer)
        .join(MCPServer, Tool.server_id == MCPServer.id)
        .where(
            Tool.organization_id == organization_id,
            Tool.is_visible_to_oauth_clients.is_(True),
            MCPServer.enabled.is_(True),
            MCPServer.is_visible_to_oauth_clients.is_(True),
        )
    )
    for tool, server in (await db.execute(tool_stmt)).all():
        entries.append(_tool_to_entry(tool, server))
        seen_tool_ids.add(tool.id)

    # ---------- Layer 2: org default pool ----------
    default_stmt = (
        select(OrgDefaultPoolEntry)
        .where(OrgDefaultPoolEntry.organization_id == organization_id)
        .order_by(OrgDefaultPoolEntry.position.asc())
    )
    default_rows = (await db.execute(default_stmt)).scalars().all()

    if default_rows:
        wanted_tool_ids = {
            r.tool_id for r in default_rows if r.tool_id and r.tool_id not in seen_tool_ids
        }
        if wanted_tool_ids:
            extra_tools = await db.execute(
                select(Tool, MCPServer)
                .join(MCPServer, Tool.server_id == MCPServer.id)
                .where(Tool.id.in_(wanted_tool_ids))
                .where(MCPServer.enabled.is_(True))
            )
            for tool, server in extra_tools.all():
                entries.append(_tool_to_entry(tool, server))
                seen_tool_ids.add(tool.id)

        wanted_comp_ids = {
            r.composition_id
            for r in default_rows
            if r.composition_id and r.composition_id not in seen_composition_ids
        }
        if wanted_comp_ids:
            extra_comps = (
                await db.execute(
                    select(Composition).where(Composition.id.in_(wanted_comp_ids))
                )
            ).scalars().all()
            for comp in extra_comps:
                entries.append(_composition_to_entry(comp))
                seen_composition_ids.add(comp.id)

    # ---------- Layer 3: per-user pinned ----------
    if user_id is not None:
        pin_stmt = select(UserPersistentPoolEntry).where(
            UserPersistentPoolEntry.user_id == user_id
        )
        pin_rows = (await db.execute(pin_stmt)).scalars().all()

        if pin_rows:
            wanted_tool_ids = {
                r.tool_id
                for r in pin_rows
                if r.tool_id and r.tool_id not in seen_tool_ids
            }
            if wanted_tool_ids:
                extra_tools = await db.execute(
                    select(Tool, MCPServer)
                    .join(MCPServer, Tool.server_id == MCPServer.id)
                    .where(Tool.id.in_(wanted_tool_ids))
                    .where(Tool.organization_id == organization_id)
                    .where(MCPServer.enabled.is_(True))
                )
                for tool, server in extra_tools.all():
                    entries.append(_tool_to_entry(tool, server))
                    seen_tool_ids.add(tool.id)

            wanted_comp_ids = {
                r.composition_id
                for r in pin_rows
                if r.composition_id and r.composition_id not in seen_composition_ids
            }
            if wanted_comp_ids:
                extra_comps = (
                    await db.execute(
                        select(Composition).where(
                            Composition.id.in_(wanted_comp_ids),
                            Composition.organization_id == organization_id,
                        )
                    )
                ).scalars().all()
                for comp in extra_comps:
                    entries.append(_composition_to_entry(comp))
                    seen_composition_ids.add(comp.id)

    # ---------- Production compositions ----------
    comp_stmt = select(Composition).where(
        Composition.organization_id == organization_id,
        Composition.status == "production",
    )
    for (comp,) in (await db.execute(comp_stmt)).all():
        if comp.id in seen_composition_ids:
            continue
        entries.append(_composition_to_entry(comp))
        seen_composition_ids.add(comp.id)

    return entries


async def load_searchable_pool(
    db: AsyncSession,
    organization_id: UUID,
) -> List[PoolEntry]:
    """Every entry the user *could* load: all enabled tools + production compositions.

    Used by `search` to score against, regardless of the current dynamic
    visibility flag (the user wants to discover anything in their account).
    """
    entries: List[PoolEntry] = []

    tool_stmt = (
        select(Tool, MCPServer)
        .join(MCPServer, Tool.server_id == MCPServer.id)
        .where(
            Tool.organization_id == organization_id,
            MCPServer.enabled.is_(True),
        )
    )
    for tool, server in (await db.execute(tool_stmt)).all():
        entries.append(_tool_to_entry(tool, server))

    comp_stmt = select(Composition).where(
        Composition.organization_id == organization_id,
        Composition.status == "production",
    )
    for (comp,) in (await db.execute(comp_stmt)).all():
        entries.append(_composition_to_entry(comp))

    return entries


def _output_hint(entry: PoolEntry) -> Dict[str, Any]:
    """Summarise a tool's OUTPUT format for the planner.

    The planner only ever saw input `parameters`, so it optimistically
    referenced structured paths (${step_N.datasets[*].id}) on tools that
    actually return one prose string — those references never resolve. We
    surface returns_schema so the planner knows when to bridge with a
    `transform` step.
    """
    if entry.kind != "tool" or entry.raw_tool is None:
        return {"format": "unknown"}
    rs = getattr(entry.raw_tool, "returns_schema", None)
    if isinstance(rs, dict) and isinstance(rs.get("properties"), dict) and rs["properties"]:
        props = rs["properties"]
        # FastMCP str-return signature: a single `result: string` property.
        if set(props.keys()) == {"result"} and props["result"].get("type") == "string":
            return {
                "format": "prose_text",
                "note": (
                    "Returns ONE unstructured text string at "
                    "${step_N.structuredContent.result}. Its fields are NOT "
                    "navigable. To use any value (id, name, …) from it in a later "
                    "step you MUST insert a `transform` step with source "
                    "${step_N.structuredContent.result}. Do NOT reference "
                    "${step_N.<field>} on this tool — it will not resolve."
                ),
            }
        return {"format": "structured", "schema": rs}
    return {"format": "unknown"}


def serialize_for_intent_analyzer(entry: PoolEntry) -> Dict[str, Any]:
    """Shape expected by IntentAnalyzer.analyze(available_tools=...)."""
    return {
        "id": entry.id,
        "name": entry.name,
        "description": entry.description,
        "parameters": entry.parameters_schema,
        "output": _output_hint(entry),
        "metadata": {
            "kind": entry.kind,
            "server_uuid": entry.server_id,
            "server_display_name": entry.server_name,
            "original_tool_name": entry.raw_tool.tool_name if entry.raw_tool else None,
        },
    }


def score_entry(query_tokens: List[str], entry: PoolEntry) -> int:
    """Naive textual relevance score over the unified entry shape."""
    if not query_tokens:
        return 0
    haystack = entry.haystack
    score = 0
    name_lower = entry.name.lower()
    for token in query_tokens:
        if not token:
            continue
        if token in name_lower:
            score += 2
        if token in haystack:
            score += 1
    return score
