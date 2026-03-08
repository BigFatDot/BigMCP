"""Add LemonSqueezy columns to licenses table

Revision ID: add_lemonsqueezy_to_licenses
Revises: add_public_domain_whitelist
Create Date: 2025-12-28 23:45

Adds LemonSqueezy order tracking for Enterprise license purchases.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_lemonsqueezy_to_licenses'
down_revision: Union[str, None] = 'add_public_domain_whitelist'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add LemonSqueezy columns to licenses table."""

    # Add lemonsqueezy_order_id column
    op.add_column(
        'licenses',
        sa.Column('lemonsqueezy_order_id', sa.String(255), nullable=True)
    )

    # Add lemonsqueezy_customer_id column
    op.add_column(
        'licenses',
        sa.Column('lemonsqueezy_customer_id', sa.String(255), nullable=True)
    )

    # Create unique index on lemonsqueezy_order_id
    op.create_index(
        'idx_license_lemonsqueezy_order',
        'licenses',
        ['lemonsqueezy_order_id'],
        unique=True
    )


def downgrade() -> None:
    """Remove LemonSqueezy columns from licenses table."""

    op.drop_index('idx_license_lemonsqueezy_order', table_name='licenses')
    op.drop_column('licenses', 'lemonsqueezy_customer_id')
    op.drop_column('licenses', 'lemonsqueezy_order_id')
