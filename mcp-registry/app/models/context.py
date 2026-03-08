"""
Context model for hierarchical organization structure.

Uses PostgreSQL ltree for efficient hierarchical queries.
Contexts organize tool bindings, compositions, and resources.
"""

from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy import String, Text, ForeignKey, Boolean, Integer, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property

from ..db.base import Base, UUIDMixin, TimestampMixin
from ..db.types import JSONType


class Context(Base, UUIDMixin, TimestampMixin):
    """
    Hierarchical context for organizing resources.

    Uses PostgreSQL ltree extension for efficient tree queries.

    Example hierarchy:
    - root.team_alpha (team workspace)
    - root.team_alpha.project_x (project within team)
    - root.team_alpha.project_x.docs (documents folder)

    Each context can have:
    - Tool bindings (context-specific tool configurations)
    - Compositions (workflows)
    - Webhooks (triggers)
    - Child contexts (sub-folders, sub-projects)
    """

    __tablename__ = "contexts"

    # Organization ownership
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Hierarchical path (ltree)
    # Format: 'root.level1.level2.level3'
    # Example: 'root.team_alpha.project_x.docs'
    path: Mapped[str] = mapped_column(
        String(1000),  # ltree stored as text
        nullable=False,
        index=True,
        comment="Hierarchical path using ltree notation"
    )

    # Context metadata
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable name"
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type: workspace, project, folder, task, document, etc."
    )

    # Parent relationship (redundant with path, but useful for FK)
    parent_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("contexts.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    # Lifecycle management
    ttl_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Time-to-live in seconds (null = permanent)"
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Auto-calculated expiration timestamp"
    )
    archived: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    # Metadata (renamed to meta to avoid SQLAlchemy reserved keyword)
    meta: Mapped[dict] = mapped_column(
        JSONType,
        default={},
        nullable=False,
        comment="Flexible metadata storage"
    )
    created_by: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="contexts"
    )

    parent: Mapped[Optional["Context"]] = relationship(
        "Context",
        remote_side="Context.id",
        back_populates="children"
    )

    children: Mapped[List["Context"]] = relationship(
        "Context",
        back_populates="parent",
        cascade="all, delete-orphan"
    )

    creator: Mapped[Optional["User"]] = relationship("User")

    tool_bindings: Mapped[List["ToolBinding"]] = relationship(
        "ToolBinding",
        back_populates="context",
        cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("organization_id", "path", name="uq_org_context_path"),
    )

    def __repr__(self) -> str:
        return f"<Context(id={self.id}, path={self.path}, type={self.context_type})>"

    @hybrid_property
    def depth(self) -> int:
        """Calculate depth in hierarchy from path."""
        return len(self.path.split('.'))

    @property
    def is_expired(self) -> bool:
        """Check if context has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(self.expires_at.tzinfo) > self.expires_at

    def set_ttl(self, seconds: int):
        """
        Set time-to-live and calculate expiration.

        Args:
            seconds: TTL in seconds
        """
        self.ttl_seconds = seconds
        self.expires_at = datetime.now() + timedelta(seconds=seconds)

    def get_parent_path(self) -> Optional[str]:
        """Get parent path from ltree path."""
        parts = self.path.split('.')
        if len(parts) <= 1:
            return None
        return '.'.join(parts[:-1])

    def get_name_from_path(self) -> str:
        """Extract name from last segment of path."""
        return self.path.split('.')[-1]

    @classmethod
    def build_path(cls, parent_path: Optional[str], segment: str) -> str:
        """
        Build ltree path from parent and segment.

        Args:
            parent_path: Parent's ltree path (or None for root)
            segment: New segment to add (will be sanitized)

        Returns:
            Complete ltree path
        """
        # Sanitize segment (ltree allows only alphanumeric and underscore)
        import re
        segment = re.sub(r'[^a-zA-Z0-9_]', '_', segment.lower())

        if parent_path:
            return f"{parent_path}.{segment}"
        else:
            return segment

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "path": self.path,
            "name": self.name,
            "description": self.description,
            "context_type": self.context_type,
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "depth": self.depth,
            "ttl_seconds": self.ttl_seconds,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_expired": self.is_expired,
            "archived": self.archived,
            "metadata": self.metadata,
            "created_by": str(self.created_by) if self.created_by else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
