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

Escape hatch
------------
Setting env var MCP_ALLOW_INTERNAL_HOSTS=1 disables validation. Intended for
local dev and E2E tests that hit a localhost mock server. A warning is logged
each time this bypass is exercised so it shows up in production logs if
accidentally enabled.
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

    Bypass:
        If env var MCP_ALLOW_INTERNAL_HOSTS=1 is set, validation is skipped
        and a warning is logged.
    """
    # Operational escape hatch (dev / E2E)
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
