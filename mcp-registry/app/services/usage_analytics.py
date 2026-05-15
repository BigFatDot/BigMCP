"""Usage analytics over ``execution_log`` (Phase 5).

Two consumers:

- The pin-suggestions endpoint surfaces frequently-used tools and
  compositions a user has not yet pinned, so they can promote them to
  their persistent pool with one click.
- The MCP ``tools/list`` preheat overlay quietly injects the user's top-N
  tools from the past 30 days into the visible pool at connect time, so
  an agent reconnecting after a context reset doesn't have to re-run
  ``search`` for items it already uses every day.

Backend portability
-------------------
``ExecutionLog.tools_called`` is a JSON array on every backend (we use a
custom ``ArrayType`` mapped to ``ARRAY(String)`` on PostgreSQL and
``JSON`` on SQLite). To keep the implementation backend-agnostic we
fetch the recent rows and aggregate in Python rather than ``UNNEST``.
The rows are bounded (``LIMIT 5000`` over the lookback window) so the
cost stays small in practice.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.execution_log import ExecutionLog


@dataclass(frozen=True)
class ToolUsage:
    tool_name: str  # The MCP-prefixed name as logged by call_tool
    count: int
    last_used_at: datetime


@dataclass(frozen=True)
class CompositionUsage:
    composition_id: UUID
    count: int
    last_used_at: datetime


async def _recent_logs(
    db: AsyncSession,
    *,
    user_id: UUID,
    organization_id: UUID,
    days: int,
    row_cap: int = 5000,
) -> List[ExecutionLog]:
    cutoff = datetime.utcnow() - timedelta(days=max(1, days))
    stmt = (
        select(ExecutionLog)
        .where(
            ExecutionLog.user_id == user_id,
            ExecutionLog.organization_id == organization_id,
            ExecutionLog.created_at >= cutoff,
        )
        .order_by(ExecutionLog.created_at.desc())
        .limit(row_cap)
    )
    return list((await db.execute(stmt)).scalars().all())


async def top_tools_for_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    organization_id: UUID,
    days: int = 7,
    limit: int = 10,
) -> List[ToolUsage]:
    """Top tools (by raw call count) the user invoked over the window.

    Aggregates over rows where ``tools_called`` is non-empty. Composition
    pseudo-tools (``composition_*`` / ``workflow_*``) are excluded — they
    surface in :func:`top_compositions_for_user` instead.
    """
    rows = await _recent_logs(
        db, user_id=user_id, organization_id=organization_id, days=days
    )
    counts: Counter[str] = Counter()
    last_seen: dict[str, datetime] = {}
    for r in rows:
        if not r.tools_called:
            continue
        for name in r.tools_called:
            if not isinstance(name, str):
                continue
            if name.startswith("composition_") or name.startswith("workflow_"):
                continue
            counts[name] += 1
            ts = r.created_at
            if name not in last_seen or last_seen[name] < ts:
                last_seen[name] = ts
    return [
        ToolUsage(tool_name=name, count=cnt, last_used_at=last_seen[name])
        for name, cnt in counts.most_common(limit)
    ]


async def top_compositions_for_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    organization_id: UUID,
    days: int = 7,
    limit: int = 10,
) -> List[CompositionUsage]:
    """Top compositions the user invoked over the window."""
    rows = await _recent_logs(
        db, user_id=user_id, organization_id=organization_id, days=days
    )
    counts: Counter[UUID] = Counter()
    last_seen: dict[UUID, datetime] = {}
    for r in rows:
        if not r.composition_id:
            continue
        counts[r.composition_id] += 1
        if r.composition_id not in last_seen or last_seen[r.composition_id] < r.created_at:
            last_seen[r.composition_id] = r.created_at
    return [
        CompositionUsage(
            composition_id=cid,
            count=cnt,
            last_used_at=last_seen[cid],
        )
        for cid, cnt in counts.most_common(limit)
    ]


async def resolve_tool_names_to_ids(
    db: AsyncSession,
    *,
    organization_id: UUID,
    prefixed_names: List[str],
) -> List[Tuple[str, UUID]]:
    """Map ``ServerName__tool_name`` strings back to ``Tool.id`` UUIDs.

    Used by the suggestions endpoint and the preheat overlay to convert
    the names recorded in ``execution_log`` into pin-able tool IDs.
    Returns only entries that resolve unambiguously to a single tool
    currently visible in the org.
    """
    if not prefixed_names:
        return []

    from ..models.mcp_server import MCPServer
    from ..models.tool import Tool
    import re

    rows = (
        await db.execute(
            select(Tool, MCPServer)
            .join(MCPServer, Tool.server_id == MCPServer.id)
            .where(
                Tool.organization_id == organization_id,
                MCPServer.enabled.is_(True),
            )
        )
    ).all()

    def _safe(text: Optional[str]) -> str:
        s = re.sub(r"[^a-zA-Z0-9_]", "_", text or "")
        return re.sub(r"_+", "_", s).strip("_")

    by_prefixed: dict[str, UUID] = {}
    for tool, server in rows:
        prefix = _safe(server.name or "")
        prefixed = f"{prefix}__{tool.tool_name}" if prefix else tool.tool_name
        by_prefixed[prefixed] = tool.id

    out: List[Tuple[str, UUID]] = []
    for name in prefixed_names:
        if name in by_prefixed:
            out.append((name, by_prefixed[name]))
    return out
