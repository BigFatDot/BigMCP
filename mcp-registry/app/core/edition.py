"""
Edition detection and license validation for BigMCP.

This module determines which edition of BigMCP is running:
- COMMUNITY: Free, self-hosted, single-user (default)
- ENTERPRISE: Licensed, self-hosted, unlimited users
- CLOUD_SAAS: BigFatDot's managed service at bigmcp.cloud

Security:
- Uses ECDSA P-256 (ES256) for license/token verification
- Public key embedded here (safe to commit)
- Private key only on bigmcp.cloud (never in repo)
"""

import json
import logging
from enum import Enum
from functools import lru_cache
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


class Edition(str, Enum):
    """BigMCP edition types."""
    COMMUNITY = "community"
    ENTERPRISE = "enterprise"
    CLOUD_SAAS = "cloud_saas"


# ============================================================================
# Public Key for License Verification (ES256 / ECDSA P-256)
# ============================================================================
# This public key is safe to commit - it can only VERIFY signatures.
# The corresponding private key is held exclusively by BigFatDot.
#
# To generate a new key pair (BigFatDot internal only):
#   openssl ecparam -genkey -name prime256v1 -noout -out private_key.pem
#   openssl ec -in private_key.pem -pubout -out public_key.pem
#
EDITION_PUBLIC_KEY = """
-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAENfvC8vsYOXrMgh3NPjjncTtXVTqJ
hdB0+DIOyDZso9EnkAarf6lAXVKVhV07MJU1RCCnMNMpQ/Dm+pt8Itkgdw==
-----END PUBLIC KEY-----
""".strip()

# Minimum SaaS token version (increment to invalidate old tokens after key rotation)
SAAS_TOKEN_VERSION_MIN = 1


# ============================================================================
# Cached Edition State
# ============================================================================
# Edition is determined once at startup and cached for the lifetime of the app.
# This avoids repeated validation and ensures consistent behavior.

_cached_edition: Optional[Edition] = None
_cached_license_payload: Optional[Dict[str, Any]] = None


def _validate_license_key(license_key: str) -> Optional[Dict[str, Any]]:
    """
    Validate an Enterprise LICENSE_KEY (JWT signed with ES256).

    Enterprise licenses are PERPETUAL (no expiration):
    - No 'exp' claim in the JWT
    - Only signature verification required
    - Optional revocation check via order_id

    Args:
        license_key: JWT string from LICENSE_KEY env var

    Returns:
        License payload dict if valid, None if invalid
    """
    if not license_key:
        return None

    try:
        from jose import jwt, JWTError

        # Decode without expiration check first (handle perpetual + timed licenses)
        payload = jwt.decode(
            license_key,
            EDITION_PUBLIC_KEY,
            algorithms=["ES256"],
            options={"verify_exp": False}
        )

        # Verify issuer
        if payload.get("iss") != "bigfatdot.org":
            logger.warning("Invalid issuer in LICENSE_KEY")
            return None

        # Verify edition claim
        if payload.get("edition") != "enterprise":
            logger.warning("Invalid edition in LICENSE_KEY")
            return None

        # If license has an expiration claim, check it manually
        # (perpetual licenses have no "exp" claim)
        import time
        if "exp" in payload:
            if time.time() > payload["exp"]:
                logger.warning(
                    f"Enterprise license expired at {payload['exp']} "
                    f"(org={payload.get('org_name')})"
                )
                return None

        logger.info(
            f"Valid Enterprise license: org={payload.get('org_name')}, "
            f"order={payload.get('order_id')}, "
            f"expires={'never' if 'exp' not in payload else payload['exp']}"
        )
        return payload

    except ImportError:
        logger.error("python-jose not installed, cannot validate LICENSE_KEY")
        return None
    except Exception as e:
        logger.warning(f"Invalid LICENSE_KEY: {e}")
        return None


def _validate_saas_token(saas_token: str) -> bool:
    """
    Validate a Cloud SaaS token.

    The token proves the deployment is authorized by BigFatDot.
    Structure: {"version": 1, "signature": "JWS_TOKEN", "data": {...}}

    The signature is a JWS token containing the serialized data,
    signed with ES256 using BigFatDot's private key.

    Args:
        saas_token: JSON string from SAAS_TOKEN env var

    Returns:
        True if valid, False otherwise
    """
    if not saas_token:
        return False

    try:
        from jose import jwt, JWTError

        token_data = json.loads(saas_token)

        # Check version
        version = token_data.get("version", 0)
        if version < SAAS_TOKEN_VERSION_MIN:
            logger.warning(
                f"SAAS_TOKEN version {version} < minimum {SAAS_TOKEN_VERSION_MIN}"
            )
            return False

        # The signature is a complete JWS token - verify it
        signature = token_data.get("signature")
        if not signature:
            logger.warning("SAAS_TOKEN missing signature")
            return False

        try:
            # Decode and verify the JWS token
            # The payload contains the serialized data
            decoded = jwt.decode(
                signature,
                EDITION_PUBLIC_KEY,
                algorithms=["ES256"],
                options={"verify_exp": False}
            )

            # Verify the decoded data matches what's in the token
            expected_data = token_data.get("data", {})
            if decoded.get("edition") != expected_data.get("edition"):
                logger.warning("SAAS_TOKEN signature/data mismatch")
                return False

        except JWTError as e:
            logger.warning(f"Invalid SAAS_TOKEN signature: {e}")
            return False

        # Verify edition in data
        if token_data.get("data", {}).get("edition") != "cloud_saas":
            logger.warning("Invalid edition in SAAS_TOKEN")
            return False

        logger.info(
            f"Valid SaaS token: domain={token_data.get('data', {}).get('domain')}"
        )
        return True

    except ImportError:
        logger.error("python-jose not installed, cannot validate SAAS_TOKEN")
        return False
    except json.JSONDecodeError:
        logger.warning("SAAS_TOKEN is not valid JSON")
        return False
    except Exception as e:
        logger.warning(f"Invalid SAAS_TOKEN: {e}")
        return False


