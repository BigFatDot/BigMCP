"""Add MFA fields to users table.

Revision ID: add_mfa_fields
Revises: add_tokens_revoked_at
Create Date: 2026-02-15 19:30:00.000000

Implements RFC 6238 TOTP-based two-factor authentication support.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_mfa_fields'
down_revision = 'add_tokens_revoked_at'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add MFA fields to users table."""
    # Add MFA fields
    op.add_column(
        'users',
        sa.Column(
            'mfa_enabled',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='Whether MFA is enabled for this user'
        )
    )
    op.add_column(
        'users',
        sa.Column(
            'mfa_secret',
            sa.String(255),
            nullable=True,
            comment='Encrypted TOTP secret (Fernet encrypted)'
        )
    )
    op.add_column(
        'users',
        sa.Column(
            'mfa_backup_codes',
            sa.Text(),
            nullable=True,
            comment='Encrypted JSON array of backup codes'
        )
    )
    op.add_column(
        'users',
        sa.Column(
            'mfa_enrolled_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='When MFA was enabled for this user'
        )
    )


def downgrade() -> None:
    """Remove MFA fields from users table."""
    op.drop_column('users', 'mfa_enrolled_at')
    op.drop_column('users', 'mfa_backup_codes')
    op.drop_column('users', 'mfa_secret')
    op.drop_column('users', 'mfa_enabled')
