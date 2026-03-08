"""
Tool Group models for creating specialized AI agents.

Allows users to create logical groupings of tools and compositions
for specialized use cases (read-only agent, data analysis agent, etc.)
"""

import enum
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from sqlalchemy import String, Text, ForeignKey, Boolean, Integer, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin, TimestampMixin
from ..db.types import JSONType


class ToolGroupVisibility(str, enum.Enum):
    """Visibility level for Tool Groups."""
    PRIVATE = "private"  # Only owner can see/use
    ORGANIZATION = "organization"  # All org members can see/use
    PUBLIC = "public"  # Anyone can see (future: marketplace)


class ToolGroup(Base, UUIDMixin, TimestampMixin):
    """
    A logical grouping of tools for specialized AI agents.

    Tool Groups allow users to create specialized agents by:
    - Selecting specific tools (e.g., only read operations)
    - Selecting specific compositions (e.g., pre-built workflows)
    - Combining both tools and compositions

    Examples:
        - "Read-Only Agent": Only tools that read data (no writes)
        - "Data Analysis Agent": Only tools for data processing and visualization
        - "GitHub Manager": Only GitHub-related tools
        - "Customer Support": Specific tools + compositions for support workflows
    """

    __tablename__ = "tool_groups"

    # Ownership
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who created this Tool Group"
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Organization (for multi-tenancy)"
    )

    # Basic info
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Name of the Tool Group (e.g., 'Read-Only Agent')"
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Description of what this Tool Group is for"
    )

    # Icon and color for UI
    icon: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Icon name or emoji for UI display"
    )

    color: Mapped[Optional[str]] = mapped_column(
        String(7),
        nullable=True,
        comment="Hex color code for UI display (e.g., '#FF5733')"
    )

    # Visibility
    visibility: Mapped[ToolGroupVisibility] = mapped_column(
        String(20),
        nullable=False,
        default=ToolGroupVisibility.PRIVATE,
        comment="Who can see and use this Tool Group"
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether this Tool Group is currently active"
    )

    # Metadata (renamed from 'metadata' to avoid SQLAlchemy conflict)
    extra_metadata: Mapped[dict] = mapped_column(
        JSONType,
        default={},
        nullable=False,
        comment="Additional metadata (tags, categories, etc.)"
    )

    # Usage tracking
    usage_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of times this Tool Group has been used"
    )

    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Last time this Tool Group was used"
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    organization: Mapped["Organization"] = relationship("Organization")
    items: Mapped[List["ToolGroupItem"]] = relationship(
        "ToolGroupItem",
        back_populates="tool_group",
        cascade="all, delete-orphan"
    )

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "name",
            name="uq_org_tool_group_name"
        ),
        Index("idx_tool_groups_visibility", "visibility"),
        Index("idx_tool_groups_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<ToolGroup(id={self.id}, name={self.name}, items={len(self.items)})>"


class ToolGroupItemType(str, enum.Enum):
    """Type of item in a Tool Group."""
    TOOL = "tool"  # Individual MCP tool
    COMPOSITION = "composition"  # Composition (workflow)


class ToolGroupItem(Base, UUIDMixin, TimestampMixin):
    """
    An item (tool or composition) in a Tool Group.

    Each Tool Group contains multiple items, which can be:
    - Individual tools (e.g., "grist_create_record")
    - Compositions (e.g., "github-issue-from-grist" workflow)
    """

    __tablename__ = "tool_group_items"

    # Relationship to Tool Group
    tool_group_id: Mapped[UUID] = mapped_column(
        ForeignKey("tool_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Tool Group this item belongs to"
    )

    # Item type
    item_type: Mapped[ToolGroupItemType] = mapped_column(
        String(20),
        nullable=False,
        comment="Type of item (tool or composition)"
    )

    # Reference to tool or composition
    tool_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("tools.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Tool ID (if item_type=TOOL)"
    )

    composition_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("compositions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Composition ID (if item_type=COMPOSITION)"
    )

    # Order within the group
    order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Display order within the Tool Group"
    )

    # Optional override configuration
    config: Mapped[dict] = mapped_column(
        JSONType,
        default={},
        nullable=False,
        comment="Optional configuration overrides for this item"
    )

    # Relationships
    tool_group: Mapped["ToolGroup"] = relationship("ToolGroup", back_populates="items")
    tool: Mapped[Optional["Tool"]] = relationship("Tool")
    composition: Mapped[Optional["Composition"]] = relationship("Composition")

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint(
            "tool_group_id",
            "tool_id",
            name="uq_tool_group_tool"
        ),
        UniqueConstraint(
            "tool_group_id",
            "composition_id",
            name="uq_tool_group_composition"
        ),
        Index("idx_tool_group_items_type", "item_type"),
        Index("idx_tool_group_items_order", "tool_group_id", "order"),
    )

    def __repr__(self) -> str:
        ref = self.tool_id if self.item_type == ToolGroupItemType.TOOL else self.composition_id
        return f"<ToolGroupItem(type={self.item_type}, ref={ref})>"