def _detect_edition() -> Edition:
    """
    Detect the current edition based on environment configuration.

    Detection order:
    1. If EDITION env var is set explicitly, use it (with validation)
    2. If SAAS_TOKEN is present and valid → CLOUD_SAAS
    3. If LICENSE_KEY is present and valid → ENTERPRISE
    4. Otherwise → COMMUNITY (default)

    Returns:
        Detected Edition enum value
    """
    global _cached_license_payload

    from .config import settings

    # 1. Explicit override
    if settings.EDITION:
        explicit = settings.EDITION.lower()
        if explicit == "cloud_saas":
            if settings.SAAS_TOKEN and _validate_saas_token(settings.SAAS_TOKEN):
                return Edition.CLOUD_SAAS
            logger.warning("EDITION=cloud_saas but SAAS_TOKEN is invalid, falling back")
        elif explicit == "enterprise":
            payload = _validate_license_key(settings.LICENSE_KEY)
            if payload:
                _cached_license_payload = payload
                return Edition.ENTERPRISE
            logger.warning("EDITION=enterprise but LICENSE_KEY is invalid, falling back")
        elif explicit == "community":
            return Edition.COMMUNITY
        else:
            logger.warning(f"Unknown EDITION value: {explicit}, falling back to auto-detect")

    # 2. Auto-detect: SAAS_TOKEN → CLOUD_SAAS
    if settings.SAAS_TOKEN and _validate_saas_token(settings.SAAS_TOKEN):
        return Edition.CLOUD_SAAS

    # 3. Auto-detect: LICENSE_KEY → ENTERPRISE
    if settings.LICENSE_KEY:
        payload = _validate_license_key(settings.LICENSE_KEY)
        if payload:
            _cached_license_payload = payload
            return Edition.ENTERPRISE

    # 4. Default: COMMUNITY
    return Edition.COMMUNITY


@lru_cache()
def get_edition() -> Edition:
    """
    Get the current edition.

    This function is cached - the edition is determined once at startup.
    Subsequent calls return the cached value.

    Returns:
        Current Edition enum value
    """
    global _cached_edition

    if _cached_edition is None:
        _cached_edition = _detect_edition()
        logger.info(f"BigMCP Edition: {_cached_edition.value}")

    return _cached_edition


def get_license_payload() -> Optional[Dict[str, Any]]:
    """
    Get the cached license payload (Enterprise edition only).

    Returns:
        License payload dict if Enterprise edition, None otherwise
    """
    # Ensure edition is detected (populates _cached_license_payload)
    get_edition()
    return _cached_license_payload


def get_license_org_name() -> Optional[str]:
    """Get organization name from Enterprise license."""
    payload = get_license_payload()
    return payload.get("org_name") if payload else None


def get_license_features() -> List[str]:
    """Get feature list from Enterprise license."""
    payload = get_license_payload()
    return payload.get("features", []) if payload else []


def has_feature(feature: str) -> bool:
    """
    Check if a feature is available in the current edition.

    Args:
        feature: Feature identifier (e.g., "sso", "saml", "unlimited_users")

    Returns:
        True if feature is available, False otherwise
    """
    edition = get_edition()

    # Cloud SaaS has all features
    if edition == Edition.CLOUD_SAAS:
        return True

    # Enterprise has features from license
    if edition == Edition.ENTERPRISE:
        return feature in get_license_features()

    # Community has no premium features
    return False


def is_saas() -> bool:
    """Check if running as Cloud SaaS edition."""
    return get_edition() == Edition.CLOUD_SAAS


def is_enterprise() -> bool:
    """Check if running as Enterprise edition."""
    return get_edition() == Edition.ENTERPRISE


def is_community() -> bool:
    """Check if running as Community edition."""
    return get_edition() == Edition.COMMUNITY


# ============================================================================
# Edition Limits
# ============================================================================

def get_max_users() -> int:
    """
    Get maximum number of users for current edition.

    Returns:
        User limit (1 for Community, unlimited for others)
    """
    edition = get_edition()

    if edition == Edition.COMMUNITY:
        return 1
    elif edition == Edition.ENTERPRISE:
        return 999999  # Effectively unlimited
    else:  # CLOUD_SAAS
        # SaaS uses subscription-based limits, not edition limits
        return 999999


def get_max_organizations() -> int:
    """
    Get maximum number of organizations for current edition.

    Returns:
        Organization limit (1 for Community, unlimited for others)
    """
    edition = get_edition()

    if edition == Edition.COMMUNITY:
        return 1
    else:
        return 999999  # Effectively unlimited
