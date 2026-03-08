"""add alias to mcp_servers

Revision ID: add_alias_to_mcp_servers
Revises: 8df49fd73d77
Create Date: 2025-11-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_alias_to_mcp_servers'
down_revision = '8df49fd73d77'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add alias column to mcp_servers table
    op.add_column('mcp_servers', sa.Column('alias', sa.String(length=100), nullable=True, comment='User-friendly alias for this instance (e.g., \'personal\', \'work\')'))


def downgrade() -> None:
    # Remove alias column from mcp_servers table
    op.drop_column('mcp_servers', 'alias')
