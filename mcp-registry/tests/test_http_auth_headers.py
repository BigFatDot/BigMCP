"""
Tests for HTTP credential injection in HttpMCPWrapper.

Verifies that user credentials are correctly mapped to HTTP auth headers
when proxying requests to external MCP servers.
"""

import pytest
from app.core.mcp_wrapper import HttpMCPWrapper, create_wrapper


class TestExtractAuthHeaders:
    """Tests for HttpMCPWrapper.extract_auth_headers()."""

    def test_bearer_token(self):
        """BEARER_TOKEN credential maps to Authorization: Bearer header."""
        creds = {"BEARER_TOKEN": "my-secret-token"}
        headers = HttpMCPWrapper.extract_auth_headers(creds)
        assert headers == {"Authorization": "Bearer my-secret-token"}

    def test_access_token(self):
        """ACCESS_TOKEN credential maps to Authorization: Bearer header."""
        creds = {"ACCESS_TOKEN": "tok_123"}
        headers = HttpMCPWrapper.extract_auth_headers(creds)
        assert headers == {"Authorization": "Bearer tok_123"}

    def test_api_key(self):
        """API_KEY credential maps to X-API-Key header."""
        creds = {"API_KEY": "key_abc"}
        headers = HttpMCPWrapper.extract_auth_headers(creds)
        assert headers == {"X-API-Key": "key_abc"}

    def test_direct_authorization(self):
        """AUTHORIZATION credential is passed as-is to Authorization header."""
        creds = {"AUTHORIZATION": "CustomScheme xyz"}
        headers = HttpMCPWrapper.extract_auth_headers(creds)
        assert headers == {"Authorization": "CustomScheme xyz"}

    def test_basic_auth(self):
        """BASIC_AUTH credential maps to Authorization: Basic header."""
        creds = {"BASIC_AUTH": "dXNlcjpwYXNz"}
        headers = HttpMCPWrapper.extract_auth_headers(creds)
        assert headers == {"Authorization": "Basic dXNlcjpwYXNz"}

    def test_custom_http_header(self):
        """HTTP_HEADER_ prefix maps to custom headers."""
        creds = {"HTTP_HEADER_X_CUSTOM_AUTH": "custom-val"}
        headers = HttpMCPWrapper.extract_auth_headers(creds)
        assert "X-Custom-Auth" in headers
        assert headers["X-Custom-Auth"] == "custom-val"

    def test_case_insensitive_key_matching(self):
        """Auth key matching is case-insensitive."""
        creds = {"bearer_token": "tok"}
        headers = HttpMCPWrapper.extract_auth_headers(creds)
        assert headers == {"Authorization": "Bearer tok"}

    def test_non_auth_credentials_ignored(self):
        """Non-auth credentials (e.g. DATABASE_URL) produce no headers."""
        creds = {
            "DATABASE_URL": "postgres://...",
            "SMTP_HOST": "mail.example.com",
            "MY_SECRET": "abc123"
        }
        headers = HttpMCPWrapper.extract_auth_headers(creds)
        assert headers == {}

    def test_mixed_credentials(self):
        """Mix of auth and non-auth credentials — only auth keys produce headers."""
        creds = {
            "BEARER_TOKEN": "tok_123",
            "DATABASE_URL": "postgres://...",
            "API_KEY": "key_abc",
            "REDIS_URL": "redis://..."
        }
        headers = HttpMCPWrapper.extract_auth_headers(creds)
        assert headers == {
            "Authorization": "Bearer tok_123",
            "X-API-Key": "key_abc"
        }

    def test_empty_credentials(self):
        """Empty credentials dict produces no headers."""
        headers = HttpMCPWrapper.extract_auth_headers({})
        assert headers == {}

    def test_multiple_custom_headers(self):
        """Multiple HTTP_HEADER_ prefixed keys produce multiple custom headers."""
        creds = {
            "HTTP_HEADER_X_ORG_ID": "org-123",
            "HTTP_HEADER_X_PROJECT": "proj-456"
        }
        headers = HttpMCPWrapper.extract_auth_headers(creds)
        assert len(headers) == 2
        assert headers["X-Org-Id"] == "org-123"
        assert headers["X-Project"] == "proj-456"


class TestCreateWrapperWithCredentials:
    """Tests for create_wrapper() credential forwarding."""

    def test_http_wrapper_receives_auth_headers(self):
        """HTTP wrapper gets auth headers extracted from credentials."""
        config = {
            "command": "python",
            "args": ["-m", "server", "--transport", "streamable-http", "--port", "9000"],
            "env": {}
        }
        creds = {"BEARER_TOKEN": "my-token"}
        wrapper = create_wrapper("test-server", config, credentials=creds)

        assert isinstance(wrapper, HttpMCPWrapper)
        assert wrapper._auth_headers == {"Authorization": "Bearer my-token"}

    def test_external_url_wrapper(self):
        """External URL-only config creates HTTP wrapper without command."""
        config = {
            "command": "",
            "args": [],
            "env": {},
            "url": "http://localhost:8100/mcp"
        }
        creds = {"API_KEY": "key_xyz"}
        wrapper = create_wrapper("qgis-remote", config, credentials=creds)

        assert isinstance(wrapper, HttpMCPWrapper)
        assert wrapper.url == "http://localhost:8100/mcp"
        assert wrapper.command == ""
        assert wrapper._auth_headers == {"X-API-Key": "key_xyz"}

    def test_external_url_no_credentials(self):
        """External URL wrapper works without credentials."""
        config = {
            "command": "",
            "args": [],
            "env": {},
            "url": "http://localhost:8100/mcp"
        }
        wrapper = create_wrapper("qgis-remote", config)

        assert isinstance(wrapper, HttpMCPWrapper)
        assert wrapper._auth_headers == {}

    def test_stdio_wrapper_unaffected(self):
        """STDIO wrapper is unaffected by credentials (they go to env)."""
        from app.core.mcp_wrapper import StdioMCPWrapper
        config = {
            "command": "python",
            "args": ["-m", "some_server"],
            "env": {}
        }
        creds = {"API_KEY": "key_abc"}
        wrapper = create_wrapper("stdio-server", config, credentials=creds)

        assert isinstance(wrapper, StdioMCPWrapper)
        # StdioMCPWrapper doesn't have _auth_headers
        assert not hasattr(wrapper, "_auth_headers")
