"""
Persistent pool endpoints (Phase 3).

Two surfaces:

- ``/admin/org/default-pool`` (instance admin) — manages the org's
  default pool. Every user of the org inherits these entries at MCP
  connect time, so first-time agents face a populated catalog instead
  of an empty pool.

- ``/pool/pin`` (any authenticated user) — manages the user's personal
  pinned entries. Pins survive across sessions and supplement the org
  default pool.

Both surfaces emit ``tools/list_changed`` notifications to active SSE
sessions of the affected user(s) so MCP clients refresh on the spot.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_db
from ...models.audit_log import AuditAction
from ...models.composition import Composition
from ...models.pool_persistent import (
    OrgDefaultPoolEntry,
    UserPersistentPoolEntry,
)
from ...models.tool import Tool
from ...services.audit_service import AuditService
from ..rbac import AuthContext, require_admin, require_viewer


router = APIRouter(tags=["Persistent Pool"])


# ---------------------------------------------------------------------------
# Common payloads
# ---------------------------------------------------------------------------


class PoolEntryRef(BaseModel):
    """A reference to either a tool or a composition."""
    tool_id: Optional[UUID] = None
    composition_id: Optional[UUID] = None

    def validate_xor(self) -> None:
        if (self.tool_id is None) == (self.composition_id is None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Exactly one of tool_id or composition_id is required.",
            )


class OrgDefaultPoolEntryResponse(BaseModel):
    id: UUID
    tool_id: Optional[UUID]
    composition_id: Optional[UUID]
    position: int
    added_by_user_id: Optional[UUID]
    updated_at: datetime


class OrgDefaultPoolListResponse(BaseModel):
    organization_id: UUID
    entries: List[OrgDefaultPoolEntryResponse]


class UserPinResponse(BaseModel):
    id: UUID
    tool_id: Optional[UUID]
    composition_id: Optional[UUID]
    last_used_at: Optional[datetime]
    created_at: datetime


class UserPinListResponse(BaseModel):
    user_id: UUID
    pins: List[UserPinResponse]


async def _validate_entry_belongs_to_org(
    db: AsyncSession,
    org_id: UUID,
    tool_id: Optional[UUID],
    composition_id: Optional[UUID],
) -> None:
    """Refuse cross-org references — pool entries must belong to the org."""
    if tool_id is not None:
        owner = (
            await db.execute(
                select(Tool.organization_id).where(Tool.id == tool_id)
            )
        ).scalar_one_or_none()
        if owner is None:
            raise HTTPException(404, f"Tool {tool_id} not found")
        if owner != org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tool belongs to a different organization.",
            )
    if composition_id is not None:
        owner = (
            await db.execute(
                select(Composition.organization_id).where(
                    Composition.id == composition_id
                )
            )
        ).scalar_one_or_none()
        if owner is None:
            raise HTTPException(404, f"Composition {composition_id} not found")
        if owner != org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Composition belongs to a different organization.",
            )


async def _notify_org_tools_changed(organization_id: UUID) -> None:
    """Best-effort tools/list_changed broadcast to the org's MCP sessions."""
    try:
        from ...routers.mcp_unified import notify_org_tools_changed
        await notify_org_tools_changed(str(organization_id))
    except Exception:
        # Notification is fire-and-forget — never block the API on it.
        pass


async def _notify_user_tools_changed(user_id: UUID) -> None:
    try:
        from ...routers.mcp_unified import broadcast_tools_changed_for_user
        await broadcast_tools_changed_for_user(str(user_id))
    except Exception:
        pass


# ===========================================================================
# /admin/org/default-pool — team admin (ADMIN+OWNER) or instance admin
# ===========================================================================

admin_router = APIRouter(
    prefix="/admin/org/default-pool", tags=["Default Pool Admin"]
)


