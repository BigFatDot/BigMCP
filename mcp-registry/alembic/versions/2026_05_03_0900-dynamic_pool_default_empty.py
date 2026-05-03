"""dynamic_pool_default_empty

Revision ID: dynamic_pool_default_empty
Revises: add_remote_install_type
Create Date: 2026-05-03 09:00

UX redesign: the OAuth client surface becomes a dynamic per-user pool managed
by the new `search` MCP tool. Until a user calls `search`, no native tools are
exposed (the client only sees `search` and `execute`).

Changes:
- Reset all `tools.is_visible_to_oauth_clients` to FALSE so existing users
  start from an empty pool. Servers stay enabled and stay visible at the
  server level — only tool-level visibility is reset.
- Add a partial index optimizing the hot path in `tools/list` filtering by
  organization_id where the tool is currently in the pool.
- The Python-level default of the column is changed in app/models/tool.py
  (default=False) so newly installed tools also start outside the pool.

Rollback restores the legacy "all tools visible by default" behavior.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'dynamic_pool_default_empty'
down_revision: Union[str, None] = 'add_remote_install_type'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE tools SET is_visible_to_oauth_clients = FALSE")
    op.create_index(
        'ix_tools_org_visible_partial',
        'tools',
        ['organization_id'],
        unique=False,
        postgresql_where=sa.text('is_visible_to_oauth_clients = TRUE'),
    )


def downgrade() -> None:
    op.drop_index('ix_tools_org_visible_partial', table_name='tools')
    op.execute("UPDATE tools SET is_visible_to_oauth_clients = TRUE")
