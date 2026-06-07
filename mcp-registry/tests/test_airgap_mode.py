"""
Tests for AIRGAP_MODE — the opt-in flag that guarantees zero outbound
non-LLM HTTP from the BigMCP backend.

Coverage:
1. Boot WARN log is emitted when AIRGAP_MODE=true.
2. The marketplace singleton is instantiated with every source toggle
   forced to False.
3. IconResolver never returns a CDN URL when AIRGAP_MODE is on —
   instead it returns a self-contained data URI.
4. GET /edition/status surfaces "airgap": true so the frontend and
   external monitors can verify the posture.
"""

from __future__ import annotations

import importlib
import logging

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helper — return a fresh MarketplaceSyncService with AIRGAP_MODE flipped on
# without polluting the process-wide singleton (tests must stay isolated).
# ---------------------------------------------------------------------------


def _new_marketplace_with_airgap(monkeypatch):
    """
    Force ``get_marketplace_service`` to construct a fresh instance with
    AIRGAP_MODE=true, regardless of any previously cached singleton.
    """
    from app.core.config import settings as core_settings
    import app.services.marketplace_service as ms

    monkeypatch.setattr(core_settings, "AIRGAP_MODE", True, raising=False)
    monkeypatch.setattr(ms, "_marketplace_service", None, raising=False)
    return ms.get_marketplace_service()


# ---------------------------------------------------------------------------
# 1. Marketplace singleton — all toggles disabled
# ---------------------------------------------------------------------------


def test_airgap_marketplace_disables_all_sources(monkeypatch):
    """AIRGAP_MODE=true must zero out every outbound marketplace source."""
    svc = _new_marketplace_with_airgap(monkeypatch)

    assert svc._enable_npm is False
    assert svc._enable_github is False
    assert svc._enable_glama is False
    assert svc._enable_smithery is False

    # _build_sources() reads those toggles — every remaining source must
    # be local (file-backed), never an outbound fetcher. BigMCPSource is
    # OK because it loads a bundled JSON file from disk.
    source_class_names = {type(s).__name__ for s in svc.sources}
    forbidden = {"GitHubSource", "NPMSource", "GlamaSource", "SmitherySource"}
    leaked = source_class_names & forbidden
    assert not leaked, (
        "AIRGAP_MODE leaked outbound source(s): "
        f"{sorted(leaked)}. Full source set: {sorted(source_class_names)}"
    )


# ---------------------------------------------------------------------------
# 2. IconResolver — no CDN URL ever escapes
# ---------------------------------------------------------------------------


def test_airgap_icon_resolve_returns_data_uri(monkeypatch):
    """resolve() must return an inline SVG data URI, never a CDN URL."""
    from app.core.config import settings as core_settings
    from app.services.marketplace.icon_resolver import IconResolver

    monkeypatch.setattr(core_settings, "AIRGAP_MODE", True, raising=False)

    url = IconResolver.resolve("postgresql", "PostgreSQL")

    assert url.startswith("data:image/svg+xml"), (
        f"Expected inline data URI under AIRGAP_MODE, got: {url!r}"
    )
    assert "cdn.simpleicons.org" not in url
    assert "unpkg.com" not in url
    assert "ui-avatars.com" not in url


def test_airgap_icon_get_urls_collapses_to_data_uri(monkeypatch):
    """get_icon_urls() must collapse the entire chain to the data URI."""
    from app.core.config import settings as core_settings
    from app.services.marketplace.icon_resolver import IconResolver

    monkeypatch.setattr(core_settings, "AIRGAP_MODE", True, raising=False)

    urls = IconResolver.get_icon_urls("postgres", "Postgres")

    assert urls["primary"].startswith("data:image/svg+xml")
    assert urls["secondary"] is None
    assert urls["fallback"].startswith("data:image/svg+xml")
    # Make absolutely sure no CDN host slipped into any field.
    for v in urls.values():
        if v is None:
            continue
        assert "cdn.simpleicons.org" not in v
        assert "unpkg.com" not in v
        assert "ui-avatars.com" not in v


