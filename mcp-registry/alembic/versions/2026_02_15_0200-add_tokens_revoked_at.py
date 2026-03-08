"""Add tokens_revoked_at column to users table

Revision ID: add_tokens_revoked_at
Revises: add_rls_policies
Create Date: 2026-02-15

This migration adds support for bulk token revocation by tracking
the timestamp of the last revocation event per user.

When validating a token, if it was issued before tokens_revoked_at,
it is considered invalid. This is more efficient than blacklisting
every individual token when:
- User changes password
- Admin revokes all user sessions
- Security incident requires immediate session termination

Security Design:
- NULL means no bulk revocation has occurred (all tokens valid)
- Timestamp means all tokens issued before this time are invalid
- JWT 'iat' (issued at) is compared against this timestamp
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_tokens_revoked_at'
down_revision: Union[str, None] = 'add_rls_policies'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add tokens_revoked_at column to users table."""

    op.add_column(
        'users',
        sa.Column(
            'tokens_revoked_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Timestamp of last bulk token revocation. Tokens issued before this are invalid.'
        )
    )

    # Create index for efficient lookups (though this column is rarely queried directly)
    op.create_index(
        'idx_users_tokens_revoked_at',
        'users',
        ['tokens_revoked_at'],
        unique=False,
        # Only index non-null values for space efficiency
        postgresql_where=sa.text('tokens_revoked_at IS NOT NULL')
    )


def downgrade() -> None:
    """Remove tokens_revoked_at column."""

    op.drop_index('idx_users_tokens_revoked_at', table_name='users')
    op.drop_column('users', 'tokens_revoked_at')
