"""
License Generator Service for Enterprise Edition.

Generates JWT-based LICENSE_KEY tokens for Enterprise customers.
Only available on Cloud SaaS edition (requires LICENSE_SIGNING_PRIVATE_KEY).

The license JWT includes:
- org_name: Organization name
- features: List of enabled features
- admin_token: Token for becoming Instance Admin (auto-generated)
"""

import logging
import secrets
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.license import License, LicenseEdition, LicenseType, LicenseStatus
from ..core.config import settings
from ..core.edition import is_saas

logger = logging.getLogger(__name__)


class LicenseGeneratorError(Exception):
    """Base exception for license generation errors."""
    pass


class NotSaaSEditionError(LicenseGeneratorError):
    """Raised when trying to generate license outside SaaS edition."""
    pass


class PrivateKeyNotConfiguredError(LicenseGeneratorError):
    """Raised when LICENSE_SIGNING_PRIVATE_KEY is not configured."""
    pass


class LicenseAlreadyExistsError(LicenseGeneratorError):
    """Raised when license for order already exists."""
    pass


# Default Enterprise features
DEFAULT_ENTERPRISE_FEATURES = [
    "sso",
    "saml",
    "unlimited_users",
    "priority_support",
    "audit_logs",
    "custom_branding",
    "api_access",
    "dedicated_support"
]


