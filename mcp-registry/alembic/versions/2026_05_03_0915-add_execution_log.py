"""add_execution_log

Revision ID: add_execution_log
Revises: dynamic_pool_default_empty
Create Date: 2026-05-03 09:15

Audit table for the new `execute` MCP tool. Each successful or failed
execution writes one row asynchronously (fire-and-forget) so we can answer
"what happened" questions in production without changing the wire format.

V1 minimal: no UI, no replay endpoint. A daily purge job removes rows older
than 30 days (job lives in app startup, not the migration).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'add_execution_log'
down_revision: Union[str, None] = 'dynamic_pool_default_empty'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "execution_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("shortcut_level", sa.String(length=64), nullable=True),
        sa.Column("llm_calls_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("plan", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("step_results", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("composition_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tools_called", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["composition_id"], ["compositions.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_execution_log_user_created",
        "execution_log",
        ["user_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_execution_log_org_created",
        "execution_log",
        ["organization_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_execution_log_failed_created",
        "execution_log",
        ["status", sa.text("created_at DESC")],
        unique=False,
        postgresql_where=sa.text("status <> 'success'"),
    )


def downgrade() -> None:
    op.drop_index("ix_execution_log_failed_created", table_name="execution_log")
    op.drop_index("ix_execution_log_org_created", table_name="execution_log")
    op.drop_index("ix_execution_log_user_created", table_name="execution_log")
    op.drop_table("execution_log")
