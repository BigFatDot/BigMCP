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