class LicenseGeneratorService:
    """
    Service for generating Enterprise LICENSE_KEY tokens.

    Only operates on Cloud SaaS edition with LICENSE_SIGNING_PRIVATE_KEY configured.
    """

    @staticmethod
    def _get_private_key() -> str:
        """
        Get the license signing private key.

        Returns:
            Private key PEM string

        Raises:
            NotSaaSEditionError: If not running SaaS edition
            PrivateKeyNotConfiguredError: If private key not configured
        """
        if not is_saas():
            raise NotSaaSEditionError(
                "License generation only available on Cloud SaaS edition"
            )

        private_key = settings.LICENSE_SIGNING_PRIVATE_KEY
        if not private_key:
            raise PrivateKeyNotConfiguredError(
                "LICENSE_SIGNING_PRIVATE_KEY not configured"
            )

        return private_key

    @staticmethod
    def generate_admin_token() -> str:
        """
        Generate a secure admin token for Instance Admin access.

        Returns:
            32-character hex token (e.g., "a1b2c3d4e5f6...")
        """
        return secrets.token_hex(16)

    @staticmethod
    def generate_license_jwt(
        org_name: str,
        order_id: str,
        features: Optional[List[str]] = None,
        org_id: Optional[str] = None,
        admin_token: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> str:
        """
        Generate a JWT LICENSE_KEY for Enterprise edition.

        The JWT is signed with ES256 using the private key.
        If expires_at is None → perpetual license (no "exp" claim).
        If expires_at is set → timed license (e.g. 3-month promo).

        Args:
            org_name: Organization name (customer company)
            order_id: LemonSqueezy order ID
            features: List of enabled features (optional, uses defaults)
            org_id: Optional organization ID for the license
            admin_token: Optional admin token (auto-generated if not provided)
            expires_at: Optional expiration datetime (None = perpetual)

        Returns:
            JWT token string (LICENSE_KEY)

        Raises:
            NotSaaSEditionError: If not SaaS edition
            PrivateKeyNotConfiguredError: If private key missing
        """
        from jose import jwt

        private_key = LicenseGeneratorService._get_private_key()

        if features is None:
            features = DEFAULT_ENTERPRISE_FEATURES

        # Generate admin token if not provided
        if admin_token is None:
            admin_token = LicenseGeneratorService.generate_admin_token()

        payload = {
            "iss": "bigfatdot.org",
            "sub": org_id or order_id,
            "iat": int(datetime.now().timestamp()),
            "edition": "enterprise",
            "org_name": org_name,
            "order_id": order_id,
            "features": features,
            "admin_token": admin_token,
        }

        # Add expiration only for timed licenses (perpetual = no "exp" claim)
        if expires_at is not None:
            payload["exp"] = int(expires_at.timestamp())

        return jwt.encode(payload, private_key, algorithm="ES256")

    @staticmethod
    async def generate_and_store_license(
        session: AsyncSession,
        org_name: str,
        order_id: str,
        customer_email: str,
        customer_id: Optional[str] = None,
        features: Optional[List[str]] = None,
        organization_id: Optional[UUID] = None,
        expires_at: Optional[datetime] = None,
    ) -> License:
        """
        Generate LICENSE_KEY and store in database.

        Args:
            session: Database session
            org_name: Organization/company name
            order_id: LemonSqueezy order ID
            customer_email: Customer email address
            customer_id: LemonSqueezy customer ID
            features: List of enabled features
            organization_id: Optional linked organization UUID

        Returns:
            Created License record

        Raises:
            LicenseAlreadyExistsError: If license for order exists
        """
        # Check idempotency - don't create duplicate for same order
        existing = await session.execute(
            select(License).where(License.lemonsqueezy_order_id == order_id)
        )
        if existing.scalar_one_or_none():
            raise LicenseAlreadyExistsError(
                f"License already exists for order {order_id}"
            )

        # Generate JWT
        license_jwt = LicenseGeneratorService.generate_license_jwt(
            org_name=org_name,
            order_id=order_id,
            features=features,
            org_id=str(organization_id) if organization_id else None,
            expires_at=expires_at,
        )

        # Build features dict for License model
        if features is None:
            features = DEFAULT_ENTERPRISE_FEATURES
        features_dict = {f: True for f in features}

        # Create License record
        license_record = License(
            license_key=license_jwt,
            edition=LicenseEdition.ENTERPRISE,
            license_type=LicenseType.SELF_HOSTED,
            status=LicenseStatus.ACTIVE,
            organization_id=organization_id,
            # Enterprise default limits (effectively unlimited)
            max_users=999999,
            max_servers=999999,
            max_api_keys=999999,
            max_contexts=999999,
            max_compositions=999999,
            features=features_dict,
            issued_at=datetime.now(),
            expires_at=expires_at,  # None = perpetual, datetime = timed promo
            customer_email=customer_email,
            company_name=org_name,
            lemonsqueezy_order_id=order_id,
            lemonsqueezy_customer_id=customer_id,
            license_metadata={
                "generated_by": "lemonsqueezy_webhook",
                "generated_at": datetime.now().isoformat(),
            }
        )

        session.add(license_record)
        await session.commit()
        await session.refresh(license_record)

        logger.info(
            f"Generated Enterprise license for {org_name} "
            f"(order: {order_id}, email: {customer_email})"
        )

        return license_record

    @staticmethod
    async def get_license_by_order(
        session: AsyncSession,
        order_id: str
    ) -> Optional[License]:
        """
        Get license by LemonSqueezy order ID.

        Args:
            session: Database session
            order_id: LemonSqueezy order ID

        Returns:
            License or None if not found
        """
        result = await session.execute(
            select(License).where(License.lemonsqueezy_order_id == order_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_license_by_email(
        session: AsyncSession,
        email: str
    ) -> Optional[License]:
        """
        Get license by customer email.

        Args:
            session: Database session
            email: Customer email address

        Returns:
            License or None if not found
        """
        result = await session.execute(
            select(License).where(License.customer_email == email)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_licenses_by_email(
        session: AsyncSession,
        email: str
    ) -> List[License]:
        """
        Get all licenses for a customer email.

        Args:
            session: Database session
            email: Customer email address

        Returns:
            List of License records
        """
        result = await session.execute(
            select(License)
            .where(License.customer_email == email)
            .where(License.edition == LicenseEdition.ENTERPRISE)
            .order_by(License.issued_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def revoke_license(
        session: AsyncSession,
        order_id: str,
        reason: str = "Revoked by administrator"
    ) -> Optional[License]:
        """
        Revoke a license by order ID.

        Args:
            session: Database session
            order_id: LemonSqueezy order ID
            reason: Revocation reason

        Returns:
            Updated License or None if not found
        """
        license_record = await LicenseGeneratorService.get_license_by_order(
            session, order_id
        )

        if not license_record:
            return None

        license_record.status = LicenseStatus.REVOKED
        license_record.license_metadata["revoked_at"] = datetime.now().isoformat()
        license_record.license_metadata["revocation_reason"] = reason

        await session.commit()
        await session.refresh(license_record)

        logger.info(f"Revoked license for order {order_id}: {reason}")

        return license_record
