"""
Pool management endpoints.

Web-facing wrappers around the dynamic-pool flag (`Tool.is_visible_to_oauth_clients`)
so the UI can clear or load the pool in bulk without N round-trips through
the per-tool visibility endpoint.

Reuses the same cache invalidation + SSE notification path used by the
legacy visibility toggle endpoint.
"""

import asyncio
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_async_session
from ...models.mcp_server import MCPServer
from ...models.tool import Tool
from ...models.user import User
from ..dependencies import get_current_user_jwt, get_current_organization_jwt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pool", tags=["Pool"])


class PoolStateResponse(BaseModel):
    pool_size: int = Field(..., description="Number of tools currently in the pool")
    composition_count: int = Field(..., description="Production compositions in the org (always available)")


class PoolLoadRequest(BaseModel):
    tool_ids: List[UUID] = Field(..., min_length=1, max_length=200)
    mode: str = Field("append", pattern="^(append|replace)$")


class PoolLoadResponse(BaseModel):
    loaded_count: int
    pool_size: int
    mode: str


class PoolUnloadRequest(BaseModel):
    tool_ids: List[UUID] = Field(..., min_length=1, max_length=200)


class PoolUnloadResponse(BaseModel):
    unloaded_count: int
    pool_size: int


class PoolSuggestRequest(BaseModel):
    goal: str = Field(..., min_length=4, max_length=2000)
    limit: int = Field(8, ge=1, le=20)


class PoolSuggestionItem(BaseModel):
    tool_id: str
    name: str
    server: Optional[str] = None
    description: str
    score: int
    in_pool: bool


class PoolSuggestResponse(BaseModel):
    goal: str
    suggestions: List[PoolSuggestionItem]
    note: Optional[str] = None


class ToolboxLoadResponse(BaseModel):
    tool_group_id: str
    loaded_count: int
    pool_size: int


async def _invalidate_and_notify(org_uuid: UUID, user_uuid: UUID) -> None:
    try:
        from ...services.organization_tool_cache import tool_cache

        await tool_cache.invalidate_organization(org_uuid)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"pool: org tool_cache invalidation failed: {e}")
    try:
        from ...services.user_tool_cache import get_user_tool_cache

        await get_user_tool_cache().invalidate_organization(org_uuid)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"pool: user_tool_cache invalidation failed: {e}")
    try:
        from ...routers.mcp_unified import notify_org_tools_changed

        asyncio.create_task(notify_org_tools_changed(org_uuid, user_id=user_uuid))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"pool: notification scheduling failed: {e}")


async def _pool_size(db: AsyncSession, org_uuid: UUID) -> int:
    stmt = select(Tool.id).where(
        Tool.organization_id == org_uuid,
        Tool.is_visible_to_oauth_clients.is_(True),
    )
    return len((await db.execute(stmt)).all())


@router.get("/state", response_model=PoolStateResponse)
async def get_pool_state(
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    db: AsyncSession = Depends(get_async_session),
):
    """Return the current pool size for the org plus production composition count."""
    _membership, org_id = org_context
    pool_size = await _pool_size(db, org_id)

    from ...models.composition import Composition

    comp_stmt = select(Composition.id).where(
        Composition.organization_id == org_id,
        Composition.status == "production",
    )
    composition_count = len((await db.execute(comp_stmt)).all())

    return PoolStateResponse(pool_size=pool_size, composition_count=composition_count)


@router.post("/clear", response_model=PoolStateResponse)
async def clear_pool(
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    db: AsyncSession = Depends(get_async_session),
):
    """Empty the dynamic pool for the user's organization."""
    _membership, org_id = org_context

    await db.execute(
        update(Tool)
        .where(
            Tool.organization_id == org_id,
            Tool.is_visible_to_oauth_clients.is_(True),
        )
        .values(is_visible_to_oauth_clients=False)
    )
    await db.commit()
    await _invalidate_and_notify(org_id, user.id)

    return PoolStateResponse(pool_size=0, composition_count=await _composition_count(db, org_id))


@router.post("/load", response_model=PoolLoadResponse)
async def load_pool(
    payload: PoolLoadRequest,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    db: AsyncSession = Depends(get_async_session),
):
    """Load a set of tools into the pool. Mode `append` adds, `replace` resets first.

    Tool IDs not belonging to the user's organization are silently filtered out.
    """
    _membership, org_id = org_context

    # Filter input to tools owned by the org (defence in depth).
    own_stmt = select(Tool.id, Tool.server_id).where(
        Tool.organization_id == org_id,
        Tool.id.in_(payload.tool_ids),
    )
    rows = (await db.execute(own_stmt)).all()
    owned_ids = {r[0] for r in rows}
    server_ids = {r[1] for r in rows}

    if not owned_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching tool found in your organization",
        )

    if payload.mode == "replace":
        await db.execute(
            update(Tool)
            .where(
                Tool.organization_id == org_id,
                Tool.is_visible_to_oauth_clients.is_(True),
            )
            .values(is_visible_to_oauth_clients=False)
        )

    await db.execute(
        update(Tool)
        .where(Tool.id.in_(owned_ids))
        .values(is_visible_to_oauth_clients=True)
    )
    if server_ids:
        await db.execute(
            update(MCPServer)
            .where(
                # Defence-in-depth: scope the bulk update to the caller's org
                # even though server_ids was derived from an org-scoped query.
                MCPServer.organization_id == org_id,
                MCPServer.id.in_(server_ids),
                MCPServer.is_visible_to_oauth_clients.is_(False),
            )
            .values(is_visible_to_oauth_clients=True)
        )
    await db.commit()
    await _invalidate_and_notify(org_id, user.id)

    return PoolLoadResponse(
        loaded_count=len(owned_ids),
        pool_size=await _pool_size(db, org_id),
        mode=payload.mode,
    )


