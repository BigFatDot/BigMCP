"""Add visibility field to compositions table

Revision ID: add_visibility_compositions
Revises: add_compositions
Create Date: 2025-12-20 10:00

Adds visibility control to compositions:
- PRIVATE: Only creator can see/use
- ORGANIZATION: All org members can see/use
- PUBLIC: Anyone can see (future marketplace)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'add_visibility_compositions'
down_revision: Union[str, None] = 'add_compositions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add visibility column to compositions."""

    # Create enum type if it doesn't exist
    # Note: Using checkfirst=True to avoid error if already exists
    compositionvisibility = postgresql.ENUM(
        'private', 'organization', 'public',
        name='compositionvisibility',
        create_type=False  # Don't create - already exists or will be created by checkfirst
    )

    # Create the enum type only if it doesn't exist
    connection = op.get_bind()
    result = connection.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'compositionvisibility'")
    )
    if not result.fetchone():
        compositionvisibility.create(connection)

    # Add visibility column with default 'private'
    op.add_column(
        'compositions',
        sa.Column(
            'visibility',
            postgresql.ENUM('private', 'organization', 'public', name='compositionvisibility', create_type=False),
            nullable=False,
            server_default='private',
            comment='Visibility: private, organization, public'
        )
    )

    # Create indexes for visibility queries
    op.create_index('idx_compositions_visibility', 'compositions', ['visibility'])
    op.create_index('idx_compositions_org_visibility', 'compositions', ['organization_id', 'visibility'])


def downgrade() -> None:
    """Remove visibility column from compositions."""

    op.drop_index('idx_compositions_org_visibility', table_name='compositions')
    op.drop_index('idx_compositions_visibility', table_name='compositions')
    op.drop_column('compositions', 'visibility')

    # Drop enum type
    compositionvisibility = postgresql.ENUM(name='compositionvisibility')
    compositionvisibility.drop(op.get_bind(), checkfirst=True)
