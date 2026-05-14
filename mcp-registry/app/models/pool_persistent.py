"""
Persistent pool models (Phase 3).

Two layers on top of the existing ephemeral session pool:

- ``OrgDefaultPoolEntry`` — admin-curated tools/comps that are loaded
  for *every* user of the org at MCP-connect time. Lets the admin set
  a "starter pack" so new agents don't face an empty pool.

- ``UserPersistentPoolEntry`` — per-user pinned tools/comps that
  survive across sessions. The user's ``search`` calls remain
  ephemeral (cleared next session) — pinning makes a tool stick.

Both rows reference EITHER a tool OR a composition (via a CHECK
constraint). When the underlying tool/comp is deleted the row is
cascade-deleted.

These are read by ``load_visible_pool`` (UNION) and don't replace the
existing ``Tool.is_visible_to_oauth_clients`` flag — that flag stays
the canonical "ephemerally loaded" signal that ``search`` writes to.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, TimestampMixin, UUIDMixin


class OrgDefaultPoolEntry(Base, UUIDMixin, TimestampMixin):
    """Admin-managed entry in the org's default pool.

    Every (org, tool|composition) pair shows up in the visible pool of
    every user of the org at MCP-connect time, ahead of anything they
    might add via ``search`` later.
    """

    __tablename__ = "org_default_pool"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("tools.id", ondelete="CASCADE"),
        nullable=True,
    )
    composition_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("compositions.id", ondelete="CASCADE"),
        nullable=True,
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Display order in the admin UI (lower first).",
    )
    added_by_user_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    organization = relationship("Organization", foreign_keys=[organization_id])
    added_by = relationship("User", foreign_keys=[added_by_user_id])

    __table_args__ = (
        CheckConstraint(
            "(tool_id IS NOT NULL AND composition_id IS NULL) "
            "OR (tool_id IS NULL AND composition_id IS NOT NULL)",
            name="ck_org_default_pool_tool_xor_composition",
        ),
        UniqueConstraint(
            "organization_id",
            "tool_id",
            "composition_id",
            name="uq_org_default_pool_per_org_per_entry",
        ),
        Index(
            "ix_org_default_pool_org_position",
            "organization_id",
            "position",
        ),
    )


class UserPersistentPoolEntry(Base, UUIDMixin, TimestampMixin):
    """User-managed pinned entry that survives across sessions.

    Conceptually a per-user shortcut: 'these are my favorites, always
    have them ready'. Last-seen tracking lets the auto-promotion job
    surface candidates for the org default pool later.
    """

    __tablename__ = "user_pool_pin"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("tools.id", ondelete="CASCADE"),
        nullable=True,
    )
    composition_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("compositions.id", ondelete="CASCADE"),
        nullable=True,
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        CheckConstraint(
            "(tool_id IS NOT NULL AND composition_id IS NULL) "
            "OR (tool_id IS NULL AND composition_id IS NOT NULL)",
            name="ck_user_pool_pin_tool_xor_composition",
        ),
        UniqueConstraint(
            "user_id",
            "tool_id",
            "composition_id",
            name="uq_user_pool_pin_per_user_per_entry",
        ),
    )