@admin_router.get("", response_model=OrgDefaultPoolListResponse)
async def list_default_pool(
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    org_id = auth.organization_id
    rows = (
        await db.execute(
            select(OrgDefaultPoolEntry)
            .where(OrgDefaultPoolEntry.organization_id == org_id)
            .order_by(OrgDefaultPoolEntry.position.asc())
        )
    ).scalars().all()
    return OrgDefaultPoolListResponse(
        organization_id=org_id,
        entries=[
            OrgDefaultPoolEntryResponse(
                id=r.id,
                tool_id=r.tool_id,
                composition_id=r.composition_id,
                position=r.position,
                added_by_user_id=r.added_by_user_id,
                updated_at=r.updated_at,
            )
            for r in rows
        ],
    )


class DefaultPoolAddRequest(PoolEntryRef):
    position: Optional[int] = None


@admin_router.post(
    "",
    response_model=OrgDefaultPoolEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_default_pool_entry(
    payload: DefaultPoolAddRequest,
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    payload.validate_xor()
    org_id = auth.organization_id
    admin_user = auth.user
    await _validate_entry_belongs_to_org(
        db, org_id, payload.tool_id, payload.composition_id
    )

    # Position auto-incremented to the end of the list when not given.
    if payload.position is None:
        max_pos = (
            await db.execute(
                select(OrgDefaultPoolEntry.position)
                .where(OrgDefaultPoolEntry.organization_id == org_id)
                .order_by(OrgDefaultPoolEntry.position.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        payload.position = (max_pos or 0) + 1

    # Same explicit duplicate check as user pins — NULL columns defeat
    # the unique constraint on some backends.
    dup_q = select(OrgDefaultPoolEntry).where(
        OrgDefaultPoolEntry.organization_id == org_id
    )
    if payload.tool_id is not None:
        dup_q = dup_q.where(OrgDefaultPoolEntry.tool_id == payload.tool_id)
    else:
        dup_q = dup_q.where(
            OrgDefaultPoolEntry.composition_id == payload.composition_id
        )
    if (await db.execute(dup_q)).scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This entry is already in the org default pool.",
        )

    row = OrgDefaultPoolEntry(
        organization_id=org_id,
        tool_id=payload.tool_id,
        composition_id=payload.composition_id,
        position=payload.position,
        added_by_user_id=admin_user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    try:
        await AuditService(db).log_action(
            action=AuditAction.POLICY_CHANGED,
            actor_id=admin_user.id,
            organization_id=org_id,
            resource_type="org_default_pool",
            resource_id=str(row.id),
            details={
                "operation": "add",
                "tool_id": str(payload.tool_id) if payload.tool_id else None,
                "composition_id": (
                    str(payload.composition_id) if payload.composition_id else None
                ),
                "position": payload.position,
            },
        )
    except Exception:
        pass

    await _notify_org_tools_changed(org_id)

    return OrgDefaultPoolEntryResponse(
        id=row.id,
        tool_id=row.tool_id,
        composition_id=row.composition_id,
        position=row.position,
        added_by_user_id=row.added_by_user_id,
        updated_at=row.updated_at,
    )


@admin_router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_default_pool_entry(
    entry_id: UUID,
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    org_id = auth.organization_id
    admin_user = auth.user
    row = (
        await db.execute(
            select(OrgDefaultPoolEntry).where(
                OrgDefaultPoolEntry.id == entry_id,
                OrgDefaultPoolEntry.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Entry not found in this org's default pool")
    detail = {
        "operation": "remove",
        "tool_id": str(row.tool_id) if row.tool_id else None,
        "composition_id": str(row.composition_id) if row.composition_id else None,
    }
    await db.delete(row)
    await db.commit()

    try:
        await AuditService(db).log_action(
            action=AuditAction.POLICY_CHANGED,
            actor_id=admin_user.id,
            organization_id=org_id,
            resource_type="org_default_pool",
            resource_id=str(entry_id),
            details=detail,
        )
    except Exception:
        pass

    await _notify_org_tools_changed(org_id)
    return None


# ===========================================================================
# /pool/pin — any authenticated user
# ===========================================================================

user_router = APIRouter(prefix="/pool/pin", tags=["User Pool Pins"])


@user_router.get("", response_model=UserPinListResponse)
async def list_user_pins(
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    user = auth.user
    rows = (
        await db.execute(
            select(UserPersistentPoolEntry)
            .where(UserPersistentPoolEntry.user_id == user.id)
            .order_by(UserPersistentPoolEntry.created_at.desc())
        )
    ).scalars().all()
    return UserPinListResponse(
        user_id=user.id,
        pins=[
            UserPinResponse(
                id=r.id,
                tool_id=r.tool_id,
                composition_id=r.composition_id,
                last_used_at=r.last_used_at,
                created_at=r.created_at,
            )
            for r in rows
        ],
    )


@user_router.post(
    "", response_model=UserPinResponse, status_code=status.HTTP_201_CREATED
)
async def pin_entry(
    payload: PoolEntryRef,
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    payload.validate_xor()
    user = auth.user
    org_id = auth.organization_id
    await _validate_entry_belongs_to_org(
        db, org_id, payload.tool_id, payload.composition_id
    )

    # The (user_id, tool_id, composition_id) unique constraint gets defeated
    # by NULLs in some databases (NULLs are treated as distinct). Check
    # explicitly so duplicate pins always return 409 regardless of backend.
    dup_q = select(UserPersistentPoolEntry).where(
        UserPersistentPoolEntry.user_id == user.id
    )
    if payload.tool_id is not None:
        dup_q = dup_q.where(UserPersistentPoolEntry.tool_id == payload.tool_id)
    else:
        dup_q = dup_q.where(
            UserPersistentPoolEntry.composition_id == payload.composition_id
        )
    if (await db.execute(dup_q)).scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This entry is already pinned.",
        )

    row = UserPersistentPoolEntry(
        user_id=user.id,
        tool_id=payload.tool_id,
        composition_id=payload.composition_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    await _notify_user_tools_changed(user.id)

    return UserPinResponse(
        id=row.id,
        tool_id=row.tool_id,
        composition_id=row.composition_id,
        last_used_at=row.last_used_at,
        created_at=row.created_at,
    )


@user_router.delete("/{pin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unpin_entry(
    pin_id: UUID,
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    user = auth.user
    row = (
        await db.execute(
            select(UserPersistentPoolEntry).where(
                UserPersistentPoolEntry.id == pin_id,
                UserPersistentPoolEntry.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Pin not found")
    await db.delete(row)
    await db.commit()

    await _notify_user_tools_changed(user.id)
    return None


# ===========================================================================
# /pool/pin/suggestions — Phase 5 usage-driven recommendations
# ===========================================================================


class PinSuggestion(BaseModel):
    """One pin recommendation for the caller."""
    kind: str  # "tool" | "composition"
    tool_id: Optional[UUID] = None
    composition_id: Optional[UUID] = None
    name: str
    server_name: Optional[str] = None
    description: Optional[str] = None
    count: int
    last_used_at: datetime
    days: int  # The lookback window the suggestion was computed over


class PinSuggestionsResponse(BaseModel):
    user_id: UUID
    days: int
    suggestions: List[PinSuggestion]


@user_router.get("/suggestions", response_model=PinSuggestionsResponse)
async def list_pin_suggestions(
    days: int = 7,
    limit: int = 10,
    min_count: int = 3,
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    """Return tools/compositions the user invoked at least ``min_count``
    times over the last ``days`` days but has not pinned yet.

    Already-pinned and already-in-org-default entries are filtered out:
    the user has no value in pinning what is already permanently visible
    in their pool.
    """
    user = auth.user
    org_id = auth.organization_id

    from ...services.usage_analytics import (
        top_tools_for_user,
        top_compositions_for_user,
        resolve_tool_names_to_ids,
    )
    from ...models.composition import Composition
    from ...models.mcp_server import MCPServer
    from ...models.tool import Tool

    # Already-permanent ids the user does not need suggested back at them.
    pin_rows = (
        await db.execute(
            select(UserPersistentPoolEntry).where(
                UserPersistentPoolEntry.user_id == user.id
            )
        )
    ).scalars().all()
    pinned_tool_ids = {r.tool_id for r in pin_rows if r.tool_id}
    pinned_comp_ids = {r.composition_id for r in pin_rows if r.composition_id}

    default_rows = (
        await db.execute(
            select(OrgDefaultPoolEntry).where(
                OrgDefaultPoolEntry.organization_id == org_id
            )
        )
    ).scalars().all()
    default_tool_ids = {r.tool_id for r in default_rows if r.tool_id}
    default_comp_ids = {r.composition_id for r in default_rows if r.composition_id}

    excluded_tool_ids = pinned_tool_ids | default_tool_ids
    excluded_comp_ids = pinned_comp_ids | default_comp_ids

    # Tools — pull a generous window (limit*3) so we have something left
    # to surface after filtering already-pinned entries.
    tool_usage = await top_tools_for_user(
        db,
        user_id=user.id,
        organization_id=org_id,
        days=days,
        limit=limit * 3,
    )
    tool_usage = [u for u in tool_usage if u.count >= min_count]
    resolved = await resolve_tool_names_to_ids(
        db,
        organization_id=org_id,
        prefixed_names=[u.tool_name for u in tool_usage],
    )
    name_to_id = {name: tid for name, tid in resolved}

    suggestions: List[PinSuggestion] = []
    for u in tool_usage:
        tid = name_to_id.get(u.tool_name)
        if not tid or tid in excluded_tool_ids:
            continue
        # Resolve display fields lazily — we already joined once, but
        # simpler to do a second small lookup.
        meta = (
            await db.execute(
                select(Tool, MCPServer)
                .join(MCPServer, Tool.server_id == MCPServer.id)
                .where(Tool.id == tid)
            )
        ).first()
        if not meta:
            continue
        tool, server = meta
        suggestions.append(
            PinSuggestion(
                kind="tool",
                tool_id=tid,
                name=tool.display_name or tool.tool_name,
                server_name=server.name,
                description=tool.description,
                count=u.count,
                last_used_at=u.last_used_at,
                days=days,
            )
        )

    # Compositions — same story, the caller likely cares about both.
    comp_usage = await top_compositions_for_user(
        db,
        user_id=user.id,
        organization_id=org_id,
        days=days,
        limit=limit * 3,
    )
    comp_usage = [u for u in comp_usage if u.count >= min_count]
    if comp_usage:
        comps = (
            await db.execute(
                select(Composition).where(
                    Composition.id.in_([u.composition_id for u in comp_usage]),
                    Composition.organization_id == org_id,
                )
            )
        ).scalars().all()
        comp_by_id = {c.id: c for c in comps}
        for u in comp_usage:
            if u.composition_id in excluded_comp_ids:
                continue
            comp = comp_by_id.get(u.composition_id)
            if not comp:
                continue
            suggestions.append(
                PinSuggestion(
                    kind="composition",
                    composition_id=comp.id,
                    name=comp.name,
                    description=comp.description,
                    count=u.count,
                    last_used_at=u.last_used_at,
                    days=days,
                )
            )

    # Highest count first, then most recently used. Cap to the requested
    # limit AFTER both kinds have been gathered.
    suggestions.sort(key=lambda s: (-s.count, -s.last_used_at.timestamp()))
    suggestions = suggestions[:limit]

    return PinSuggestionsResponse(
        user_id=user.id, days=days, suggestions=suggestions
    )
