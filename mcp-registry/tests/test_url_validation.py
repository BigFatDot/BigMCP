"""
Tests for the SSRF guard in app.core.url_validation.

Covers:
  - Public URLs pass
  - Private / internal IP literals refused (loopback, RFC1918, link-local/IMDS)
  - Docker service hostnames refused
  - localhost refused
  - Non-HTTP(S) schemes refused
  - Env var bypass MCP_ALLOW_INTERNAL_HOSTS=1 disables checks
"""

import socket
from unittest.mock import patch

import pytest

from app.core.url_validation import validate_external_url


# ---------------------------------------------------------------------------
# Helpers: build fake getaddrinfo responses so DNS doesn't actually run during
# tests (and so public-hostname tests stay hermetic).
# ---------------------------------------------------------------------------

def _fake_getaddrinfo_factory(ip: str, family: int = socket.AF_INET):
    """Return a getaddrinfo stub that always resolves to `ip`."""

    def _stub(host, port, *args, **kwargs):
        return [(family, socket.SOCK_STREAM, 0, "", (ip, port or 0))]

    return _stub


# ---------------------------------------------------------------------------
# Positive case: public hostnames / IPs pass
# ---------------------------------------------------------------------------

class TestPublicUrlsAccepted:
    def test_public_hostname_passes(self):
        """A public hostname resolving to a public IP is accepted."""
        with patch("app.core.url_validation.socket.getaddrinfo",
                   side_effect=_fake_getaddrinfo_factory("8.8.8.8")):
            # Should not raise
            validate_external_url("https://api.example.com/mcp")

    def test_public_ip_literal_passes(self):
        """A bare public IP in the URL is accepted."""
        validate_external_url("https://1.1.1.1/mcp")

    def test_smithery_style_subdomain_passes(self):
        """Marketplace-style URLs (smithery.ai, glama.ai) pass."""
        with patch("app.core.url_validation.socket.getaddrinfo",
                   side_effect=_fake_getaddrinfo_factory("104.21.10.5")):
            validate_external_url("https://server.smithery.ai/abc/mcp")
            validate_external_url("https://glama.ai/api/mcp/v1/something")

    def test_https_with_port_passes(self):
        """Custom ports on public hosts are fine."""
        # Use a real-world public IP (Cloudflare DNS) rather than 203.0.113.x
        # which is the TEST-NET-3 documentation range and gets flagged as
        # reserved by ipaddress.is_reserved.
        with patch("app.core.url_validation.socket.getaddrinfo",
                   side_effect=_fake_getaddrinfo_factory("1.0.0.1")):
            validate_external_url("https://api.example.com:8443/mcp")


# ---------------------------------------------------------------------------
# Private IP literals refused
# ---------------------------------------------------------------------------

class TestPrivateIpLiteralsRefused:
    def test_loopback_127_refused(self):
        with pytest.raises(ValueError, match="public address"):
            validate_external_url("http://127.0.0.1:6379")

    def test_loopback_127_other_octet_refused(self):
        with pytest.raises(ValueError, match="public address"):
            validate_external_url("http://127.5.5.5/")

    def test_imds_169_254_169_254_refused(self):
        """AWS / GCP IMDS endpoint must be blocked."""
        with pytest.raises(ValueError, match="public address"):
            validate_external_url("http://169.254.169.254/latest/meta-data/")

    def test_rfc1918_10_refused(self):
        with pytest.raises(ValueError, match="public address"):
            validate_external_url("http://10.0.0.1/")

    def test_rfc1918_192_168_refused(self):
        with pytest.raises(ValueError, match="public address"):
            validate_external_url("http://192.168.1.1/")

    def test_rfc1918_172_16_refused(self):
        with pytest.raises(ValueError, match="public address"):
            validate_external_url("http://172.16.0.1/")

    def test_ipv6_loopback_refused(self):
        with pytest.raises(ValueError, match="public address"):
            validate_external_url("http://[::1]/")

    def test_ipv4_mapped_ipv6_loopback_refused(self):
        """::ffff:127.0.0.1 should unwrap and be rejected."""
        with pytest.raises(ValueError, match="public address"):
            validate_external_url("http://[::ffff:127.0.0.1]/")

    def test_ipv6_ula_refused(self):
        with pytest.raises(ValueError, match="public address"):
            validate_external_url("http://[fc00::1]/")


# ---------------------------------------------------------------------------
# Docker service names + localhost refused at the hostname layer
# ---------------------------------------------------------------------------

