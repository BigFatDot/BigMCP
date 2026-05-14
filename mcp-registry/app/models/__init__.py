"""
Database models for MCPHub.

All SQLAlchemy ORM models for the multi-tenant platform.
"""

from .organization import Organization, OrganizationType, OrganizationMember, UserRole
from .user import User, AuthProvider, UserStatus
from .mcp_server import MCPServer, InstallType, ServerStatus
from .context import Context
from .tool import Tool, ToolBinding
from .oauth import (
    OAuthClient,
    AuthorizationCode,
    OAuthClientRegistrationMethod,
    OAuthClientApprovalStatus,
)
from .oauth_session import OAuthSession
from .credential_setup_token import CredentialSetupToken
from .audit_log import AuditLog, AuditAction
from .api_key import APIKey, APIKeyScope
from .refresh_token import RefreshToken
from .license import License, LicenseValidation, LicenseEdition, LicenseType, LicenseStatus
from .subscription import Subscription, SubscriptionTier, SubscriptionStatus
from .token_blacklist import TokenBlacklist, BlacklistReason
from .invitation import Invitation, InvitationStatus
from .password_reset_token import PasswordResetToken
from .email_verification_token import EmailVerificationToken
from .composition import Composition, CompositionStatus
from .public_sector import PublicDomainWhitelist, PublicSectorCategory
from .instance_settings import InstanceSettings

__all__ = [
    # Organizations
    "Organization",
    "OrganizationType",
    "OrganizationMember",
    "UserRole",

    # Users
    "User",
    "AuthProvider",
    "UserStatus",

    # MCP Servers
    "MCPServer",
    "InstallType",
    "ServerStatus",

    # Contexts
    "Context",

    # Tools & Bindings
    "Tool",
    "ToolBinding",

    # OAuth
    "OAuthClient",
    "AuthorizationCode",
    "OAuthClientRegistrationMethod",
    "OAuthClientApprovalStatus",
    "OAuthSession",

    # Discovery & Credentials
    "CredentialSetupToken",

    # Audit & Security
    "AuditLog",
    "AuditAction",

    # Authentication
    "APIKey",
    "APIKeyScope",
    "RefreshToken",

    # Licensing
    "License",
    "LicenseValidation",
    "LicenseEdition",
    "LicenseType",
    "LicenseStatus",

    # Cloud Subscriptions
    "Subscription",
    "SubscriptionTier",
    "SubscriptionStatus",

    # Token Blacklist
    "TokenBlacklist",
    "BlacklistReason",

    # Invitations
    "Invitation",
    "InvitationStatus",

    # Password Reset
    "PasswordResetToken",

    # Email Verification
    "EmailVerificationToken",

    # Compositions
    "Composition",
    "CompositionStatus",

    # Public Sector
    "PublicDomainWhitelist",
    "PublicSectorCategory",

    # Instance configuration (singleton)
    "InstanceSettings",
]
