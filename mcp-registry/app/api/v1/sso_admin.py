"""
SSO admin endpoints (Story I.1).

CRUD on ``OIDCProvider`` and ``OIDCGroupMapping``, plus the
``force-SSO-only`` instance setting toggle. Guarded by the existing
``require_instance_admin`` dependency.

All write paths emit audit events. The two protective checks live here:

- Saving an OIDCProvider with ``reject_unmapped_users=true`` AND
  zero mappings AND no ``fallback_organization_id`` is a guaranteed
  lockout — refused with 400 + clear remediation hint.
- Enabling instance-wide ``force_sso_only`` requires that at least one
  active instance-admin still has a local password — otherwise the
  admin would lock themselves out instantly.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...core.oidc_presets import PRESETS
from ...db.database import get_db
from ...models.audit_log import AuditAction
from ...models.instance_settings import InstanceSettings
from ...models.oidc import OIDCGroupMapping, OIDCProvider
from ...models.user import User, UserStatus
from ...services.audit_service import AuditService
from ...services.oidc_service import OIDCDiscovery
from ..dependencies import require_instance_admin


router = APIRouter(prefix="/admin/sso", tags=["SSO Admin"])


# ---------------------------------------------------------------------------
# Presets (Story I.2) — pre-filled config templates per IdP vendor
# ---------------------------------------------------------------------------


@router.get("/presets")
async def list_presets(
    admin_user: User = Depends(require_instance_admin),
):
    """Return the static OIDC preset catalog.

    The frontend uses these to populate "Configure {Vendor}" buttons
    that pre-fill the new-provider form. No secrets — only config
    templates that the admin still has to complete with their tenant
    client_id / client_secret.
    """
    return {"presets": PRESETS}


@router.get("/organizations")
async def list_all_organizations(
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return every team/org in the instance for the SSO config picker.

    The classic /api/v1/organizations only lists orgs the caller is a
    member of, which is wrong for instance-admin SSO config (they need
    to assign a fallback / mapping to a team they may not belong to).
    """
    from ...models.organization import Organization
    rows = await db.execute(select(Organization).order_by(Organization.name))
    return {
        "organizations": [
            {"id": str(o.id), "name": o.name, "slug": o.slug}
            for o in rows.scalars().all()
        ]
    }


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class OIDCProviderCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    display_label: str = Field(..., min_length=2, max_length=100)
    issuer_url: str = Field(..., min_length=8, max_length=500)
    client_id: str = Field(..., min_length=1, max_length=255)
    client_secret: str = Field(..., min_length=1, max_length=2048)
    scopes: List[str] = Field(default_factory=lambda: ["openid", "profile", "email"])
    groups_claim_path: Optional[str] = "groups"
    email_claim_path: str = "email"
    name_claim_path: str = "name"
    auto_link_by_verified_email: bool = False
    require_email_verified: bool = True
    reject_unmapped_users: bool = True
    fallback_organization_id: Optional[UUID] = None
    fallback_role: str = "member"
    is_active: bool = True
    manual_endpoints_json: Optional[dict] = None


class OIDCProviderUpdate(BaseModel):
    display_label: Optional[str] = None
    issuer_url: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None  # only re-set if non-null
    scopes: Optional[List[str]] = None
    groups_claim_path: Optional[str] = None
    email_claim_path: Optional[str] = None
    name_claim_path: Optional[str] = None
    auto_link_by_verified_email: Optional[bool] = None
    require_email_verified: Optional[bool] = None
    reject_unmapped_users: Optional[bool] = None
    fallback_organization_id: Optional[UUID] = None
    fallback_role: Optional[str] = None
    is_active: Optional[bool] = None
    manual_endpoints_json: Optional[dict] = None


