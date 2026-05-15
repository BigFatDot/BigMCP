"""add_composition_share_request

Revision ID: add_composition_share_request
Revises: add_persistent_pool
Create Date: 2026-05-15 09:00

Phase 4 — org-share review gate for compositions.

Six new nullable columns on ``compositions``:

- ``share_request_status``  : 'pending' | 'rejected' | NULL
- ``share_requested_by``    : user who opened the latest request
- ``share_requested_at``    : timestamp of that request
- ``share_review_notes``    : reviewer's free-text rationale
- ``share_reviewed_by``     : admin who decided
- ``share_reviewed_at``     : decision timestamp

Plus an index on (organization_id, share_request_status) so the admin
review queue is a fast lookup. All columns are nullable; no backfill
needed — every existing composition implicitly has no in-flight request.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_composition_share_request"
down_revision: Union[str, None] = "add_persistent_pool"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "compositions",
        sa.Column("share_request_status", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "compositions",
        sa.Column(
            "share_requested_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "compositions",
        sa.Column("share_requested_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "compositions",
        sa.Column("share_review_notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "compositions",
        sa.Column(
            "share_reviewed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "compositions",
        sa.Column("share_reviewed_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "idx_compositions_share_request_pending",
        "compositions",
        ["organization_id", "share_request_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_compositions_share_request_pending", table_name="compositions"
    )
    op.drop_column("compositions", "share_reviewed_at")
    op.drop_column("compositions", "share_reviewed_by")
    op.drop_column("compositions", "share_review_notes")
    op.drop_column("compositions", "share_requested_at")
    op.drop_column("compositions", "share_requested_by")
    op.drop_column("compositions", "share_request_status")
