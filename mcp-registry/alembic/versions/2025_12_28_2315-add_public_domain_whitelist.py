"""Add public_domain_whitelist table for Public Sector Program

Revision ID: add_public_domain_whitelist
Revises: add_visibility_compositions
Create Date: 2025-12-28 23:15

Public Sector Program allows government, education, and healthcare
organizations to receive free Enterprise licenses through domain verification.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'add_public_domain_whitelist'
down_revision: Union[str, None] = 'add_visibility_compositions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create public_domain_whitelist table."""

    # Create enum type for public sector category
    connection = op.get_bind()
    result = connection.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'public_sector_category'")
    )
    if not result.fetchone():
        public_sector_category = postgresql.ENUM(
            'government',
            'local_authority',
            'education',
            'healthcare',
            'research',
            'international',
            name='public_sector_category'
        )
        public_sector_category.create(connection)

    # Create public_domain_whitelist table
    op.create_table(
        'public_domain_whitelist',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('domain', sa.String(255), nullable=False),
        sa.Column('organization_name', sa.String(255), nullable=False),
        sa.Column('country', sa.String(2), nullable=False),
        sa.Column(
            'category',
            postgresql.ENUM(
                'government',
                'local_authority',
                'education',
                'healthcare',
                'research',
                'international',
                name='public_sector_category',
                create_type=False
            ),
            nullable=False
        ),
        sa.Column('added_by', sa.String(255), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('idx_whitelist_domain', 'public_domain_whitelist', ['domain'], unique=True)
    op.create_index('idx_whitelist_domain_active', 'public_domain_whitelist', ['domain', 'is_active'])
    op.create_index('idx_whitelist_country', 'public_domain_whitelist', ['country'])
    op.create_index('idx_whitelist_category', 'public_domain_whitelist', ['category'])


def downgrade() -> None:
    """Drop public_domain_whitelist table."""

    op.drop_index('idx_whitelist_category', table_name='public_domain_whitelist')
    op.drop_index('idx_whitelist_country', table_name='public_domain_whitelist')
    op.drop_index('idx_whitelist_domain_active', table_name='public_domain_whitelist')
    op.drop_index('idx_whitelist_domain', table_name='public_domain_whitelist')
    op.drop_table('public_domain_whitelist')

    # Drop enum type
    op.execute('DROP TYPE IF EXISTS public_sector_category')
