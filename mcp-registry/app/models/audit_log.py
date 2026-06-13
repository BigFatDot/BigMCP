"""
Immutable Audit Log Model for Security Compliance.

Implements:
- Cryptographic signature (HMAC-SHA256) for tamper detection
- Immutability via SQLAlchemy event listeners
- Comprehensive action tracking for RGPD Article 30 compliance
- PII-sanitized details storage
"""

import enum
import hmac
import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from uuid import UUID


def _canonical_timestamp(ts: Optional[datetime]) -> str:
    """Render a datetime in a canonical UTC-naive ISO 8601 string.

    The signature includes the timestamp. Postgres returns
    timezone-aware datetimes after a row reload, while ``datetime.utcnow()``
    produced naive datetimes at write time — the two ``isoformat()``
    representations differ (no offset vs. ``+00:00``), so signature
    verification would silently fail.

    Normalising to a single representation closes that gap and also
    makes any existing log written before this fix verifiable again
    (the bytes that signed the original payload are reproduced exactly).
    """
    if ts is None:
        return ""
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
    return ts.isoformat()

from sqlalchemy import String, DateTime, event, Index
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, UUIDMixin
from ..db.types import JSONType


class AuditAction(str, enum.Enum):
    """
    Standard audit actions for security tracking.
    Format: {domain}.{action}
    """
    # Authentication
    LOGIN_SUCCESS = "auth.login_success"
    LOGIN_FAILED = "auth.login_failed"
    LOGOUT = "auth.logout"
    USER_REGISTER = "auth.user_register"
    PASSWORD_RESET_REQUEST = "auth.password_reset_request"
    PASSWORD_RESET_CONFIRM = "auth.password_reset_confirm"
    # N0 #2 — close the auth-audit gap on user-driven flows
    TOKEN_REFRESH = "auth.token_refresh"
    CHANGE_PASSWORD = "auth.change_password"
    EMAIL_VERIFY = "auth.email_verify"
    ORGANIZATION_SWITCH = "auth.organization_switch"
    ACCOUNT_DELETE = "auth.account_delete"

    # OAuth 2.0 (authorization server)
    OAUTH_CLIENT_REGISTER = "oauth.client_register"
    OAUTH_CLIENT_CREATE = "oauth.client_create"
    OAUTH_CONSENT_GRANT = "oauth.consent_grant"
    OAUTH_TOKEN_GRANT = "oauth.token_grant"
    OAUTH_TOKEN_REFRESH = "oauth.token_refresh"
    OAUTH_TOKEN_GRANT_FAILED = "oauth.token_grant_failed"

    # OAuth client control (N2.2)
    OAUTH_CLIENT_APPROVE = "oauth.client_approve"
    OAUTH_CLIENT_REJECT = "oauth.client_reject"
    OAUTH_CLIENT_REVOKE = "oauth.client_revoke"
    OAUTH_CIMD_FETCH = "oauth.cimd_fetch"
    OAUTH_CIMD_FETCH_FAILED = "oauth.cimd_fetch_failed"
    POLICY_CHANGED = "instance.policy_changed"

    # Credentials
    CREDENTIAL_CREATE = "credential.create"
    CREDENTIAL_UPDATE = "credential.update"
    CREDENTIAL_DELETE = "credential.delete"
    CREDENTIAL_ACCESS = "credential.access"

    # Compositions / Workflows
    COMPOSITION_CREATE = "composition.create"
    COMPOSITION_EXECUTE = "composition.execute"
    COMPOSITION_PROMOTE = "composition.promote"
    COMPOSITION_DELETE = "composition.delete"
    COMPOSITION_SHARE_REQUEST = "composition.share_request"
    COMPOSITION_SHARE_DIRECT = "composition.share_direct"
    COMPOSITION_SHARE_APPROVE = "composition.share_approve"
    COMPOSITION_SHARE_REJECT = "composition.share_reject"

    # Composition executions (Phase B-0). One value per terminal/
    # transition emitted from the executor and the cancel/resume
    # endpoints. resource_type is always 'composition_execution',
    # resource_id is the execution UUID.
    COMPOSITION_EXECUTION_CREATED   = "composition.execution_created"
    COMPOSITION_EXECUTION_STARTED   = "composition.execution_started"   # queued → running
    COMPOSITION_EXECUTION_SUSPENDED = "composition.execution_suspended"
    COMPOSITION_EXECUTION_RESUMED   = "composition.execution_resumed"
    COMPOSITION_EXECUTION_COMPLETED = "composition.execution_completed"
    COMPOSITION_EXECUTION_FAILED    = "composition.execution_failed"
    COMPOSITION_EXECUTION_CANCELLED = "composition.execution_cancelled"
    COMPOSITION_EXECUTION_EXPIRED   = "composition.execution_expired"
    # B-1.4: cross-user approval flow on a suspended execution
    COMPOSITION_APPROVAL_REQUESTED  = "composition.approval_requested"
    COMPOSITION_APPROVAL_APPROVED   = "composition.approval_approved"
    COMPOSITION_APPROVAL_REJECTED   = "composition.approval_rejected"

    # Permissions & IAM
    PERMISSION_CHANGE = "iam.permission_change"
    ROLE_ASSIGN = "iam.role_assign"
    ROLE_REVOKE = "iam.role_revoke"
    # RBAC enforcement signals (recorded by app/api/rbac.py)
    AUTHORIZATION_DENIED = "iam.authorization_denied"
    CROSS_ORG_INSTANCE_OVERRIDE = "iam.cross_org_instance_override"

    # Data & Export
    DATA_EXPORT = "data.export"
    DATA_IMPORT = "data.import"

    # MCP Servers
    SERVER_CREATE = "server.create"
    SERVER_UPDATE = "server.update"
    SERVER_DELETE = "server.delete"

    # Pool (dynamic OAuth-client tool surface)
    POOL_CLEAR = "pool.clear"
    POOL_LOAD = "pool.load"
    POOL_UNLOAD = "pool.unload"
    POOL_TOOLBOX_LOAD = "pool.toolbox_load"

    # Toolboxes (LLM-first proposals)
    TOOLBOX_PROPOSE = "toolbox.propose"

    # Security Events
    SECURITY_ALERT = "security.alert"
    UNAUTHORIZED_ACCESS = "security.unauthorized_access"
    APIKEY_SCOPE_DENIED = "security.apikey_scope_denied"

    # Instance / Configuration
    SETTINGS_CHANGED = "instance.settings_changed"
    ENCRYPTION_KEY_ROTATED = "instance.encryption_key_rotated"

    # User lifecycle (N1.4)
    USER_SUSPENDED = "user.suspended"
    USER_REACTIVATED = "user.reactivated"
    USER_SOFT_DELETED = "user.soft_deleted"

    # Cross-surface kill switch (N1.3)
    USER_TOKENS_REVOKED = "user.tokens_revoked_all"

    # User-driven connected-apps revocation (N2.4 / Story H)
    CONNECTED_APP_REVOKE = "auth.connected_app_revoke"

    # Sprint 3.A — Self-heal orphan users on login (no personal org)
    ACCOUNT_AUTO_HEAL_ORG = "auth.account_auto_heal_org"

    # SSO / OIDC (Story I.1)
    SSO_LOGIN_SUCCESS = "auth.sso_login_success"
    SSO_LOGIN_FAILED = "auth.sso_login_failed"
    SSO_PROVISION_USER = "auth.sso_provision_user"
    OIDC_AUTO_LINK_ENABLED = "oidc.auto_link_enabled"
    OIDC_AUTO_LINK_USER = "oidc.auto_link_user"
    OIDC_PROVIDER_CREATE = "oidc.provider_create"
    OIDC_PROVIDER_UPDATE = "oidc.provider_update"
    OIDC_PROVIDER_DELETE = "oidc.provider_delete"
    OIDC_GROUP_MAPPING_CHANGED = "oidc.group_mapping_changed"
    INSTANCE_FORCE_SSO_ONLY = "instance.force_sso_only"


