"""
Org-scoped marketplace curation (Phase 2).

The global marketplace catalog (~184 servers from npm + GitHub + curated
sources) is the same for every BigMCP instance. But each org wants its own
view: Cerema may want to hide consumer-grade servers and feature its
in-house ones, while another org wants the full catalog.

This table stores per-org override per server. Default behaviour when no
row exists is permissive (show the server) so existing instances keep
working without admin action.

Schema choices
--------------
- ``marketplace_server_id`` is a string, not a FK: the global catalog is
  sourced from ``marketplace_registry.json`` (synced from npm/GitHub),
  not from a DB table, so there is no row to reference.
- ``status`` is an enum with three values:
    APPROVED  : visible, normal display
    FEATURED  : visible + highlighted (admin promotes for visibility)
    HIDDEN    : not visible to non-admin users of this org
- ``featured_order`` lets admins manually sort featured servers; the
  global popularity sort kicks in for everything else.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, TimestampMixin, UUIDMixin


class OrgMarketplaceCurationStatus(str, enum.Enum):
    APPROVED = "approved"
    FEATURED = "featured"
    HIDDEN = "hidden"


class OrgMarketplaceCuration(Base, UUIDMixin, TimestampMixin):
    """One curation decision per (org, marketplace_server)."""

    __tablename__ = "org_marketplace_curation"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    marketplace_server_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Server id from the global marketplace (e.g. 'github', 'notion').",
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=OrgMarketplaceCurationStatus.APPROVED.value,
        comment="approved | featured | hidden",
    )

    featured_order: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="When status=featured, manual sort order. Lower = first.",
    )

    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Admin notes about why this server has this status.",
    )

    curated_by_user_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    organization = relationship("Organization", foreign_keys=[organization_id])
    curated_by = relationship("User", foreign_keys=[curated_by_user_id])

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "marketplace_server_id",
            name="uq_org_marketplace_curation_per_org_per_server",
        ),
        Index(
            "ix_org_marketplace_curation_status",
            "organization_id",
            "status",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<OrgMarketplaceCuration(org={self.organization_id}, "
            f"server={self.marketplace_server_id!r}, status={self.status})>"
        )
