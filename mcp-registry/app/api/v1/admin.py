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
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..dependencies import get_current_user, require_instance_admin
from ...db.database import get_async_session
from ...models.user import User, UserStatus
from ...models.api_key import APIKey
from ...models.audit_log import AuditLog
from ...schemas.audit_log import AuditLogListResponse, AuditLogResponse
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
