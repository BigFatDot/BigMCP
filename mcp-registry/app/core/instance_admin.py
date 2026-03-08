"""
Instance Admin management for BigMCP.

This module handles instance-level administration across all editions:
- COMMUNITY: Single user is automatically instance admin
- ENTERPRISE: Admin token from LICENSE_KEY JWT
- CLOUD_SAAS: Admin token from PLATFORM_ADMIN_TOKEN env var

Instance Admins can:
- Configure marketplace sources
- Manage the local registry (available servers)
- Sync and curate marketplace
- Access the admin interface

Security:
- Tokens are never stored, only validated
- Admin status is stored in user.preferences["instance_admin"]
- Each edition has its own validation mechanism
"""

import logging
from typing import Optional

from .edition import get_edition, get_license_payload, Edition
from .config import settings

logger = logging.getLogger(__name__)


def is_instance_admin(user) -> bool:
    """
    Check if a user is an instance admin.

    The check depends on the current edition:
    - COMMUNITY: Always True (single user = admin)
    - ENTERPRISE/CLOUD_SAAS: Check user.preferences["instance_admin"]

    Args:
        user: User model instance with preferences attribute

    Returns:
        True if user is an instance admin, False otherwise

    Example:
        from app.core.instance_admin import is_instance_admin

        if is_instance_admin(user):
            # Show admin UI
            pass
    """
    edition = get_edition()

    # Community: single user is always admin
    if edition == Edition.COMMUNITY:
        return True

    # Enterprise/SaaS: check user preference (set after token validation)
    if hasattr(user, 'preferences') and user.preferences:
        return user.preferences.get("instance_admin") is True

    return False


def validate_admin_token(token: str) -> bool:
    """
    Validate an admin token for the current edition.

    This is used when a user wants to become an instance admin.
    They enter the token received during setup/purchase.

    Args:
        token: Admin token to validate

    Returns:
        True if token is valid, False otherwise

    Token sources by edition:
    - COMMUNITY: Always valid (or can be None/empty)
    - ENTERPRISE: Must match admin_token from LICENSE_KEY JWT
    - CLOUD_SAAS: Must match PLATFORM_ADMIN_TOKEN env var

    Example:
        if validate_admin_token(user_entered_token):
            user.preferences["instance_admin"] = True
            await db.commit()
    """
    if not token:
        return False

    edition = get_edition()

    if edition == Edition.COMMUNITY:
        # Community edition: no token needed
        logger.info("Community edition: admin token validation always succeeds")
        return True

    elif edition == Edition.ENTERPRISE:
        # Enterprise: validate against admin_token in license
        payload = get_license_payload()
        if not payload:
            logger.warning("Enterprise edition but no valid license payload")
            return False

        expected_token = payload.get("admin_token")
        if not expected_token:
            logger.warning("Enterprise license missing admin_token claim")
            return False

        is_valid = token == expected_token
        if is_valid:
            logger.info("Enterprise admin token validated successfully")
        else:
            logger.warning("Invalid Enterprise admin token attempt")
        return is_valid

    elif edition == Edition.CLOUD_SAAS:
        # SaaS: validate against PLATFORM_ADMIN_TOKEN env var
        expected_token = settings.PLATFORM_ADMIN_TOKEN
        if not expected_token:
            logger.error("SaaS edition but PLATFORM_ADMIN_TOKEN not configured")
            return False

        is_valid = token == expected_token
        if is_valid:
            logger.info("SaaS platform admin token validated successfully")
        else:
            logger.warning("Invalid SaaS platform admin token attempt")
        return is_valid

    return False


def get_admin_token_hint() -> Optional[str]:
    """
    Get a hint about where to find the admin token.

    Used in the UI to guide users on how to become an instance admin.

    Returns:
        Human-readable hint string, or None for Community edition

    Example:
        hint = get_admin_token_hint()
        if hint:
            show_message(f"To become admin: {hint}")
    """
    edition = get_edition()

    if edition == Edition.COMMUNITY:
        return None  # No token needed

    elif edition == Edition.ENTERPRISE:
        return "Enter the Admin Token received with your Enterprise license purchase"

    elif edition == Edition.CLOUD_SAAS:
        return "Enter the Platform Admin Token from your deployment configuration"

    return None


def requires_admin_token() -> bool:
    """
    Check if the current edition requires admin token validation.

    Returns:
        True if admin token is required, False for Community edition
    """
    return get_edition() != Edition.COMMUNITY
