"""
MFA Service - TOTP-based two-factor authentication.

Implements RFC 6238 (TOTP) with:
- 30-second time step
- SHA-1 HMAC (standard for TOTP)
- 6-digit codes
- 10 backup codes
"""

import json
import logging
import secrets
from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

import pyotp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User
from ..core.secrets_manager import get_secrets_manager

logger = logging.getLogger(__name__)


class MFAService:
    """Service for managing user MFA enrollment and verification."""

    BACKUP_CODE_COUNT = 10
    ISSUER_NAME = "BigMCP"

    def __init__(self, db: AsyncSession):
        self.db = db
        self.secrets = get_secrets_manager()

    async def _get_user(self, user_id: UUID) -> Optional[User]:
        """Get user by ID."""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def generate_setup(self, user_id: UUID) -> Tuple[str, str, List[str]]:
        """
        Generate MFA setup data for user enrollment.

        This creates a new TOTP secret and backup codes, but does NOT enable
        MFA until the user verifies with a code.

        Args:
            user_id: User UUID

        Returns:
            Tuple of (secret, provisioning_uri, backup_codes)

        Raises:
            ValueError: If user not found or MFA already enabled
        """
        user = await self._get_user(user_id)
        if not user:
            raise ValueError("User not found")

        if user.mfa_enabled:
            raise ValueError("MFA is already enabled for this user")

        # Generate TOTP secret (base32 encoded, 32 chars = 160 bits)
        secret = pyotp.random_base32()

        # Generate provisioning URI for authenticator apps
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(
            name=user.email,
            issuer_name=self.ISSUER_NAME
        )

        # Generate backup codes (8 hex chars each = 32 bits)
        backup_codes = [
            secrets.token_hex(4).upper()
            for _ in range(self.BACKUP_CODE_COUNT)
        ]

        # Store encrypted secret and backup codes (not enabled until verified)
        user.mfa_secret = self.secrets.encrypt({"secret": secret})
        user.mfa_backup_codes = self.secrets.encrypt({"codes": backup_codes})

        await self.db.commit()

        logger.info(f"MFA setup initiated for user {user_id}")

        return secret, provisioning_uri, backup_codes

    async def verify_and_enable(
        self,
        user_id: UUID,
        code: str
    ) -> bool:
        """
        Verify TOTP code and enable MFA for user.

        This completes the MFA enrollment by verifying the user can
        generate valid codes.

        Args:
            user_id: User UUID
            code: 6-digit TOTP code from authenticator

        Returns:
            True if verified and enabled

        Raises:
            ValueError: If MFA not set up for user
        """
        user = await self._get_user(user_id)
        if not user or not user.mfa_secret:
            raise ValueError("MFA not set up for this user")

        if user.mfa_enabled:
            raise ValueError("MFA is already enabled")

        # Decrypt secret
        try:
            secret_data = self.secrets.decrypt(user.mfa_secret)
            secret = secret_data["secret"]
        except Exception as e:
            logger.error(f"Failed to decrypt MFA secret for user {user_id}: {e}")
            raise ValueError("MFA setup is corrupted, please start over")

        # Verify code (allow 1 window tolerance = 30 seconds drift)
        totp = pyotp.TOTP(secret)
        if not totp.verify(code, valid_window=1):
            logger.warning(f"Invalid MFA verification code for user {user_id}")
            return False

        # Enable MFA
        user.mfa_enabled = True
        user.mfa_enrolled_at = datetime.utcnow()

        await self.db.commit()

        logger.info(f"MFA enabled for user {user_id}")

        return True

    async def verify_code(
        self,
        user_id: UUID,
        code: str
    ) -> bool:
        """
        Verify TOTP code for login or sensitive operations.

        Accepts either a 6-digit TOTP code or an 8-character backup code.

        Args:
            user_id: User UUID
            code: 6-digit TOTP code or 8-char backup code

        Returns:
            True if code is valid
        """
        user = await self._get_user(user_id)
        if not user:
            return False

        if not user.mfa_enabled:
            return True  # MFA not enabled, pass through

        if not user.mfa_secret:
            logger.error(f"MFA enabled but no secret for user {user_id}")
            return False

        # Try TOTP first (6-digit codes)
        try:
            secret_data = self.secrets.decrypt(user.mfa_secret)
            totp = pyotp.TOTP(secret_data["secret"])

            if totp.verify(code, valid_window=1):
                logger.debug(f"MFA TOTP verification successful for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to verify TOTP for user {user_id}: {e}")

        # Try backup code (8-char codes)
        if user.mfa_backup_codes:
            try:
                codes_data = self.secrets.decrypt(user.mfa_backup_codes)
                codes = codes_data["codes"]
                code_upper = code.upper().strip()

                if code_upper in codes:
                    # Remove used backup code
                    codes.remove(code_upper)
                    user.mfa_backup_codes = self.secrets.encrypt({"codes": codes})
                    await self.db.commit()

                    logger.info(
                        f"MFA backup code used for user {user_id}. "
                        f"{len(codes)} codes remaining."
                    )
                    return True
            except Exception as e:
                logger.error(f"Failed to verify backup code for user {user_id}: {e}")

        logger.warning(f"MFA verification failed for user {user_id}")
        return False

    async def disable(self, user_id: UUID, code: str) -> bool:
        """
        Disable MFA for user.

        Requires a valid MFA code for security.

        Args:
            user_id: User UUID
            code: Current TOTP code for verification

        Returns:
            True if MFA was disabled

        Raises:
            ValueError: If user not found or MFA not enabled
        """
        user = await self._get_user(user_id)
        if not user:
            raise ValueError("User not found")

        if not user.mfa_enabled:
            raise ValueError("MFA is not enabled for this user")

        # Verify current code before disabling
        if not await self.verify_code(user_id, code):
            logger.warning(f"Failed to disable MFA for user {user_id}: invalid code")
            return False

        # Disable MFA
        user.mfa_enabled = False
        user.mfa_secret = None
        user.mfa_backup_codes = None
        user.mfa_enrolled_at = None

        await self.db.commit()

        logger.info(f"MFA disabled for user {user_id}")

        return True

    async def regenerate_backup_codes(self, user_id: UUID, code: str) -> Optional[List[str]]:
        """
        Regenerate backup codes for a user.

        Requires a valid MFA code for security.

        Args:
            user_id: User UUID
            code: Current TOTP code for verification

        Returns:
            List of new backup codes, or None if verification failed

        Raises:
            ValueError: If user not found or MFA not enabled
        """
        user = await self._get_user(user_id)
        if not user:
            raise ValueError("User not found")

        if not user.mfa_enabled:
            raise ValueError("MFA is not enabled for this user")

        # Verify current code
        if not await self.verify_code(user_id, code):
            logger.warning(f"Failed to regenerate backup codes for user {user_id}: invalid code")
            return None

        # Generate new backup codes
        new_codes = [
            secrets.token_hex(4).upper()
            for _ in range(self.BACKUP_CODE_COUNT)
        ]

        user.mfa_backup_codes = self.secrets.encrypt({"codes": new_codes})
        await self.db.commit()

        logger.info(f"Backup codes regenerated for user {user_id}")

        return new_codes

    async def get_status(self, user_id: UUID) -> dict:
        """
        Get MFA status for a user.

        Args:
            user_id: User UUID

        Returns:
            Dict with MFA status info
        """
        user = await self._get_user(user_id)
        if not user:
            raise ValueError("User not found")

        backup_codes_remaining = 0
        if user.mfa_enabled and user.mfa_backup_codes:
            try:
                codes_data = self.secrets.decrypt(user.mfa_backup_codes)
                backup_codes_remaining = len(codes_data.get("codes", []))
            except Exception:
                pass

        return {
            "enabled": user.mfa_enabled,
            "enrolled_at": user.mfa_enrolled_at.isoformat() if user.mfa_enrolled_at else None,
            "backup_codes_remaining": backup_codes_remaining if user.mfa_enabled else None
        }


def get_mfa_service(db: AsyncSession) -> MFAService:
    """Factory function for MFAService."""
    return MFAService(db)
