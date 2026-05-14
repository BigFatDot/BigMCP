"""add_user_status

Revision ID: add_user_status
Revises: add_instance_settings
Create Date: 2026-05-14 09:00

Non-destructive offboarding (N1.4 of the access-control roadmap).
Adds a lifecycle status to ``users`` so admins can suspend or
soft-delete an account without losing audit history, organisational
membership records, or referential integrity.

The status defaults to ``active`` for every existing row, so this
migration is a pure schema addition — no data backfill needed beyond
the server_default.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_user_status"
down_revision: Union[str, None] = "add_instance_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "status_changed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "status_reason",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Indexed lookup of "find me everyone in a non-active state" — small,
    # admin-side query that benefits from the index on a low-cardinality
    # column thanks to the partial filter.
    op.create_index(
        "ix_users_status_non_active",
        "users",
        ["status"],
        unique=False,
        postgresql_where=sa.text("status <> 'active'"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_status_non_active", table_name="users")
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "status_reason")
    op.drop_column("users", "status_changed_at")
    op.drop_column("users", "status")
