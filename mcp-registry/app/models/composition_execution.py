"""Composition execution models (Phase B-0).

Three tables that turn compositions from synchronous DAG runs into
durable resumable state machines:

- ``CompositionExecution`` — one row per execution attempt. Carries
  the full ``state`` JSONB plus enough metadata to route MCP
  notifications and adapt to client capabilities.

- ``ExecutionStepEvent`` — append-only timeline of step transitions
  (started/succeeded/failed/suspended). Used by the UI detail page
  and audit. Cleanup job drops > 90d.

- ``PendingNotification`` — buffer for MCP notifications that fired
  while the recipient session was disconnected. Flushed at the next
  ``initialize`` from that ``session_id``.

The state machine relies on **status-as-lock + conditional UPDATE-
RETURNING** for concurrency control — no Postgres advisory locks.
A ``UPDATE ... WHERE status = 'suspended' RETURNING *`` style query
guarantees only one mutator wins; subsequent attempts see 0 rows
back and surface a 409.

See ``mcp-registry/docs/composition_executions_b0.md`` for the
design doc.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin
from ..db.types import JSONType

if TYPE_CHECKING:
    from .composition import Composition
    from .organization import Organization
    from .user import User


class ExecutionStatus(str, enum.Enum):
    """Lifecycle status of a composition execution.

    Terminal statuses (no further transitions): ``completed``,
    ``failed``, ``expired``, ``cancelled``.

    Each terminal transition fires one final ``notifications/
    resources/updated`` to subscribers, then the resource is
    read-only-stable.
    """
    QUEUED = "queued"          # Over-quota, waiting for slot
    RUNNING = "running"        # Currently executing
    SUSPENDED = "suspended"    # Waiting for external event (resume)
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ExecutionTrigger(str, enum.Enum):
    """How the execution was started.

    B-0 implements the first three. ``cron`` arrives in B-2,
    ``webhook`` in B-3. The enum is extensible — adding a value is
    a code-only change (no migration; the DB column is a plain
    VARCHAR(20)).
    """
    MCP_CALL = "mcp_call"
    MANUAL = "manual"
    API = "api"
    CRON = "cron"
    WEBHOOK = "webhook"


class CompositionExecution(Base, UUIDMixin):
    """One execution attempt of a composition.

    The ``state`` JSONB carries everything needed to resume:
    ``step_results``, ``step_status``, ``step_started_at``,
    ``current_step_id``, ``suspension`` (when applicable), and
    ``depth`` (sub-composition nesting).

    ``mcp_session_id`` ties the execution to the MCP client that
    triggered it — used to route ``notifications/resources/updated``
    to the right SSE session, and to queue them in
    ``PendingNotification`` if that session is disconnected.

    ``client_capabilities`` is a snapshot at start so adaptive
    negotiation (e.g., elicit-via-MCP vs UI fallback) reflects what
    the client could do at the time, not what it can do now.
    """

    __tablename__ = "composition_execution"

    # Ownership / multi-tenancy
    composition_id: Mapped[UUID] = mapped_column(
        ForeignKey("compositions.id", ondelete="RESTRICT"),
        nullable=False,
        comment="RESTRICT preserves audit on composition soft-delete",
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Sub-composition chain. ON DELETE SET NULL so deleting a parent
    # orphans the child rather than nuking it (preserves audit).
    parent_execution_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("composition_execution.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="See ExecutionStatus enum",
    )
    state: Mapped[dict] = mapped_column(
        JSONType,
        default=dict,
        nullable=False,
        comment=(
            "{ step_results, step_status, step_started_at, "
            "current_step_id, suspension, depth }"
        ),
    )

    # Routing / capability negotiation
    trigger: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="See ExecutionTrigger enum",
    )
    mcp_session_id: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Originating MCP session — drives notification routing",
    )
    client_capabilities: Mapped[Optional[dict]] = mapped_column(
        JSONType,
        nullable=True,
        comment="Snapshot at start, drives adaptive negotiation",
    )

    # Cooperative cancel — checked at every step boundary by the executor
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Timestamps. ``updated_at`` is bumped explicitly by the executor
    # at every state transition (NOT via TimestampMixin onupdate, which
    # only fires for ORM updates and would miss raw SQL UPDATE paths
    # used by the status-as-lock pattern).
    started_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="TTL set per suspension reason (e.g., 5 min for _test_suspend)",
    )

    # Final outcome
    result: Mapped[Optional[dict]] = mapped_column(
        JSONType,
        nullable=True,
    )
    error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships (lazy by default — these rows are typically loaded
    # one-at-a-time and the executor uses raw SQL for the hot path).
    composition: Mapped["Composition"] = relationship(
        "Composition",
        foreign_keys=[composition_id],
    )
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    organization: Mapped["Organization"] = relationship(
        "Organization",
        foreign_keys=[organization_id],
    )
    parent: Mapped[Optional["CompositionExecution"]] = relationship(
        "CompositionExecution",
        remote_side="CompositionExecution.id",
        foreign_keys=[parent_execution_id],
    )

    __table_args__ = (
        # Hot lookup: per-user list filtered by status
        Index("idx_compexec_user_status", "user_id", "status"),
        # Per-org list (admin governance view)
        Index("idx_compexec_org_status", "organization_id", "status"),
        # Expiry scanner only cares about non-terminal rows
        Index(
            "idx_compexec_expiry",
            "expires_at",
            postgresql_where="status IN ('suspended', 'queued')",
        ),
        # Sub-composition chain walk
        Index(
            "idx_compexec_parent",
            "parent_execution_id",
            postgresql_where="parent_execution_id IS NOT NULL",
        ),
        # Pending notification flush by session
        Index(
            "idx_compexec_session",
            "mcp_session_id",
            postgresql_where="mcp_session_id IS NOT NULL",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CompositionExecution(id={self.id}, "
            f"composition_id={self.composition_id}, status={self.status})>"
        )


class ExecutionStepEvent(Base, UUIDMixin):
    """Append-only timeline of step transitions for an execution.

    One row per ``started``/``succeeded``/``failed``/``suspended``/
    ``skipped``/``retry`` event. Used by the UI detail page and as
    a reconstruction log for debugging.

    Cleanup job drops rows older than 90 days.
    """

    __tablename__ = "execution_step_event"

    execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("composition_execution.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="started | succeeded | failed | suspended | skipped | retry",
    )
    payload: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    __table_args__ = (
        Index("idx_stepev_exec_time", "execution_id", "timestamp"),
    )


class PendingNotification(Base, UUIDMixin):
    """MCP notification fired while the recipient session was disconnected.

    Stores only ``(session_id, uri, method)`` — per spec,
    ``notifications/resources/updated`` carries only the URI; the
    client must ``resources/read`` to fetch new content. So we don't
    persist payloads.

    Flushed at the next ``initialize`` from the same ``session_id``.
    Cleanup job drops rows older than 7 days.
    """

    __tablename__ = "pending_notification"

    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    uri: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="composition://executions/{id} (or other resource scheme)",
    )
    method: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="notifications/resources/updated",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    __table_args__ = (
        Index("idx_pendnotif_session", "session_id", "created_at"),
    )
