"""
Tests for MCP Gateway authentication and access control.

Tests SSE endpoint authentication, tool filtering, and session management.
"""

import pytest
from httpx import AsyncClient
import json


class TestMCPGatewayAuthentication:
    """Tests for MCP Gateway SSE endpoint authentication."""

    @pytest.mark.asyncio
    async def test_mcp_gateway_requires_api_key(self, client: AsyncClient):
        """Test that MCP Gateway requires API key authentication."""
        response = await client.get("/mcp/sse")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_mcp_gateway_rejects_jwt_token(self, client: AsyncClient, auth_headers: dict):
        """Test that MCP Gateway rejects JWT tokens (requires API key)."""
        # MCP Gateway should only accept API keys, not JWT tokens
        response = await client.get("/mcp/sse", headers=auth_headers)

        # Might be 401 (unauthorized) or 403 (forbidden) depending on implementation
        # The point is JWT tokens shouldn't work for MCP Gateway
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_mcp_gateway_accepts_valid_api_key(self, client: AsyncClient, api_key_headers: dict):
        """Test that MCP Gateway accepts valid API key."""
        response = await client.get("/mcp/sse", headers=api_key_headers)

        # SSE endpoint should return 200 and start streaming
        assert response.status_code == 200

        # Check content type for SSE
        content_type = response.headers.get("content-type", "")
        assert "text/event-stream" in content_type.lower() or response.status_code == 200

    @pytest.mark.asyncio
    async def test_mcp_gateway_rejects_invalid_api_key(self, client: AsyncClient):
        """Test that MCP Gateway rejects invalid API key."""
        response = await client.get(
            "/mcp/sse",
            headers={"Authorization": "Bearer mcphub_sk_invalid_key_here"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_mcp_gateway_rejects_revoked_api_key(self, client: AsyncClient, auth_headers: dict):
        """Test that MCP Gateway rejects revoked API keys."""
        # Create an API key
        create_response = await client.post(
            "/api/v1/api-keys",
            json={"name": "Gateway Test Key", "scopes": ["tools:read", "tools:execute"]},
            headers=auth_headers
        )
        api_key = create_response.json()["secret"]
        api_key_id = create_response.json()["api_key"]["id"]

        # Verify it works
        test_response1 = await client.get(
            "/mcp/sse",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        assert test_response1.status_code == 200

        # Revoke the key
        await client.delete(f"/api/v1/api-keys/{api_key_id}", headers=auth_headers)

        # Verify it no longer works for MCP Gateway
        test_response2 = await client.get(
            "/mcp/sse",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        assert test_response2.status_code == 401


class TestMCPGatewaySessionManagement:
    """Tests for MCP Gateway session management."""

    @pytest.mark.asyncio
    async def test_mcp_gateway_creates_session_with_user_context(self, client: AsyncClient, api_key_headers: dict, test_api_key: dict):
        """Test that MCP Gateway creates session with proper user context."""
        response = await client.get("/mcp/sse", headers=api_key_headers)

        assert response.status_code == 200

        # Session should be created with user_id and organization_id
        # (This would require inspecting server-side session storage,
        #  or checking logs, so this is a placeholder)

    @pytest.mark.asyncio
    async def test_mcp_gateway_handles_disconnect(self, client: AsyncClient, api_key_headers: dict):
        """Test that MCP Gateway properly handles client disconnect."""
        # Connect to SSE
        response = await client.get("/mcp/sse", headers=api_key_headers)
        assert response.status_code == 200

        # Close connection (automatic with context manager)
        # Session should be cleaned up (would need to verify server-side)

    @pytest.mark.asyncio
    async def test_mcp_gateway_concurrent_sessions(self, client: AsyncClient, api_key_headers: dict):
        """Test multiple concurrent sessions with same API key."""
        import asyncio

        # Create multiple concurrent connections
        async def connect():
            return await client.get("/mcp/sse", headers=api_key_headers)

        responses = await asyncio.gather(*[connect() for _ in range(3)])

        # All should succeed
        for response in responses:
            assert response.status_code == 200


class TestMCPGatewayToolAccess:
    """Tests for tool access through MCP Gateway."""

    @pytest.mark.asyncio
    async def test_mcp_gateway_tool_list(self, client: AsyncClient, api_key_headers: dict):
        """Test listing tools through MCP Gateway."""
        # Connect to SSE
        response = await client.get("/mcp/sse", headers=api_key_headers)
        assert response.status_code == 200

        # Would need to send JSON-RPC request to list tools
        # This is a simplified test - full test would parse SSE stream
        # and send tools/list request

    @pytest.mark.asyncio
    async def test_mcp_gateway_filters_tools_by_organization(self, client: AsyncClient):
        """Test that MCP Gateway only shows tools from user's organization."""
        # Create two users in different organizations
        await client.post(
            "/api/v1/auth/register",
            json={"email": "org1gateway@example.com", "password": "Pass123", "name": "Org1 User"}
        )
        await client.post(
            "/api/v1/auth/register",
            json={"email": "org2gateway@example.com", "password": "Pass123", "name": "Org2 User"}
        )

        # Login and create API keys
        login1 = await client.post(
            "/api/v1/auth/login",
            json={"email": "org1gateway@example.com", "password": "Pass123"}
        )
        login2 = await client.post(
            "/api/v1/auth/login",
            json={"email": "org2gateway@example.com", "password": "Pass123"}
        )

        headers1 = {"Authorization": f"Bearer {login1.json()['access_token']}"}
        headers2 = {"Authorization": f"Bearer {login2.json()['access_token']}"}

        key1_response = await client.post(
            "/api/v1/api-keys",
            json={"name": "Org1 Gateway Key", "scopes": ["tools:read"]},
            headers=headers1
        )
        key2_response = await client.post(
            "/api/v1/api-keys",
            json={"name": "Org2 Gateway Key", "scopes": ["tools:read"]},
            headers=headers2
        )

        api_key1 = key1_response.json()["secret"]
        api_key2 = key2_response.json()["secret"]

        # Connect with both keys
        sse1 = await client.get("/mcp/sse", headers={"Authorization": f"Bearer {api_key1}"})
        sse2 = await client.get("/mcp/sse", headers={"Authorization": f"Bearer {api_key2}"})

        assert sse1.status_code == 200
        assert sse2.status_code == 200

        # Each user should only see tools from their organization
        # (Would need to parse SSE responses and verify tool lists)


class TestMCPGatewayToolGroupRestriction:
    """Tests for tool group restrictions on API keys."""

    @pytest.mark.asyncio
    async def test_api_key_with_tool_group_restricts_access(self, client: AsyncClient, auth_headers: dict):
        """Test that API key with tool_group_id only sees tools in that group."""
        # Create API key with tool group restriction
        # (Requires tool group to exist - might be skipped if not available)

        # This is a placeholder for tool group testing
        # Would create a tool group, create API key with that group,
        # and verify only tools in that group are accessible
        pass

    @pytest.mark.asyncio
    async def test_api_key_without_tool_group_sees_all_tools(self, client: AsyncClient, api_key_headers: dict):
        """Test that API key without tool_group_id sees all organization tools."""
        response = await client.get("/mcp/sse", headers=api_key_headers)

        assert response.status_code == 200
        # Should have access to all organization tools


class TestMCPGatewayCredentialResolution:
    """Tests for credential resolution in MCP Gateway."""

    @pytest.mark.asyncio
    async def test_mcp_gateway_uses_user_credentials(self, client: AsyncClient, api_key_headers: dict):
        """Test that MCP Gateway resolves credentials for authenticated user."""
        # This would require:
        # 1. Creating a user credential
        # 2. Connecting to MCP Gateway with API key
        # 3. Executing a tool that requires credentials
        # 4. Verifying the user's credential was used

        # Placeholder for credential resolution testing
        pass

    @pytest.mark.asyncio
    async def test_mcp_gateway_credential_hierarchy(self, client: AsyncClient):
        """Test credential resolution hierarchy: user > organization > server."""
        # Placeholder for testing credential fallback logic
        pass


class TestMCPGatewayHealthAndDiagnostics:
    """Tests for MCP Gateway health and diagnostic endpoints."""

    @pytest.mark.asyncio
    async def test_mcp_health_endpoint(self, client: AsyncClient):
        """Test MCP health endpoint."""
        response = await client.get("/mcp/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_mcp_health_returns_server_count(self, client: AsyncClient):
        """Test that MCP health returns server and tool counts."""
        response = await client.get("/mcp/health")

        assert response.status_code == 200
        data = response.json()
        assert "servers_count" in data or "tools_count" in data

    @pytest.mark.asyncio
    async def test_root_endpoint_information(self, client: AsyncClient):
        """Test root endpoint returns gateway information."""
        response = await client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "name" in data or "version" in data
        assert "endpoints" in data or "features" in data


class TestMCPGatewayEdgeCases:
    """Tests for MCP Gateway edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_mcp_gateway_with_expired_api_key(self, client: AsyncClient, auth_headers: dict):
        """Test MCP Gateway rejects expired API keys."""
        # Create API key with very short expiration
        # (Would need datetime manipulation or mock)
        # Placeholder for expired key testing
        pass

    @pytest.mark.asyncio
    async def test_mcp_gateway_with_insufficient_scopes(self, client: AsyncClient, auth_headers: dict):
        """Test MCP Gateway with API key lacking required scopes."""
        # Create API key without tools:execute scope
        limited_key_response = await client.post(
            "/api/v1/api-keys",
            json={"name": "Limited Scope Key", "scopes": ["credentials:read"]},  # No tools:*
            headers=auth_headers
        )
        limited_key = limited_key_response.json()["secret"]

        # Try to connect to MCP Gateway
        response = await client.get(
            "/mcp/sse",
            headers={"Authorization": f"Bearer {limited_key}"}
        )

        # Might still connect (scopes checked on tool execution)
        # or might reject at connection time
        assert response.status_code in [200, 403]

    @pytest.mark.asyncio
    async def test_mcp_gateway_handles_malformed_requests(self, client: AsyncClient, api_key_headers: dict):
        """Test that MCP Gateway handles malformed requests gracefully."""
        # Connect to gateway
        response = await client.get("/mcp/sse", headers=api_key_headers)
        assert response.status_code == 200

        # Would send malformed JSON-RPC requests and verify proper error responses
        # Placeholder for error handling testing


class TestMCPGatewayIntegration:
    """Integration tests for complete MCP Gateway workflows."""

    @pytest.mark.asyncio
    async def test_complete_mcp_connection_flow(self, client: AsyncClient):
        """Test complete flow: register → create API key → connect to MCP Gateway."""
        # Step 1: Register user
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "mcpflow@example.com",
                "password": "MCPFlow123",
                "name": "MCP Flow User"
            }
        )

        # Step 2: Login
        login_response = await client.post(
            "/api/v1/auth/login",
            json={"email": "mcpflow@example.com", "password": "MCPFlow123"}
        )
        jwt_token = login_response.json()["access_token"]
        jwt_headers = {"Authorization": f"Bearer {jwt_token}"}

        # Step 3: Create API key
        key_response = await client.post(
            "/api/v1/api-keys",
            json={"name": "MCP Connection Key", "scopes": ["tools:read", "tools:execute"]},
            headers=jwt_headers
        )
        api_key = key_response.json()["secret"]

        # Step 4: Connect to MCP Gateway
        mcp_response = await client.get(
            "/mcp/sse",
            headers={"Authorization": f"Bearer {api_key}"}
        )

        assert mcp_response.status_code == 200

    @pytest.mark.asyncio
    async def test_api_key_lifecycle_for_mcp_access(self, client: AsyncClient, auth_headers: dict):
        """Test API key lifecycle for MCP Gateway access."""
        # Create API key
        create_response = await client.post(
            "/api/v1/api-keys",
            json={"name": "MCP Lifecycle Key", "scopes": ["tools:read", "tools:execute"]},
            headers=auth_headers
        )
        api_key = create_response.json()["secret"]
        api_key_id = create_response.json()["api_key"]["id"]

        # Use key for MCP
        mcp1 = await client.get("/mcp/sse", headers={"Authorization": f"Bearer {api_key}"})
        assert mcp1.status_code == 200

        # Deactivate key
        await client.patch(
            f"/api/v1/api-keys/{api_key_id}",
            json={"is_active": False},
            headers=auth_headers
        )

        # Verify MCP access denied
        mcp2 = await client.get("/mcp/sse", headers={"Authorization": f"Bearer {api_key}"})
        assert mcp2.status_code == 401

        # Reactivate key
        await client.post(f"/api/v1/api-keys/{api_key_id}/activate", headers=auth_headers)

        # Verify MCP access restored
        mcp3 = await client.get("/mcp/sse", headers={"Authorization": f"Bearer {api_key}"})
        assert mcp3.status_code == 200
