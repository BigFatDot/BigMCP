"""Raise default organization limits for open source pivot.

Revision ID: raise_org_default_limits
Revises: add_mfa_fields
Create Date: 2026-04-14 10:00:00.000000

Updates existing organizations that still have the old restrictive defaults
to the new generous defaults for self-hosted deployments.
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = 'raise_org_default_limits'
down_revision = 'add_mfa_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Update organizations still on old defaults to new defaults
    op.execute(
        "UPDATE organizations SET max_mcp_servers = 100 WHERE max_mcp_servers = 3"
    )
    op.execute(
        "UPDATE organizations SET max_contexts = 100 WHERE max_contexts = 10"
    )
    op.execute(
        "UPDATE organizations SET max_tool_bindings = 500 WHERE max_tool_bindings = 50"
    )
    op.execute(
        "UPDATE organizations SET max_api_keys = 50 WHERE max_api_keys = 5"
    )


def downgrade() -> None:
    # Revert to old defaults (only for orgs that match new defaults)
    op.execute(
        "UPDATE organizations SET max_mcp_servers = 3 WHERE max_mcp_servers = 100"
    )
    op.execute(
        "UPDATE organizations SET max_contexts = 10 WHERE max_contexts = 100"
    )
    op.execute(
        "UPDATE organizations SET max_tool_bindings = 50 WHERE max_tool_bindings = 500"
    )
    op.execute(
        "UPDATE organizations SET max_api_keys = 5 WHERE max_api_keys = 50"
    )
