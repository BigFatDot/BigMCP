"""
Instance Admin API endpoints.

Provides endpoints for:
- Admin token validation
- Admin status check
- Instance configuration
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..dependencies import get_current_user, require_instance_admin
from ...db.database import get_async_session
from ...models.user import User
from ...models.api_key import APIKey
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

    # Community edition: auto-admin, no validation needed
    if edition == Edition.COMMUNITY:
        logger.info(f"Community edition: user {user.email} is automatically instance admin")
        return AdminTokenResponse(
            success=True,
            message="Community edition: you are automatically an instance admin"
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
    Not available on Community edition (always admin).
    """
    user, _ = auth
    edition = get_edition()

    # Community edition: cannot revoke
    if edition == Edition.COMMUNITY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke admin on Community edition"
        )

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

    # Log the rotation attempt
    audit_service = AuditService(db)
    await audit_service.log_action(
        action=AuditAction.SETTINGS_CHANGED,
        actor_id=admin_user.id,
        organization_id=admin_user.primary_organization_id,
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
