"""add_welcome_message

Revision ID: add_welcome_message
Revises: add_instance_branding
Create Date: 2026-05-17 00:30

Self-hosted landing page (axis A): adds a nullable `welcome_message`
text column to `instance_settings`. When set on a non-SaaS edition,
the landing page (`/`) renders a sober "this is YOUR instance"
welcome screen instead of the BigMCP SaaS marketing page.

Markdown-rendered client-side. 4KB is a soft cap — enforce in the
admin UI, not in the schema (Text is fine in Postgres).
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


revision: str = "add_welcome_message"
down_revision: Union[str, None] = "add_instance_branding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("instance_settings") as batch:
        batch.add_column(sa.Column("welcome_message", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("instance_settings") as batch:
        batch.drop_column("welcome_message")
