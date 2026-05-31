"""add_lemonsqueezy_webhook_events

Revision ID: add_lemonsqueezy_webhook_events
Revises: add_welcome_message
Create Date: 2026-05-31 22:00

Anti-replay idempotency log for inbound LemonSqueezy webhooks.

The webhook endpoint already verifies HMAC SHA256 on the raw body, but a
valid signed payload can be replayed (intercepted in transit or replayed
from logs). Each delivery is now fingerprinted with sha256(raw_body) and
inserted into this table BEFORE the handler runs; a duplicate fingerprint
short-circuits with 200 already_processed (handler ran) or 202 processing
(another worker holds the row).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision: str = "add_lemonsqueezy_webhook_events"
down_revision: Union[str, None] = "add_welcome_message"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lemonsqueezy_webhook_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_name", sa.String(length=128), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "event_id",
            name="uq_lemonsqueezy_webhook_events_event_id",
        ),
    )

    op.create_index(
        "ix_lemonsqueezy_webhook_events_event_id",
        "lemonsqueezy_webhook_events",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        "ix_lemonsqueezy_webhook_events_event_name_received",
        "lemonsqueezy_webhook_events",
        ["event_name", "received_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lemonsqueezy_webhook_events_event_name_received",
        table_name="lemonsqueezy_webhook_events",
    )
    op.drop_index(
        "ix_lemonsqueezy_webhook_events_event_id",
        table_name="lemonsqueezy_webhook_events",
    )
    op.drop_table("lemonsqueezy_webhook_events")
