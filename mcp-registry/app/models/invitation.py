"""
Invitation model for organization member invitations.

Tracks pending invitations with expiration and status.
"""

import enum
import secrets
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import String, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin, TimestampMixin


class InvitationStatus(str, enum.Enum):
    """Status of an invitation."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    REVOKED = "revoked"


class Invitation(Base, UUIDMixin, TimestampMixin):
    """
    Organization invitation model.

    Tracks pending invitations to join an organization.
    Invitations expire after a configurable period.
    """

    __tablename__ = "invitations"

    # Foreign keys
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    invited_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # Invitation details
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Status - stored as String, validated by Python enum
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=InvitationStatus.PENDING.value
    )

    # Expiration
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    # Tracking
    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    accepted_user_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        foreign_keys=[organization_id]
    )

    inviter: Mapped["User"] = relationship(
        "User",
        foreign_keys=[invited_by]
    )

    accepted_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[accepted_user_id]
    )

    @classmethod
    def generate_token(cls) -> str:
        """Generate a secure invitation token."""
        return secrets.token_urlsafe(32)

    @classmethod
    def create_invitation(
        cls,
        organization_id: UUID,
        invited_by: UUID,
        email: str,
        role: str = "member",
        message: Optional[str] = None,
        expires_in_days: int = 7
    ) -> "Invitation":
        """Create a new invitation with generated token."""
        return cls(
            organization_id=organization_id,
            invited_by=invited_by,
            email=email.lower(),
            token=cls.generate_token(),
            role=role,
            message=message,
            status=InvitationStatus.PENDING.value,
            expires_at=datetime.utcnow() + timedelta(days=expires_in_days)
        )

    @property
    def is_expired(self) -> bool:
        """Check if invitation has expired."""
        return datetime.utcnow() > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if invitation is still valid (pending and not expired)."""
        return self.status == InvitationStatus.PENDING.value and not self.is_expired

    def __repr__(self) -> str:
        return f"<Invitation(org={self.organization_id}, email={self.email}, status={self.status})>"
