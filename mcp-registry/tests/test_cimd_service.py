"""Tests for the CIMD (SEP-991) service.

Pure logic tests — no DB, no live HTTP. The fetch path is exercised
against a mock httpx transport so we can simulate every failure mode
the validator has to handle.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.services.cimd_service import (
    CIMDFetchError,
    CIMDInvalidURL,
    CIMDService,
    CIMDValidationError,
    is_https_url,
)


GOOD_URL = "https://claude.ai/.well-known/cimd"
GOOD_DOC = {
    "client_id": GOOD_URL,
    "client_name": "Claude Desktop",
    "redirect_uris": ["https://claude.ai/api/oauth/callback"],
}


# ---------------------------------------------------------------------------
# is_https_url helper
# ---------------------------------------------------------------------------


def test_is_https_url_accepts_only_https():
    assert is_https_url("https://claude.ai/cimd") is True
    assert is_https_url("http://claude.ai/cimd") is False
    assert is_https_url("ftp://example.org") is False
    assert is_https_url("not-a-url") is False
    assert is_https_url("https://") is False  # no host


# ---------------------------------------------------------------------------
# validate() — mandatory SEP-991 checks
# ---------------------------------------------------------------------------


def test_validate_happy_path():
    assert CIMDService.validate(GOOD_URL, GOOD_DOC) == GOOD_DOC


def test_validate_client_id_must_match_fetch_url():
    bad = {**GOOD_DOC, "client_id": "https://evil.example/cimd"}
    with pytest.raises(CIMDValidationError, match="mismatch"):
        CIMDService.validate(GOOD_URL, bad)


def test_validate_requires_non_empty_client_name():
    bad = {**GOOD_DOC, "client_name": ""}
    with pytest.raises(CIMDValidationError, match="client_name"):
        CIMDService.validate(GOOD_URL, bad)


def test_validate_redirect_uris_must_be_non_empty_list_of_https():
    with pytest.raises(CIMDValidationError):
        CIMDService.validate(GOOD_URL, {**GOOD_DOC, "redirect_uris": []})

    with pytest.raises(CIMDValidationError):
        CIMDService.validate(
            GOOD_URL,
            {**GOOD_DOC, "redirect_uris": ["http://insecure.example/cb"]},
        )


def test_validate_rejects_non_dict():
    with pytest.raises(CIMDValidationError):
        CIMDService.validate(GOOD_URL, ["not", "a", "dict"])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# fetch() — mocked transport
# ---------------------------------------------------------------------------


def _mock_transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_fetch_rejects_non_https_url():
    svc = CIMDService(http=httpx.AsyncClient(transport=_mock_transport(lambda r: httpx.Response(200))))
    with pytest.raises(CIMDInvalidURL):
        await svc.fetch("http://insecure.example/cimd")


@pytest.mark.asyncio
async def test_fetch_returns_parsed_json_on_200():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept"] == "application/json"
        return httpx.Response(200, json=GOOD_DOC)

    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        svc = CIMDService(http=client)
        got = await svc.fetch(GOOD_URL)
    assert got == GOOD_DOC


@pytest.mark.asyncio
async def test_fetch_raises_on_non_200():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        svc = CIMDService(http=client)
        with pytest.raises(CIMDFetchError, match="HTTP 404"):
            await svc.fetch(GOOD_URL)


@pytest.mark.asyncio
async def test_fetch_raises_on_oversized_body():
    big = ("x" * (70 * 1024)).encode()

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big)

    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        svc = CIMDService(http=client)
        with pytest.raises(CIMDFetchError, match="too large"):
            await svc.fetch(GOOD_URL)


@pytest.mark.asyncio
async def test_fetch_raises_on_bad_json():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        svc = CIMDService(http=client)
        with pytest.raises(CIMDFetchError, match="JSON"):
            await svc.fetch(GOOD_URL)


@pytest.mark.asyncio
async def test_fetch_and_validate_full_path():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=GOOD_DOC)

    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        svc = CIMDService(http=client)
        result = await svc.fetch_and_validate(GOOD_URL)
    assert result == GOOD_DOC


# ---------------------------------------------------------------------------
# cache_is_fresh helper
# ---------------------------------------------------------------------------


def test_cache_is_fresh_with_naive_recent():
    recent = datetime.utcnow() - timedelta(hours=1)
    assert CIMDService.cache_is_fresh(recent) is True


def test_cache_is_fresh_with_aware_recent():
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    assert CIMDService.cache_is_fresh(recent) is True


def test_cache_is_fresh_returns_false_for_stale():
    stale = datetime.utcnow() - timedelta(days=2)
    assert CIMDService.cache_is_fresh(stale) is False


def test_cache_is_fresh_returns_false_for_none():
    assert CIMDService.cache_is_fresh(None) is False
