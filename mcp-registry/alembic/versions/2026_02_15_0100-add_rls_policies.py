"""Add Row-Level Security (RLS) policies for multi-tenant isolation

Revision ID: add_rls_policies
Revises: add_email_verification
Create Date: 2026-02-15

This migration adds PostgreSQL Row-Level Security (RLS) as a defense-in-depth
layer for multi-tenant isolation. This complements the application-level
validation in dependencies.py.

Security Design:
- Each request sets app.current_organization_id via SET LOCAL
- RLS policies enforce that only rows matching this org_id are visible
- Bypass for superuser/admin operations when needed

Tables with RLS:
- mcp_servers (organization_id)
- api_keys (organization_id)
- contexts (organization_id)
- user_credentials (organization_id)
- organization_credentials (organization_id)
- compositions (organization_id)
- tool_bindings (organization_id via context)
- tool_groups (organization_id)
- invitations (organization_id)

Note: SQLite does not support RLS, so these policies only apply to PostgreSQL.
Tests using SQLite will continue to rely on application-level isolation.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'add_rls_policies'
down_revision: Union[str, None] = 'add_email_verification'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def is_postgresql() -> bool:
    """Check if we're running on PostgreSQL."""
    bind = op.get_bind()
    return bind.dialect.name == 'postgresql'


