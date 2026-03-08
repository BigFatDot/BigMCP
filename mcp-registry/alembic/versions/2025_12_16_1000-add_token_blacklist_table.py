"""Add token blacklist table for JWT revocation

Revision ID: add_token_blacklist
Revises: 89c2a66ca171
Create Date: 2025-12-16 10:00

Implements token blacklist for secure logout:
- Stores blacklisted JWT IDs (JTI)
- Enables token revocation on logout, password change, or admin action
- Auto-cleanup via expires_at index
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_token_blacklist'
down_revision: Union[str, None] = 'add_refresh_tokens'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create token_blacklist table."""

    op.create_table(
        'token_blacklist',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('jti', sa.String(64), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('token_type', sa.String(10), nullable=False, server_default='access'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason', sa.String(50), nullable=False, server_default='logout'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    # Create indexes for fast lookups
    op.create_index('ix_token_blacklist_jti', 'token_blacklist', ['jti'], unique=True)
    op.create_index('ix_token_blacklist_user_id', 'token_blacklist', ['user_id'])
    op.create_index('idx_token_blacklist_expires_at', 'token_blacklist', ['expires_at'])


def downgrade() -> None:
    """Drop token_blacklist table."""

    op.drop_index('idx_token_blacklist_expires_at', table_name='token_blacklist')
    op.drop_index('ix_token_blacklist_user_id', table_name='token_blacklist')
    op.drop_index('ix_token_blacklist_jti', table_name='token_blacklist')
    op.drop_table('token_blacklist')
