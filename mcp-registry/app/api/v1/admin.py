"""
Instance Admin API endpoints.

Provides endpoints for:
- Admin token validation
- Admin status check
- Instance configuration
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
import sqlalchemy as sa
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..dependencies import get_current_user, require_instance_admin
from ...db.database import get_async_session
from ...models.user import User, UserStatus
from ...models.api_key import APIKey
from ...models.audit_log import AuditLog
from ...models.refresh_token import RefreshToken
from ...schemas.audit_log import AuditLogListResponse, AuditLogResponse
from ...schemas.admin_user import AdminUserListItem, AdminUserListResponse
from ...schemas.policy import ClientControlPolicy
from ...services.policy_resolver import PolicyResolver
from ...models.instance_settings import InstanceSettings
from ...models.oauth import (
    OAuthClient,
    OAuthClientApprovalStatus,
    OAuthClientRegistrationMethod,
)
from ...core.instance_admin import (
    is_instance_admin,
    validate_admin_token,
    get_admin_token_hint,
    requires_admin_token
)
from ...core.edition import get_edition, Edition

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Instance Admin"])


# ============================================================================
# Request/Response Models
# ============================================================================

class AdminTokenRequest(BaseModel):
    """Request to validate an admin token."""
    token: str


class AdminTokenResponse(BaseModel):
    """Response from admin token validation."""
    success: bool
    message: str


class AdminStatusResponse(BaseModel):
    """Response with admin status information."""
    is_instance_admin: bool
    edition: str
    requires_token: bool
    token_hint: Optional[str] = None


# ============================================================================
# Admin Status Endpoints
# ============================================================================

@router.get("/status", response_model=AdminStatusResponse)
async def get_admin_status(
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user)
):
    """
    Get the current user's instance admin status.

    Returns whether the user is an instance admin, the current edition,
    and information about how to become an admin if not already.

    This endpoint is available to all authenticated users.
    """
    user, _ = auth
    edition = get_edition()

    return AdminStatusResponse(
        is_instance_admin=is_instance_admin(user),
        edition=edition.value,
        requires_token=requires_admin_token(),
        token_hint=get_admin_token_hint()
    )


@router.post("/validate-token", response_model=AdminTokenResponse)
async def validate_token(
    request: AdminTokenRequest,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Validate an admin token and grant instance admin privileges.

    For Community edition: Token is not required (auto-admin).
    For Enterprise edition: Token must match admin_token in LICENSE_KEY JWT.
    For Cloud SaaS edition: Token must match PLATFORM_ADMIN_TOKEN env var.

    On success, sets user.preferences["instance_admin"] = True.
    """
    user, _ = auth
    edition = get_edition()

    # Community edition: token validation always succeeds, persist admin status
    if edition == Edition.COMMUNITY:
        if user.preferences is None:
            user.preferences = {}
        user.preferences["instance_admin"] = True
        flag_modified(user, "preferences")
        db.add(user)
        await db.commit()
        logger.info(f"Community edition: user {user.email} granted instance admin")
        return AdminTokenResponse(
            success=True,
            message="Community edition: you are now an instance admin"
        )

    # Check if already admin
    if is_instance_admin(user):
        return AdminTokenResponse(
            success=True,
            message="You are already an instance admin"
        )

    # Validate the token
    if not validate_admin_token(request.token):
        logger.warning(f"Invalid admin token attempt by user {user.email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin token"
        )

    # Token is valid - grant admin privileges
    # Update user preferences
    if user.preferences is None:
        user.preferences = {}

    user.preferences["instance_admin"] = True

    # Flag the JSON column as modified (SQLAlchemy doesn't detect dict mutations)
    flag_modified(user, "preferences")

    # Commit the change
    db.add(user)
    await db.commit()

    logger.info(f"User {user.email} granted instance admin privileges")

    return AdminTokenResponse(
        success=True,
        message="Admin token validated. You are now an instance admin."
    )