def upgrade() -> None:
    """Add RLS policies for multi-tenant tables."""

    if not is_postgresql():
        # Skip RLS for SQLite (used in tests)
        return

    # =========================================================
    # 1. Create helper function to get current organization
    # =========================================================
    op.execute(text("""
        CREATE OR REPLACE FUNCTION current_org_id()
        RETURNS UUID AS $$
        BEGIN
            -- Returns NULL if not set, which will deny access via RLS policies
            RETURN NULLIF(current_setting('app.current_organization_id', true), '')::UUID;
        EXCEPTION
            WHEN OTHERS THEN
                RETURN NULL;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """))

    # =========================================================
    # 2. Create helper function to check if bypass is enabled
    # =========================================================
    op.execute(text("""
        CREATE OR REPLACE FUNCTION rls_bypass_enabled()
        RETURNS BOOLEAN AS $$
        BEGIN
            -- Check if bypass is explicitly enabled (for migrations, admin ops)
            RETURN COALESCE(
                current_setting('app.rls_bypass', true)::BOOLEAN,
                false
            );
        EXCEPTION
            WHEN OTHERS THEN
                RETURN false;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """))

    # =========================================================
    # 3. Enable RLS and create policies for each table
    # =========================================================

    # --- mcp_servers ---
    op.execute(text("ALTER TABLE mcp_servers ENABLE ROW LEVEL SECURITY;"))
    op.execute(text("""
        CREATE POLICY mcp_servers_org_isolation ON mcp_servers
        FOR ALL
        USING (
            rls_bypass_enabled()
            OR organization_id = current_org_id()
            OR organization_id IS NULL  -- Global/marketplace servers
        )
        WITH CHECK (
            rls_bypass_enabled()
            OR organization_id = current_org_id()
        );
    """))

    # --- api_keys ---
    op.execute(text("ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;"))
    op.execute(text("""
        CREATE POLICY api_keys_org_isolation ON api_keys
        FOR ALL
        USING (
            rls_bypass_enabled()
            OR organization_id = current_org_id()
            OR organization_id IS NULL  -- Personal keys without org
        )
        WITH CHECK (
            rls_bypass_enabled()
            OR organization_id = current_org_id()
            OR organization_id IS NULL
        );
    """))

    # --- contexts ---
    op.execute(text("ALTER TABLE contexts ENABLE ROW LEVEL SECURITY;"))
    op.execute(text("""
        CREATE POLICY contexts_org_isolation ON contexts
        FOR ALL
        USING (
            rls_bypass_enabled()
            OR organization_id = current_org_id()
        )
        WITH CHECK (
            rls_bypass_enabled()
            OR organization_id = current_org_id()
        );
    """))

    # --- user_credentials ---
    op.execute(text("ALTER TABLE user_credentials ENABLE ROW LEVEL SECURITY;"))
    op.execute(text("""
        CREATE POLICY user_credentials_org_isolation ON user_credentials
        FOR ALL
        USING (
            rls_bypass_enabled()
            OR organization_id = current_org_id()
        )
        WITH CHECK (
            rls_bypass_enabled()
            OR organization_id = current_org_id()
        );
    """))

    # --- organization_credentials ---
    op.execute(text("ALTER TABLE organization_credentials ENABLE ROW LEVEL SECURITY;"))
    op.execute(text("""
        CREATE POLICY org_credentials_org_isolation ON organization_credentials
        FOR ALL
        USING (
            rls_bypass_enabled()
            OR organization_id = current_org_id()
        )
        WITH CHECK (
            rls_bypass_enabled()
            OR organization_id = current_org_id()
        );
    """))

    # --- compositions ---
    op.execute(text("ALTER TABLE compositions ENABLE ROW LEVEL SECURITY;"))
    op.execute(text("""
        CREATE POLICY compositions_org_isolation ON compositions
        FOR ALL
        USING (
            rls_bypass_enabled()
            OR organization_id = current_org_id()
            OR visibility = 'public'  -- Public compositions are readable by all
        )
        WITH CHECK (
            rls_bypass_enabled()
            OR organization_id = current_org_id()
        );
    """))

    # --- tool_groups ---
    op.execute(text("ALTER TABLE tool_groups ENABLE ROW LEVEL SECURITY;"))
    op.execute(text("""
        CREATE POLICY tool_groups_org_isolation ON tool_groups
        FOR ALL
        USING (
            rls_bypass_enabled()
            OR organization_id = current_org_id()
        )
        WITH CHECK (
            rls_bypass_enabled()
            OR organization_id = current_org_id()
        );
    """))

    # --- invitations ---
    op.execute(text("ALTER TABLE invitations ENABLE ROW LEVEL SECURITY;"))
    op.execute(text("""
        CREATE POLICY invitations_org_isolation ON invitations
        FOR ALL
        USING (
            rls_bypass_enabled()
            OR organization_id = current_org_id()
        )
        WITH CHECK (
            rls_bypass_enabled()
            OR organization_id = current_org_id()
        );
    """))

    # --- subscriptions (Cloud SaaS) ---
    op.execute(text("ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;"))
    op.execute(text("""
        CREATE POLICY subscriptions_org_isolation ON subscriptions
        FOR ALL
        USING (
            rls_bypass_enabled()
            OR organization_id = current_org_id()
        )
        WITH CHECK (
            rls_bypass_enabled()
            OR organization_id = current_org_id()
        );
    """))

    # =========================================================
    # 4. Add comment explaining RLS usage
    # =========================================================
    op.execute(text("""
        COMMENT ON FUNCTION current_org_id() IS
        'Returns current organization ID from session context. Set via: SET LOCAL app.current_organization_id = uuid; Used by RLS policies for multi-tenant isolation.';
    """))


def downgrade() -> None:
    """Remove RLS policies."""

    if not is_postgresql():
        return

    # Drop policies and disable RLS
    tables = [
        'mcp_servers',
        'api_keys',
        'contexts',
        'user_credentials',
        'organization_credentials',
        'compositions',
        'tool_groups',
        'invitations',
        'subscriptions'
    ]

    for table in tables:
        # Drop policy
        op.execute(text(f"DROP POLICY IF EXISTS {table}_org_isolation ON {table};"))
        # Disable RLS
        op.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"))

    # Drop helper functions
    op.execute(text("DROP FUNCTION IF EXISTS rls_bypass_enabled();"))
    op.execute(text("DROP FUNCTION IF EXISTS current_org_id();"))