class OIDCProviderResponse(BaseModel):
    id: UUID
    name: str
    display_label: str
    issuer_url: str
    client_id: str
    scopes: list
    groups_claim_path: Optional[str]
    email_claim_path: str
    name_claim_path: str
    auto_link_by_verified_email: bool
    require_email_verified: bool
    reject_unmapped_users: bool
    fallback_organization_id: Optional[UUID]
    fallback_role: str
    is_active: bool
    manual_endpoints_json: Optional[dict]
    created_at: datetime
    updated_at: datetime
    mapping_count: int


class OIDCGroupMappingCreate(BaseModel):
    idp_group_name: str = Field(..., min_length=1, max_length=255)
    organization_id: Optional[UUID] = None
    role: Optional[str] = None
    grants_instance_admin: bool = False


class OIDCGroupMappingResponse(BaseModel):
    id: UUID
    provider_id: UUID
    idp_group_name: str
    organization_id: Optional[UUID]
    role: Optional[str]
    grants_instance_admin: bool


class ForceSSOOnlyToggle(BaseModel):
    enabled: bool
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def _validate_provisioning_safety(
    *,
    reject_unmapped_users: bool,
    fallback_organization_id: Optional[UUID],
    mapping_count: int,
) -> None:
    """Refuse a config that would deterministically lock everyone out."""
    if reject_unmapped_users and fallback_organization_id is None and mapping_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This configuration would lock out every user "
                "(reject_unmapped_users=true with no group mappings "
                "and no fallback organization). Add at least one "
                "GroupMapping or set fallback_organization_id."
            ),
        )


async def _count_mappings(db: AsyncSession, provider_id: UUID) -> int:
    res = await db.execute(
        select(func.count(OIDCGroupMapping.id)).where(
            OIDCGroupMapping.provider_id == provider_id
        )
    )
    return int(res.scalar() or 0)


async def _has_local_admin(db: AsyncSession) -> bool:
    """True if any active instance-admin still has a usable local password."""
    res = await db.execute(
        select(User).where(
            User.password_hash.is_not(None),
            User.status == UserStatus.ACTIVE.value,
        )
    )
    for u in res.scalars().all():
        if (u.preferences or {}).get("instance_admin"):
            return True
    return False


# ---------------------------------------------------------------------------
# Provider CRUD
# ---------------------------------------------------------------------------


def _provider_to_response(p: OIDCProvider, mapping_count: int) -> OIDCProviderResponse:
    return OIDCProviderResponse(
        id=p.id,
        name=p.name,
        display_label=p.display_label,
        issuer_url=p.issuer_url,
        client_id=p.client_id,
        scopes=p.scopes or [],
        groups_claim_path=p.groups_claim_path,
        email_claim_path=p.email_claim_path,
        name_claim_path=p.name_claim_path,
        auto_link_by_verified_email=p.auto_link_by_verified_email,
        require_email_verified=p.require_email_verified,
        reject_unmapped_users=p.reject_unmapped_users,
        fallback_organization_id=p.fallback_organization_id,
        fallback_role=p.fallback_role,
        is_active=p.is_active,
        manual_endpoints_json=p.manual_endpoints_json,
        created_at=p.created_at,
        updated_at=p.updated_at,
        mapping_count=mapping_count,
    )


