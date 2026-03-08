"""
Security Audit Service - Immutable audit logging for compliance.

Provides:
- Cryptographically signed audit trails
- Automatic PII sanitization
- Tamper-proof logging
- RGPD Article 30 compliance

Usage:
    from app.services.audit_service import AuditService

    audit = AuditService(db_session)
    await audit.log_action(
        action=AuditAction.CREDENTIAL_CREATE,
        actor_id=user.id,
        organization_id=org.id,
        resource_type="credential",
        resource_id=str(cred.id),
        details={"server": "notion"},
        request_context=request
    )
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit_log import AuditLog, AuditAction
from ..core.pii_sanitizer import PIIDetector
from ..core.config import get_settings

logger = logging.getLogger(__name__)


class AuditService:
    """
    Service for managing immutable audit logs.

    Features:
    - Automatic PII sanitization before storage
    - HMAC-SHA256 signature for tamper detection
    - Context extraction from FastAPI requests
    - Fire-and-forget logging (doesn't fail transactions)

    Compliance:
    - GDPR Article 30 (processing records)
    - RGS Level 2+ (immutable audit)
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize audit service.

        Args:
            db: Async database session
        """
        self.db = db
        self.settings = get_settings()
        self.secret_key = self.settings.SECRET_KEY

    async def log_action(
        self,
        action: AuditAction,
        actor_id: Optional[UUID],
        organization_id: Optional[UUID],
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        request: Optional[Request] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuditLog:
        """
        Log an auditable action.

        This is the main entry point for audit logging.
        All details are automatically sanitized for PII.

        Args:
            action: Action type (from AuditAction enum)
            actor_id: User who performed the action (None for system actions)
            organization_id: Organization context
            resource_type: Type of resource affected
            resource_id: ID of the affected resource
            details: Additional context (will be PII-sanitized)
            request: FastAPI request object (for context extraction)
            ip_address: Manual IP override (if no request)
            user_agent: Manual UA override (if no request)

        Returns:
            Created AuditLog instance

        Example:
            await audit.log_action(
                action=AuditAction.CREDENTIAL_CREATE,
                actor_id=user.id,
                organization_id=org.id,
                resource_type="credential",
                resource_id=str(cred.id),
                details={"server_id": "notion", "name": "Personal"},
                request=request
            )
        """
        try:
            # 1. Extract context from request if provided
            if request:
                ip_address = ip_address or self._extract_ip(request)
                user_agent = user_agent or self._extract_user_agent(request)

            # 2. Sanitize details (PII protection)
            safe_details = None
            if details:
                safe_details = PIIDetector.sanitize_structure(details)

            # 3. Create audit log entry
            log_entry = AuditLog(
                timestamp=datetime.utcnow(),
                actor_id=actor_id,
                organization_id=organization_id,
                action=action.value if isinstance(action, AuditAction) else action,
                resource_type=resource_type,
                resource_id=resource_id,
                ip_address=ip_address,
                user_agent=user_agent,
                details=safe_details
            )

            # 4. Calculate cryptographic signature
            log_entry.signature = log_entry.calculate_signature(self.secret_key)

            # 5. Persist to database
            self.db.add(log_entry)

            # IMPORTANT: Commit immediately for audit logs
            # This ensures logs are written even if the main transaction fails
            await self.db.commit()
            await self.db.refresh(log_entry)

            logger.info(
                f"Audit log created: {action.value if isinstance(action, AuditAction) else action} "
                f"by {actor_id} on {resource_type}/{resource_id}"
            )

            return log_entry

        except Exception as e:
            # Critical: Audit logging failure is serious
            logger.error(f"Failed to create audit log: {e}", exc_info=True)

            # Rollback to avoid corrupting the session
            await self.db.rollback()

            # In production, you might want to:
            # - Write to a fallback file-based log
            # - Send alert to monitoring system
            # - Raise exception to fail the transaction (depends on requirements)

            # For now, we re-raise to make audit failures visible
            raise

    async def log_authentication(
        self,
        success: bool,
        user_id: Optional[UUID],
        organization_id: Optional[UUID],
        method: str,
        request: Optional[Request] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Log authentication attempt (success or failure).

        Args:
            success: Whether authentication succeeded
            user_id: User ID (None if failed)
            organization_id: Organization context
            method: Auth method (password, oauth, api_key, etc.)
            request: FastAPI request
            details: Additional context
        """
        action = AuditAction.LOGIN_SUCCESS if success else AuditAction.LOGIN_FAILED

        audit_details = {"method": method}
        if details:
            audit_details.update(details)

        await self.log_action(
            action=action,
            actor_id=user_id,
            organization_id=organization_id,
            resource_type="authentication",
            resource_id=str(user_id) if user_id else None,
            details=audit_details,
            request=request
        )

    async def log_credential_access(
        self,
        actor_id: UUID,
        organization_id: UUID,
        credential_id: UUID,
        server_id: str,
        request: Optional[Request] = None
    ):
        """
        Log credential access (for sensitive operations tracking).

        Args:
            actor_id: User accessing credentials
            organization_id: Organization context
            credential_id: Credential UUID
            server_id: MCP server identifier
            request: FastAPI request
        """
        await self.log_action(
            action=AuditAction.CREDENTIAL_ACCESS,
            actor_id=actor_id,
            organization_id=organization_id,
            resource_type="credential",
            resource_id=str(credential_id),
            details={"server_id": server_id},
            request=request
        )

    async def log_composition_execution(
        self,
        actor_id: UUID,
        organization_id: UUID,
        composition_id: str,
        status: str,
        request: Optional[Request] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Log composition execution.

        Args:
            actor_id: User executing composition
            organization_id: Organization context
            composition_id: Composition identifier
            status: Execution status (success, failed, etc.)
            request: FastAPI request
            details: Execution details (PII-sanitized)
        """
        audit_details = {"status": status}
        if details:
            audit_details.update(details)

        await self.log_action(
            action=AuditAction.COMPOSITION_EXECUTE,
            actor_id=actor_id,
            organization_id=organization_id,
            resource_type="composition",
            resource_id=composition_id,
            details=audit_details,
            request=request
        )

    async def log_composition_execution_with_iam(
        self,
        actor_id: UUID,
        organization_id: UUID,
        composition_id: str,
        status: str,
        credential_source: Optional[str],
        credential_owner_id: Optional[UUID],
        user_role: Optional[str],
        forced_org_mode: bool,
        request: Optional[Request] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Log composition execution with IAM delegation details.

        This method is used when IAM Delegation (Service Account Mode) is enabled.
        It tracks who executed, with whose credentials, and under what permissions.

        Args:
            actor_id: User executing composition
            organization_id: Organization context
            composition_id: Composition identifier
            status: Execution status (success, failed, etc.)
            credential_source: "user" | "organization" | None
            credential_owner_id: UUID of credential owner (admin who configured org creds)
            user_role: Role of executing user ("owner", "admin", "member", "viewer")
            forced_org_mode: Whether force_org_credentials was enabled
            request: FastAPI request
            details: Additional execution details

        Example:
            await audit.log_composition_execution_with_iam(
                actor_id=user.id,
                organization_id=org.id,
                composition_id="comp-123",
                status="success",
                credential_source="organization",
                credential_owner_id=admin.id,
                user_role="member",
                forced_org_mode=True,
                request=request,
                details={"steps_count": 3, "duration_ms": 1234}
            )
        """
        # Build IAM-enriched audit details
        iam_details = {
            "status": status,
            "credential_source": credential_source,
            "forced_org_mode": forced_org_mode,
            "user_role": user_role,
        }

        # Add credential owner if different from actor (Service Account Mode indicator)
        if credential_owner_id and credential_owner_id != actor_id:
            iam_details["credential_owner_id"] = str(credential_owner_id)
            iam_details["delegation_mode"] = "service_account"
        else:
            iam_details["delegation_mode"] = "user_credentials"

        # Merge with additional details
        if details:
            iam_details.update(details)

        await self.log_action(
            action=AuditAction.COMPOSITION_EXECUTE,
            actor_id=actor_id,
            organization_id=organization_id,
            resource_type="composition",
            resource_id=composition_id,
            details=iam_details,
            request=request
        )

    def _extract_ip(self, request: Request) -> Optional[str]:
        """
        Extract client IP address from request.

        Handles proxy headers (X-Forwarded-For, X-Real-IP).

        Args:
            request: FastAPI request

        Returns:
            IP address or None
        """
        # Check proxy headers first
        if "x-forwarded-for" in request.headers:
            # X-Forwarded-For can contain multiple IPs
            # Format: "client, proxy1, proxy2"
            forwarded = request.headers["x-forwarded-for"].split(",")[0].strip()
            if forwarded:
                return forwarded

        if "x-real-ip" in request.headers:
            return request.headers["x-real-ip"]

        # Fallback to direct client
        if request.client:
            return request.client.host

        return None

    def _extract_user_agent(self, request: Request) -> Optional[str]:
        """
        Extract user agent from request.

        Args:
            request: FastAPI request

        Returns:
            User agent string or None
        """
        return request.headers.get("user-agent")

    async def verify_log_integrity(self, log_id: UUID) -> bool:
        """
        Verify that an audit log hasn't been tampered with.

        Args:
            log_id: Audit log UUID

        Returns:
            True if signature is valid, False otherwise
        """
        log_entry = await self.db.get(AuditLog, log_id)
        if not log_entry:
            return False

        return log_entry.verify_integrity(self.secret_key)


# Singleton pattern for convenience
_audit_service_instance = None


def get_audit_service(db: AsyncSession) -> AuditService:
    """
    Get or create audit service instance.

    Args:
        db: Async database session

    Returns:
        AuditService instance
    """
    # Note: We don't cache the service because it needs a fresh db session
    return AuditService(db)
