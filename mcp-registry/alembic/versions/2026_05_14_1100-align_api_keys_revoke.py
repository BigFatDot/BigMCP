"""align_api_keys_revoke

Revision ID: align_api_keys_revoke
Revises: add_user_status
Create Date: 2026-05-14 11:00

Aligns api_keys with the RefreshToken.revoke() pattern so the N1.3
kill-switch endpoint can revoke both surfaces with a single vocabulary.

Adds:
- api_keys.revoked_at      TIMESTAMPTZ
- api_keys.revoked_reason  VARCHAR(64)

Existing rows: nothing to backfill — revoked_at NULL means "never
revoked"; the previous is_active=False rows stay valid as-is.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "align_api_keys_revoke"
down_revision: Union[str, None] = "add_user_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "api_keys",
        sa.Column("revoked_reason", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "revoked_reason")
    op.drop_column("api_keys", "revoked_at")