@router.get("/providers", response_model=List[OIDCProviderResponse])
async def list_providers(
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(select(OIDCProvider).order_by(OIDCProvider.name))
    out: List[OIDCProviderResponse] = []
    for p in rows.scalars().all():
        out.append(_provider_to_response(p, await _count_mappings(db, p.id)))
    return out


@router.post(
    "/providers",
    response_model=OIDCProviderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider(
    data: OIDCProviderCreate,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_db),
):
    _validate_provisioning_safety(
        reject_unmapped_users=data.reject_unmapped_users,
        fallback_organization_id=data.fallback_organization_id,
        mapping_count=0,
    )

    p = OIDCProvider(
        name=data.name,
        display_label=data.display_label,
        issuer_url=data.issuer_url,
        client_id=data.client_id,
        scopes=data.scopes,
        groups_claim_path=data.groups_claim_path,
        email_claim_path=data.email_claim_path,
        name_claim_path=data.name_claim_path,
        auto_link_by_verified_email=data.auto_link_by_verified_email,
        require_email_verified=data.require_email_verified,
        reject_unmapped_users=data.reject_unmapped_users,
        fallback_organization_id=data.fallback_organization_id,
        fallback_role=data.fallback_role,
        is_active=data.is_active,
        manual_endpoints_json=data.manual_endpoints_json,
    )
    p.client_secret = data.client_secret  # encrypts via the setter
    db.add(p)
    await db.commit()
    await db.refresh(p)

    try:
        await AuditService(db).log_action(
            action=AuditAction.OIDC_PROVIDER_CREATE,
            actor_id=admin_user.id,
            organization_id=None,
            resource_type="oidc_provider",
            resource_id=str(p.id),
            details={
                "name": p.name,
                "issuer_url": p.issuer_url,
                "client_id": p.client_id,
            },
        )
    except Exception:
        pass

    return _provider_to_response(p, 0)


@router.put("/providers/{provider_id}", response_model=OIDCProviderResponse)
async def update_provider(
    provider_id: UUID,
    data: OIDCProviderUpdate,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(OIDCProvider, provider_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")

    payload = data.model_dump(exclude_unset=True, exclude_none=True)
    new_secret = payload.pop("client_secret", None)

    # Compute the post-update view to validate the safety invariant
    target_reject = payload.get("reject_unmapped_users", p.reject_unmapped_users)
    target_fallback = payload.get(
        "fallback_organization_id", p.fallback_organization_id
    )
    mapping_count = await _count_mappings(db, p.id)
    _validate_provisioning_safety(
        reject_unmapped_users=target_reject,
        fallback_organization_id=target_fallback,
        mapping_count=mapping_count,
    )

    audit_changes: dict = {}
    for k, v in payload.items():
        if getattr(p, k) != v:
            audit_changes[k] = {"from": getattr(p, k), "to": v}
            setattr(p, k, v)
    if new_secret is not None:
        p.client_secret = new_secret
        audit_changes["client_secret"] = "rotated"

    await db.commit()
    OIDCDiscovery.invalidate(p.id)
    await db.refresh(p)

    if audit_changes:
        try:
            await AuditService(db).log_action(
                action=AuditAction.OIDC_PROVIDER_UPDATE,
                actor_id=admin_user.id,
                organization_id=None,
                resource_type="oidc_provider",
                resource_id=str(p.id),
                details={"name": p.name, "changes": audit_changes},
            )
            if (
                "auto_link_by_verified_email" in audit_changes
                and audit_changes["auto_link_by_verified_email"]["to"] is True
            ):
                await AuditService(db).log_action(
                    action=AuditAction.OIDC_AUTO_LINK_ENABLED,
                    actor_id=admin_user.id,
                    organization_id=None,
                    resource_type="oidc_provider",
                    resource_id=str(p.id),
                    details={"name": p.name},
                )
        except Exception:
            pass

    return _provider_to_response(p, mapping_count)


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: UUID,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(OIDCProvider, provider_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
    name = p.name
    await db.delete(p)
    await db.commit()
    OIDCDiscovery.invalidate(provider_id)
    try:
        await AuditService(db).log_action(
            action=AuditAction.OIDC_PROVIDER_DELETE,
            actor_id=admin_user.id,
            organization_id=None,
            resource_type="oidc_provider",
            resource_id=str(provider_id),
            details={"name": name},
        )
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Group mappings
# ---------------------------------------------------------------------------


def _mapping_to_response(m: OIDCGroupMapping) -> OIDCGroupMappingResponse:
    return OIDCGroupMappingResponse(
        id=m.id,
        provider_id=m.provider_id,
        idp_group_name=m.idp_group_name,
        organization_id=m.organization_id,
        role=m.role,
        grants_instance_admin=m.grants_instance_admin,
    )


@router.get(
    "/providers/{provider_id}/mappings",
    response_model=List[OIDCGroupMappingResponse],
)
async def list_mappings(
    provider_id: UUID,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(OIDCProvider, provider_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
    rows = await db.execute(
        select(OIDCGroupMapping)
        .where(OIDCGroupMapping.provider_id == provider_id)
        .order_by(OIDCGroupMapping.idp_group_name)
    )
    return [_mapping_to_response(m) for m in rows.scalars().all()]


@router.post(
    "/providers/{provider_id}/mappings",
    response_model=OIDCGroupMappingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_mapping(
    provider_id: UUID,
    data: OIDCGroupMappingCreate,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(OIDCProvider, provider_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")

    if not data.grants_instance_admin and (data.organization_id is None or data.role is None):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Mapping must either grant_instance_admin or specify (organization_id, role).",
        )

    m = OIDCGroupMapping(
        provider_id=provider_id,
        idp_group_name=data.idp_group_name,
        organization_id=data.organization_id,
        role=data.role,
        grants_instance_admin=data.grants_instance_admin,
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)

    try:
        await AuditService(db).log_action(
            action=AuditAction.OIDC_GROUP_MAPPING_CHANGED,
            actor_id=admin_user.id,
            organization_id=data.organization_id,
            resource_type="oidc_group_mapping",
            resource_id=str(m.id),
            details={
                "operation": "create",
                "provider_id": str(provider_id),
                "idp_group": data.idp_group_name,
                "role": data.role,
                "grants_instance_admin": data.grants_instance_admin,
            },
        )
    except Exception:
        pass

    return _mapping_to_response(m)


@router.delete(
    "/providers/{provider_id}/mappings/{mapping_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_mapping(
    provider_id: UUID,
    mapping_id: UUID,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_db),
):
    m = await db.get(OIDCGroupMapping, mapping_id)
    if not m or m.provider_id != provider_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mapping not found")

    detail = {
        "operation": "delete",
        "provider_id": str(provider_id),
        "idp_group": m.idp_group_name,
    }
    await db.delete(m)
    await db.commit()
    try:
        await AuditService(db).log_action(
            action=AuditAction.OIDC_GROUP_MAPPING_CHANGED,
            actor_id=admin_user.id,
            organization_id=None,
            resource_type="oidc_group_mapping",
            resource_id=str(mapping_id),
            details=detail,
        )
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Force-SSO-only toggle (instance setting)
# ---------------------------------------------------------------------------


@router.get("/force-sso-only")
async def get_force_sso_only(
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(InstanceSettings, 1)
    enabled = bool((row.client_control or {}).get("force_sso_only")) if row else False
    return {"enabled": enabled}


@router.put("/force-sso-only")
async def set_force_sso_only(
    payload: ForceSSOOnlyToggle,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_db),
):
    """Enabling this disables local-password login. Requires a break-glass admin.

    The check protects against the most common foot-gun: an admin
    enabling SSO-only without a fallback path, then locking themselves
    out at the next session refresh.
    """
    from sqlalchemy.orm.attributes import flag_modified

    if payload.enabled and not await _has_local_admin(db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot enable force-SSO-only: no active instance admin "
                "with a local password remains. Create a break-glass "
                "admin (a user with password_hash + instance_admin=true) "
                "before enabling."
            ),
        )

    row = await db.get(InstanceSettings, 1)
    if row is None:
        row = InstanceSettings(id=1, client_control={})
        db.add(row)

    cc = dict(row.client_control or {})
    cc["force_sso_only"] = payload.enabled
    row.client_control = cc
    row.updated_by_user_id = admin_user.id
    flag_modified(row, "client_control")
    await db.commit()

    try:
        await AuditService(db).log_action(
            action=AuditAction.INSTANCE_FORCE_SSO_ONLY,
            actor_id=admin_user.id,
            organization_id=None,
            resource_type="instance_settings",
            resource_id="force_sso_only",
            details={"enabled": payload.enabled, "reason": payload.reason},
        )
    except Exception:
        pass

    return {"enabled": payload.enabled}
