"""Add password_reset_tokens table for secure password recovery

Revision ID: add_password_reset_tokens
Revises: ffd31a710c74
Create Date: 2026-01-21

Enables secure password reset flow:
- Stores hashed tokens (SHA-256)
- Tracks token expiration and usage
- Records request metadata for security auditing
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_password_reset_tokens'
down_revision: Union[str, None] = 'ffd31a710c74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create password_reset_tokens table."""

    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.UUID(), nullable=False),

        # User reference
        sa.Column('user_id', sa.UUID(), nullable=False,
                  comment='User who requested password reset'),

        # Token (hashed)
        sa.Column('token_hash', sa.String(length=64), nullable=False,
                  comment='SHA-256 hash of the reset token'),

        # Expiration
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False,
                  comment='Token expiration timestamp'),

        # Usage tracking
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True,
                  comment='When the token was used (None if not used)'),

        # Request metadata
        sa.Column('ip_address', sa.String(length=45), nullable=True,
                  comment='IP address that requested the reset'),
        sa.Column('user_agent', sa.String(length=500), nullable=True,
                  comment='User agent that requested the reset'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),

        # Primary key
        sa.PrimaryKeyConstraint('id'),

        # Foreign keys
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),

        # Unique constraint on token_hash
        sa.UniqueConstraint('token_hash', name='uq_password_reset_tokens_token_hash'),
    )

    # Create indexes for performance
    op.create_index('idx_password_reset_user', 'password_reset_tokens', ['user_id'])
    op.create_index('idx_password_reset_token_hash', 'password_reset_tokens', ['token_hash'])
    op.create_index('idx_password_reset_user_expires', 'password_reset_tokens', ['user_id', 'expires_at'])


def downgrade() -> None:
    """Drop password_reset_tokens table."""

    # Drop indexes
    op.drop_index('idx_password_reset_user_expires', table_name='password_reset_tokens')
    op.drop_index('idx_password_reset_token_hash', table_name='password_reset_tokens')
    op.drop_index('idx_password_reset_user', table_name='password_reset_tokens')

    # Drop table
    op.drop_table('password_reset_tokens')
