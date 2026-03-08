"""Add refresh_tokens table for per-device session management

Revision ID: add_refresh_tokens
Revises: 89c2a66ca171
Create Date: 2025-12-09

Enables per-device session tracking for:
- Session visibility (list active devices)
- Session revocation (logout from specific devices)
- Token rotation security (detect reuse attacks)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_refresh_tokens'
down_revision: Union[str, None] = '89c2a66ca171'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create refresh_tokens table for per-device session management."""

    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.UUID(), nullable=False),

        # Ownership
        sa.Column('user_id', sa.UUID(), nullable=False),

        # Token data
        sa.Column('token_hash', sa.String(length=255), nullable=False,
                  comment='SHA-256 hash of the refresh token'),
        sa.Column('token_family', sa.String(length=64), nullable=False,
                  comment='Token family ID for detecting reuse attacks'),

        # Device identification
        sa.Column('device_id', sa.String(length=255), nullable=False,
                  comment='Hash of user_agent + fingerprint'),
        sa.Column('device_name', sa.String(length=255), nullable=True,
                  comment='Human-readable device name'),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),

        # Status and lifecycle
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_ip', sa.String(length=45), nullable=True),

        # Revocation info
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_reason', sa.String(length=255), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),

        # Primary key
        sa.PrimaryKeyConstraint('id'),

        # Foreign keys
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    # Create indexes for performance
    op.create_index('idx_refresh_tokens_user', 'refresh_tokens', ['user_id'])
    op.create_index('idx_refresh_tokens_user_active', 'refresh_tokens', ['user_id', 'is_active'])
    op.create_index('idx_refresh_tokens_user_device', 'refresh_tokens', ['user_id', 'device_id'])
    op.create_index('idx_refresh_tokens_token_family', 'refresh_tokens', ['token_family'])
    op.create_index('idx_refresh_tokens_expires', 'refresh_tokens', ['expires_at'])
    op.create_index('idx_refresh_tokens_active', 'refresh_tokens', ['is_active'])


def downgrade() -> None:
    """Drop refresh_tokens table."""

    # Drop indexes
    op.drop_index('idx_refresh_tokens_active', table_name='refresh_tokens')
    op.drop_index('idx_refresh_tokens_expires', table_name='refresh_tokens')
    op.drop_index('idx_refresh_tokens_token_family', table_name='refresh_tokens')
    op.drop_index('idx_refresh_tokens_user_device', table_name='refresh_tokens')
    op.drop_index('idx_refresh_tokens_user_active', table_name='refresh_tokens')
    op.drop_index('idx_refresh_tokens_user', table_name='refresh_tokens')

    # Drop table
    op.drop_table('refresh_tokens')
