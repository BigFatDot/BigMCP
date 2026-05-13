"""add_instance_settings

Revision ID: add_instance_settings
Revises: add_execution_log
Create Date: 2026-05-13 17:00

First instance-scoped configuration table in BigMCP — a singleton row
that holds JSON-blob policy fields the instance admin can mutate at
runtime without a redeploy. Phase 1 (N1.1 of the access-control roadmap)
only seeds the row with empty client_control; subsequent phases will add
more JSON columns as new instance-wide knobs land.

The CheckConstraint on id forces singleton semantics — readers always
`db.get(InstanceSettings, 1)`. A second insert would violate the
constraint by design.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_instance_settings"
down_revision: Union[str, None] = "add_execution_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instance_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "client_control",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint("id = 1", name="ck_instance_settings_singleton"),
    )

    # Seed the singleton row so business code can always assume it exists.
    op.execute(
        "INSERT INTO instance_settings (id, client_control) "
        "VALUES (1, '{}'::jsonb) "
        "ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("instance_settings")