async def _composition_count(db: AsyncSession, org_uuid: UUID) -> int:
    from ...models.composition import Composition

    stmt = select(Composition.id).where(
        Composition.organization_id == org_uuid,
        Composition.status == "production",
    )
    return len((await db.execute(stmt)).all())


@router.post("/unload", response_model=PoolUnloadResponse)
async def unload_pool(
    payload: PoolUnloadRequest,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    db: AsyncSession = Depends(get_async_session),
):
    """Remove a set of tools from the active pool (bulk)."""
    _membership, org_id = org_context

    own_stmt = select(Tool.id).where(
        Tool.organization_id == org_id,
        Tool.id.in_(payload.tool_ids),
    )
    rows = (await db.execute(own_stmt)).all()
    owned_ids = {r[0] for r in rows}

    if not owned_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching tool found in your organization",
        )

    await db.execute(
        update(Tool)
        .where(Tool.id.in_(owned_ids))
        .values(is_visible_to_oauth_clients=False)
    )
    await db.commit()
    await _invalidate_and_notify(org_id, user.id)

    return PoolUnloadResponse(
        unloaded_count=len(owned_ids),
        pool_size=await _pool_size(db, org_id),
    )


@router.post("/suggest", response_model=PoolSuggestResponse)
async def suggest_for_goal(
    payload: PoolSuggestRequest,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    db: AsyncSession = Depends(get_async_session),
):
    """Ask the LLM to suggest tools to load for a given NL goal.

    Reuses the same scoring engine the `search` MCP tool uses (textual match
    over the org's enabled tools), then enriches the result with whether each
    candidate is already in the pool. Lighter than the IntentAnalyzer (no
    plan generation), aimed at the workspace assistant.
    """
    _membership, org_id = org_context

    # Load every tool from enabled servers — same scope as the `search` tool.
    from ...routers.mcp_gateway.pool.pool_loader import (
        load_searchable_pool,
        score_entry,
    )
    from ...routers.mcp_gateway.pool.search_handler import _tokenize

    candidates = await load_searchable_pool(db, org_id)
    if not candidates:
        return PoolSuggestResponse(
            goal=payload.goal,
            suggestions=[],
            note="No enabled servers in your organization yet.",
        )

    tokens = _tokenize(payload.goal)
    scored = []
    for entry in candidates:
        s = score_entry(tokens, entry)
        if s > 0:
            scored.append((s, entry))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = scored[: payload.limit]

    # Tools currently in pool (so the UI can pre-flag them).
    pool_stmt = select(Tool.id).where(
        Tool.organization_id == org_id,
        Tool.is_visible_to_oauth_clients.is_(True),
    )
    in_pool_ids = {str(r[0]) for r in (await db.execute(pool_stmt)).all()}

    suggestions = [
        PoolSuggestionItem(
            tool_id=e.id,
            name=e.name,
            server=e.server_name,
            description=(e.description or "")[:200],
            score=s,
            in_pool=(e.id in in_pool_ids),
        )
        for s, e in top
    ]

    return PoolSuggestResponse(
        goal=payload.goal,
        suggestions=suggestions,
        note=None if suggestions else "No tool matched. Try a broader description.",
    )


@router.post("/tool-groups/{tool_group_id}/load-into-pool", response_model=ToolboxLoadResponse)
async def load_toolbox_into_pool(
    tool_group_id: UUID,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    db: AsyncSession = Depends(get_async_session),
):
    """Load every tool of a toolbox (ToolGroup) into the active pool."""
    _membership, org_id = org_context

    from ...models.tool_group import ToolGroup, ToolGroupItem

    # Verify ownership.
    group_stmt = select(ToolGroup).where(
        ToolGroup.id == tool_group_id,
        ToolGroup.organization_id == org_id,
    )
    group = (await db.execute(group_stmt)).scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Toolbox not found")

    item_stmt = select(ToolGroupItem.tool_id).where(
        ToolGroupItem.tool_group_id == tool_group_id,
        ToolGroupItem.tool_id.isnot(None),
    )
    tool_ids = [r[0] for r in (await db.execute(item_stmt)).all() if r[0] is not None]
    if not tool_ids:
        return ToolboxLoadResponse(
            tool_group_id=str(tool_group_id),
            loaded_count=0,
            pool_size=await _pool_size(db, org_id),
        )

    # Filter to tools still owned by the org (defence in depth).
    own_stmt = select(Tool.id, Tool.server_id).where(
        Tool.organization_id == org_id,
        Tool.id.in_(tool_ids),
    )
    rows = (await db.execute(own_stmt)).all()
    owned_ids = {r[0] for r in rows}
    server_ids = {r[1] for r in rows}

    if owned_ids:
        await db.execute(
            update(Tool)
            .where(Tool.id.in_(owned_ids))
            .values(is_visible_to_oauth_clients=True)
        )
        if server_ids:
            await db.execute(
                update(MCPServer)
                .where(
                    # Defence-in-depth: scope the bulk update to the caller's org.
                    MCPServer.organization_id == org_id,
                    MCPServer.id.in_(server_ids),
                    MCPServer.is_visible_to_oauth_clients.is_(False),
                )
                .values(is_visible_to_oauth_clients=True)
            )
        await db.commit()
        await _invalidate_and_notify(org_id, user.id)

    return ToolboxLoadResponse(
        tool_group_id=str(tool_group_id),
        loaded_count=len(owned_ids),
        pool_size=await _pool_size(db, org_id),
    )
