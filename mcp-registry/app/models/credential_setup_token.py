"""
Credential Setup Token Model.

Generates secure temporary links for credential configuration.
Used when the assistant detects missing credentials.
"""

import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, JSON, Boolean, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin, TimestampMixin


class CredentialSetupToken(Base, UUIDMixin, TimestampMixin):
    """
    Secure token for credential configuration via web link.

    Flow:
    1. Assistant detects missing credentials
    2. Generates a token with `create_token()`
    3. Returns link: https://mcphub.app/setup/{token}
    4. User clicks, configures credentials
    5. Token consumed and invalidated
    """

    __tablename__ = "credential_setup_tokens"

    # Token (URL-safe, 32 bytes = 43 chars base64)
    token: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="URL-safe token for credential setup"
    )

    # Ownership
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who will configure credentials"
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Organization context"
    )

    # Context
    composition_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Associated composition ID (if created from composition)"
    )

    # Required credentials
    required_credentials: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="""
        Structure:
        {
            "servers": [
                {
                    "server_id": "notion",
                    "server_name": "Notion",
                    "credentials": [
                        {
                            "name": "NOTION_API_KEY",
                            "type": "secret",
                            "required": true,
                            "description": "Notion Integration Token",
                            "documentation_url": "https://..."
                        }
                    ]
                }
            ]
        }
        """
    )

    # Callback info
    callback_url: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        comment="URL to redirect after successful setup"
    )

    webhook_url: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        comment="Webhook to notify when credentials configured"
    )

    # State
    is_used: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether token has been consumed"
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="When credentials were successfully configured"
    )

    # Expiration
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
        comment="Token expiration (default: 1 hour)"
    )

    # Metadata
    created_from: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="api",
        comment="Source: 'api', 'assistant', 'web_ui'"
    )

    user_agent: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        comment="User agent of creation request"
    )

    meta: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional context (query, tool calls, etc.)"
    )

    # Note: created_at and updated_at are provided by TimestampMixin

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="credential_setup_tokens")
    organization: Mapped["Organization"] = relationship("Organization", back_populates="credential_setup_tokens")

    @classmethod
    def generate_token(cls) -> str:
        """Generate a secure URL-safe token."""
        return secrets.token_urlsafe(32)

    @classmethod
    def create_token(
        cls,
        user_id: UUID,
        organization_id: UUID,
        required_credentials: Dict[str, Any],
        composition_id: Optional[str] = None,
        callback_url: Optional[str] = None,
        webhook_url: Optional[str] = None,
        expires_in_seconds: int = 3600,  # 1 hour default
        created_from: str = "api",
        metadata: Optional[Dict[str, Any]] = None
    ) -> "CredentialSetupToken":
        """
        Factory method to create a new credential setup token.

        Args:
            user_id: User who will configure credentials
            organization_id: Organization context
            required_credentials: Credential specifications
            composition_id: Optional composition ID
            callback_url: Where to redirect after success
            webhook_url: Webhook to notify on completion
            expires_in_seconds: Token lifetime (default 1h)
            created_from: Source of creation
            metadata: Additional context

        Returns:
            New CredentialSetupToken instance
        """
        token = cls.generate_token()
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)

        return cls(
            token=token,
            user_id=user_id,
            organization_id=organization_id,
            required_credentials=required_credentials,
            composition_id=composition_id,
            callback_url=callback_url,
            webhook_url=webhook_url,
            expires_at=expires_at,
            created_from=created_from,
            meta=metadata or {}
        )

    @property
    def is_valid(self) -> bool:
        """Check if token is still valid (not used and not expired)."""
        if self.is_used:
            return False
        if datetime.utcnow() > self.expires_at:
            return False
        return True

    @property
    def setup_url(self) -> str:
        """Generate the full setup URL."""
        # TODO: Get base URL from config
        base_url = "https://mcphub.app"  # Or from environment
        return f"{base_url}/setup/{self.token}"

    def mark_as_used(self) -> None:
        """Mark token as consumed."""
        self.is_used = True
        self.completed_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "token": self.token,
            "setup_url": self.setup_url,
            "composition_id": self.composition_id,
            "required_credentials": self.required_credentials,
            "is_used": self.is_used,
            "is_valid": self.is_valid,
            "expires_at": self.expires_at.isoformat(),
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }
