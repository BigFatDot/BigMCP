"""add_org_marketplace_curation

Revision ID: add_org_marketplace_curation
Revises: add_oidc_sso
Create Date: 2026-05-14 21:00

Phase 2 — Org-scoped marketplace curation. One row per (org, server)
override. Default behaviour when no row exists is permissive: full
catalog visible. Status enum: approved | featured | hidden.

The legacy ``conf/server_visibility.json`` file remains parsed at
``MarketplaceSyncService`` boot time as a *fallback* for instances that
have not yet curated anything via the new admin UI; once the org has at
least one curation row, the JSON file is ignored.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_org_marketplace_curation"
down_revision: Union[str, None] = "add_oidc_sso"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "org_marketplace_curation",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "marketplace_server_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="approved",
        ),
        sa.Column(
            "featured_order",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "curated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
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
        sa.UniqueConstraint(
            "organization_id",
            "marketplace_server_id",
            name="uq_org_marketplace_curation_per_org_per_server",
        ),
    )
    op.create_index(
        "ix_org_marketplace_curation_organization_id",
        "org_marketplace_curation",
        ["organization_id"],
    )
    op.create_index(
        "ix_org_marketplace_curation_status",
        "org_marketplace_curation",
        ["organization_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_org_marketplace_curation_status",
        table_name="org_marketplace_curation",
    )
    op.drop_index(
        "ix_org_marketplace_curation_organization_id",
        table_name="org_marketplace_curation",
    )
    op.drop_table("org_marketplace_curation")
