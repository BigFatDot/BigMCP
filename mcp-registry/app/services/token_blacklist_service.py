"""
Token Blacklist Service - Hybrid in-memory + database implementation.

Provides fast O(1) token validation with persistent storage for restarts.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Set
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.token_blacklist import TokenBlacklist, BlacklistReason
from ..core.config import settings

logger = logging.getLogger("token_blacklist")


class TokenBlacklistService:
    """
    Hybrid token blacklist with in-memory cache and database persistence.

    - In-memory Set for O(1) lookup on every request
    - Database for persistence across restarts
    - Auto-cleanup of expired tokens
    """

    # Class-level in-memory blacklist (shared across instances)
    _blacklisted_jtis: Set[str] = set()
    _initialized: bool = False
    _cleanup_task: Optional[asyncio.Task] = None

    def __init__(self, db: AsyncSession):
        self.db = db

    @classmethod
    async def initialize(cls, db: AsyncSession) -> None:
        """
        Load blacklisted tokens from database into memory on startup.

        Should be called once during application startup.
        """
        if cls._initialized:
            return

        try:
            # Load non-expired blacklisted JTIs from database
            result = await db.execute(
                select(TokenBlacklist.jti)
                .where(TokenBlacklist.expires_at > datetime.utcnow())
            )
            jtis = result.scalars().all()

            cls._blacklisted_jtis = set(jtis)
            cls._initialized = True

            logger.info(f"Token blacklist initialized with {len(cls._blacklisted_jtis)} entries")

        except Exception as e:
            logger.error(f"Failed to initialize token blacklist: {e}")
            cls._blacklisted_jtis = set()
            cls._initialized = True

    @classmethod
    def is_blacklisted(cls, jti: str) -> bool:
        """
        Check if a token JTI is blacklisted.

        O(1) in-memory lookup - called on every authenticated request.

        Args:
            jti: JWT ID to check

        Returns:
            bool: True if token is blacklisted
        """
        return jti in cls._blacklisted_jtis

    async def blacklist_token(
        self,
        jti: str,
        user_id: Optional[UUID],
        token_type: str,
        expires_at: datetime,
        reason: BlacklistReason = BlacklistReason.LOGOUT
    ) -> bool:
        """
        Add a token to the blacklist.

        Args:
            jti: JWT ID
            user_id: User who owns the token
            token_type: 'access' or 'refresh'
            expires_at: When the token naturally expires
            reason: Why the token is being blacklisted

        Returns:
            bool: True if successfully blacklisted
        """
        try:
            # Add to in-memory set immediately
            self._blacklisted_jtis.add(jti)

            # Persist to database
            blacklist_entry = TokenBlacklist(
                jti=jti,
                user_id=user_id,
                token_type=token_type,
                expires_at=expires_at,
                reason=reason.value
            )

            self.db.add(blacklist_entry)
            await self.db.commit()

            logger.info(f"Token blacklisted: jti={jti[:8]}... reason={reason.value}")
            return True

        except Exception as e:
            # Even if DB fails, keep in memory for this session
            logger.error(f"Failed to persist token blacklist: {e}")
            return False

    async def blacklist_all_user_tokens(
        self,
        user_id: UUID,
        reason: BlacklistReason = BlacklistReason.PASSWORD_CHANGE
    ) -> int:
        """
        Blacklist all active tokens for a user.

        This method uses the tokens_revoked_at timestamp approach:
        - Sets User.tokens_revoked_at to current time
        - All tokens issued before this timestamp become invalid
        - No need to track individual tokens
        - Checked during token validation in AuthService.get_user_from_token()

        Used when user changes password or admin revokes access.

        Args:
            user_id: User whose tokens to blacklist
            reason: Why tokens are being blacklisted

        Returns:
            int: 1 if successful (represents one bulk revocation), 0 on error
        """
        from ..models.user import User

        try:
            result = await self.db.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                logger.warning(f"User {user_id} not found for token revocation")
                return 0

            # Set the revocation timestamp
            user.tokens_revoked_at = datetime.utcnow()
            await self.db.commit()

            logger.info(
                f"All tokens revoked for user {user_id}: {reason.value}. "
                f"Tokens issued before {user.tokens_revoked_at} are now invalid."
            )

            return 1  # One bulk revocation operation

        except Exception as e:
            logger.error(f"Failed to revoke all tokens for user {user_id}: {e}")
            return 0

    async def cleanup_expired(self) -> int:
        """
        Remove expired tokens from blacklist.

        Called periodically to prevent memory/database growth.

        Returns:
            int: Number of entries cleaned up
        """
        try:
            now = datetime.utcnow()

            # Get expired JTIs from database
            result = await self.db.execute(
                select(TokenBlacklist.jti)
                .where(TokenBlacklist.expires_at <= now)
            )
            expired_jtis = result.scalars().all()

            if not expired_jtis:
                return 0

            # Remove from in-memory set
            for jti in expired_jtis:
                self._blacklisted_jtis.discard(jti)

            # Delete from database
            await self.db.execute(
                delete(TokenBlacklist)
                .where(TokenBlacklist.expires_at <= now)
            )
            await self.db.commit()

            logger.info(f"Cleaned up {len(expired_jtis)} expired blacklist entries")
            return len(expired_jtis)

        except Exception as e:
            logger.error(f"Failed to cleanup expired tokens: {e}")
            return 0

    @classmethod
    async def start_cleanup_task(cls, get_db_session) -> None:
        """
        Start background task for periodic cleanup.

        Args:
            get_db_session: Async generator that yields database sessions
        """
        async def cleanup_loop():
            while True:
                try:
                    # Wait for cleanup interval (default: 1 hour)
                    await asyncio.sleep(3600)

                    # Get a new database session
                    async for db in get_db_session():
                        service = cls(db)
                        await service.cleanup_expired()
                        break

                except asyncio.CancelledError:
                    logger.info("Token blacklist cleanup task cancelled")
                    break
                except Exception as e:
                    logger.error(f"Token blacklist cleanup error: {e}")

        cls._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("Token blacklist cleanup task started")

    @classmethod
    def stop_cleanup_task(cls) -> None:
        """Stop the background cleanup task."""
        if cls._cleanup_task:
            cls._cleanup_task.cancel()
            cls._cleanup_task = None
            logger.info("Token blacklist cleanup task stopped")

    @classmethod
    def get_stats(cls) -> dict:
        """Get blacklist statistics."""
        return {
            "initialized": cls._initialized,
            "entries_in_memory": len(cls._blacklisted_jtis),
            "cleanup_task_running": cls._cleanup_task is not None and not cls._cleanup_task.done()
        }
