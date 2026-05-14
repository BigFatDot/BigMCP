"""add_oauth_client_control

Revision ID: add_oauth_client_control
Revises: add_mcp_allowed_roles
Create Date: 2026-05-14 15:00

Foundation for N2.2 client control + CIMD. Pure schema additions on
oauth_clients — no behaviour change yet. Existing rows default to
``registration_method=dcr_open`` and ``approval_status=auto_approved``
so the historical "anyone can DCR and authorize" flow keeps working
until the policy engine (later sub-PR) starts enforcing.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_oauth_client_control"
down_revision: Union[str, None] = "add_mcp_allowed_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "oauth_clients",
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_oauth_clients_organization_id",
        "oauth_clients",
        ["organization_id"],
        unique=False,
    )

    op.add_column(
        "oauth_clients",
        sa.Column(
            "registration_method",
            sa.String(length=32),
            nullable=False,
            server_default="dcr_open",
        ),
    )
    op.add_column(
        "oauth_clients",
        sa.Column(
            "approval_status",
            sa.String(length=32),
            nullable=False,
            server_default="auto_approved",
        ),
    )
    op.add_column(
        "oauth_clients",
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "oauth_clients",
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "oauth_clients",
        sa.Column("cimd_url", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "oauth_clients",
        sa.Column(
            "cimd_metadata_cached",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "oauth_clients",
        sa.Column(
            "cimd_last_fetched_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Index on (approval_status) for fast "what's pending?" admin queries.
    op.create_index(
        "ix_oauth_clients_pending",
        "oauth_clients",
        ["approval_status"],
        unique=False,
        postgresql_where=sa.text("approval_status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_oauth_clients_pending", table_name="oauth_clients")
    op.drop_column("oauth_clients", "cimd_last_fetched_at")
    op.drop_column("oauth_clients", "cimd_metadata_cached")
    op.drop_column("oauth_clients", "cimd_url")
    op.drop_column("oauth_clients", "approved_at")
    op.drop_column("oauth_clients", "approved_by_user_id")
    op.drop_column("oauth_clients", "approval_status")
    op.drop_column("oauth_clients", "registration_method")
    op.drop_index("ix_oauth_clients_organization_id", table_name="oauth_clients")
    op.drop_column("oauth_clients", "organization_id")
