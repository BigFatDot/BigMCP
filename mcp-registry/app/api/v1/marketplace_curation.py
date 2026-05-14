"""
Org-scoped marketplace curation endpoints (Phase 2).

The marketplace catalog (~184 servers from npm/GitHub/curated) is global
to the BigMCP codebase. Each org wants its own view: hide consumer
servers that don't fit a public-sector deployment, feature in-house ones
at the top of the catalog, etc. This module exposes the admin CRUD on
top of the ``OrgMarketplaceCuration`` table.

Surface
-------
- ``GET  /admin/org/marketplace-curation`` — return the org's curation
  rules + a count of approved/featured/hidden + the global catalog
  size. The curation grid in the frontend joins this with the global
  ``GET /marketplace/servers?limit=200`` response on its own.
- ``PUT  /admin/org/marketplace-curation`` — batch upsert. Body is a
  list of ``{server_id, status, featured_order, notes}`` items. Each
  row is upserted; ``status="approved"`` (default) clears any prior
  ``hidden`` decision; passing ``status=null`` removes the row entirely
  (back to default = visible).

All endpoints require instance-admin (no org-admin role yet — to add
when the org-vs-instance role split lands).
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...db.database import get_db
from ...models.audit_log import AuditAction
from ...models.org_marketplace_curation import (
    OrgMarketplaceCuration,
    OrgMarketplaceCurationStatus,
)
from ...models.organization import OrganizationMember
from ...models.user import User
from ...services.audit_service import AuditService
from ..dependencies import require_instance_admin


router = APIRouter(
    prefix="/admin/org/marketplace-curation",
    tags=["Marketplace Curation"],
)


VALID_STATUSES = {s.value for s in OrgMarketplaceCurationStatus}


class CurationRuleResponse(BaseModel):
    server_id: str
    status: str
    featured_order: Optional[int] = None
    notes: Optional[str] = None
    curated_by_user_id: Optional[UUID] = None
    updated_at: datetime


class CurationListResponse(BaseModel):
    organization_id: UUID
    rules: List[CurationRuleResponse]
    counts: dict  # {approved: int, featured: int, hidden: int}


class CurationUpdateItem(BaseModel):
    server_id: str = Field(..., min_length=1, max_length=255)
    # status=None removes any existing rule (back to default visible).
    status: Optional[str] = None
    featured_order: Optional[int] = None
    notes: Optional[str] = None


class CurationBatchUpdate(BaseModel):
    items: List[CurationUpdateItem] = Field(..., min_length=1)


def _resolve_org_id(user: User) -> UUID:
    """Pick the deterministic org for the admin (oldest membership)."""
    if not user.organization_memberships:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin user has no organization membership.",
        )
    return sorted(
        user.organization_memberships,
        key=lambda m: m.created_at,
    )[0].organization_id


@router.get("", response_model=CurationListResponse)
async def list_curation_rules(
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_db),
):
    org_id = _resolve_org_id(admin_user)

    rows = (
        await db.execute(
            select(OrgMarketplaceCuration)
            .where(OrgMarketplaceCuration.organization_id == org_id)
            .order_by(OrgMarketplaceCuration.marketplace_server_id)
        )
    ).scalars().all()

    counts = {"approved": 0, "featured": 0, "hidden": 0}
    rules: List[CurationRuleResponse] = []
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
        rules.append(
            CurationRuleResponse(
                server_id=r.marketplace_server_id,
                status=r.status,
                featured_order=r.featured_order,
                notes=r.notes,
                curated_by_user_id=r.curated_by_user_id,
                updated_at=r.updated_at,
            )
        )

    return CurationListResponse(
        organization_id=org_id, rules=rules, counts=counts
    )


@router.put("", response_model=CurationListResponse)
async def batch_upsert_curation(
    payload: CurationBatchUpdate,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_db),
):
    """Batch upsert curation rules for the admin's org.

    Each item:
    - ``status=null`` → remove the row (back to default = visible)
    - ``status="approved"|"featured"|"hidden"`` → upsert the row
    - ``status="featured"`` + ``featured_order`` → also set the sort hint
    """
    org_id = _resolve_org_id(admin_user)

    # Validate all statuses upfront so we don't half-apply
    for item in payload.items:
        if item.status is not None and item.status not in VALID_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid status '{item.status}' for {item.server_id!r}. "
                    f"Allowed: {sorted(VALID_STATUSES)} or null to remove."
                ),
            )

    audit_changes: list = []
    for item in payload.items:
        existing = (
            await db.execute(
                select(OrgMarketplaceCuration)
                .where(OrgMarketplaceCuration.organization_id == org_id)
                .where(
                    OrgMarketplaceCuration.marketplace_server_id == item.server_id
                )
            )
        ).scalar_one_or_none()

        if item.status is None:
            if existing is not None:
                await db.delete(existing)
                audit_changes.append(
                    {
                        "server_id": item.server_id,
                        "action": "removed",
                        "previous_status": existing.status,
                    }
                )
            continue

        if existing is None:
            row = OrgMarketplaceCuration(
                organization_id=org_id,
                marketplace_server_id=item.server_id,
                status=item.status,
                featured_order=item.featured_order,
                notes=item.notes,
                curated_by_user_id=admin_user.id,
            )
            db.add(row)
            audit_changes.append(
                {
                    "server_id": item.server_id,
                    "action": "created",
                    "status": item.status,
                    "featured_order": item.featured_order,
                }
            )
        else:
            previous = {
                "status": existing.status,
                "featured_order": existing.featured_order,
                "notes": existing.notes,
            }
            existing.status = item.status
            existing.featured_order = item.featured_order
            existing.notes = item.notes
            existing.curated_by_user_id = admin_user.id
            audit_changes.append(
                {
                    "server_id": item.server_id,
                    "action": "updated",
                    "from": previous,
                    "to": {
                        "status": item.status,
                        "featured_order": item.featured_order,
                        "notes": item.notes,
                    },
                }
            )

    await db.commit()

    if audit_changes:
        try:
            await AuditService(db).log_action(
                action=AuditAction.POLICY_CHANGED,
                actor_id=admin_user.id,
                organization_id=org_id,
                resource_type="org_marketplace_curation",
                resource_id=str(org_id),
                details={
                    "changes_count": len(audit_changes),
                    "changes": audit_changes[:50],  # cap to avoid log bloat
                },
            )
        except Exception:
            pass

    # Return the fresh state so the frontend can refresh without a 2nd hop
    return await list_curation_rules(admin_user=admin_user, db=db)
