"""add_visibility_fields_to_servers_and_tools

Revision ID: ffd31a710c74
Revises: 2025_12_28_2350
Create Date: 2026-01-14 17:35

Adds is_visible_to_oauth_clients field to both mcp_servers and tools tables
to enable hiding servers/tools from OAuth clients while keeping them available for API keys.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ffd31a710c74'
down_revision: Union[str, None] = 'expand_license_key_size'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_visible_to_oauth_clients to mcp_servers and tools."""

    # Add is_visible_to_oauth_clients to mcp_servers
    op.add_column('mcp_servers',
        sa.Column('is_visible_to_oauth_clients',
                  sa.Boolean(),
                  nullable=False,
                  server_default='true',
                  comment='If False, server is hidden from OAuth clients but available for API keys'))

    # Add is_visible_to_oauth_clients to tools
    op.add_column('tools',
        sa.Column('is_visible_to_oauth_clients',
                  sa.Boolean(),
                  nullable=False,
                  server_default='true',
                  comment='If False, tool is hidden from OAuth clients but available via API keys'))

    # Add composite index for performance on mcp_servers
    op.create_index(
        'idx_servers_org_enabled_visible',
        'mcp_servers',
        ['organization_id', 'enabled', 'is_visible_to_oauth_clients']
    )

    # Add index for performance on tools
    op.create_index(
        'idx_tools_server_visible',
        'tools',
        ['server_id', 'is_visible_to_oauth_clients']
    )


def downgrade() -> None:
    """Remove is_visible_to_oauth_clients from mcp_servers and tools."""

    # Drop indexes
    op.drop_index('idx_tools_server_visible', table_name='tools')
    op.drop_index('idx_servers_org_enabled_visible', table_name='mcp_servers')

    # Drop columns
    op.drop_column('tools', 'is_visible_to_oauth_clients')
    op.drop_column('mcp_servers', 'is_visible_to_oauth_clients')
