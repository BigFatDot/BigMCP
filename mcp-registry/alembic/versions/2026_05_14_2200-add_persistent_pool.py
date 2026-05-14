"""add_persistent_pool

Revision ID: add_persistent_pool
Revises: add_org_marketplace_curation
Create Date: 2026-05-14 22:00

Phase 3 — Persistent pool overlays.

Two new tables both stacked on top of the existing ephemeral session
pool (``Tool.is_visible_to_oauth_clients`` flag, manipulated by
``search``):

- ``org_default_pool``  — admin-curated entries every user of the org
  inherits at MCP-connect time.
- ``user_pool_pin``     — per-user pins that survive across sessions.

Both reference EITHER a tool OR a composition via a CHECK constraint;
both cascade-delete when the underlying entry is removed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_persistent_pool"
down_revision: Union[str, None] = "add_org_marketplace_curation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_table(name: str, cascade_owner_col: str) -> None:
    op.create_table(
        name,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            cascade_owner_col,
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{'organizations' if cascade_owner_col == 'organization_id' else 'users'}.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "tool_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tools.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "composition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("compositions.id", ondelete="CASCADE"),
            nullable=True,
        ),
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


def upgrade() -> None:
    # ----- org_default_pool ---------------------------------------------
    _create_table("org_default_pool", "organization_id")
    op.add_column(
        "org_default_pool",
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "org_default_pool",
        sa.Column(
            "added_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_org_default_pool_tool_xor_composition",
        "org_default_pool",
        "(tool_id IS NOT NULL AND composition_id IS NULL) "
        "OR (tool_id IS NULL AND composition_id IS NOT NULL)",
    )
    op.create_unique_constraint(
        "uq_org_default_pool_per_org_per_entry",
        "org_default_pool",
        ["organization_id", "tool_id", "composition_id"],
    )
    op.create_index(
        "ix_org_default_pool_organization_id",
        "org_default_pool",
        ["organization_id"],
    )
    op.create_index(
        "ix_org_default_pool_org_position",
        "org_default_pool",
        ["organization_id", "position"],
    )

    # ----- user_pool_pin ------------------------------------------------
    _create_table("user_pool_pin", "user_id")
    op.add_column(
        "user_pool_pin",
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_user_pool_pin_tool_xor_composition",
        "user_pool_pin",
        "(tool_id IS NOT NULL AND composition_id IS NULL) "
        "OR (tool_id IS NULL AND composition_id IS NOT NULL)",
    )
    op.create_unique_constraint(
        "uq_user_pool_pin_per_user_per_entry",
        "user_pool_pin",
        ["user_id", "tool_id", "composition_id"],
    )
    op.create_index(
        "ix_user_pool_pin_user_id",
        "user_pool_pin",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_pool_pin_user_id", table_name="user_pool_pin")
    op.drop_constraint("uq_user_pool_pin_per_user_per_entry", "user_pool_pin")
    op.drop_constraint("ck_user_pool_pin_tool_xor_composition", "user_pool_pin")
    op.drop_table("user_pool_pin")

    op.drop_index("ix_org_default_pool_org_position", table_name="org_default_pool")
    op.drop_index("ix_org_default_pool_organization_id", table_name="org_default_pool")
    op.drop_constraint("uq_org_default_pool_per_org_per_entry", "org_default_pool")
    op.drop_constraint("ck_org_default_pool_tool_xor_composition", "org_default_pool")
    op.drop_table("org_default_pool")
