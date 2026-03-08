"""Add compositions table for workflow definitions

Revision ID: add_compositions
Revises: add_invitations
Create Date: 2025-12-18 10:00

Implements composition storage in database:
- Stores workflow definitions with steps and data mappings
- Organization-scoped with RBAC via allowed_roles
- Supports server bindings for credential resolution
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'add_compositions'
down_revision: Union[str, None] = 'add_invitations'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create compositions table."""

    op.create_table(
        'compositions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('steps', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('data_mappings', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('input_schema', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('output_schema', postgresql.JSONB(), nullable=True),
        sa.Column('server_bindings', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('force_org_credentials', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('allowed_roles', postgresql.ARRAY(sa.String()), nullable=False, server_default='{}'),
        sa.Column('requires_approval', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('status', sa.String(20), nullable=False, server_default='temporary'),
        sa.Column('ttl', sa.Integer(), nullable=True),
        sa.Column('extra_metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
    )

    # Create indexes for common queries
    op.create_index('ix_compositions_organization_id', 'compositions', ['organization_id'])
    op.create_index('ix_compositions_created_by', 'compositions', ['created_by'])
    op.create_index('idx_compositions_org_status', 'compositions', ['organization_id', 'status'])
    op.create_index('idx_compositions_org_creator', 'compositions', ['organization_id', 'created_by'])

    # Add FK from tool_group_items to compositions (was commented out before)
    op.create_foreign_key(
        'fk_tool_group_items_composition_id',
        'tool_group_items',
        'compositions',
        ['composition_id'],
        ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    """Drop compositions table."""

    # Drop FK from tool_group_items first
    op.drop_constraint('fk_tool_group_items_composition_id', 'tool_group_items', type_='foreignkey')

    # Drop indexes
    op.drop_index('idx_compositions_org_creator', table_name='compositions')
    op.drop_index('idx_compositions_org_status', table_name='compositions')
    op.drop_index('ix_compositions_created_by', table_name='compositions')
    op.drop_index('ix_compositions_organization_id', table_name='compositions')

    # Drop table
    op.drop_table('compositions')
