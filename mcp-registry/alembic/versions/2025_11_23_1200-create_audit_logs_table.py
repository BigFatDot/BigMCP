"""create audit_logs table for security compliance

Revision ID: create_audit_logs_table
Revises: add_alias_to_mcp_servers
Create Date: 2025-11-23 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'create_audit_logs_table'
down_revision = 'add_alias_to_mcp_servers'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, comment='Unique identifier'),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, comment='When the action occurred'),
        sa.Column('actor_id', postgresql.UUID(as_uuid=True), nullable=True, comment='User who performed the action (null for system actions)'),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True, comment='Organization context'),
        sa.Column('action', sa.String(length=50), nullable=False, comment='Action type (see AuditAction enum)'),
        sa.Column('resource_type', sa.String(length=50), nullable=False, comment='Type of resource affected (credential, composition, user, etc.)'),
        sa.Column('resource_id', sa.String(length=255), nullable=True, comment='ID of the affected resource'),
        sa.Column('ip_address', sa.String(length=45), nullable=True, comment='IPv4 or IPv6 address'),
        sa.Column('user_agent', sa.String(length=512), nullable=True, comment='User agent string'),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Additional context (PII-sanitized)'),
        sa.Column('signature', sa.String(length=64), nullable=False, comment='HMAC-SHA256 signature for tamper detection'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for common query patterns
    op.create_index('idx_audit_actor_timestamp', 'audit_logs', ['actor_id', 'timestamp'])
    op.create_index('idx_audit_org_timestamp', 'audit_logs', ['organization_id', 'timestamp'])
    op.create_index('idx_audit_action_timestamp', 'audit_logs', ['action', 'timestamp'])
    op.create_index('idx_audit_resource', 'audit_logs', ['resource_type', 'resource_id'])
    op.create_index('ix_audit_logs_timestamp', 'audit_logs', ['timestamp'])
    op.create_index('ix_audit_logs_actor_id', 'audit_logs', ['actor_id'])
    op.create_index('ix_audit_logs_organization_id', 'audit_logs', ['organization_id'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_resource_type', 'audit_logs', ['resource_type'])
    op.create_index('ix_audit_logs_resource_id', 'audit_logs', ['resource_id'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_audit_logs_resource_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_resource_type', table_name='audit_logs')
    op.drop_index('ix_audit_logs_action', table_name='audit_logs')
    op.drop_index('ix_audit_logs_organization_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_actor_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_timestamp', table_name='audit_logs')
    op.drop_index('idx_audit_resource', table_name='audit_logs')
    op.drop_index('idx_audit_action_timestamp', table_name='audit_logs')
    op.drop_index('idx_audit_org_timestamp', table_name='audit_logs')
    op.drop_index('idx_audit_actor_timestamp', table_name='audit_logs')

    # Drop table
    op.drop_table('audit_logs')
