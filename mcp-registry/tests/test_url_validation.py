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

from app.core.url_validation import (
    enforce_airgap_llm_constraint,
    is_local_endpoint,
    validate_external_url,
)


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


# =============================================================================
# Targeted internal-hosts allow-list (MCP_ALLOWED_INTERNAL_HOSTS)
# =============================================================================

class TestAllowedInternalHostsList:
    """A CSV env var lets an admin deliberately expose specific internal MCP
    servers (chrome-devtools bridge, RPC tunnels, …) without flipping the
    global escape hatch."""

    def test_allows_host_docker_internal_when_listed(self, monkeypatch):
        monkeypatch.setenv("MCP_ALLOWED_INTERNAL_HOSTS", "host.docker.internal")
        # Would normally raise — host.docker.internal is in the hard blocklist.
        validate_external_url("http://host.docker.internal:9222/devtools")

    def test_allows_docker_service_name_when_listed(self, monkeypatch):
        monkeypatch.setenv("MCP_ALLOWED_INTERNAL_HOSTS", "chrome-devtools,host.docker.internal")
        validate_external_url("http://chrome-devtools:9222/json/version")

    def test_still_refuses_unlisted_internal_host(self, monkeypatch):
        monkeypatch.setenv("MCP_ALLOWED_INTERNAL_HOSTS", "chrome-devtools")
        # postgres is NOT in the allow-list → still blocked.
        with pytest.raises(ValueError, match="internal service"):
            validate_external_url("http://postgres:5432/foo")

    def test_unset_env_keeps_blocklist_active(self, monkeypatch):
        monkeypatch.delenv("MCP_ALLOWED_INTERNAL_HOSTS", raising=False)
        with pytest.raises(ValueError, match="internal service"):
            validate_external_url("http://host.docker.internal:9222/foo")

    def test_empty_env_keeps_blocklist_active(self, monkeypatch):
        monkeypatch.setenv("MCP_ALLOWED_INTERNAL_HOSTS", "")
        with pytest.raises(ValueError, match="internal service"):
            validate_external_url("http://host.docker.internal:9222/foo")

    def test_csv_is_trimmed_and_lowercased(self, monkeypatch):
        # Spaces, mixed case, trailing dot — all normalised on parse.
        monkeypatch.setenv("MCP_ALLOWED_INTERNAL_HOSTS", "  Host.Docker.Internal. ,  ,chrome-devtools  ")
        validate_external_url("http://HOST.docker.internal/x")
        validate_external_url("http://chrome-devtools:9222/x")

    def test_allow_list_still_refuses_non_http_scheme(self, monkeypatch):
        # Even on a whitelisted hostname, scheme must be HTTP(S).
        monkeypatch.setenv("MCP_ALLOWED_INTERNAL_HOSTS", "host.docker.internal")
        with pytest.raises(ValueError, match="scheme"):
            validate_external_url("file:///etc/passwd")


# =============================================================================
# AIRGAP_MODE boot guard — `is_local_endpoint` + `enforce_airgap_llm_constraint`
# =============================================================================
#
# Same primitives as the SSRF guard (DNS resolution, private-range
# introspection) but with the sign flipped: "external = bad" becomes
# "local = required". Tests here pin the contract surface used by
# app/main.py at startup.


class TestIsLocalEndpoint:
    """Mirror of TestPublicUrlsAccepted / TestPrivateIpLiteralsRefused — same
    discrimination, inverse expectation."""

    def test_localhost_ollama_is_local(self):
        assert is_local_endpoint("http://localhost:11434/v1") is True

    def test_loopback_ip_literal_is_local(self):
        assert is_local_endpoint("http://127.0.0.1:11434/v1") is True

    def test_ipv6_loopback_is_local(self):
        assert is_local_endpoint("http://[::1]:11434/v1") is True

    def test_docker_service_ollama_is_local(self):
        # No DNS round-trip needed — `ollama` is in the curated allow-list.
        assert is_local_endpoint("http://ollama:11434/v1") is True

    def test_docker_service_vllm_is_local(self):
        assert is_local_endpoint("http://vllm:8000/v1") is True

    def test_host_docker_internal_is_local(self):
        assert is_local_endpoint("http://host.docker.internal:11434/v1") is True

    def test_rfc1918_literal_is_local(self):
        assert is_local_endpoint("http://10.0.0.5:8000/v1") is True
        assert is_local_endpoint("http://192.168.1.10:8000/v1") is True
        assert is_local_endpoint("http://172.16.0.1:8000/v1") is True

    def test_public_ip_literal_is_not_local(self):
        assert is_local_endpoint("https://1.1.1.1/v1") is False

    def test_public_hostname_is_not_local(self):
        with patch("app.core.url_validation.socket.getaddrinfo",
                   side_effect=_fake_getaddrinfo_factory("8.8.8.8")):
            assert is_local_endpoint("https://api.mistral.ai/v1") is False

    def test_openai_is_not_local(self):
        with patch("app.core.url_validation.socket.getaddrinfo",
                   side_effect=_fake_getaddrinfo_factory("104.18.0.5")):
            assert is_local_endpoint("https://api.openai.com/v1") is False

    def test_private_resolution_is_local(self):
        """A hostname that resolves entirely to private IPs is local."""
        with patch("app.core.url_validation.socket.getaddrinfo",
                   side_effect=_fake_getaddrinfo_factory("10.0.0.5")):
            assert is_local_endpoint("https://ollama.lan.example/v1") is True

    def test_mixed_resolution_is_not_local(self):
        """Same defensive stance as the SSRF guard: a single public IP in
        the round-robin response disqualifies the hostname."""
        def stub(host, port, *args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "",
                 ("10.0.0.5", port or 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 0, "",
                 ("8.8.8.8", port or 0)),
            ]

        with patch("app.core.url_validation.socket.getaddrinfo", side_effect=stub):
            assert is_local_endpoint("https://sneaky.example.com/v1") is False

    def test_unresolvable_is_not_local(self):
        """When in doubt, fail closed — refuse to mark as local."""
        def stub(host, port, *args, **kwargs):
            raise socket.gaierror("nope")

        with patch("app.core.url_validation.socket.getaddrinfo", side_effect=stub):
            assert is_local_endpoint("https://nope.invalid/v1") is False

    def test_malformed_url_is_not_local(self):
        assert is_local_endpoint("") is False
        assert is_local_endpoint("not a url") is False
        assert is_local_endpoint("file:///etc/passwd") is False
        assert is_local_endpoint("http:///nohostname") is False


