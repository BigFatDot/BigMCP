"""
LemonSqueezyWebhookEvent model — anti-replay idempotency log for inbound
LemonSqueezy webhooks.

Each row records one webhook delivery (fingerprinted by sha256 of the raw
payload) so we can:
- reject replays (same payload arriving twice → already_processed)
- detect duplicates in flight (insert with processed_at=NULL is a soft lock)
- diagnose handler failures after the fact (error column)

The HMAC signature is still verified upstream; this table is the second
line of defence ("the signature checks out, but have we seen this exact
delivery before?").
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, UUIDMixin


class LemonSqueezyWebhookEvent(Base, UUIDMixin):
    """One persisted LemonSqueezy webhook delivery (anti-replay fingerprint)."""

    __tablename__ = "lemonsqueezy_webhook_events"

    # Deterministic fingerprint of the delivery — currently sha256(raw_body).
    # Unique so a duplicate INSERT raises IntegrityError, which we catch to
    # return either 200 already_processed or 202 processing_in_progress.
    event_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
        comment="Deterministic fingerprint (sha256 of raw payload) of the delivery",
    )

    event_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="LemonSqueezy meta.event_name (subscription_created, ...)",
    )

    # Stored separately from event_id so future strategies (structured
    # event_id = event_name:data_id:custom_data_hash) keep a raw-body hash
    # for forensic comparison. For now event_id == payload_hash.
    payload_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="sha256 hex of the raw request body, for forensic comparison",
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        comment="When the webhook hit our edge (post-HMAC validation)",
    )

    # NULL while a handler is mid-flight (soft lock); set on successful
    # completion. Replay protection only fires when processed_at IS NOT NULL.
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the handler finished successfully (NULL = in flight or failed)",
    )

    # Populated if the handler raised. Mutually exclusive with a 'clean'
    # processed_at row, but processed_at is left NULL on failure so a
    # retry from LemonSqueezy can still be processed (after deleting / on
    # next delivery with a different payload fingerprint).
    error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="str(exception) if the handler raised; NULL on success",
    )

    __table_args__ = (
        Index(
            "ix_lemonsqueezy_webhook_events_event_name_received",
            "event_name",
            "received_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<LemonSqueezyWebhookEvent(id={self.id}, "
            f"event_name={self.event_name}, "
            f"event_id={self.event_id[:12]}..., "
            f"processed={self.processed_at is not None})>"
        )
