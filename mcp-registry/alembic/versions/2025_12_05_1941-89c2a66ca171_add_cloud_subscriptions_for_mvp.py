"""Add Cloud subscriptions for MVP

Revision ID: 89c2a66ca171
Revises: create_audit_logs_table
Create Date: 2025-12-05 19:41

Ultra-simplified subscription model for Cloud MVP:
- 2 tiers only (Individual $5/month, Team $7/user/month)
- No LLM quota tracking (AI features unlimited)
- User limit enforcement only (1 for Individual, 20 for Team)
- LemonSqueezy billing integration
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '89c2a66ca171'
down_revision: Union[str, None] = 'create_audit_logs_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create subscriptions table for Cloud SaaS MVP."""

    # Create subscription_tier enum
    op.execute("CREATE TYPE subscription_tier AS ENUM ('individual', 'team')")

    # Create subscription_status enum
    op.execute("CREATE TYPE subscription_status AS ENUM ('trialing', 'active', 'past_due', 'cancelled', 'expired')")

    # Create subscriptions table
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.UUID(), nullable=False),

        # Tier & Status
        sa.Column('tier', sa.Enum('individual', 'team', name='subscription_tier'), nullable=False),
        sa.Column('status', sa.Enum('trialing', 'active', 'past_due', 'cancelled', 'expired', name='subscription_status'),
                  nullable=False, server_default='trialing'),

        # Organization link (nullable for Individual tier)
        sa.Column('organization_id', sa.UUID(), nullable=True),

        # Resource limits (ONLY user limit - no LLM quotas!)
        sa.Column('max_users', sa.Integer(), nullable=False, server_default='1'),

        # LemonSqueezy billing
        sa.Column('lemonsqueezy_subscription_id', sa.String(length=255), nullable=False),
        sa.Column('lemonsqueezy_customer_id', sa.String(length=255), nullable=True),
        sa.Column('lemonsqueezy_variant_id', sa.String(length=255), nullable=True),

        # Billing period
        sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=False),

        # Trial period (optional)
        sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True),

        # Cancellation tracking
        sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),

        # Metadata (JSONB)
        sa.Column('subscription_metadata', sa.JSON(), nullable=False, server_default='{}'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),

        # Primary key
        sa.PrimaryKeyConstraint('id'),

        # Foreign keys
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),

        # Unique constraints
        sa.UniqueConstraint('organization_id', name='uq_subscription_organization'),
        sa.UniqueConstraint('lemonsqueezy_subscription_id', name='uq_subscription_lemonsqueezy')
    )

    # Create indexes for performance
    op.create_index('idx_subscription_org_status', 'subscriptions', ['organization_id', 'status'])
    op.create_index('idx_subscription_lemonsqueezy', 'subscriptions', ['lemonsqueezy_subscription_id', 'status'])
    op.create_index('idx_subscription_period_end', 'subscriptions', ['current_period_end'])
    op.create_index('idx_subscriptions_tier', 'subscriptions', ['tier'])
    op.create_index('idx_subscriptions_status', 'subscriptions', ['status'])


def downgrade() -> None:
    """Drop subscriptions table and related enums."""

    # Drop indexes
    op.drop_index('idx_subscription_period_end', table_name='subscriptions')
    op.drop_index('idx_subscription_lemonsqueezy', table_name='subscriptions')
    op.drop_index('idx_subscription_org_status', table_name='subscriptions')
    op.drop_index('idx_subscriptions_status', table_name='subscriptions')
    op.drop_index('idx_subscriptions_tier', table_name='subscriptions')

    # Drop table
    op.drop_table('subscriptions')

    # Drop enums
    op.execute("DROP TYPE subscription_status")
    op.execute("DROP TYPE subscription_tier")