@router.post("/revoke")
async def revoke_admin(
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Revoke instance admin privileges from the current user.

    This allows an admin to voluntarily give up their admin status.
    """
    user, _ = auth

    # Check if actually admin
    if not is_instance_admin(user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are not an instance admin"
        )

    # Revoke admin privileges
    if user.preferences:
        user.preferences["instance_admin"] = False
        flag_modified(user, "preferences")
        db.add(user)
        await db.commit()

    logger.info(f"User {user.email} revoked their instance admin privileges")

    return {"success": True, "message": "Instance admin privileges revoked"}


# ============================================================================
# Admin-Protected Endpoints
# ============================================================================

@router.get("/info")
async def get_admin_info(
    admin_user: User = Depends(require_instance_admin)
):
    """
    Get instance admin information.

    Requires: Instance Admin privileges.

    Returns detailed information about the instance configuration.
    """
    edition = get_edition()

    info = {
        "edition": edition.value,
        "admin_email": admin_user.email,
        "features": {
            "marketplace_sources": True,
            "registry_management": True,
            "server_curation": True
        }
    }

    # Add edition-specific info
    if edition == Edition.ENTERPRISE:
        from ...core.edition import get_license_org_name, get_license_features
        info["license"] = {
            "organization": get_license_org_name(),
            "features": get_license_features()
        }
    elif edition == Edition.CLOUD_SAAS:
        info["saas"] = {
            "marketplace_curation": True,
            "license_generation": True
        }

    return info


# ============================================================================
# Encryption Key Management Endpoints
# ============================================================================

class EncryptionStatusResponse(BaseModel):
    """Response with encryption status information."""
    current_version: int
    available_versions: list[int]
    is_dev_mode: bool
    user_credentials_by_version: dict[int, int]
    org_credentials_by_version: dict[int, int]
    total_credentials: int
    credentials_needing_rotation: int
    rotation_recommended: bool


class KeyRotationRequest(BaseModel):
    """Request to rotate encryption keys."""
    dry_run: bool = True
    batch_size: int = 100


class KeyRotationResponse(BaseModel):
    """Response from key rotation operation."""
    success: bool
    dry_run: bool
    to_version: int
    user_credentials_migrated: int
    org_credentials_migrated: int
    total_migrated: int
    failed: int
    error: Optional[str] = None


@router.get("/encryption-status", response_model=EncryptionStatusResponse)
async def get_encryption_status(
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get current encryption status and credential version distribution.

    Requires: Instance Admin privileges.

    Returns information about:
    - Current encryption key version
    - Available key versions for decryption
    - Distribution of credentials by encryption version
    - Whether key rotation is recommended
    """
    from ...services.key_rotation_service import KeyRotationService

    service = KeyRotationService(db)
    status = await service.get_encryption_status()

    return EncryptionStatusResponse(
        current_version=status.current_version,
        available_versions=status.available_versions,
        is_dev_mode=status.is_dev_mode,
        user_credentials_by_version=status.user_credentials_by_version,
        org_credentials_by_version=status.org_credentials_by_version,
        total_credentials=status.total_credentials,
        credentials_needing_rotation=status.credentials_needing_rotation,
        rotation_recommended=status.credentials_needing_rotation > 0
    )


@router.post("/rotate-keys", response_model=KeyRotationResponse)
async def rotate_encryption_keys(
    request: KeyRotationRequest,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Rotate encryption keys by re-encrypting all credentials.

    Requires: Instance Admin privileges.

    This operation re-encrypts all credentials with the current
    (latest) encryption key version. Use dry_run=true to preview
    the operation without making changes.

    WARNING: This operation can take time for large credential sets.
    Consider running during low-traffic periods.
    """
    from ...services.key_rotation_service import KeyRotationService
    from ...services.audit_service import AuditService, AuditAction

    service = KeyRotationService(db)

    # Log the rotation attempt.
    # Key rotation is an instance-wide action: organization_id is intentionally
    # None (User has no `primary_organization_id` field and instance admins
    # operate cross-organization).
    audit_service = AuditService(db)
    await audit_service.log_action(
        action=AuditAction.ENCRYPTION_KEY_ROTATED,
        actor_id=admin_user.id,
        organization_id=None,
        resource_type="encryption_keys",
        resource_id="rotation",
        details={
            "dry_run": request.dry_run,
            "batch_size": request.batch_size
        }
    )

    # Perform rotation
    report = await service.rotate_all_credentials(
        batch_size=request.batch_size,
        dry_run=request.dry_run
    )

    total_migrated = report.user_credentials.migrated + report.org_credentials.migrated
    total_failed = report.user_credentials.failed + report.org_credentials.failed

    logger.info(
        f"Key rotation {'(dry run) ' if request.dry_run else ''}completed by {admin_user.email}: "
        f"{total_migrated} migrated, {total_failed} failed"
    )

    return KeyRotationResponse(
        success=report.success,
        dry_run=request.dry_run,
        to_version=report.to_version,
        user_credentials_migrated=report.user_credentials.migrated,
        org_credentials_migrated=report.org_credentials.migrated,
        total_migrated=total_migrated,
        failed=total_failed,
        error=report.error
    )


# ============================================================================
# Audit logs (instance admin only)
# ============================================================================

@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    actor_id: Optional[UUID] = Query(
        None, description="Filter by acting user UUID"
    ),
    organization_id: Optional[UUID] = Query(
        None, description="Filter by organization context"
    ),
    action: Optional[str] = Query(
        None,
        description=(
            "Exact action match (e.g. 'auth.login_failed') or a prefix "
            "ending in '*' (e.g. 'oauth.*' for any OAuth event)."
        ),
    ),
    resource_type: Optional[str] = Query(
        None, description="Filter by resource type (user, api_key, credential, ...)"
    ),
    resource_id: Optional[str] = Query(
        None, description="Filter by resource UUID"
    ),
    ip_address: Optional[str] = Query(
        None, description="Filter by source IP address (exact match)"
    ),
    since: Optional[datetime] = Query(
        None, description="Inclusive lower bound on timestamp (ISO 8601)"
    ),
    until: Optional[datetime] = Query(
        None, description="Inclusive upper bound on timestamp (ISO 8601)"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_async_session),
) -> AuditLogListResponse:
    """List immutable audit logs across the whole instance.

    Returns the most recent rows first. Filters compose with AND
    semantics; an unset filter is ignored. The HMAC signature is
    never exposed in the response — only server-side
    ``AuditLog.verify_integrity()`` reads it.

    Requires instance-admin privileges.
    """
    filters = []
    if actor_id is not None:
        filters.append(AuditLog.actor_id == actor_id)
    if organization_id is not None:
        filters.append(AuditLog.organization_id == organization_id)
    if action is not None:
        if action.endswith("*"):
            prefix = action[:-1]
            filters.append(AuditLog.action.like(f"{prefix}%"))
        else:
            filters.append(AuditLog.action == action)
    if resource_type is not None:
        filters.append(AuditLog.resource_type == resource_type)
    if resource_id is not None:
        filters.append(AuditLog.resource_id == resource_id)
    if ip_address is not None:
        filters.append(AuditLog.ip_address == ip_address)
    if since is not None:
        filters.append(AuditLog.timestamp >= since)
    if until is not None:
        filters.append(AuditLog.timestamp <= until)

    where_clause = and_(*filters) if filters else None

    # Total count (for pagination UI) — separate cheap query.
    count_stmt = select(func.count()).select_from(AuditLog)
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)
    total = (await db.execute(count_stmt)).scalar_one()

    # Page query.
    stmt = (
        select(AuditLog)
        .order_by(desc(AuditLog.timestamp))
        .limit(limit)
        .offset(offset)
    )
    if where_clause is not None:
        stmt = stmt.where(where_clause)

    rows = (await db.execute(stmt)).scalars().all()
    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/audit-logs/{log_id}", response_model=AuditLogResponse)
async def get_audit_log(
    log_id: UUID,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_async_session),
) -> AuditLogResponse:
    """Return a single audit log entry (without its HMAC signature)."""
    row = await db.get(AuditLog, log_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit log {log_id} not found",
        )
    return AuditLogResponse.model_validate(row)


# ============================================================================
# Users list (admin)
# ============================================================================

@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by lifecycle status (active, suspended, deleted)",
    ),
    search: Optional[str] = Query(
        None,
        description="Case-insensitive substring match on email or name",
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_async_session),
) -> AdminUserListResponse:
    """List users with lifecycle status — admin-only.

    Sort: most recently created first. Filters compose with AND.
    The response intentionally excludes password hashes, MFA secrets,
    and full preferences; only the ``instance_admin`` derived flag is
    surfaced.
    """
    filters = []
    if status_filter:
        filters.append(User.status == status_filter)
    if search:
        like = f"%{search.lower()}%"
        filters.append(
            sa.or_(
                func.lower(User.email).like(like),
                func.lower(func.coalesce(User.name, "")).like(like),
            )
        )

    where_clause = and_(*filters) if filters else None

    count_stmt = select(func.count()).select_from(User)
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(User)
        .order_by(desc(User.created_at))
        .limit(limit)
        .offset(offset)
    )
    if where_clause is not None:
        stmt = stmt.where(where_clause)
    rows = (await db.execute(stmt)).scalars().all()

    items = []
    for u in rows:
        is_admin = bool((u.preferences or {}).get("instance_admin"))
        items.append(
            AdminUserListItem(
                id=u.id,
                email=u.email,
                name=u.name,
                status=u.status,
                status_changed_at=u.status_changed_at,
                status_reason=u.status_reason,
                deleted_at=u.deleted_at,
                email_verified=u.email_verified,
                last_login_at=u.last_login_at,
                tokens_revoked_at=u.tokens_revoked_at,
                is_instance_admin=is_admin,
                created_at=u.created_at,
            )
        )

    return AdminUserListResponse(items=items, total=total, limit=limit, offset=offset)


# ============================================================================
# User lifecycle endpoints (N1.4 — non-destructive offboarding)
# ============================================================================

class UserLifecycleRequest(BaseModel):
    reason: Optional[str] = None


class UserLifecycleResponse(BaseModel):
    id: UUID
    email: str
    status: str
    status_changed_at: Optional[datetime] = None
    status_reason: Optional[str] = None
    deleted_at: Optional[datetime] = None


async def _load_user_or_404(db: AsyncSession, user_id: UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    return user


async def _audit_lifecycle(
    db: AsyncSession,
    action: "AuditAction",
    actor_id: UUID,
    target: User,
    reason: Optional[str],
) -> None:
    """Best-effort audit emission for a lifecycle change."""
    try:
        from ...services.audit_service import AuditService
        from ...models.audit_log import AuditAction as _AA  # local re-import for clarity
        await AuditService(db).log_action(
            action=action,
            actor_id=actor_id,
            organization_id=None,
            resource_type="user",
            resource_id=str(target.id),
            details={
                "target_email": target.email,
                "new_status": target.status,
                "reason": reason,
            },
        )
    except Exception:
        pass


@router.post(
    "/users/{user_id}/suspend",
    response_model=UserLifecycleResponse,
    summary="Suspend a user account (instance admin)",
)
async def suspend_user(
    user_id: UUID,
    body: UserLifecycleRequest,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_async_session),
) -> UserLifecycleResponse:
    """Suspend a user. Reversible. Login + token validation immediately fail."""
    from ...models.audit_log import AuditAction

    target = await _load_user_or_404(db, user_id)

    if target.id == admin_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refusing to suspend the calling instance admin account.",
        )
    if target.status == UserStatus.DELETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot suspend a soft-deleted account; reactivate it first.",
        )

    target.status = UserStatus.SUSPENDED.value
    target.status_changed_at = datetime.utcnow()
    target.status_reason = body.reason
    await db.commit()
    await db.refresh(target)

    await _audit_lifecycle(db, AuditAction.USER_SUSPENDED, admin_user.id, target, body.reason)
    logger.info("User %s suspended by %s", target.email, admin_user.email)
    return UserLifecycleResponse.model_validate(target.__dict__)


@router.post(
    "/users/{user_id}/reactivate",
    response_model=UserLifecycleResponse,
    summary="Reactivate a suspended (or soft-deleted) user account",
)
async def reactivate_user(
    user_id: UUID,
    body: UserLifecycleRequest,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_async_session),
) -> UserLifecycleResponse:
    """Move a suspended or soft-deleted account back to active.

    Reactivating a soft-deleted account also clears ``deleted_at`` so the
    retention purge job will leave it alone.
    """
    from ...models.audit_log import AuditAction

    target = await _load_user_or_404(db, user_id)
    if target.status == UserStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already active.",
        )

    target.status = UserStatus.ACTIVE.value
    target.status_changed_at = datetime.utcnow()
    target.status_reason = body.reason
    target.deleted_at = None
    await db.commit()
    await db.refresh(target)

    await _audit_lifecycle(db, AuditAction.USER_REACTIVATED, admin_user.id, target, body.reason)
    logger.info("User %s reactivated by %s", target.email, admin_user.email)
    return UserLifecycleResponse.model_validate(target.__dict__)


@router.post(
    "/users/{user_id}/soft-delete",
    response_model=UserLifecycleResponse,
    summary="Soft-delete a user account (RGPD-friendly)",
)
async def soft_delete_user(
    user_id: UUID,
    body: UserLifecycleRequest,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_async_session),
) -> UserLifecycleResponse:
    """Mark a user as deleted without dropping the row.

    Audit history, organisation memberships, and credential references
    stay intact for the retention period. A separate purge job (out of
    scope for this endpoint) is responsible for hard-deletion or
    PII anonymisation after the configured window.
    """
    from ...models.audit_log import AuditAction

    target = await _load_user_or_404(db, user_id)
    if target.id == admin_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refusing to soft-delete the calling instance admin account.",
        )

    now = datetime.utcnow()
    target.status = UserStatus.DELETED.value
    target.status_changed_at = now
    target.status_reason = body.reason
    target.deleted_at = now
    await db.commit()
    await db.refresh(target)

    await _audit_lifecycle(db, AuditAction.USER_SOFT_DELETED, admin_user.id, target, body.reason)
    logger.info("User %s soft-deleted by %s", target.email, admin_user.email)
    return UserLifecycleResponse.model_validate(target.__dict__)


# ============================================================================
# Cross-surface kill switch (N1.3)
# ============================================================================

class RevokeAllResponse(BaseModel):
    user_id: UUID
    tokens_revoked_at: datetime
    api_keys_revoked: int
    refresh_tokens_revoked: int


@router.post(
    "/users/{user_id}/revoke-all",
    response_model=RevokeAllResponse,
    summary="Revoke every authentication surface for a user",
)
async def revoke_all_user_sessions(
    user_id: UUID,
    body: UserLifecycleRequest,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_async_session),
) -> RevokeAllResponse:
    """Sever every active authentication for a user in one shot.

    Three surfaces are invalidated:

    1. JWT access tokens — by bumping ``user.tokens_revoked_at``,
       so any access token whose ``iat`` predates this call fails
       at next ``get_user_from_token``.
    2. Refresh tokens — DB rows flipped to is_active=False with a
       reason and timestamp, mirroring ``RefreshToken.revoke()``.
       The same ``tokens_revoked_at`` check also catches any not-yet-
       seen token whose iat predates this call.
    3. API keys — same treatment via the new ``APIKey.revoke()``
       helper (also enforced through ``tokens_revoked_at`` in
       ``validate_api_key``).

    The user record itself is NOT touched; combine with /suspend or
    /soft-delete for a full offboarding.
    """
    from ...models.audit_log import AuditAction

    target = await _load_user_or_404(db, user_id)
    if target.id == admin_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refusing to revoke the calling instance admin's own sessions.",
        )

    now = datetime.utcnow()
    reason = body.reason or "admin_revoke_all"

    # 1. JWT bulk revocation — single timestamp on the user row.
    target.tokens_revoked_at = now

    # 2. Active refresh tokens — explicit per-row revoke for an audit
    # trail richer than the bulk timestamp can carry.
    rt_rows = (
        await db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == target.id,
                RefreshToken.is_active.is_(True),
            )
        )
    ).scalars().all()
    for rt in rt_rows:
        rt.revoke(reason=reason)

    # 3. Active API keys — same pattern via the helper added in N1.3.
    ak_rows = (
        await db.execute(
            select(APIKey).where(
                APIKey.user_id == target.id,
                APIKey.is_active.is_(True),
            )
        )
    ).scalars().all()
    for ak in ak_rows:
        ak.revoke(reason=reason)

    await db.commit()

    # Audit
    try:
        from ...services.audit_service import AuditService
        await AuditService(db).log_action(
            action=AuditAction.USER_TOKENS_REVOKED,
            actor_id=admin_user.id,
            organization_id=None,
            resource_type="user",
            resource_id=str(target.id),
            details={
                "target_email": target.email,
                "reason": reason,
                "api_keys_revoked": len(ak_rows),
                "refresh_tokens_revoked": len(rt_rows),
            },
        )
    except Exception:
        pass

    logger.info(
        "User %s sessions kill-switched by %s (api_keys=%d, refresh=%d)",
        target.email, admin_user.email, len(ak_rows), len(rt_rows),
    )

    return RevokeAllResponse(
        user_id=target.id,
        tokens_revoked_at=now,
        api_keys_revoked=len(ak_rows),
        refresh_tokens_revoked=len(rt_rows),
    )


# ============================================================================
# Client control policy (N2.2 — instance-level)
# ============================================================================

@router.get("/client-policy", response_model=ClientControlPolicy)
async def get_client_policy(
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_async_session),
) -> ClientControlPolicy:
    """Return the resolved instance-level client-control policy.

    Layers env-var defaults under the stored instance_settings row.
    Org overrides apply at /authorize, not here.
    """
    return await PolicyResolver(db).get_instance_policy()


@router.put("/client-policy", response_model=ClientControlPolicy)
async def update_client_policy(
    new_policy: ClientControlPolicy,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_async_session),
) -> ClientControlPolicy:
    """Persist the instance-level client-control policy.

    The whole policy object replaces what's stored — partial updates
    aren't supported on purpose, so the admin always sees what they
    are committing.
    """
    from ...models.audit_log import AuditAction

    row = await db.get(InstanceSettings, 1)
    if row is None:
        # Should never happen (the migration seeds id=1), but be safe.
        row = InstanceSettings(id=1, client_control={})
        db.add(row)

    previous = dict(row.client_control or {})
    row.client_control = new_policy.model_dump()
    row.updated_by_user_id = admin_user.id
    flag_modified(row, "client_control")
    await db.commit()
    await db.refresh(row)

    try:
        from ...services.audit_service import AuditService
        await AuditService(db).log_action(
            action=AuditAction.POLICY_CHANGED,
            actor_id=admin_user.id,
            organization_id=None,
            resource_type="instance_settings",
            resource_id="client_control",
            details={
                "previous": previous,
                "new": row.client_control,
            },
        )
    except Exception:
        pass

    return await PolicyResolver(db).get_instance_policy()


# ============================================================================
# OAuth clients management (N2.2 — instance admin)
# ============================================================================

class OAuthClientAdminItem(BaseModel):
    id: UUID
    client_id: str
    name: str
    description: Optional[str] = None
    organization_id: Optional[UUID] = None
    registration_method: str
    approval_status: str
    is_active: bool
    is_trusted: bool
    cimd_url: Optional[str] = None
    redirect_uris: list
    created_at: datetime
    approved_by_user_id: Optional[UUID] = None
    approved_at: Optional[datetime] = None


class OAuthClientListResponse(BaseModel):
    items: list[OAuthClientAdminItem]
    total: int
    limit: int
    offset: int


class ApprovalRequest(BaseModel):
    reason: Optional[str] = None


@router.get("/oauth-clients", response_model=OAuthClientListResponse)
async def list_oauth_clients(
    approval_status: Optional[str] = Query(
        None,
        description="Filter by approval_status (auto_approved/pending/approved/rejected)",
    ),
    registration_method: Optional[str] = Query(None),
    organization_id: Optional[UUID] = Query(None),
    search: Optional[str] = Query(
        None, description="Substring on client name (case-insensitive)"
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_async_session),
) -> OAuthClientListResponse:
    """List every OAuth client across the instance — admin-only."""
    filters = []
    if approval_status:
        filters.append(OAuthClient.approval_status == approval_status)
    if registration_method:
        filters.append(OAuthClient.registration_method == registration_method)
    if organization_id:
        filters.append(OAuthClient.organization_id == organization_id)
    if search:
        filters.append(func.lower(OAuthClient.name).like(f"%{search.lower()}%"))

    where_clause = and_(*filters) if filters else None

    count_stmt = select(func.count()).select_from(OAuthClient)
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(OAuthClient)
        .order_by(desc(OAuthClient.created_at))
        .limit(limit)
        .offset(offset)
    )
    if where_clause is not None:
        stmt = stmt.where(where_clause)
    rows = (await db.execute(stmt)).scalars().all()

    items = [
        OAuthClientAdminItem(
            id=c.id,
            client_id=c.client_id,
            name=c.name,
            description=c.description,
            organization_id=c.organization_id,
            registration_method=c.registration_method,
            approval_status=c.approval_status,
            is_active=c.is_active,
            is_trusted=c.is_trusted,
            cimd_url=c.cimd_url,
            redirect_uris=c.redirect_uris,
            created_at=c.created_at,
            approved_by_user_id=c.approved_by_user_id,
            approved_at=c.approved_at,
        )
        for c in rows
    ]
    return OAuthClientListResponse(
        items=items, total=total, limit=limit, offset=offset
    )


async def _set_oauth_client_status(
    db: AsyncSession,
    admin_user: User,
    client_id: UUID,
    new_status: OAuthClientApprovalStatus,
    audit_action: "AuditAction",
    body: ApprovalRequest,
) -> OAuthClient:
    from ...models.audit_log import AuditAction  # local for typing only

    client = await db.get(OAuthClient, client_id)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OAuth client {client_id} not found",
        )
    client.approval_status = new_status.value
    client.approved_by_user_id = admin_user.id
    client.approved_at = datetime.utcnow()
    await db.commit()
    await db.refresh(client)

    try:
        from ...services.audit_service import AuditService
        await AuditService(db).log_action(
            action=audit_action,
            actor_id=admin_user.id,
            organization_id=client.organization_id,
            resource_type="oauth_client",
            resource_id=str(client.id),
            details={
                "client_id": client.client_id,
                "client_name": client.name,
                "registration_method": client.registration_method,
                "reason": body.reason,
            },
        )
    except Exception:
        pass

    return client


@router.post("/oauth-clients/{client_id}/approve")
async def approve_oauth_client(
    client_id: UUID,
    body: ApprovalRequest,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """Approve a pending OAuth client so it can complete /authorize."""
    from ...models.audit_log import AuditAction

    client = await _set_oauth_client_status(
        db,
        admin_user,
        client_id,
        OAuthClientApprovalStatus.APPROVED,
        AuditAction.OAUTH_CLIENT_APPROVE,
        body,
    )
    return {"id": str(client.id), "approval_status": client.approval_status}


@router.post("/oauth-clients/{client_id}/reject")
async def reject_oauth_client(
    client_id: UUID,
    body: ApprovalRequest,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """Reject an OAuth client. /authorize will refuse with 403."""
    from ...models.audit_log import AuditAction

    client = await _set_oauth_client_status(
        db,
        admin_user,
        client_id,
        OAuthClientApprovalStatus.REJECTED,
        AuditAction.OAUTH_CLIENT_REJECT,
        body,
    )
    return {"id": str(client.id), "approval_status": client.approval_status}


@router.delete(
    "/oauth-clients/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_oauth_client(
    client_id: UUID,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """Revoke an OAuth client — sets is_active=False so future
    validation rejects it. The row is kept for audit history."""
    from ...models.audit_log import AuditAction

    client = await db.get(OAuthClient, client_id)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OAuth client {client_id} not found",
        )
    client.is_active = False
    await db.commit()

    try:
        from ...services.audit_service import AuditService
        await AuditService(db).log_action(
            action=AuditAction.OAUTH_CLIENT_REVOKE,
            actor_id=admin_user.id,
            organization_id=client.organization_id,
            resource_type="oauth_client",
            resource_id=str(client.id),
            details={
                "client_id": client.client_id,
                "client_name": client.name,
            },
        )
    except Exception:
        pass
    return None