class TestAirgapBootGuard:
    """The contract is dead simple:
        AIRGAP=0  → no-op (returns None)
        AIRGAP=1 + local URL → returns the URL
        AIRGAP=1 + no URL → defaults to local Ollama, returns it
        AIRGAP=1 + public URL → RuntimeError with actionable message
    """

    def test_airgap_off_does_not_check(self):
        """A public LLM_API_URL is fine when AIRGAP_MODE is off."""
        # Must NOT raise — guard is inert.
        assert enforce_airgap_llm_constraint(
            airgap_mode=False,
            llm_api_url="https://api.mistral.ai/v1",
        ) is None

    def test_airgap_off_with_no_url_returns_none(self):
        assert enforce_airgap_llm_constraint(
            airgap_mode=False,
            llm_api_url=None,
        ) is None

    def test_airgap_on_with_ollama_docker_boots(self):
        assert enforce_airgap_llm_constraint(
            airgap_mode=True,
            llm_api_url="http://ollama:11434/v1",
        ) == "http://ollama:11434/v1"

    def test_airgap_on_with_localhost_boots(self):
        assert enforce_airgap_llm_constraint(
            airgap_mode=True,
            llm_api_url="http://localhost:11434/v1",
        ) == "http://localhost:11434/v1"

    def test_airgap_on_with_host_docker_internal_boots(self):
        assert enforce_airgap_llm_constraint(
            airgap_mode=True,
            llm_api_url="http://host.docker.internal:11434/v1",
        ) == "http://host.docker.internal:11434/v1"

    def test_airgap_on_with_rfc1918_boots(self):
        assert enforce_airgap_llm_constraint(
            airgap_mode=True,
            llm_api_url="http://10.0.0.5:8000/v1",
        ) == "http://10.0.0.5:8000/v1"

    def test_airgap_on_with_public_mistral_refuses(self):
        with patch("app.core.url_validation.socket.getaddrinfo",
                   side_effect=_fake_getaddrinfo_factory("162.159.140.245")):
            with pytest.raises(RuntimeError) as exc_info:
                enforce_airgap_llm_constraint(
                    airgap_mode=True,
                    llm_api_url="https://api.mistral.ai/v1",
                )
        # Operator-facing message must mention both possible fixes so they
        # can act without grepping the source.
        msg = str(exc_info.value)
        assert "AIRGAP_MODE=1" in msg
        assert "api.mistral.ai" in msg
        assert "LLM_API_URL" in msg
        assert "ollama" in msg.lower()  # the local-fix example

    def test_airgap_on_with_public_openai_refuses(self):
        with patch("app.core.url_validation.socket.getaddrinfo",
                   side_effect=_fake_getaddrinfo_factory("104.18.0.5")):
            with pytest.raises(RuntimeError, match="AIRGAP_MODE=1"):
                enforce_airgap_llm_constraint(
                    airgap_mode=True,
                    llm_api_url="https://api.openai.com/v1",
                )

    def test_airgap_on_without_url_defaults_to_local_ollama(self):
        """No LLM_API_URL set → silently default to localhost:11434/v1.
        Boot succeeds, returned URL matches the default."""
        url = enforce_airgap_llm_constraint(
            airgap_mode=True,
            llm_api_url=None,
        )
        assert url == "http://localhost:11434/v1"

    def test_airgap_on_with_empty_url_defaults_to_local_ollama(self):
        """Empty string treated same as unset — operator left LLM_API_URL=
        in their .env."""
        url = enforce_airgap_llm_constraint(
            airgap_mode=True,
            llm_api_url="",
        )
        assert url == "http://localhost:11434/v1"

    def test_default_url_is_overridable(self):
        """The default endpoint is a kwarg so vLLM-default deployments can
        flip it without monkeypatching."""
        url = enforce_airgap_llm_constraint(
            airgap_mode=True,
            llm_api_url=None,
            default_local_url="http://vllm:8000/v1",
        )
        assert url == "http://vllm:8000/v1"

    def test_airgap_on_with_malformed_url_refuses(self):
        """A garbage URL with AIRGAP=1 must not silently sneak through —
        we can't prove it's local, so we refuse."""
        with pytest.raises(RuntimeError, match="AIRGAP_MODE=1"):
            enforce_airgap_llm_constraint(
                airgap_mode=True,
                llm_api_url="not-a-real-url",
            )
