"""
Composition model for workflow definitions.

Stores compositions (multi-step workflows) with organization scoping
and visibility-based access control.

Visibility: Controlled by visibility field (private, organization, public)
Execution: Controlled by allowed_roles field
"""

import enum
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from sqlalchemy import String, Text, ForeignKey, Boolean, Integer, Index, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin, TimestampMixin
from ..db.types import JSONType, ArrayType


class CompositionStatus(str, enum.Enum):
    """Lifecycle status of a composition."""
    TEMPORARY = "temporary"    # Auto-expires, in-memory only
    VALIDATED = "validated"    # Reviewed and approved for use
    PRODUCTION = "production"  # Production-ready, stable


class ShareRequestStatus(str, enum.Enum):
    """Phase 4: state of a non-admin's request to share a composition org-wide.

    The composition row stores the *latest* request state. There is no
    history table — audit logs capture each transition. ``None`` means
    no pending or rejected request currently exists.
    """
    PENDING = "pending"      # Awaiting admin review
    REJECTED = "rejected"    # Last review denied; visibility unchanged


class CompositionVisibility(str, enum.Enum):
    """Visibility level for Compositions."""
    PRIVATE = "private"        # Only creator can see/use
    ORGANIZATION = "organization"  # All org members can see/use
    PUBLIC = "public"          # Anyone can see (future: marketplace)


class Composition(Base, UUIDMixin, TimestampMixin):
    """
    Workflow composition model.

    A composition is a multi-step workflow that chains multiple MCP tools.
    Compositions belong to an organization and use RBAC for execution control.

    Visibility Model:
        - PRIVATE: Only creator can see/use
        - ORGANIZATION: All org members can see/use
        - PUBLIC: Anyone can see (future marketplace)
        - Execution controlled by allowed_roles field
        - Edit/delete: creator OR admin/owner

    Examples:
        - "GitHub Issue from Grist": Creates GitHub issue from Grist record
        - "Refund Customer": Multi-step Stripe refund workflow
        - "Daily Report": Aggregates data from multiple sources
    """

    __tablename__ = "compositions"

    # Ownership & Multi-tenancy
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Organization this composition belongs to"
    )

    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who created this composition"
    )

    # Visibility control (like ToolGroup)
    # Note: values_callable ensures SQLAlchemy uses enum VALUES ('private', 'organization')
    # instead of enum NAMES (PRIVATE, ORGANIZATION) to match PostgreSQL storage
    visibility: Mapped[CompositionVisibility] = mapped_column(
        SQLEnum(
            CompositionVisibility,
            name="compositionvisibility",
            values_callable=lambda obj: [e.value for e in obj]
        ),
        default=CompositionVisibility.PRIVATE,
        nullable=False,
        index=True,
        comment="Visibility: private (creator only), organization (team), public (future)"
    )

    # Basic info
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Name of the composition"
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Description of what this composition does"
    )

    # Workflow definition
    steps: Mapped[list] = mapped_column(
        JSONType,
        default=[],
        nullable=False,
        comment="List of workflow steps [{id, tool, params, depends_on}]"
    )

    data_mappings: Mapped[list] = mapped_column(
        JSONType,
        default=[],
        nullable=False,
        comment="Data flow mappings between steps"
    )

    # Schemas for I/O validation
    input_schema: Mapped[dict] = mapped_column(
        JSONType,
        default={},
        nullable=False,
        comment="JSON Schema for composition inputs"
    )

    output_schema: Mapped[Optional[dict]] = mapped_column(
        JSONType,
        nullable=True,
        comment="JSON Schema for composition outputs"
    )

    # Server bindings (maps logical server_id -> actual server UUID)
    # Example: {"notion": "abc-123-uuid", "grist": "def-456-uuid"}
    server_bindings: Mapped[dict] = mapped_column(
        JSONType,
        default={},
        nullable=False,
        comment="Maps logical server IDs to actual server UUIDs"
    )

    # IAM & Credential Delegation
    force_org_credentials: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="If true, use org credentials instead of user credentials (service account mode)"
    )

    # RBAC: Execution control
    # Empty list = all roles except VIEWER can execute
    # ["admin"] = only ADMIN and OWNER can execute
    # ["viewer"] = even VIEWER can execute
    allowed_roles: Mapped[list] = mapped_column(
        ArrayType,
        default=[],
        nullable=False,
        comment="Roles allowed to execute (empty = all except viewer)"
    )

    # Future: Approval workflow
    requires_approval: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="If true, execution requires prior approval (Phase 2 feature)"
    )

    # Lifecycle status
    status: Mapped[str] = mapped_column(
        String(20),
        default=CompositionStatus.TEMPORARY.value,
        nullable=False,
        comment="Lifecycle status: temporary, validated, production"
    )

    # TTL for temporary compositions (in seconds)
    ttl: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Time-to-live in seconds (for temporary compositions)"
    )

    # Metadata: execution stats, tags, etc.
    extra_metadata: Mapped[dict] = mapped_column(
        JSONType,
        default={},
        nullable=False,
        comment="Additional metadata (tags, execution_count, success_rate, etc.)"
    )

    # ---- Phase 4: org-share review workflow ---------------------------------
    # NULL means no review in flight. Set to 'pending' when a non-admin asks
    # to share with the org; flips to NULL on approval (composition itself
    # gets visibility=organization + status=production), or 'rejected' to
    # stop the gate from firing again until the user re-requests.
    share_request_status: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Phase 4 share-request gate: pending | rejected | NULL"
    )
    share_requested_by: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who last requested an org-share review"
    )
    share_requested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="When the latest share-request was opened"
    )
    share_review_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Reviewer's free-text rationale (typically only set for rejections)"
    )
    share_reviewed_by: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Admin who approved or rejected the latest request"
    )
    share_reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="When the latest review decision was recorded"
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        foreign_keys=[organization_id]
    )

    creator: Mapped["User"] = relationship(
        "User",
        foreign_keys=[created_by]
    )

    # Indexes for common queries
    __table_args__ = (
        Index("idx_compositions_org_status", "organization_id", "status"),
        Index("idx_compositions_org_creator", "organization_id", "created_by"),
        Index("idx_compositions_visibility", "visibility"),
        Index("idx_compositions_org_visibility", "organization_id", "visibility"),
        Index(
            "idx_compositions_share_request_pending",
            "organization_id",
            "share_request_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<Composition(id={self.id}, name={self.name}, status={self.status})>"
