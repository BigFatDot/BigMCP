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
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID

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

    # Permissions & IAM
    PERMISSION_CHANGE = "iam.permission_change"
    ROLE_ASSIGN = "iam.role_assign"
    ROLE_REVOKE = "iam.role_revoke"

    # Data & Export
    DATA_EXPORT = "data.export"
    DATA_IMPORT = "data.import"

    # MCP Servers
    SERVER_CREATE = "server.create"
    SERVER_UPDATE = "server.update"
    SERVER_DELETE = "server.delete"

    # Security Events
    SECURITY_ALERT = "security.alert"
    UNAUTHORIZED_ACCESS = "security.unauthorized_access"


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
        # Construct canonical payload (order matters for verification)
        payload_parts = [
            str(self.id),
            self.timestamp.isoformat() if self.timestamp else "",
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
