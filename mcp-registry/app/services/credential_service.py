"""
Credential Service - Hierarchical credential management.

Manages user and organization credentials with proper hierarchy:
- User credentials override organization credentials
- Organization credentials are shared and hidden from regular users
- Credentials are encrypted at rest
- Audit trail for all credential access operations

Security:
- All credential access (decryption) is logged to the audit trail
- Supports RGPD Article 30 compliance for processing records
"""

import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.user_credential import UserCredential, OrganizationCredential
from ..models.mcp_server import MCPServer
from ..models.user import User
from ..models.audit_log import AuditLog, AuditAction
from ..core.secrets_manager import get_secrets_manager


class CredentialService:
    """
    Service for managing hierarchical credentials.

    Hierarchy:
    1. User-level credentials (personal, highest priority)
    2. Organization-level credentials (shared, fallback)

    Audit:
    All credential access (decryption) is logged for compliance.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.secrets_manager = get_secrets_manager()

    async def _log_credential_access(
        self,
        actor_id: UUID,
        organization_id: UUID,
        credential_id: UUID,
        server_id: UUID,
        credential_type: str,
        source: str
    ) -> None:
        """
        Log credential access to the audit trail.

        This is called every time credentials are decrypted for use.
        Supports RGPD Article 30 compliance.

        Args:
            actor_id: User accessing the credentials
            organization_id: Organization context
            credential_id: UUID of the credential record
            server_id: MCP server the credential is for
            credential_type: "user" or "organization"
            source: How credentials were resolved ("user", "organization", "merged")
        """
        try:
            log_entry = AuditLog(
                timestamp=datetime.utcnow(),
                actor_id=actor_id,
                organization_id=organization_id,
                action=AuditAction.CREDENTIAL_ACCESS.value,
                resource_type="credential",
                resource_id=str(credential_id),
                details={
                    "server_id": str(server_id),
                    "credential_type": credential_type,
                    "resolution_source": source
                }
            )

            # Calculate signature for tamper detection
            from ..core.config import get_settings
            settings = get_settings()
            log_entry.signature = log_entry.calculate_signature(settings.SECRET_KEY)

            self.db.add(log_entry)
            # Don't commit here - let the caller's transaction handle it
            # This ensures atomic operations

            logger.debug(
                f"Credential access logged: user={actor_id}, "
                f"credential={credential_id}, server={server_id}"
            )

        except Exception as e:
            # Log but don't fail the credential resolution
            logger.error(f"Failed to log credential access: {e}", exc_info=True)

    # ==================== User Credentials ====================

    async def create_user_credential(
        self,
        user_id: UUID,
        server_id: UUID,
        organization_id: UUID,
        credentials: Dict[str, Any],
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> UserCredential:
        """
        Create user-specific credentials for an MCP server.

        Args:
            user_id: User UUID
            server_id: MCP server UUID
            organization_id: Organization UUID
            credentials: Dictionary of environment variables (e.g., {"API_KEY": "secret"})
            name: Optional name for this credential set
            description: Optional description

        Returns:
            UserCredential object

        Raises:
            ValueError: If server doesn't exist or credentials already exist
        """
        # Verify server exists
        server = await self.db.get(MCPServer, server_id)
        if not server:
            raise ValueError(f"MCP server {server_id} not found")

        # Check for existing credentials
        existing = await self._get_user_credential(user_id, server_id)
        if existing:
            raise ValueError(
                f"User credentials already exist for server {server_id}. "
                f"Use update_user_credential() instead."
            )

        # Create credential object
        credential = UserCredential(
            user_id=user_id,
            server_id=server_id,
            organization_id=organization_id,
            name=name,
            description=description,
            is_active=True
        )

        # Encrypt and set credentials
        credential.credentials = credentials

        self.db.add(credential)
        await self.db.commit()
        await self.db.refresh(credential)

        return credential

    async def update_user_credential(
        self,
        user_id: UUID,
        server_id: UUID,
        credentials: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> UserCredential:
        """
        Update user credentials.

        Args:
            user_id: User UUID
            server_id: MCP server UUID
            credentials: New credentials (if provided)
            name: New name (if provided)
            description: New description (if provided)
            is_active: New active status (if provided)

        Returns:
            Updated UserCredential object

        Raises:
            ValueError: If credentials don't exist
        """
        credential = await self._get_user_credential(user_id, server_id)
        if not credential:
            raise ValueError(
                f"User credentials not found for server {server_id}. "
                f"Use create_user_credential() instead."
            )

        # Update fields
        if credentials is not None:
            credential.credentials = credentials
        if name is not None:
            credential.name = name
        if description is not None:
            credential.description = description
        if is_active is not None:
            credential.is_active = is_active

        await self.db.commit()
        await self.db.refresh(credential)

        return credential

    async def delete_user_credential(
        self,
        user_id: UUID,
        server_id: UUID
    ) -> None:
        """
        Delete user credentials by server_id.

        Args:
            user_id: User UUID
            server_id: MCP server UUID

        Raises:
            ValueError: If credentials don't exist
        """
        credential = await self._get_user_credential(user_id, server_id)
        if not credential:
            raise ValueError(f"User credentials not found for server {server_id}")

        await self.db.delete(credential)
        await self.db.commit()

    async def delete_user_credential_by_id(
        self,
        user_id: UUID,
        credential_id: UUID
    ) -> None:
        """
        Delete user credentials by credential ID.

        This method is preferred for multi-instance scenarios where
        a user may have multiple credentials for different instances
        of the same service.

        Also deletes the associated MCP server if no other credentials exist for it.

        Args:
            user_id: User UUID (for ownership verification)
            credential_id: The UUID of the credential record itself

        Raises:
            ValueError: If credentials don't exist or don't belong to user
        """
        from app.models.mcp_server import MCPServer

        query = select(UserCredential).where(
            and_(
                UserCredential.id == credential_id,
                UserCredential.user_id == user_id
            )
        )
        result = await self.db.execute(query)
        credential = result.scalar_one_or_none()

        if not credential:
            raise ValueError(f"Credential {credential_id} not found or does not belong to user")

        # Store server_id before deleting credential
        server_id = credential.server_id

        # Delete the credential
        await self.db.delete(credential)
        await self.db.commit()

        # Check if any other credentials exist for this server
        other_creds_query = select(UserCredential).where(
            UserCredential.server_id == server_id
        ).limit(1)
        other_creds_result = await self.db.execute(other_creds_query)
        has_other_creds = other_creds_result.scalar_one_or_none() is not None

        # Also check for org credentials
        org_creds_query = select(OrganizationCredential).where(
            OrganizationCredential.server_id == server_id
        ).limit(1)
        org_creds_result = await self.db.execute(org_creds_query)
        has_org_creds = org_creds_result.scalar_one_or_none() is not None

        # If no credentials exist, delete the MCP server
        if not has_other_creds and not has_org_creds:
            server_query = select(MCPServer).where(MCPServer.id == server_id)
            server_result = await self.db.execute(server_query)
            server = server_result.scalar_one_or_none()
            if server:
                logger.info(f"Deleting orphan MCP server: {server.server_id}")
                await self.db.delete(server)
                await self.db.commit()

    async def get_user_credential_by_id(
        self,
        user_id: UUID,
        credential_id: UUID
    ) -> Optional[UserCredential]:
        """
        Get a user credential by its ID.

        Args:
            user_id: User UUID (for ownership verification)
            credential_id: The UUID of the credential record

        Returns:
            UserCredential if found and belongs to user, None otherwise
        """
        query = select(UserCredential).where(
            and_(
                UserCredential.id == credential_id,
                UserCredential.user_id == user_id
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_user_credentials(
        self,
        user_id: UUID,
        organization_id: UUID,
        include_inactive: bool = False
    ) -> List[UserCredential]:
        """
        Get all credentials for a user.

        Args:
            user_id: User UUID
            organization_id: Organization UUID
            include_inactive: Whether to include inactive credentials

        Returns:
            List of UserCredential objects
        """
        query = select(UserCredential).where(
            and_(
                UserCredential.user_id == user_id,
                UserCredential.organization_id == organization_id
            )
        )

        if not include_inactive:
            query = query.where(UserCredential.is_active == True)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _get_user_credential(
        self,
        user_id: UUID,
        server_id: UUID
    ) -> Optional[UserCredential]:
        """Get user credential by user_id and server_id."""
        query = select(UserCredential).where(
            and_(
                UserCredential.user_id == user_id,
                UserCredential.server_id == server_id
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    # ==================== Organization Credentials ====================

    async def create_org_credential(
        self,
        organization_id: UUID,
        server_id: UUID,
        credentials: Dict[str, Any],
        name: str,
        description: Optional[str] = None,
        visible_to_users: bool = False,
        created_by: Optional[UUID] = None
    ) -> OrganizationCredential:
        """
        Create organization-level shared credentials for an MCP server.

        Args:
            organization_id: Organization UUID
            server_id: MCP server UUID
            credentials: Dictionary of environment variables
            name: Name for this credential set (required)
            description: Optional description
            visible_to_users: Whether users can see that org credentials exist
            created_by: UUID of admin creating the credentials

        Returns:
            OrganizationCredential object

        Raises:
            ValueError: If server doesn't exist or credentials already exist
        """
        # Verify server exists
        server = await self.db.get(MCPServer, server_id)
        if not server:
            raise ValueError(f"MCP server {server_id} not found")

        # Check for existing credentials
        existing = await self._get_org_credential(organization_id, server_id)
        if existing:
            raise ValueError(
                f"Organization credentials already exist for server {server_id}. "
                f"Use update_org_credential() instead."
            )

        # Create credential object
        credential = OrganizationCredential(
            organization_id=organization_id,
            server_id=server_id,
            name=name,
            description=description,
            visible_to_users=visible_to_users,
            is_active=True,
            created_by=created_by,
            usage_count=0
        )

        # Encrypt and set credentials
        credential.credentials = credentials

        self.db.add(credential)
        await self.db.commit()
        await self.db.refresh(credential)

        return credential

    async def update_org_credential(
        self,
        organization_id: UUID,
        server_id: UUID,
        credentials: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        visible_to_users: Optional[bool] = None,
        is_active: Optional[bool] = None,
        updated_by: Optional[UUID] = None
    ) -> OrganizationCredential:
        """
        Update organization credentials.

        Args:
            organization_id: Organization UUID
            server_id: MCP server UUID
            credentials: New credentials (if provided)
            name: New name (if provided)
            description: New description (if provided)
            visible_to_users: New visibility setting (if provided)
            is_active: New active status (if provided)
            updated_by: UUID of admin updating the credentials

        Returns:
            Updated OrganizationCredential object

        Raises:
            ValueError: If credentials don't exist
        """
        credential = await self._get_org_credential(organization_id, server_id)
        if not credential:
            raise ValueError(
                f"Organization credentials not found for server {server_id}. "
                f"Use create_org_credential() instead."
            )

        # Update fields
        if credentials is not None:
            credential.credentials = credentials
        if name is not None:
            credential.name = name
        if description is not None:
            credential.description = description
        if visible_to_users is not None:
            credential.visible_to_users = visible_to_users
        if is_active is not None:
            credential.is_active = is_active
        if updated_by is not None:
            credential.updated_by = updated_by

        await self.db.commit()
        await self.db.refresh(credential)

        return credential

    async def delete_org_credential(
        self,
        organization_id: UUID,
        server_id: UUID
    ) -> None:
        """
        Delete organization credentials.

        Args:
            organization_id: Organization UUID
            server_id: MCP server UUID

        Raises:
            ValueError: If credentials don't exist
        """
        credential = await self._get_org_credential(organization_id, server_id)
        if not credential:
            raise ValueError(f"Organization credentials not found for server {server_id}")

        await self.db.delete(credential)
        await self.db.commit()

    async def get_org_credentials(
        self,
        organization_id: UUID,
        include_inactive: bool = False
    ) -> List[OrganizationCredential]:
        """
        Get all organization credentials.

        Args:
            organization_id: Organization UUID
            include_inactive: Whether to include inactive credentials

        Returns:
            List of OrganizationCredential objects
        """
        query = select(OrganizationCredential).where(
            OrganizationCredential.organization_id == organization_id
        ).options(selectinload(OrganizationCredential.server))

        if not include_inactive:
            query = query.where(OrganizationCredential.is_active == True)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _get_org_credential(
        self,
        organization_id: UUID,
        server_id: UUID
    ) -> Optional[OrganizationCredential]:
        """Get org credential by organization_id and server_id."""
        query = select(OrganizationCredential).where(
            and_(
                OrganizationCredential.organization_id == organization_id,
                OrganizationCredential.server_id == server_id
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    # ==================== Hierarchical Resolution ====================

    async def resolve_credentials(
        self,
        user_id: UUID,
        server_id: UUID,
        organization_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve credentials for a user and server using hierarchy.

        Hierarchy:
        1. User-level credentials (highest priority)
        2. Organization-level credentials (fallback)

        All credential access is logged for audit compliance (RGPD Article 30).

        Args:
            user_id: User UUID
            server_id: MCP server UUID
            organization_id: Organization UUID

        Returns:
            Dictionary of decrypted credentials, or None if no credentials found
        """
        # Try user credentials first
        user_cred = await self._get_user_credential(user_id, server_id)
        if user_cred and user_cred.is_active:
            # Update usage tracking
            user_cred.last_used_at = datetime.utcnow()

            # Log credential access for audit trail
            await self._log_credential_access(
                actor_id=user_id,
                organization_id=organization_id,
                credential_id=user_cred.id,
                server_id=server_id,
                credential_type="user",
                source="user"
            )

            await self.db.commit()
            return user_cred.credentials

        # Fallback to organization credentials
        org_cred = await self._get_org_credential(organization_id, server_id)
        if org_cred and org_cred.is_active:
            # Update usage tracking
            org_cred.last_used_at = datetime.utcnow()
            org_cred.usage_count += 1

            # Log credential access for audit trail
            await self._log_credential_access(
                actor_id=user_id,
                organization_id=organization_id,
                credential_id=org_cred.id,
                server_id=server_id,
                credential_type="organization",
                source="organization"
            )

            await self.db.commit()
            return org_cred.credentials

        # No credentials found
        return None

    async def resolve_credentials_with_mode(
        self,
        user_id: UUID,
        server_id: UUID,
        organization_id: UUID,
        force_org_only: bool = False
    ) -> tuple[Optional[Dict[str, Any]], Optional[str], Optional[UUID]]:
        """
        Resolve credentials with explicit control over hierarchy mode.

        This method supports IAM Delegation (Service Account Mode) where
        compositions can force usage of organization credentials only,
        preventing users from seeing/using their own credentials.

        All credential access is logged for audit compliance (RGPD Article 30).

        Args:
            user_id: User UUID
            server_id: MCP server UUID
            organization_id: Organization UUID
            force_org_only: If True, ONLY use organization credentials (ignore user)

        Returns:
            Tuple of (credentials, source, owner_id):
            - credentials: Dict of decrypted credentials, or None if not found
            - source: "user" | "organization" | None
            - owner_id: UUID of the credential owner (for audit trail)

        Example:
            # Normal mode (User → Org fallback)
            creds, source, owner = await service.resolve_credentials_with_mode(
                user_id, server_id, org_id, force_org_only=False
            )

            # Service Account mode (Org only)
            creds, source, owner = await service.resolve_credentials_with_mode(
                user_id, server_id, org_id, force_org_only=True
            )
            # Returns: (org_creds, "organization", admin_user_id)
        """
        if force_org_only:
            # Force organization credentials ONLY (Service Account Mode)
            org_cred = await self._get_org_credential(organization_id, server_id)
            if org_cred and org_cred.is_active:
                # Update usage tracking
                org_cred.last_used_at = datetime.utcnow()
                org_cred.usage_count += 1

                # Log credential access for audit trail
                await self._log_credential_access(
                    actor_id=user_id,
                    organization_id=organization_id,
                    credential_id=org_cred.id,
                    server_id=server_id,
                    credential_type="organization",
                    source="organization_forced"
                )

                await self.db.commit()

                return (
                    org_cred.credentials,
                    "organization",
                    org_cred.created_by  # Admin who configured the credentials
                )

            # No org credentials found
            return (None, None, None)

        # Normal hierarchy mode (User → Org fallback)
        # Try user credentials first
        user_cred = await self._get_user_credential(user_id, server_id)
        if user_cred and user_cred.is_active:
            # Update usage tracking
            user_cred.last_used_at = datetime.utcnow()

            # Log credential access for audit trail
            await self._log_credential_access(
                actor_id=user_id,
                organization_id=organization_id,
                credential_id=user_cred.id,
                server_id=server_id,
                credential_type="user",
                source="user"
            )

            await self.db.commit()

            return (
                user_cred.credentials,
                "user",
                user_id  # User owns their own credentials
            )

        # Fallback to organization credentials
        org_cred = await self._get_org_credential(organization_id, server_id)
        if org_cred and org_cred.is_active:
            # Update usage tracking
            org_cred.last_used_at = datetime.utcnow()
            org_cred.usage_count += 1

            # Log credential access for audit trail
            await self._log_credential_access(
                actor_id=user_id,
                organization_id=organization_id,
                credential_id=org_cred.id,
                server_id=server_id,
                credential_type="organization",
                source="organization"
            )

            await self.db.commit()

            return (
                org_cred.credentials,
                "organization",
                org_cred.created_by
            )

        # No credentials found
        return (None, None, None)

    async def resolve_credentials_merged(
        self,
        user_id: UUID,
        server_id: UUID,
        organization_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve credentials by MERGING organization and user credentials.

        This is used for Team Services where:
        - Admin pre-configures some credentials (org level)
        - User provides remaining credentials (user level)
        - Both are merged to form complete credentials

        Merge strategy:
        1. Start with organization credentials (base layer)
        2. Overlay user credentials (user values take priority for any overlap)

        All credential access is logged for audit compliance (RGPD Article 30).

        Args:
            user_id: User UUID
            server_id: MCP server UUID
            organization_id: Organization UUID

        Returns:
            Dictionary of merged decrypted credentials, or None if no credentials found
        """
        merged_credentials = {}
        accessed_credentials = []

        # Get organization credentials (base layer)
        org_cred = await self._get_org_credential(organization_id, server_id)
        if org_cred and org_cred.is_active:
            org_credentials = org_cred.credentials or {}
            merged_credentials.update(org_credentials)

            # Update usage tracking
            org_cred.last_used_at = datetime.utcnow()
            org_cred.usage_count += 1

            # Log credential access
            await self._log_credential_access(
                actor_id=user_id,
                organization_id=organization_id,
                credential_id=org_cred.id,
                server_id=server_id,
                credential_type="organization",
                source="merged"
            )

        # Get user credentials (overlay - takes priority)
        user_cred = await self._get_user_credential(user_id, server_id)
        if user_cred and user_cred.is_active:
            user_credentials = user_cred.credentials or {}
            merged_credentials.update(user_credentials)

            # Update usage tracking
            user_cred.last_used_at = datetime.utcnow()

            # Log credential access
            await self._log_credential_access(
                actor_id=user_id,
                organization_id=organization_id,
                credential_id=user_cred.id,
                server_id=server_id,
                credential_type="user",
                source="merged"
            )

        # Commit usage tracking updates and audit logs
        if merged_credentials:
            await self.db.commit()
            return merged_credentials

        return None

    async def validate_credentials(
        self,
        credential_id: UUID,
        is_user_credential: bool = True
    ) -> None:
        """
        Mark credentials as validated.

        This should be called after successfully testing credentials
        (e.g., after successfully starting an MCP server).

        Args:
            credential_id: Credential UUID
            is_user_credential: True for UserCredential, False for OrganizationCredential
        """
        if is_user_credential:
            credential = await self.db.get(UserCredential, credential_id)
        else:
            credential = await self.db.get(OrganizationCredential, credential_id)

        if not credential:
            raise ValueError(f"Credential {credential_id} not found")

        credential.is_validated = True
        credential.validated_at = datetime.utcnow()

        await self.db.commit()

    async def get_masked_credentials(
        self,
        user_id: UUID,
        server_id: UUID,
        organization_id: UUID
    ) -> Optional[Dict[str, str]]:
        """
        Get masked credentials for safe display in API responses.

        Uses merged resolution to show all credentials (org + user combined).

        Args:
            user_id: User UUID
            server_id: MCP server UUID
            organization_id: Organization UUID

        Returns:
            Dictionary with masked credential values (e.g., {"API_KEY": "abc***xyz"})
        """
        credentials = await self.resolve_credentials_merged(user_id, server_id, organization_id)
        if not credentials:
            return None

        return self.secrets_manager.mask_credentials(credentials)
