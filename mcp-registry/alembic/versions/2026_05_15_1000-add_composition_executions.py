"""add_composition_executions

Revision ID: add_composition_executions
Revises: add_composition_share_request
Create Date: 2026-05-15 10:00

Phase B-0 — durable suspension infrastructure for compositions.

Three new tables turn compositions from synchronous DAG runs into
resumable state machines:

- ``composition_execution``  — one row per execution attempt. Carries
  the full state JSONB (step_results, step_status, suspension info)
  plus enough metadata to route notifications (mcp_session_id, snapshot
  of client capabilities at start). FK semantics:
    * composition_id ON DELETE RESTRICT (preserve audit on soft-delete)
    * user_id, organization_id ON DELETE CASCADE (hard-delete cascades)
    * parent_execution_id ON DELETE SET NULL (orphan child instead of nuke)

- ``execution_step_event`` — append-only timeline for the UI detail
  page and audit. One row per step transition (started/succeeded/
  failed/suspended/skipped/retry). Cleanup job drops > 90d.

- ``pending_notification`` — durable buffer for MCP notifications that
  fired while the recipient session was disconnected. Flushed at the
  next ``initialize`` from the same session_id.

State machine relies on status-as-lock + conditional UPDATE-RETURNING
(no Postgres advisory locks needed). MVCC handles the rest.

Reversible via standard downgrade(). No backfill needed (existing
executor is sync, no in-flight executions to migrate).

See ``mcp-registry/docs/composition_executions_b0.md`` for the full
design doc.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_composition_executions"
down_revision: Union[str, None] = "add_composition_share_request"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- composition_execution ---------------------------------------------
    op.create_table(
        "composition_execution",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "composition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("compositions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_execution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("composition_execution.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            comment="queued | running | suspended | completed | failed | expired | cancelled",
        ),
        sa.Column(
            "state",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
            comment="{ step_results, step_status, step_started_at, current_step_id, suspension, depth }",
        ),
        sa.Column(
            "trigger",
            sa.String(length=20),
            nullable=False,
            comment="mcp_call | manual | api (cron + webhook arrive in B-2/B-3)",
        ),
        sa.Column(
            "mcp_session_id",
            sa.Text(),
            nullable=True,
            comment="Route notifications/resources/updated to the originating client",
        ),
        sa.Column(
            "client_capabilities",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Snapshot at execution start, drives adaptive negotiation",
        ),
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(),
            nullable=True,
            comment="TTL set per suspension reason",
        ),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "error",
            sa.Text(),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_compexec_user_status",
        "composition_execution",
        ["user_id", "status"],
    )
    op.create_index(
        "idx_compexec_org_status",
        "composition_execution",
        ["organization_id", "status"],
    )
    op.create_index(
        "idx_compexec_expiry",
        "composition_execution",
        ["expires_at"],
        postgresql_where=sa.text("status IN ('suspended', 'queued')"),
    )
    op.create_index(
        "idx_compexec_parent",
        "composition_execution",
        ["parent_execution_id"],
        postgresql_where=sa.text("parent_execution_id IS NOT NULL"),
    )
    op.create_index(
        "idx_compexec_session",
        "composition_execution",
        ["mcp_session_id"],
        postgresql_where=sa.text("mcp_session_id IS NOT NULL"),
    )

    # ---- execution_step_event ----------------------------------------------
    op.create_table(
        "execution_step_event",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "execution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("composition_execution.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "step_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.String(length=32),
            nullable=False,
            comment="started | succeeded | failed | suspended | skipped | retry",
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_stepev_exec_time",
        "execution_step_event",
        ["execution_id", "timestamp"],
    )

    # ---- pending_notification ----------------------------------------------
    op.create_table(
        "pending_notification",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "uri",
            sa.Text(),
            nullable=False,
            comment="composition://executions/{id} (or other resource scheme)",
        ),
        sa.Column(
            "method",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'notifications/resources/updated'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_pendnotif_session",
        "pending_notification",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_pendnotif_session", table_name="pending_notification")
    op.drop_table("pending_notification")

    op.drop_index("idx_stepev_exec_time", table_name="execution_step_event")
    op.drop_table("execution_step_event")

    op.drop_index("idx_compexec_session", table_name="composition_execution")
    op.drop_index("idx_compexec_parent", table_name="composition_execution")
    op.drop_index("idx_compexec_expiry", table_name="composition_execution")
    op.drop_index("idx_compexec_org_status", table_name="composition_execution")
    op.drop_index("idx_compexec_user_status", table_name="composition_execution")
    op.drop_table("composition_execution")
