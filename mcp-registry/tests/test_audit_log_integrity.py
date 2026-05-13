"""Regression test for the audit-log HMAC integrity bug.

Before this fix, ``AuditLog.verify_integrity()`` returned False on every
row — including freshly written ones — because the timestamp was naive
at write time but timezone-aware after reload, producing a different
``isoformat()`` string between signing and verification.

This test guards the canonical-timestamp normalisation: a log written
with a naive datetime must verify after reload, and a log written with
an explicitly aware datetime must verify equally.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.audit_log import AuditAction, AuditLog


SECRET = "test-secret-for-audit-hmac"


def _make_log(ts: datetime) -> AuditLog:
    return AuditLog(
        id=uuid4(),
        timestamp=ts,
        actor_id=uuid4(),
        organization_id=uuid4(),
        action=AuditAction.LOGIN_SUCCESS.value,
        resource_type="user",
        resource_id="abc-123",
        details={"key": "value"},
    )


def test_verify_with_naive_timestamp_in_memory():
    """Signature computed once, verified immediately — must roundtrip."""
    log = _make_log(datetime(2026, 5, 13, 12, 0, 0, 123456))
    log.signature = log.calculate_signature(SECRET)
    assert log.verify_integrity(SECRET) is True


def test_verify_with_aware_timestamp_in_memory():
    """Aware timestamp must also produce a stable signature."""
    log = _make_log(datetime(2026, 5, 13, 12, 0, 0, 123456, tzinfo=timezone.utc))
    log.signature = log.calculate_signature(SECRET)
    assert log.verify_integrity(SECRET) is True


def test_verify_survives_naive_to_aware_conversion():
    """The bug scenario: sign with naive, verify with aware — must still match."""
    naive = datetime(2026, 5, 13, 12, 0, 0, 123456)
    log = _make_log(naive)
    log.signature = log.calculate_signature(SECRET)

    # Simulate the postgres reload that turns the timestamp into aware UTC.
    log.timestamp = naive.replace(tzinfo=timezone.utc)
    assert log.verify_integrity(SECRET) is True


def test_tampering_is_detected():
    """Sanity check the signature still detects tampering."""
    log = _make_log(datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc))
    log.signature = log.calculate_signature(SECRET)

    # Mutate the action — verify must fail.
    log.action = AuditAction.UNAUTHORIZED_ACCESS.value
    assert log.verify_integrity(SECRET) is False


@pytest.mark.asyncio
async def test_verify_after_real_db_roundtrip(db_session: AsyncSession):
    """End-to-end: write a log via AuditService, reload it, verify."""
    from app.services.audit_service import AuditService

    audit = AuditService(db_session)
    written = await audit.log_action(
        action=AuditAction.LOGIN_SUCCESS,
        actor_id=uuid4(),
        organization_id=uuid4(),
        resource_type="user",
        resource_id="roundtrip-test",
        details={"email": "[EMAIL_MASKED]"},
    )
    assert written is not None

    # Reload from DB to trigger the naive→aware conversion path.
    db_session.expire_all()
    result = await db_session.execute(
        select(AuditLog).where(AuditLog.resource_id == "roundtrip-test")
    )
    reloaded = result.scalar_one()
    assert reloaded.verify_integrity(settings.SECRET_KEY) is True
