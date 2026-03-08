"""Add invitations table for organization member invitations

Revision ID: add_invitations
Revises: add_token_blacklist
Create Date: 2025-12-17 10:00

Implements invitation system for organizations:
- Stores pending invitations with secure tokens
- Tracks invitation status (pending, accepted, declined, expired, revoked)
- Supports expiration dates and role assignment
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_invitations'
down_revision: Union[str, None] = 'add_token_blacklist'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create invitations table."""

    # Use String for status instead of Enum to avoid double-creation issues
    # The application layer handles enum validation via Pydantic
    op.create_table(
        'invitations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('invited_by', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('token', sa.String(64), nullable=False),
        sa.Column('role', sa.String(20), nullable=False, server_default='member'),
        sa.Column('message', sa.String(500), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('accepted_user_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['accepted_user_id'], ['users.id'], ondelete='SET NULL'),
    )

    # Create indexes for fast lookups
    op.create_index('ix_invitations_organization_id', 'invitations', ['organization_id'])
    op.create_index('ix_invitations_email', 'invitations', ['email'])
    op.create_index('ix_invitations_token', 'invitations', ['token'], unique=True)
    op.create_index('ix_invitations_status', 'invitations', ['status'])


def downgrade() -> None:
    """Drop invitations table."""

    op.drop_index('ix_invitations_status', table_name='invitations')
    op.drop_index('ix_invitations_token', table_name='invitations')
    op.drop_index('ix_invitations_email', table_name='invitations')
    op.drop_index('ix_invitations_organization_id', table_name='invitations')
    op.drop_table('invitations')
