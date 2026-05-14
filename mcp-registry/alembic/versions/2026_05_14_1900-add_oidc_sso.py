"""add_oidc_sso

Revision ID: add_oidc_sso
Revises: add_oauth_sessions
Create Date: 2026-05-14 19:00

Story I.1 — OIDC SSO foundation.

Three changes:

1. New table ``oidc_providers`` — one row per IdP configured for the
   instance (issuer URL, client_id, encrypted client_secret, scopes,
   provisioning policy, fallback team/role).

2. New table ``oidc_group_mappings`` — n:m mapping from IdP group
   claims to BigMCP teams (Organization) + role, with optional
   ``grants_instance_admin`` flag.

3. Two new nullable columns on ``users`` for the SSO identity primitive:
   ``oidc_provider_id`` (FK to oidc_providers) + ``oidc_subject``,
   plus a partial UNIQUE index ``(oidc_provider_id, oidc_subject)``
   that enforces uniqueness only for SSO users (NULL pairs allowed
   for legacy local users).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_oidc_sso"
down_revision: Union[str, None] = "add_oauth_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------- oidc_providers ----------
    op.create_table(
        "oidc_providers",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("display_label", sa.String(length=100), nullable=False),
        sa.Column("issuer_url", sa.String(length=500), nullable=False),
        sa.Column(
            "manual_endpoints_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column(
            "client_secret_encrypted", sa.String(length=2048), nullable=False
        ),
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("""'["openid","profile","email"]'::jsonb"""),
        ),
        sa.Column(
            "groups_claim_path",
            sa.String(length=255),
            nullable=True,
            server_default="groups",
        ),
        sa.Column(
            "email_claim_path",
            sa.String(length=255),
            nullable=False,
            server_default="email",
        ),
        sa.Column(
            "name_claim_path",
            sa.String(length=255),
            nullable=False,
            server_default="name",
        ),
        sa.Column(
            "auto_link_by_verified_email",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "require_email_verified",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "reject_unmapped_users",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "fallback_organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "fallback_role",
            sa.String(length=20),
            nullable=False,
            server_default="member",
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default="true"
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

    # ---------- oidc_group_mappings ----------
    op.create_table(
        "oidc_group_mappings",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "provider_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("oidc_providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idp_group_name", sa.String(length=255), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("role", sa.String(length=20), nullable=True),
        sa.Column(
            "grants_instance_admin",
            sa.Boolean(),
            nullable=False,
            server_default="false",
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
            "provider_id",
            "idp_group_name",
            "organization_id",
            name="uq_oidc_mapping_per_provider_group_org",
        ),
    )
    op.create_index(
        "ix_oidc_mappings_provider_group",
        "oidc_group_mappings",
        ["provider_id", "idp_group_name"],
    )
    op.create_index(
        "ix_oidc_group_mappings_provider_id",
        "oidc_group_mappings",
        ["provider_id"],
    )

    # ---------- users.oidc_provider_id + users.oidc_subject ----------
    op.add_column(
        "users",
        sa.Column(
            "oidc_provider_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("oidc_providers.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column("oidc_subject", sa.String(length=255), nullable=True),
    )
    # Partial UNIQUE index — only enforced when both columns are non-null,
    # so that the millions of legacy local users with NULL/NULL don't
    # collide with each other.
    op.create_index(
        "uq_users_oidc_identity",
        "users",
        ["oidc_provider_id", "oidc_subject"],
        unique=True,
        postgresql_where=sa.text(
            "oidc_provider_id IS NOT NULL AND oidc_subject IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_users_oidc_identity", table_name="users")
    op.drop_column("users", "oidc_subject")
    op.drop_column("users", "oidc_provider_id")

    op.drop_index(
        "ix_oidc_group_mappings_provider_id", table_name="oidc_group_mappings"
    )
    op.drop_index(
        "ix_oidc_mappings_provider_group", table_name="oidc_group_mappings"
    )
    op.drop_table("oidc_group_mappings")
    op.drop_table("oidc_providers")
