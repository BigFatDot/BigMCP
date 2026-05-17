"""add_instance_branding

Revision ID: add_instance_branding
Revises: add_composition_executions
Create Date: 2026-05-16 11:00

Self-hosted persona: white-label the singleton ``instance_settings`` row
so an organisation deploying their own BigMCP can rebrand it without
forking + rebuilding the frontend.

New columns (all nullable so env-var fallback kicks in):
- instance_name, instance_tagline
- logo_url, favicon_url
- primary_color
- support_email, instance_url, legal_entity
- setup_completed (bool, NOT NULL, defaults to True on existing rows so
  production instances skip the first-run wizard; new rows from a fresh
  deploy default to False).

The /api/v1/instance/branding endpoint reads this table and merges with
env-var defaults; the admin PATCH endpoint writes to it. See
app/services/branding.py for the merge contract.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


revision: str = "add_instance_branding"
down_revision: Union[str, None] = "add_composition_executions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable branding columns + setup_completed (default True on
    # existing rows so production instances skip the wizard).
    with op.batch_alter_table("instance_settings") as batch:
        batch.add_column(sa.Column("instance_name", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("instance_tagline", sa.String(length=240), nullable=True))
        batch.add_column(sa.Column("logo_url", sa.String(length=2048), nullable=True))
        batch.add_column(sa.Column("favicon_url", sa.String(length=2048), nullable=True))
        batch.add_column(sa.Column("primary_color", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("support_email", sa.String(length=254), nullable=True))
        batch.add_column(sa.Column("instance_url", sa.String(length=2048), nullable=True))
        batch.add_column(sa.Column("legal_entity", sa.String(length=240), nullable=True))
        batch.add_column(
            sa.Column(
                "setup_completed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            )
        )

    # Existing instances are already in production — don't trigger the
    # first-run wizard on them. The server_default above handles new
    # rows, but we also explicitly mark the singleton (if present) as
    # completed in case any older row landed before the default applied.
    op.execute(
        "UPDATE instance_settings SET setup_completed = true WHERE id = 1"
    )


def downgrade() -> None:
    with op.batch_alter_table("instance_settings") as batch:
        batch.drop_column("setup_completed")
        batch.drop_column("legal_entity")
        batch.drop_column("instance_url")
        batch.drop_column("support_email")
        batch.drop_column("primary_color")
        batch.drop_column("favicon_url")
        batch.drop_column("logo_url")
        batch.drop_column("instance_tagline")
        batch.drop_column("instance_name")
