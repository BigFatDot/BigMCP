"""
URL Validation Module — SSRF Protection

Validates external URLs used by MCP wrappers (HttpMCPWrapper, etc.) to ensure
they cannot be pointed at internal infrastructure.

Threat model
------------
A malicious user can declare a "remote HTTP" MCP server with an arbitrary URL.
Without validation, the gateway would happily proxy requests to:

  - http://127.0.0.1:6379          → internal Redis
  - http://169.254.169.254/...     → cloud IMDS (AWS/GCP) — credential exfil
  - http://postgres:5432           → internal Docker services
  - http://10.x.x.x, 192.168.x.x   → RFC1918 LAN

This module's `validate_external_url` raises ValueError on any such target.

Limitations (intentional, P0 scope)
-----------------------------------
We do not pin the resolved IP for the actual HTTP call → a determined attacker
could perform DNS rebinding (resolve to a public IP during the check, then to
127.0.0.1 when the request is sent milliseconds later). Pinning would require
intercepting the underlying socket layer in aiohttp, which is invasive and out
of scope for this P0. The current guard blocks the trivial attack (URL points
literally at a private address or known internal hostname).

Escape hatches
--------------
Two opt-in mechanisms, used for very different reasons:

  1. **MCP_ALLOW_INTERNAL_HOSTS=1** — disables validation entirely. Intended
     for local dev and E2E tests that hit a localhost mock server. A warning
     is logged each time this bypass is exercised so it shows up in
     production logs if accidentally enabled. DO NOT use in prod.

  2. **MCP_ALLOWED_INTERNAL_HOSTS=hostA,hostB** — a targeted allow-list of
     hostnames the admin has deliberately exposed to BigMCP. Use case: an
     internal Chrome DevTools / Playwright / RPC MCP server reachable via
     `host.docker.internal` or a docker-compose service name. Only the
     listed hostnames bypass the guard; everything else still goes through
     full validation (scheme, blocklist, IP-range). This is the right knob
     for prod when you know what you're exposing.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# Docker-compose service names + common dev shortcuts.
# Even if these resolve to public IPs in some weird DNS setup, we still want
# to refuse them at the hostname layer.
_BLOCKED_HOSTNAMES = {
    "localhost",
    "host.docker.internal",
    # Docker-compose service names from docker-compose.yml
    "postgres",
    "redis",
    "qdrant",
    "frontend",
    "backend",
    "nginx",
    "certbot",
    # Prefixed container names (bigmcp-*)
    "bigmcp-gateway",
    "bigmcp-postgres",
    "bigmcp-redis",
    "bigmcp-qdrant",
    "bigmcp-frontend",
    "bigmcp-nginx",
    "bigmcp-backend",
}

_ALLOWED_SCHEMES = {"http", "https"}

_ALLOW_INTERNAL_ENV_VAR = "MCP_ALLOW_INTERNAL_HOSTS"
_ALLOWED_INTERNAL_HOSTS_ENV_VAR = "MCP_ALLOWED_INTERNAL_HOSTS"


# Hostnames that the AIRGAP_MODE boot guard accepts as "local LLM endpoints".
# These cover docker-compose service names for the LLM runtimes BigMCP
# integrates with (Ollama / vLLM / llama.cpp / TGI / LocalAI), plus the
# standard host-machine pointers. Used by `is_local_endpoint`; intentionally
# narrow (we only want to ack endpoints we expect to see in an air-gapped
# deployment).
_LOCAL_LLM_HOSTNAMES = {
    "localhost",
    "host.docker.internal",
    "ollama",
    "vllm",
    "llama-cpp",
    "llama.cpp",
    "llamacpp",
    "text-generation-inference",
    "tgi",
    "localai",
    "ollama.internal",
}


def _load_allowed_internal_hosts() -> frozenset[str]:
    """
    Parse `MCP_ALLOWED_INTERNAL_HOSTS` into a frozenset of lowercase hostnames.

    Format: comma-separated. Whitespace and trailing dots are trimmed.
    Empty entries are skipped. Returns an empty set when the env var is
    unset or empty.
    """
    raw = os.environ.get(_ALLOWED_INTERNAL_HOSTS_ENV_VAR, "")
    if not raw:
        return frozenset()
    items = (
        item.strip().rstrip(".").lower()
        for item in raw.split(",")
    )
    return frozenset(item for item in items if item)


def _is_private_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """
    Return True if the IP address belongs to a non-routable / internal range.

    Covers:
      - Loopback (127.0.0.0/8, ::1)
      - Link-local (169.254.0.0/16, fe80::/10) — includes cloud IMDS
      - RFC1918 private (10/8, 172.16/12, 192.168/16)
      - IPv6 ULA (fc00::/7)
      - 0.0.0.0/8 unspecified
      - Multicast (224.0.0.0/4, ff00::/8)
      - Reserved
    """
    # ipaddress's built-in flags cover most of the dangerous categories.
    # We combine them defensively.
    if ip.is_loopback:
        return True
    if ip.is_link_local:  # 169.254.0.0/16 (IMDS!), fe80::/10
        return True
    if ip.is_private:  # RFC1918 + ULA
        return True
    if ip.is_multicast:
        return True
    if ip.is_unspecified:  # 0.0.0.0, ::
        return True
    if ip.is_reserved:
        return True

    # Defensive: explicit IMDS check in case is_link_local semantics drift
    if isinstance(ip, ipaddress.IPv4Address) and ip == ipaddress.IPv4Address("169.254.169.254"):
        return True

    # IPv4-mapped IPv6 (::ffff:127.0.0.1) — unwrap and recheck the v4 side
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _is_private_ip(ip.ipv4_mapped)

    return False


def _resolve_all(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """
    Resolve a hostname to all its A/AAAA records.

    Returns a list of ip_address objects. Raises socket.gaierror on failure.
    """
    infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        sockaddr = info[4]
        raw_ip = sockaddr[0]
        # Strip zone id from IPv6 link-local addresses (e.g. "fe80::1%eth0")
        if "%" in raw_ip:
            raw_ip = raw_ip.split("%", 1)[0]
        try:
            ips.append(ipaddress.ip_address(raw_ip))
        except ValueError:
            # Unparseable — treat as internal to fail closed
            raise
    return ips


def validate_external_url(url: str) -> None:
    """
    Raise ValueError if `url` is not safe to use as an outbound HTTP(S) target.

    Args:
        url: The full URL to validate.

    Raises:
        ValueError: When the URL scheme, hostname, or resolved IP(s) point at
            internal infrastructure (loopback, RFC1918, link-local/IMDS, Docker
            service names, etc.).

    Bypasses (both opt-in):
        - `MCP_ALLOW_INTERNAL_HOSTS=1` — global bypass, dev only, warning-logged
          per call.
        - `MCP_ALLOWED_INTERNAL_HOSTS=hostA,hostB` — targeted allow-list. If the
          URL's hostname matches an entry (after lowercasing and stripping a
          trailing dot), only the scheme is validated and the URL is accepted
          regardless of the blocklist or the resolved IP. Use this when you
          deliberately expose an internal MCP server (e.g. a chrome-devtools
          / playwright bridge reachable via `host.docker.internal`).
    """
    # Operational escape hatch (dev / E2E) — global bypass.
    if os.environ.get(_ALLOW_INTERNAL_ENV_VAR) == "1":
        logger.warning(
            f"⚠️  SSRF check bypassed via {_ALLOW_INTERNAL_ENV_VAR}=1 for URL "
            f"(do not use in production): {url}"
        )
        return

    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL must be a non-empty string")

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"URL is not parseable: {e}") from e

    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"URL scheme must be http or https (received: {scheme or '<empty>'})"
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("URL must include a hostname")

    # Strip trailing dot (FQDN form) for hostname comparisons
    hostname_norm = hostname.rstrip(".")

    # Targeted allow-list: the admin has explicitly opted in for this hostname.
    # Bypass blocklist + IP-range check; the scheme has already been validated.
    allowed_internal = _load_allowed_internal_hosts()
    if hostname_norm in allowed_internal:
        logger.info(
            f"SSRF guard: hostname '{hostname_norm}' is in "
            f"{_ALLOWED_INTERNAL_HOSTS_ENV_VAR}, accepting"
        )
        return

    if hostname_norm in _BLOCKED_HOSTNAMES:
        raise ValueError(
            f"URL hostname '{hostname_norm}' is an internal service and is not allowed"
        )

    # If the hostname is literally an IP address, check it directly. This
    # short-circuits any DNS resolution and catches the trivial attack of
    # passing http://127.0.0.1 or http://169.254.169.254.
    try:
        literal_ip = ipaddress.ip_address(hostname_norm)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if _is_private_ip(literal_ip):
            raise ValueError(
                f"URL must resolve to a public address (received: {hostname_norm})"
            )
        return  # Public IP literal — accept

    # Hostname → resolve and validate every returned address. Round-robin DNS
    # could return a mix of public and private IPs; we reject if any is private.
    try:
        resolved = _resolve_all(hostname_norm)
    except socket.gaierror as e:
        raise ValueError(
            f"URL hostname '{hostname_norm}' could not be resolved: {e}"
        ) from e

    if not resolved:
        raise ValueError(
            f"URL hostname '{hostname_norm}' did not resolve to any address"
        )

    for ip in resolved:
        if _is_private_ip(ip):
            raise ValueError(
                f"URL must resolve to a public address (received: {ip})"
            )


def is_local_endpoint(url: str) -> bool:
    """
    Return True if ``url`` points at a loopback / RFC1918 / ULA / link-local
    / Docker-internal host. Mirror of ``validate_external_url`` but with the
    sign flipped: external = bad over there, **local = required** here.

    Used by the AIRGAP_MODE boot guard (``app/main.py``) to refuse a public
    LLM_API_URL that would silently break the air-gap promise — every prompt
    would leak to e.g. ``api.mistral.ai`` or ``api.openai.com``.

    We reuse the same primitives as ``validate_external_url`` (URL parsing,
    DNS resolution via ``_resolve_all``, private-range introspection via
    ``_is_private_ip``) so that "what counts as private" stays a single
    source of truth across SSRF guard and air-gap guard.

    Accepts as "local":
      - Hostnames in the curated _LOCAL_LLM_HOSTNAMES list (``ollama``,
        ``vllm``, ``host.docker.internal``, ``localhost``, …) — these are
        the docker-compose service names we expect to see in an air-gapped
        deployment, regardless of how DNS resolves them inside the cluster.
      - Hostnames in _BLOCKED_HOSTNAMES (the SSRF blocklist — postgres,
        redis, etc.) → if you point LLM_API_URL at a docker service name,
        you're necessarily on a private network.
      - IP literals whose address belongs to a private range (covered by
        ``_is_private_ip`` — loopback, RFC1918, link-local, ULA, …).
      - Hostnames whose DNS resolution lands entirely on private IPs.

    Returns False on parse / resolution failure: when in doubt, err on the
    side of refusing the boot. A misconfigured DNS that flips an "internal"
    hostname to a public IP should not silently let us boot.
    """
    if not isinstance(url, str) or not url.strip():
        return False

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        # Anything that isn't http(s) — file:, gopher:, etc. — is not a
        # valid LLM endpoint and definitely not a sign that the operator
        # has set up a local LLM. Fail closed.
        return False

    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname:
        return False

    # Curated allow-list: docker-compose service names for the LLM runtimes
    # we support. Independent of how DNS resolves them — even if your local
    # split-horizon DNS maps `ollama` to a public IP for whatever reason,
    # the *intent* is unambiguous.
    if hostname in _LOCAL_LLM_HOSTNAMES:
        return True

    # SSRF blocklist also counts as "local" here: if the operator points
    # LLM_API_URL at e.g. `postgres` or `bigmcp-backend`, they're on a
    # private network (and arguably misconfigured, but not breaching the
    # air-gap promise — that's a different problem).
    if hostname in _BLOCKED_HOSTNAMES:
        return True

    # IP literal — check directly without DNS round-trip.
    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        return _is_private_ip(literal_ip)

    # Hostname → resolve and require **every** address to be private.
    # If a single public IP shows up in the round-robin response, the
    # endpoint can leak outbound and we refuse it.
    try:
        resolved = _resolve_all(hostname)
    except (socket.gaierror, ValueError):
        return False

    if not resolved:
        return False

    return all(_is_private_ip(ip) for ip in resolved)


def enforce_airgap_llm_constraint(
    airgap_mode: bool,
    llm_api_url: str | None,
    *,
    default_local_url: str = "http://localhost:11434/v1",
) -> str | None:
    """
    Boot-time guard: refuse to start when AIRGAP_MODE=1 + a public LLM_API_URL.

    Returns the effective LLM URL (the input value when set, or
    ``default_local_url`` when AIRGAP_MODE=1 and LLM_API_URL is unset).
    Returns None when AIRGAP_MODE=0 (the guard is inert).

    Raises:
        RuntimeError: When AIRGAP_MODE=1 but the configured LLM_API_URL
            resolves to a public host. Message includes both possible
            fixes (point at a local endpoint, or drop AIRGAP_MODE).

    Kept as a pure function — no settings or logger imports — so it can be
    unit-tested without booting FastAPI, and reused from CLI / smoke tools.
    """
    if not airgap_mode:
        return None

    url = (llm_api_url or "").strip() or default_local_url

    if is_local_endpoint(url):
        return url

    raise RuntimeError(
        "\n\n"
        f"  AIRGAP_MODE=1 but LLM_API_URL is public: {url}\n"
        "  Air-gap is a hard promise — refusing to boot rather than\n"
        "  silently routing every prompt to a public LLM endpoint.\n"
        "  Fix one of:\n"
        "    - set LLM_API_URL to a local endpoint "
        "(e.g. http://ollama:11434/v1)\n"
        "    - unset AIRGAP_MODE\n"
        "  See https://bigmcp.cloud/docs/self-hosting/llm-providers#air-gap-mode\n"
    )
