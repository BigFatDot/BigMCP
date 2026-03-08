"""
Authentication Service - JWT and API Key management.

Handles user authentication, token generation, and API key validation.
"""

import asyncio
import bcrypt
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple
from uuid import UUID, uuid4

from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.config import settings
from ..models.user import User
from ..models.api_key import APIKey
from ..models.organization import OrganizationMember


class AuthService:
    """
    Service for authentication and authorization.

    Provides methods for:
    - User password authentication
    - JWT token generation and validation
    - API key generation and validation
    - Password hashing and verification
    """

    # Precomputed dummy hash for timing attack prevention
    # This is used to ensure consistent response times regardless of user existence
    _DUMMY_HASH = bcrypt.hashpw(b"dummy_password_for_timing", bcrypt.gensalt()).decode('utf-8')

    def __init__(self, db: AsyncSession):
        self.db = db

    # ===== Password Management =====

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password using bcrypt.

        Args:
            password: Plaintext password

        Returns:
            str: Bcrypt hash
        """
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """
        Verify a password against a hash.

        Args:
            password: Plaintext password
            hashed: Bcrypt hash

        Returns:
            bool: True if password matches
        """
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except Exception:
            return False

    @staticmethod
    def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
        """
        Validate password strength based on configured requirements.

        Args:
            password: Password to validate

        Returns:
            tuple: (is_valid, error_message)
        """
        if len(password) < settings.PASSWORD_MIN_LENGTH:
            return False, f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters"

        if settings.PASSWORD_REQUIRE_UPPERCASE and not any(c.isupper() for c in password):
            return False, "Password must contain at least one uppercase letter"

        if settings.PASSWORD_REQUIRE_LOWERCASE and not any(c.islower() for c in password):
            return False, "Password must contain at least one lowercase letter"

        if settings.PASSWORD_REQUIRE_DIGIT and not any(c.isdigit() for c in password):
            return False, "Password must contain at least one digit"

        if settings.PASSWORD_REQUIRE_SPECIAL:
            special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
            if not any(c in special_chars for c in password):
                return False, "Password must contain at least one special character"

        return True, None

    # ===== User Authentication =====

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """
        Authenticate a user with email and password.

        This method uses constant-time comparison to prevent timing attacks.
        Even for non-existent users, a bcrypt verification is performed.

        Args:
            email: User email
            password: Plaintext password

        Returns:
            User: Authenticated user or None
        """
        # Get user by email (eager load organization_memberships for login endpoint)
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.organization_memberships))
            .where(User.email == email)
        )
        user = result.scalar_one_or_none()

        if not user:
            # SECURITY: Run dummy bcrypt to prevent timing attacks
            # This ensures response time is consistent whether user exists or not
            await asyncio.to_thread(self.verify_password, password, self._DUMMY_HASH)
            return None

        # Check if user uses local authentication (not SSO)
        if user.password_hash is None:
            # SECURITY: Run dummy bcrypt even for SSO users
            await asyncio.to_thread(self.verify_password, password, self._DUMMY_HASH)
            return None  # SSO user cannot authenticate with password

        # Verify password (run bcrypt in thread to avoid blocking event loop)
        if not await asyncio.to_thread(self.verify_password, password, user.password_hash):
            return None

        # Update last login
        user.last_login_at = datetime.utcnow()
        await self.db.commit()

        return user

    async def revoke_all_user_sessions(
        self,
        user_id: UUID,
        reason: str = "password_change"
    ) -> bool:
        """
        Revoke all active sessions for a user.

        This sets the tokens_revoked_at timestamp, which invalidates
        all tokens issued before this time. This is more efficient than
        blacklisting individual tokens.

        Use cases:
        - Password change
        - Admin security action
        - User request to log out everywhere
        - Security incident response

        Args:
            user_id: User UUID
            reason: Reason for revocation (for audit logging)

        Returns:
            bool: True if successful
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            return False

        # Set the revocation timestamp
        user.tokens_revoked_at = datetime.utcnow()
        await self.db.commit()

        # Log the action (import here to avoid circular import)
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"All sessions revoked for user {user_id}: {reason}")

        return True

    # ===== JWT Token Management =====

    @staticmethod
    def create_access_token(
        user_id: UUID,
        organization_id: Optional[UUID] = None,
        return_jti: bool = False
    ) -> str | Tuple[str, str, datetime]:
        """
        Create a JWT access token with unique JTI for revocation support.

        Args:
            user_id: User UUID
            organization_id: Optional organization UUID
            return_jti: If True, returns (token, jti, expires_at) tuple

        Returns:
            str: JWT token (if return_jti=False)
            Tuple[str, str, datetime]: (token, jti, expires_at) (if return_jti=True)
        """
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        expire = datetime.utcnow() + expires_delta
        jti = str(uuid4())

        to_encode = {
            "sub": str(user_id),
            "exp": expire,
            "type": "access",
            "jti": jti
        }

        if organization_id:
            to_encode["org_id"] = str(organization_id)

        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

        if return_jti:
            return encoded_jwt, jti, expire
        return encoded_jwt

    @staticmethod
    def create_mfa_token(
        user_id: UUID,
        organization_id: Optional[UUID] = None
    ) -> str:
        """
        Create a short-lived MFA challenge token.

        This token is returned when a user with MFA enabled attempts login.
        It is valid for 5 minutes and can only be used to complete MFA verification.

        Args:
            user_id: User UUID
            organization_id: Optional organization UUID

        Returns:
            str: JWT MFA challenge token
        """
        # Short-lived token: 5 minutes
        expires_delta = timedelta(minutes=5)
        expire = datetime.utcnow() + expires_delta
        jti = str(uuid4())

        to_encode = {
            "sub": str(user_id),
            "exp": expire,
            "type": "mfa_challenge",
            "jti": jti
        }

        if organization_id:
            to_encode["org_id"] = str(organization_id)

        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    @staticmethod
    def create_refresh_token(
        user_id: UUID,
        organization_id: Optional[UUID] = None,
        return_jti: bool = False
    ) -> str | Tuple[str, str, datetime]:
        """
        Create a JWT refresh token (long-lived) with unique JTI.

        Args:
            user_id: User UUID
            organization_id: Optional organization UUID
            return_jti: If True, returns (token, jti, expires_at) tuple

        Returns:
            str: JWT refresh token (if return_jti=False)
            Tuple[str, str, datetime]: (token, jti, expires_at) (if return_jti=True)
        """
        expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        expire = datetime.utcnow() + expires_delta
        jti = str(uuid4())

        to_encode = {
            "sub": str(user_id),
            "exp": expire,
            "type": "refresh",
            "jti": jti
        }

        if organization_id:
            to_encode["org_id"] = str(organization_id)

        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

        if return_jti:
            return encoded_jwt, jti, expire
        return encoded_jwt

    @staticmethod
    def decode_token(token: str) -> Optional[dict]:
        """
        Decode and validate a JWT token.

        Args:
            token: JWT token

        Returns:
            dict: Token payload or None if invalid
        """
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            return payload
        except JWTError:
            return None

    async def get_user_from_token(self, token: str) -> Optional[User]:
        """
        Get user from JWT token.

        Validates token signature, type, checks blacklist, and verifies
        the token wasn't issued before a bulk revocation event.

        Args:
            token: JWT access token

        Returns:
            User: User object or None
        """
        payload = self.decode_token(token)
        if not payload:
            return None

        # Verify token type
        if payload.get("type") != "access":
            return None

        # Check if token is blacklisted (O(1) in-memory check)
        jti = payload.get("jti")
        if jti:
            from .token_blacklist_service import TokenBlacklistService
            if TokenBlacklistService.is_blacklisted(jti):
                return None

        # Get user ID
        user_id_str = payload.get("sub")
        if not user_id_str:
            return None

        try:
            user_id = UUID(user_id_str)
        except ValueError:
            return None

        # Get user from database (eager load organization_memberships to avoid lazy loading issues)
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.organization_memberships))
            .where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            return None

        # Check if token was issued before bulk revocation
        # This invalidates all tokens issued before tokens_revoked_at
        if user.tokens_revoked_at:
            iat = payload.get("iat")
            if iat:
                # iat is Unix timestamp, tokens_revoked_at is datetime
                token_issued_at = datetime.utcfromtimestamp(iat)
                # Make tokens_revoked_at timezone-naive for comparison
                revoked_at = user.tokens_revoked_at.replace(tzinfo=None) if user.tokens_revoked_at.tzinfo else user.tokens_revoked_at
                if token_issued_at < revoked_at:
                    return None  # Token was issued before revocation

        return user

    # ===== API Key Management =====

    async def create_api_key(
        self,
        user_id: UUID,
        organization_id: UUID,
        name: str,
        scopes: list[str],
        tool_group_id: Optional[UUID] = None,
        description: Optional[str] = None,
        expires_at: Optional[datetime] = None
    ) -> tuple[APIKey, str]:
        """
        Create a new API key.

        Args:
            user_id: User UUID
            organization_id: Organization UUID
            name: API key name
            scopes: List of scopes
            tool_group_id: Optional Tool Group restriction
            description: Optional description
            expires_at: Optional expiration date

        Returns:
            tuple: (APIKey object, plaintext_key)
                IMPORTANT: plaintext_key is only returned once!
        """
        # Generate API key
        plaintext_key, key_prefix = APIKey.generate_key()

        # Hash the key (run bcrypt in thread to avoid blocking event loop)
        key_hash = await asyncio.to_thread(APIKey.hash_key, plaintext_key)

        # Create API key object
        api_key = APIKey(
            user_id=user_id,
            organization_id=organization_id,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scopes=scopes,
            tool_group_id=tool_group_id,
            description=description,
            expires_at=expires_at,
            is_active=True
        )

        self.db.add(api_key)
        await self.db.commit()
        await self.db.refresh(api_key)

        return api_key, plaintext_key

    async def validate_api_key(self, key: str) -> Optional[tuple[APIKey, User]]:
        """
        Validate an API key and return associated user.

        Args:
            key: Plaintext API key (e.g., mcphub_sk_abc123...)

        Returns:
            tuple: (APIKey, User) or None if invalid
        """
        # Extract key prefix for quick lookup
        if not key.startswith(settings.API_KEY_PREFIX):
            return None

        key_prefix = key[:20]  # mcphub_sk_abc12345

        # Find API keys with matching prefix
        result = await self.db.execute(
            select(APIKey)
            .where(APIKey.key_prefix == key_prefix)
            .where(APIKey.is_active == True)
        )
        api_keys = result.scalars().all()

        # Try to verify the key against each candidate
        # (There should only be one, but we handle hash collisions gracefully)
        for api_key in api_keys:
            # Run bcrypt in thread to avoid blocking event loop
            if await asyncio.to_thread(api_key.verify_key, key):
                # Check if expired
                if api_key.is_expired:
                    return None

                # Update last used
                api_key.last_used_at = datetime.utcnow()
                await self.db.commit()

                # Get user (eager load organization_memberships to avoid lazy loading issues)
                result = await self.db.execute(
                    select(User)
                    .options(selectinload(User.organization_memberships))
                    .where(User.id == api_key.user_id)
                )
                user = result.scalar_one_or_none()

                if not user:
                    return None

                return api_key, user

        return None

    async def revoke_api_key(self, api_key_id: UUID, user_id: UUID) -> bool:
        """
        Revoke (deactivate) an API key.

        Args:
            api_key_id: API key UUID
            user_id: User UUID (must be owner)

        Returns:
            bool: True if revoked, False if not found or unauthorized
        """
        result = await self.db.execute(
            select(APIKey)
            .where(APIKey.id == api_key_id)
            .where(APIKey.user_id == user_id)
        )
        api_key = result.scalar_one_or_none()

        if not api_key:
            return False

        api_key.is_active = False
        await self.db.commit()
        return True

    async def list_user_api_keys(
        self,
        user_id: UUID,
        organization_id: UUID,
        include_revoked: bool = False
    ) -> list[APIKey]:
        """
        List API keys for a user in an organization.

        Args:
            user_id: User UUID
            organization_id: Organization UUID
            include_revoked: If True, include revoked (inactive) keys

        Returns:
            list[APIKey]: List of API keys
        """
        query = (
            select(APIKey)
            .where(APIKey.user_id == user_id)
            .where(APIKey.organization_id == organization_id)
        )

        # By default, only return active keys
        if not include_revoked:
            query = query.where(APIKey.is_active == True)

        query = query.order_by(APIKey.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ===== Authorization Helpers =====

    async def check_user_org_membership(
        self,
        user_id: UUID,
        organization_id: UUID
    ) -> Optional[OrganizationMember]:
        """
        Check if user is a member of organization.

        Args:
            user_id: User UUID
            organization_id: Organization UUID

        Returns:
            OrganizationMember: Membership or None
        """
        result = await self.db.execute(
            select(OrganizationMember)
            .where(OrganizationMember.user_id == user_id)
            .where(OrganizationMember.organization_id == organization_id)
        )
        return result.scalar_one_or_none()

    async def check_user_admin(self, user_id: UUID, organization_id: UUID) -> bool:
        """
        Check if user is admin of organization.

        Args:
            user_id: User UUID
            organization_id: Organization UUID

        Returns:
            bool: True if user is admin
        """
        membership = await self.check_user_org_membership(user_id, organization_id)
        if not membership:
            return False

        from ..models.organization import UserRole
        return membership.role == UserRole.ADMIN