class AuditLog(Base, UUIDMixin):
    """
    Immutable audit log for security compliance.

    Features:
    - HMAC-SHA256 signature for tamper detection
    - Event listeners prevent UPDATE/DELETE
    - PII-sanitized details
    - Indexed for query performance

    Compliance:
    - GDPR Article 30 (processing records)
    - RGS Level 2+ (immutable audit)
    """

    __tablename__ = "audit_logs"

    # Timestamp (auto-managed, indexed)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="When the action occurred"
    )

    # Actor (who performed the action)
    actor_id: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        index=True,
        comment="User who performed the action (null for system actions)"
    )

    organization_id: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        index=True,
        comment="Organization context"
    )

    # Action details
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Action type (see AuditAction enum)"
    )

    resource_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Type of resource affected (credential, composition, user, etc.)"
    )

    resource_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="ID of the affected resource"
    )

    # Context
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="IPv4 or IPv6 address"
    )

    user_agent: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        comment="User agent string"
    )

    # Details (PII-sanitized JSON)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONType,
        nullable=True,
        comment="Additional context (PII-sanitized)"
    )

    # Immutability proof
    signature: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="HMAC-SHA256 signature for tamper detection"
    )

    # Note: id and timestamps from UUIDMixin are inherited
    # created_at would be redundant with timestamp, so we use timestamp directly

    # Indexes for common queries
    __table_args__ = (
        Index('idx_audit_actor_timestamp', 'actor_id', 'timestamp'),
        Index('idx_audit_org_timestamp', 'organization_id', 'timestamp'),
        Index('idx_audit_action_timestamp', 'action', 'timestamp'),
        Index('idx_audit_resource', 'resource_type', 'resource_id'),
    )

    def calculate_signature(self, secret_key: str) -> str:
        """
        Generate HMAC-SHA256 signature for this log entry.

        The signature covers all critical fields to detect any tampering.

        Args:
            secret_key: Secret key for HMAC (from environment)

        Returns:
            Hex-encoded HMAC-SHA256 signature
        """
        # Construct canonical payload (order matters for verification).
        # Timestamp is normalised through _canonical_timestamp so that a
        # signature stays valid across the naive→aware reload boundary.
        payload_parts = [
            str(self.id),
            _canonical_timestamp(self.timestamp),
            str(self.actor_id) if self.actor_id else "",
            str(self.organization_id) if self.organization_id else "",
            self.action,
            self.resource_type,
            self.resource_id or "",
            json.dumps(self.details, sort_keys=True) if self.details else ""
        ]

        payload = "|".join(payload_parts)

        return hmac.new(
            secret_key.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def verify_integrity(self, secret_key: str) -> bool:
        """
        Verify that this log entry hasn't been tampered with.

        Args:
            secret_key: Secret key for HMAC verification

        Returns:
            True if signature is valid, False otherwise
        """
        expected_signature = self.calculate_signature(secret_key)
        return hmac.compare_digest(expected_signature, self.signature)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "timestamp": self.timestamp.isoformat(),
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "organization_id": str(self.organization_id) if self.organization_id else None,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "details": self.details,
            # Note: We don't expose the signature in API responses for security
        }


# =============================================================================
# IMMUTABILITY ENFORCEMENT
# =============================================================================

@event.listens_for(AuditLog, 'before_update')
def prevent_audit_update(mapper, connection, target):
    """
    Prevent any UPDATE operations on audit logs.

    Audit logs are append-only. Once written, they must never be modified.
    For archiving, use a separate rotation process, not SQL UPDATE.
    """
    raise RuntimeError(
        "SECURITY ALERT: Attempted to modify immutable audit log. "
        "Audit logs are append-only and cannot be updated after creation. "
        f"Log ID: {target.id}"
    )


@event.listens_for(AuditLog, 'before_delete')
def prevent_audit_delete(mapper, connection, target):
    """
    Prevent any DELETE operations on audit logs.

    Audit logs must be retained for legal/compliance purposes.
    For archiving, use a separate rotation process that moves logs
    to cold storage, not SQL DELETE.
    """
    raise RuntimeError(
        "SECURITY ALERT: Attempted to delete immutable audit log. "
        "Audit logs must be retained for compliance. "
        "Use archival procedures for old logs, not deletion. "
        f"Log ID: {target.id}"
    )
