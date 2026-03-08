"""
MFA API Endpoints - Two-factor authentication management.

Provides endpoints for:
- Setting up MFA (generating QR code)
- Verifying and enabling MFA
- Disabling MFA
- Checking MFA status
- Regenerating backup codes
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_async_session
from ...api.dependencies import get_current_user_jwt
from ...models.user import User
from ...services.mfa_service import MFAService, get_mfa_service
from ...schemas.mfa import (
    MFASetupResponse,
    MFAVerifyRequest,
    MFAStatusResponse,
    MFAEnableResponse,
    MFADisableResponse,
    MFABackupCodesResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mfa", tags=["MFA"])


def get_mfa_service_dep(
    db: AsyncSession = Depends(get_async_session)
) -> MFAService:
    """Dependency to get MFAService."""
    return get_mfa_service(db)


@router.post("/setup", response_model=MFASetupResponse)
async def setup_mfa(
    user: User = Depends(get_current_user_jwt),
    mfa_service: MFAService = Depends(get_mfa_service_dep)
):
    """
    Generate MFA setup data.

    Returns a provisioning URI (for QR code) and backup codes.
    MFA is not enabled until verified with /verify endpoint.

    The provisioning URI can be:
    - Displayed as a QR code for scanning with authenticator apps
    - Manually entered into authenticator apps using the secret

    Backup codes should be stored securely by the user for recovery.
    """
    try:
        secret, uri, backup_codes = await mfa_service.generate_setup(user.id)

        logger.info(f"MFA setup initiated for user {user.email}")

        return MFASetupResponse(
            provisioning_uri=uri,
            backup_codes=backup_codes,
            message="Scan QR code with authenticator app, then verify with a code"
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/verify", response_model=MFAEnableResponse)
async def verify_and_enable_mfa(
    request: MFAVerifyRequest,
    user: User = Depends(get_current_user_jwt),
    mfa_service: MFAService = Depends(get_mfa_service_dep)
):
    """
    Verify TOTP code and enable MFA.

    This completes the MFA enrollment process. After this endpoint
    returns successfully, MFA will be required for sensitive operations.

    The code must be a valid 6-digit TOTP code from the authenticator app.
    """
    try:
        success = await mfa_service.verify_and_enable(user.id, request.code)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code. Please try again."
            )

        logger.info(f"MFA enabled for user {user.email}")

        return MFAEnableResponse(
            status="enabled",
            message="MFA successfully enabled"
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/disable", response_model=MFADisableResponse)
async def disable_mfa(
    request: MFAVerifyRequest,
    user: User = Depends(get_current_user_jwt),
    mfa_service: MFAService = Depends(get_mfa_service_dep)
):
    """
    Disable MFA.

    Requires a valid current MFA code for security.
    This will remove all MFA configuration including backup codes.
    """
    try:
        success = await mfa_service.disable(user.id, request.code)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid MFA code. Cannot disable MFA."
            )

        logger.info(f"MFA disabled for user {user.email}")

        return MFADisableResponse(
            status="disabled",
            message="MFA disabled"
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/status", response_model=MFAStatusResponse)
async def get_mfa_status(
    user: User = Depends(get_current_user_jwt),
    mfa_service: MFAService = Depends(get_mfa_service_dep)
):
    """
    Get MFA status for current user.

    Returns whether MFA is enabled, when it was enrolled,
    and how many backup codes remain.
    """
    try:
        status_data = await mfa_service.get_status(user.id)

        return MFAStatusResponse(**status_data)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/backup-codes/regenerate", response_model=MFABackupCodesResponse)
async def regenerate_backup_codes(
    request: MFAVerifyRequest,
    user: User = Depends(get_current_user_jwt),
    mfa_service: MFAService = Depends(get_mfa_service_dep)
):
    """
    Regenerate backup codes.

    Requires a valid current MFA code for security.
    This invalidates all previous backup codes.
    """
    try:
        new_codes = await mfa_service.regenerate_backup_codes(user.id, request.code)

        if not new_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid MFA code. Cannot regenerate backup codes."
            )

        logger.info(f"Backup codes regenerated for user {user.email}")

        return MFABackupCodesResponse(
            backup_codes=new_codes,
            message="New backup codes generated. Previous codes are now invalid."
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/verify-code")
async def verify_mfa_code(
    request: MFAVerifyRequest,
    user: User = Depends(get_current_user_jwt),
    mfa_service: MFAService = Depends(get_mfa_service_dep)
):
    """
    Verify an MFA code without any side effects.

    Useful for validating codes before sensitive operations.
    Does not consume backup codes (they're only consumed during actual auth).

    Note: This endpoint is for testing MFA codes only.
    Actual authentication should use the X-MFA-Code header.
    """
    # For TOTP verification only (not backup codes) - dry run
    if not user.mfa_enabled:
        return {"valid": True, "message": "MFA not enabled"}

    if not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA configuration is corrupted"
        )

    # Only verify TOTP, don't consume backup codes
    import pyotp
    from ...core.secrets_manager import get_secrets_manager

    secrets = get_secrets_manager()
    try:
        secret_data = secrets.decrypt(user.mfa_secret)
        totp = pyotp.TOTP(secret_data["secret"])
        valid = totp.verify(request.code, valid_window=1)

        return {
            "valid": valid,
            "message": "Code is valid" if valid else "Invalid code"
        }
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to verify code"
        )
