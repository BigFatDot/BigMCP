"""Add email verification support

Revision ID: add_email_verification
Revises: add_password_reset_tokens
Create Date: 2026-01-21

Adds:
- email_verified column to users table
- email_verification_tokens table for verification flow
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_email_verification'
down_revision: Union[str, None] = 'add_password_reset_tokens'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add email verification support."""

    # Add email_verified column to users table
    # Default to True for existing users (they were already able to login)
    op.add_column('users',
        sa.Column('email_verified',
                  sa.Boolean(),
                  nullable=False,
                  server_default='true',
                  comment='Whether user has verified their email address'))

    # Create email_verification_tokens table
    op.create_table(
        'email_verification_tokens',
        sa.Column('id', sa.UUID(), nullable=False),

        # User reference
        sa.Column('user_id', sa.UUID(), nullable=False,
                  comment='User who needs email verification'),

        # Token (hashed)
        sa.Column('token_hash', sa.String(length=64), nullable=False,
                  comment='SHA-256 hash of the verification token'),

        # Email being verified
        sa.Column('email', sa.String(length=255), nullable=False,
                  comment='Email address being verified'),

        # Expiration
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False,
                  comment='Token expiration timestamp'),

        # Usage tracking
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True,
                  comment='When the email was verified (None if not verified)'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),

        # Primary key
        sa.PrimaryKeyConstraint('id'),

        # Foreign keys
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),

        # Unique constraint on token_hash
        sa.UniqueConstraint('token_hash', name='uq_email_verification_tokens_token_hash'),
    )

    # Create indexes for performance
    op.create_index('idx_email_verification_user', 'email_verification_tokens', ['user_id'])
    op.create_index('idx_email_verification_token_hash', 'email_verification_tokens', ['token_hash'])
    op.create_index('idx_email_verification_user_expires', 'email_verification_tokens', ['user_id', 'expires_at'])


def downgrade() -> None:
    """Remove email verification support."""

    # Drop indexes
    op.drop_index('idx_email_verification_user_expires', table_name='email_verification_tokens')
    op.drop_index('idx_email_verification_token_hash', table_name='email_verification_tokens')
    op.drop_index('idx_email_verification_user', table_name='email_verification_tokens')

    # Drop table
    op.drop_table('email_verification_tokens')

    # Remove column from users
    op.drop_column('users', 'email_verified')