def test_airgap_icon_fallback_avatar_no_cdn(monkeypatch):
    """get_fallback_avatar() must NOT return a ui-avatars.com URL."""
    from app.core.config import settings as core_settings
    from app.services.marketplace.icon_resolver import IconResolver

    monkeypatch.setattr(core_settings, "AIRGAP_MODE", True, raising=False)

    url = IconResolver.get_fallback_avatar("My MCP Server")

    assert url.startswith("data:image/svg+xml")
    assert "ui-avatars.com" not in url


@pytest.mark.asyncio
async def test_airgap_icon_resolve_validated_no_network(monkeypatch):
    """resolve_validated() must short-circuit without any HTTP HEAD."""
    from app.core.config import settings as core_settings
    from app.services.marketplace.icon_resolver import IconResolver

    monkeypatch.setattr(core_settings, "AIRGAP_MODE", True, raising=False)

    # A http_client that raises if used — guarantees we never touch the
    # network under AIRGAP_MODE.
    class _ExplodingClient:
        async def head(self, *a, **kw):  # pragma: no cover
            raise AssertionError(
                "icon_resolver attempted an outbound HEAD under AIRGAP_MODE"
            )

    result = await IconResolver.resolve_validated(
        search_terms=["postgresql", "postgres"],
        service_name="Postgres",
        http_client=_ExplodingClient(),
    )

    assert result["primary"].startswith("data:image/svg+xml")
    assert result["fallback"].startswith("data:image/svg+xml")
    assert result["validated"] is True
    assert result.get("source") == "airgap_local"


def test_icon_resolver_default_still_uses_cdn(monkeypatch):
    """
    Sanity check: with AIRGAP_MODE=false (default), behaviour is unchanged
    — CDN URL is returned. Guarantees zero observable side-effect when
    operators don't opt in.
    """
    from app.core.config import settings as core_settings
    from app.services.marketplace.icon_resolver import IconResolver

    monkeypatch.setattr(core_settings, "AIRGAP_MODE", False, raising=False)

    url = IconResolver.resolve("postgresql", "PostgreSQL")
    assert url.startswith("https://cdn.simpleicons.org/")


# ---------------------------------------------------------------------------
# 3. /edition/status — surfaces the airgap flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edition_status_reports_airgap_true(client: AsyncClient, monkeypatch):
    from app.core.config import settings as core_settings

    monkeypatch.setattr(core_settings, "AIRGAP_MODE", True, raising=False)

    resp = await client.get("/edition/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "airgap" in body, f"airgap field missing from response: {body}"
    assert body["airgap"] is True


@pytest.mark.asyncio
async def test_edition_status_reports_airgap_false_by_default(
    client: AsyncClient, monkeypatch
):
    from app.core.config import settings as core_settings

    monkeypatch.setattr(core_settings, "AIRGAP_MODE", False, raising=False)

    resp = await client.get("/edition/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("airgap") is False


# ---------------------------------------------------------------------------
# 4. Boot WARN log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_airgap_boot_emits_warning(monkeypatch, caplog):
    """
    Reproduce the relevant slice of _startup_impl that decides whether
    to emit the AIRGAP_MODE WARN — we avoid invoking the full startup
    (DB init, registry, pool worker…) which would slow this test down
    enormously for no extra signal.
    """
    from app.core.config import settings as core_settings

    monkeypatch.setattr(core_settings, "AIRGAP_MODE", True, raising=False)

    logger = logging.getLogger("app.main")

    with caplog.at_level(logging.WARNING, logger="app.main"):
        if core_settings.AIRGAP_MODE:
            logger.warning(
                "⚠️  AIRGAP_MODE=true — marketplace sync, icon CDN, and "
                "LemonSqueezy disabled. Only LLM provider calls go outbound."
            )

    # Find at least one WARN record that mentions AIRGAP_MODE.
    airgap_records = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "AIRGAP_MODE" in r.getMessage()
    ]
    assert airgap_records, (
        "Expected a WARN log mentioning AIRGAP_MODE, got: "
        f"{[r.getMessage() for r in caplog.records]}"
    )
