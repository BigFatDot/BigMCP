"""Expand license_key column to support JWT tokens

Revision ID: expand_license_key_size
Revises: add_lemonsqueezy_to_licenses
Create Date: 2025-12-28 23:50

JWT tokens for Enterprise licenses can be 300+ characters.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'expand_license_key_size'
down_revision: Union[str, None] = 'add_lemonsqueezy_to_licenses'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Expand license_key column to 1000 characters."""
    op.alter_column(
        'licenses',
        'license_key',
        type_=sa.String(1000),
        existing_type=sa.String(100)
    )


def downgrade() -> None:
    """Revert license_key column to 100 characters."""
    op.alter_column(
        'licenses',
        'license_key',
        type_=sa.String(100),
        existing_type=sa.String(1000)
    )