class TestDockerHostnamesRefused:
    def test_postgres_hostname_refused(self):
        with pytest.raises(ValueError, match="internal service"):
            validate_external_url("http://postgres:5432/")

    def test_redis_hostname_refused(self):
        with pytest.raises(ValueError, match="internal service"):
            validate_external_url("http://redis:6379/")

    def test_qdrant_hostname_refused(self):
        with pytest.raises(ValueError, match="internal service"):
            validate_external_url("http://qdrant:6333/")

    def test_backend_hostname_refused(self):
        with pytest.raises(ValueError, match="internal service"):
            validate_external_url("http://backend:8001/")

    def test_bigmcp_prefixed_refused(self):
        with pytest.raises(ValueError, match="internal service"):
            validate_external_url("http://bigmcp-postgres:5432/")

    def test_localhost_refused(self):
        with pytest.raises(ValueError, match="internal service"):
            validate_external_url("http://localhost:6379/")

    def test_host_docker_internal_refused(self):
        with pytest.raises(ValueError, match="internal service"):
            validate_external_url("http://host.docker.internal:8080/")


# ---------------------------------------------------------------------------
# Scheme + shape errors
# ---------------------------------------------------------------------------

class TestSchemeRefused:
    def test_file_scheme_refused(self):
        with pytest.raises(ValueError, match="scheme"):
            validate_external_url("file:///etc/passwd")

    def test_gopher_scheme_refused(self):
        with pytest.raises(ValueError, match="scheme"):
            validate_external_url("gopher://example.com/")

    def test_ftp_scheme_refused(self):
        with pytest.raises(ValueError, match="scheme"):
            validate_external_url("ftp://example.com/")

    def test_empty_url_refused(self):
        with pytest.raises(ValueError):
            validate_external_url("")

    def test_no_hostname_refused(self):
        with pytest.raises(ValueError):
            validate_external_url("http:///foo")


# ---------------------------------------------------------------------------
# DNS round-robin: any private IP in the response trips the guard
# ---------------------------------------------------------------------------

class TestDnsRoundRobin:
    def test_mixed_public_and_private_refused(self):
        """If DNS returns a public IP AND a private IP, refuse."""

        def stub(host, port, *args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "",
                 ("8.8.8.8", port or 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 0, "",
                 ("10.0.0.5", port or 0)),
            ]

        with patch("app.core.url_validation.socket.getaddrinfo", side_effect=stub):
            with pytest.raises(ValueError, match="public address"):
                validate_external_url("https://sneaky.example.com/")

    def test_unresolvable_hostname_refused(self):
        """DNS failure → fail closed."""

        def stub(host, port, *args, **kwargs):
            raise socket.gaierror("nope")

        with patch("app.core.url_validation.socket.getaddrinfo", side_effect=stub):
            with pytest.raises(ValueError, match="could not be resolved"):
                validate_external_url("https://this-does-not-exist.invalid/")


# ---------------------------------------------------------------------------
# Env var bypass
# ---------------------------------------------------------------------------

class TestEnvBypass:
    def test_env_bypass_allows_loopback(self, monkeypatch):
        monkeypatch.setenv("MCP_ALLOW_INTERNAL_HOSTS", "1")
        # Should not raise
        validate_external_url("http://127.0.0.1:6379")

    def test_env_bypass_allows_docker_hostname(self, monkeypatch):
        monkeypatch.setenv("MCP_ALLOW_INTERNAL_HOSTS", "1")
        validate_external_url("http://postgres:5432/")

    def test_env_bypass_allows_imds(self, monkeypatch):
        monkeypatch.setenv("MCP_ALLOW_INTERNAL_HOSTS", "1")
        validate_external_url("http://169.254.169.254/latest/meta-data/")

    def test_env_bypass_value_not_1_does_not_bypass(self, monkeypatch):
        """Only value '1' triggers bypass — '0', 'true', etc. don't."""
        monkeypatch.setenv("MCP_ALLOW_INTERNAL_HOSTS", "0")
        with pytest.raises(ValueError):
            validate_external_url("http://127.0.0.1:6379")

    def test_env_bypass_logs_warning(self, monkeypatch, caplog):
        import logging
        monkeypatch.setenv("MCP_ALLOW_INTERNAL_HOSTS", "1")
        with caplog.at_level(logging.WARNING, logger="app.core.url_validation"):
            validate_external_url("http://127.0.0.1:6379")
        assert any("SSRF check bypassed" in rec.message for rec in caplog.records)
