"""
OAuth 2.0 Service - Authorization Code Flow implementation.

Handles OAuth client registration, authorization code generation,
and token exchange for third-party integrations like Claude Desktop.
"""

import secrets
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.oauth import OAuthClient, AuthorizationCode
from ..models.user import User
from ..models.organization import Organization
from .auth_service import AuthService


class OAuthService:
    """
    Service for OAuth 2.0 Authorization Code Flow.

    Provides methods for:
    - OAuth client registration and management
    - Authorization code generation
    - Code validation and exchange for tokens
    - PKCE support for public clients
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.auth_service = AuthService(db)

    # ===== Client Management =====

    async def create_client(
        self,
        name: str,
        redirect_uris: List[str],
        description: Optional[str] = None,
        allowed_scopes: Optional[List[str]] = None,
        is_trusted: bool = False
    ) -> OAuthClient:
        """
        Register a new OAuth client.

        Args:
            name: Client application name (e.g., "Claude Desktop")
            redirect_uris: List of allowed redirect URIs
            description: Optional description
            allowed_scopes: Scopes this client can request
            is_trusted: Whether to skip consent screen

        Returns:
            OAuthClient: Created client with client_id and client_secret
        """
        # Generate secure client credentials
        client_id = f"client_{secrets.token_urlsafe(32)}"
        client_secret = secrets.token_urlsafe(48)

        # Hash the client secret (similar to password hashing)
        client_secret_hash = self.auth_service.hash_password(client_secret)

        client = OAuthClient(
            client_id=client_id,
            client_secret=client_secret_hash,
            name=name,
            description=description,
            redirect_uris=redirect_uris,
            allowed_scopes=allowed_scopes or ["mcp:execute", "mcp:read", "mcp:write", "offline_access"],
            is_trusted=is_trusted,
            is_active=True
        )

        self.db.add(client)
        await self.db.commit()
        await self.db.refresh(client)

        # Return the plain client_secret ONLY on creation
        # (won't be accessible again)
        client.plaintext_secret = client_secret

        return client

    async def get_client_by_id(self, client_id: str) -> Optional[OAuthClient]:
        """
        Get OAuth client by client_id.

        Args:
            client_id: OAuth client ID

        Returns:
            OAuthClient if found, None otherwise
        """
        result = await self.db.execute(
            select(OAuthClient).where(
                OAuthClient.client_id == client_id,
                OAuthClient.is_active == True
            )
        )
        return result.scalar_one_or_none()

    async def validate_client_credentials(
        self,
        client_id: str,
        client_secret: str
    ) -> Optional[OAuthClient]:
        """
        Validate client credentials.

        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret

        Returns:
            OAuthClient if valid, None otherwise
        """
        client = await self.get_client_by_id(client_id)
        if not client:
            return None

        # Verify client secret (like password verification)
        if not self.auth_service.verify_password(client_secret, client.client_secret):
            return None

        return client

    def validate_redirect_uri(self, client: OAuthClient, redirect_uri: str) -> bool:
        """
        Validate that redirect_uri is registered for this client.

        Args:
            client: OAuthClient
            redirect_uri: Redirect URI to validate

        Returns:
            True if valid, False otherwise
        """
        return redirect_uri in client.redirect_uris

    # ===== Authorization Code Management =====

    async def create_authorization_code(
        self,
        client: OAuthClient,
        user: User,
        organization: Organization,
        redirect_uri: str,
        scopes: List[str],
        code_challenge: Optional[str] = None,
        code_challenge_method: Optional[str] = None,
        expires_in_minutes: int = 5
    ) -> AuthorizationCode:
        """
        Create an authorization code.

        Args:
            client: OAuth client
            user: User authorizing access
            organization: Organization context
            redirect_uri: Redirect URI for this authorization
            scopes: Granted scopes
            code_challenge: PKCE code challenge (optional)
            code_challenge_method: PKCE method (S256 or plain)
            expires_in_minutes: Code expiration time (default 5 min)

        Returns:
            AuthorizationCode
        """
        # Generate secure random code
        code = secrets.token_urlsafe(32)

        # Calculate expiration
        expires_at = datetime.utcnow() + timedelta(minutes=expires_in_minutes)

        auth_code = AuthorizationCode(
            code=code,
            client_id=client.id,
            user_id=user.id,
            organization_id=organization.id,
            redirect_uri=redirect_uri,
            scopes=scopes,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            expires_at=expires_at,
            is_used=False
        )

        self.db.add(auth_code)
        await self.db.commit()
        await self.db.refresh(auth_code)

        return auth_code

    async def get_authorization_code(self, code: str) -> Optional[AuthorizationCode]:
        """
        Get authorization code by code string.

        Args:
            code: Authorization code

        Returns:
            AuthorizationCode if found, None otherwise
        """
        result = await self.db.execute(
            select(AuthorizationCode).where(AuthorizationCode.code == code)
        )
        return result.scalar_one_or_none()

    async def validate_and_consume_code(
        self,
        code: str,
        client_id: str,
        redirect_uri: str,
        code_verifier: Optional[str] = None
    ) -> Optional[AuthorizationCode]:
        """
        Validate and consume an authorization code.

        Args:
            code: Authorization code
            client_id: Client ID (must match)
            redirect_uri: Redirect URI (must match)
            code_verifier: PKCE code verifier (if PKCE was used)

        Returns:
            AuthorizationCode if valid, None otherwise
        """
        auth_code = await self.get_authorization_code(code)

        if not auth_code:
            return None

        # Check if code is valid
        if not auth_code.is_valid():
            return None

        # Verify client_id matches
        client = await self.db.get(OAuthClient, auth_code.client_id)
        if not client or client.client_id != client_id:
            return None

        # Verify redirect_uri matches
        if auth_code.redirect_uri != redirect_uri:
            return None

        # Verify PKCE if required
        if auth_code.code_challenge:
            if not code_verifier:
                return None

            if not self._verify_pkce(
                code_verifier,
                auth_code.code_challenge,
                auth_code.code_challenge_method
            ):
                return None

        # Mark as used
        auth_code.is_used = True
        auth_code.used_at = datetime.utcnow()
        await self.db.commit()

        return auth_code

    def _verify_pkce(
        self,
        code_verifier: str,
        code_challenge: str,
        method: Optional[str] = "S256"
    ) -> bool:
        """
        Verify PKCE code challenge.

        Args:
            code_verifier: Code verifier from client
            code_challenge: Code challenge from authorization request
            method: Challenge method (S256 or plain)

        Returns:
            True if valid, False otherwise
        """
        if method == "S256":
            # SHA-256 hash of verifier, base64url encoded (RFC 7636)
            # code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
            sha256_hash = hashlib.sha256(code_verifier.encode('ascii')).digest()
            computed_challenge = base64.urlsafe_b64encode(sha256_hash).decode('ascii').rstrip('=')
        else:
            # Plain (not recommended but supported)
            computed_challenge = code_verifier

        return computed_challenge == code_challenge

    async def cleanup_expired_codes(self):
        """
        Clean up expired authorization codes.

        Should be run periodically (e.g., via background task).
        """
        from sqlalchemy import delete

        result = await self.db.execute(
            delete(AuthorizationCode).where(
                AuthorizationCode.expires_at < datetime.utcnow()
            )
        )

        deleted_count = result.rowcount
        await self.db.commit()

        return deleted_count
