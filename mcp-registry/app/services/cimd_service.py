"""CIMD (Client ID Metadata Document) service — SEP-991 / MCP 2025-11-25.

Lets BigMCP authenticate an OAuth client by **the URL it claims as its
own client_id**. The URL must be an HTTPS endpoint that returns a JSON
metadata document; we fetch, validate, cache, and let the policy engine
decide whether to auto-approve or queue for admin approval.

Validation rules (SEP-991, mandatory):
1. ``client_id`` is an HTTPS URL.
2. The fetched JSON contains a ``client_id`` field whose value
   **equals** the URL we just fetched (no impersonation).
3. ``redirect_uris`` is a non-empty list of HTTPS URLs.
4. ``client_name`` is a non-empty string.

Optional fields (``jwks_uri``, ``token_endpoint_auth_method``,
``logo_uri``, ``policy_uri``, ``tos_uri``) are passed through but not
enforced here — the OAuth flow will use them where applicable.

The service is deliberately small: no DB writes, no audit calls. It
returns either a validated dict (caller persists) or raises a typed
error the DCR endpoint translates to a 400 with a meaningful body.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx


logger = logging.getLogger(__name__)


class CIMDError(Exception):
    """Base error for CIMD operations."""


class CIMDInvalidURL(CIMDError):
    """The supposed CIMD URL is malformed or not HTTPS."""


class CIMDFetchError(CIMDError):
    """Network / HTTP-level failure when fetching the CIMD."""


class CIMDValidationError(CIMDError):
    """Fetched document violates the SEP-991 contract."""


# Cap the body so a malicious or misconfigured server can't OOM us.
MAX_DOCUMENT_BYTES = 64 * 1024  # 64 KiB
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_CACHE_TTL = timedelta(hours=24)


def is_https_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc)


class CIMDService:
    """Fetcher + validator for SEP-991 Client ID Metadata Documents.

    Stateless other than an injected httpx.AsyncClient (mockable in
    tests). Uses a plain awaitable interface so callers don't have
    to manage the client lifetime themselves; supply your own when
    you want connection pooling across many calls.
    """

    def __init__(
        self,
        http: Optional[httpx.AsyncClient] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._http = http
        self._owns_http = http is None
        self._timeout = timeout

    async def __aenter__(self) -> "CIMDService":
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._owns_http and self._http is not None:
            await self._http.aclose()
            self._http = None

    # ------------------------------------------------------------------ fetch

    async def fetch(self, url: str) -> Dict[str, Any]:
        """Download the JSON document at ``url`` and return it as a dict.

        Raises CIMDInvalidURL / CIMDFetchError. Does NOT validate the
        document yet — call ``validate`` for that.
        """
        if not is_https_url(url):
            raise CIMDInvalidURL(f"client_id must be an HTTPS URL, got: {url!r}")

        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._timeout)
            self._owns_http = True

        try:
            resp = await self._http.get(
                url,
                headers={"Accept": "application/json"},
                follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            raise CIMDFetchError(f"CIMD fetch failed for {url!r}: {exc}") from exc

        if resp.status_code != 200:
            raise CIMDFetchError(
                f"CIMD fetch returned HTTP {resp.status_code} for {url!r}"
            )

        if len(resp.content) > MAX_DOCUMENT_BYTES:
            raise CIMDFetchError(
                f"CIMD document too large ({len(resp.content)} bytes) for {url!r}"
            )

        try:
            return resp.json()
        except ValueError as exc:
            raise CIMDFetchError(f"CIMD document is not valid JSON: {exc}") from exc

    # ----------------------------------------------------------------- validate

    @staticmethod
    def validate(url: str, document: Dict[str, Any]) -> Dict[str, Any]:
        """Apply the SEP-991 mandatory checks. Returns the document on success."""
        if not isinstance(document, dict):
            raise CIMDValidationError("CIMD document must be a JSON object")

        claimed = document.get("client_id")
        if claimed != url:
            raise CIMDValidationError(
                f"CIMD client_id mismatch: document says {claimed!r}, "
                f"fetched from {url!r}"
            )

        name = document.get("client_name")
        if not isinstance(name, str) or not name.strip():
            raise CIMDValidationError("CIMD must have a non-empty client_name")

        redirect_uris = document.get("redirect_uris")
        if not isinstance(redirect_uris, list) or not redirect_uris:
            raise CIMDValidationError("CIMD must have a non-empty redirect_uris list")
        for ru in redirect_uris:
            if not isinstance(ru, str) or not is_https_url(ru):
                raise CIMDValidationError(
                    f"CIMD redirect_uri must be HTTPS, got: {ru!r}"
                )

        return document

    # ------------------------------------------------------------ fetch+validate

    async def fetch_and_validate(self, url: str) -> Dict[str, Any]:
        document = await self.fetch(url)
        return self.validate(url, document)

    # ------------------------------------------------------------- cache helpers

    @staticmethod
    def cache_is_fresh(
        last_fetched_at: Optional[datetime], ttl: timedelta = DEFAULT_CACHE_TTL
    ) -> bool:
        """Return True iff a cached doc dated ``last_fetched_at`` is still usable."""
        if last_fetched_at is None:
            return False
        # Normalise to naive UTC for comparison — the column is TIMESTAMPTZ
        # in Postgres but the ORM may return naive in tests.
        now = datetime.utcnow()
        if last_fetched_at.tzinfo is not None:
            last_fetched_at = last_fetched_at.replace(tzinfo=None)
        return (now - last_fetched_at) < ttl
