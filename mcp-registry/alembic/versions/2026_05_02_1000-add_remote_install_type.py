"""add_remote_install_type

Revision ID: add_remote_install_type
Revises: raise_org_default_limits
Create Date: 2026-05-02 10:00

Adds support for remote/streamable-HTTP MCP servers:
- New `url` column on mcp_servers (the upstream HTTP endpoint)
- `command` and `install_package` made nullable (remote servers have neither)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'add_remote_install_type'
down_revision: Union[str, None] = 'raise_org_default_limits'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'mcp_servers',
        sa.Column('url', sa.String(length=1000), nullable=True,
                  comment='Upstream HTTP endpoint for remote (streamable-http/SSE) servers')
    )
    op.alter_column('mcp_servers', 'command', existing_type=sa.String(length=500), nullable=True)
    op.alter_column('mcp_servers', 'install_package', existing_type=sa.String(length=500), nullable=True)


def downgrade() -> None:
    op.alter_column('mcp_servers', 'install_package', existing_type=sa.String(length=500), nullable=False)
    op.alter_column('mcp_servers', 'command', existing_type=sa.String(length=500), nullable=False)
    op.drop_column('mcp_servers', 'url')
