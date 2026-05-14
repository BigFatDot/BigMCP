"""add_oauth_sessions

Revision ID: add_oauth_sessions
Revises: add_oauth_client_control
Create Date: 2026-05-14 17:00

Story H (Design C) — connected-apps tracking.

A new table that records each OAuth grant (per user × client × token
issuance) so the user can list "connected apps" in the UI and revoke a
specific client without burning their full session set. Independent of
``refresh_tokens`` (which is currently a ghost table — no inserts).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_oauth_sessions"
down_revision: Union[str, None] = "add_oauth_client_control"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oauth_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "oauth_client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("oauth_clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("access_token_jti", sa.String(length=64), nullable=True),
        sa.Column("refresh_token_jti", sa.String(length=64), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_oauth_sessions_user_id",
        "oauth_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_oauth_sessions_oauth_client_id",
        "oauth_sessions",
        ["oauth_client_id"],
        unique=False,
    )
    op.create_index(
        "ix_oauth_sessions_organization_id",
        "oauth_sessions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_oauth_sessions_revoked_at",
        "oauth_sessions",
        ["revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_oauth_sessions_user_active",
        "oauth_sessions",
        ["user_id", "revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_oauth_sessions_user_client",
        "oauth_sessions",
        ["user_id", "oauth_client_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_oauth_sessions_user_client", table_name="oauth_sessions")
    op.drop_index("ix_oauth_sessions_user_active", table_name="oauth_sessions")
    op.drop_index("ix_oauth_sessions_revoked_at", table_name="oauth_sessions")
    op.drop_index("ix_oauth_sessions_organization_id", table_name="oauth_sessions")
    op.drop_index("ix_oauth_sessions_oauth_client_id", table_name="oauth_sessions")
    op.drop_index("ix_oauth_sessions_user_id", table_name="oauth_sessions")
    op.drop_table("oauth_sessions")
