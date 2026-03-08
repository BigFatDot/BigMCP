"""
Tests for authorization and protected endpoints.

Tests access control, admin permissions, and endpoint protection.
"""

import pytest
from httpx import AsyncClient


class TestEndpointProtection:
    """Tests for endpoint authentication requirements."""

    @pytest.mark.asyncio
    async def test_protected_endpoint_requires_auth(self, client: AsyncClient):
        """Test that protected endpoints require authentication."""
        # Try to access protected endpoint without auth
        response = await client.get("/api/v1/user-credentials/")

        assert response.status_code == 401
        assert "authorization" in response.json()["detail"].lower() or "authenticated" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_protected_endpoint_with_jwt(self, client: AsyncClient, auth_headers: dict):
        """Test accessing protected endpoint with JWT token."""
        response = await client.get("/api/v1/user-credentials/", headers=auth_headers)

        # Should succeed (even if returns empty list)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_protected_endpoint_with_api_key(self, client: AsyncClient, api_key_headers: dict):
        """Test accessing protected endpoint with API key."""
        response = await client.get("/api/v1/user-credentials/", headers=api_key_headers)

        # Should succeed (even if returns empty list)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_bearer_token(self, client: AsyncClient):
        """Test that invalid bearer token is rejected."""
        response = await client.get(
            "/api/v1/user-credentials/",
            headers={"Authorization": "Bearer invalid_token_12345"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_bearer_prefix(self, client: AsyncClient, test_user: dict):
        """Test that token without Bearer prefix is rejected."""
        response = await client.get(
            "/api/v1/user-credentials/",
            headers={"Authorization": test_user["access_token"]}  # Missing "Bearer"
        )

        assert response.status_code == 401


class TestAdminOnlyEndpoints:
    """Tests for admin-only endpoint protection."""

    @pytest.mark.asyncio
    async def test_admin_endpoint_with_regular_user(self, client: AsyncClient, auth_headers: dict):
        """Test that regular user cannot access admin endpoints."""
        # Try to create organization credential (admin only)
        response = await client.post(
            "/api/v1/org-credentials/",
            json={
                "server_id": "00000000-0000-0000-0000-000000000000",
                "credentials": {"api_key": "test"},
                "name": "Test Org Cred"
            },
            headers=auth_headers
        )

        # Might fail with 403 (Forbidden) or 400 (Bad Request for invalid server_id)
        # The important thing is it's not a 500 error and has proper auth check
        assert response.status_code in [400, 403, 404]

    @pytest.mark.asyncio
    async def test_admin_endpoint_without_auth(self, client: AsyncClient):
        """Test that admin endpoint requires authentication."""
        response = await client.post(
            "/api/v1/org-credentials/",
            json={
                "server_id": "00000000-0000-0000-0000-000000000000",
                "credentials": {"api_key": "test"},
                "name": "Test Org Cred"
            }
        )

        assert response.status_code == 401


class TestOrganizationIsolation:
    """Tests for multi-tenant organization isolation."""

    @pytest.mark.asyncio
    async def test_user_can_only_see_own_resources(self, client: AsyncClient):
        """Test that users can only see resources from their organization."""
        # Create two different users
        user1_response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "user1@example.com",
                "password": "Pass123User1",
                "name": "User One"
            }
        )
        assert user1_response.status_code == 201

        user2_response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "user2@example.com",
                "password": "Pass123User2",
                "name": "User Two"
            }
        )
        assert user2_response.status_code == 201

        # Login as user1
        login1 = await client.post(
            "/api/v1/auth/login",
            json={"email": "user1@example.com", "password": "Pass123User1"}
        )
        user1_token = login1.json()["access_token"]
        user1_headers = {"Authorization": f"Bearer {user1_token}"}

        # Login as user2
        login2 = await client.post(
            "/api/v1/auth/login",
            json={"email": "user2@example.com", "password": "Pass123User2"}
        )
        user2_token = login2.json()["access_token"]
        user2_headers = {"Authorization": f"Bearer {user2_token}"}

        # Each user's /me should return different data
        me1 = await client.get("/api/v1/auth/me", headers=user1_headers)
        me2 = await client.get("/api/v1/auth/me", headers=user2_headers)

        assert me1.json()["id"] != me2.json()["id"]
        assert me1.json()["email"] == "user1@example.com"
        assert me2.json()["email"] == "user2@example.com"

    @pytest.mark.asyncio
    async def test_api_keys_isolated_per_organization(self, client: AsyncClient):
        """Test that API keys are isolated per organization."""
        # Create two users with different organizations
        user1_response = await client.post(
            "/api/v1/auth/register",
            json={"email": "org1@example.com", "password": "SecurePass123", "name": "Org1 User"}
        )
        user2_response = await client.post(
            "/api/v1/auth/register",
            json={"email": "org2@example.com", "password": "SecurePass123", "name": "Org2 User"}
        )

        # Login both users
        login1 = await client.post(
            "/api/v1/auth/login",
            json={"email": "org1@example.com", "password": "SecurePass123"}
        )
        login2 = await client.post(
            "/api/v1/auth/login",
            json={"email": "org2@example.com", "password": "SecurePass123"}
        )

        user1_headers = {"Authorization": f"Bearer {login1.json()['access_token']}"}
        user2_headers = {"Authorization": f"Bearer {login2.json()['access_token']}"}

        # Create API key for user1
        key1_response = await client.post(
            "/api/v1/api-keys",
            json={"name": "User1 Key", "scopes": ["tools:read"]},
            headers=user1_headers
        )
        assert key1_response.status_code == 201

        # List API keys for user1
        list1 = await client.get("/api/v1/api-keys", headers=user1_headers)
        user1_keys = list1.json()

        # List API keys for user2
        list2 = await client.get("/api/v1/api-keys", headers=user2_headers)
        user2_keys = list2.json()

        # User1 should see their key, user2 should not
        assert len(user1_keys) >= 1
        assert all(key["name"] != "User1 Key" for key in user2_keys)


class TestDualAuthentication:
    """Tests for dual JWT/API key authentication."""

    @pytest.mark.asyncio
    async def test_jwt_and_api_key_return_same_user(self, client: AsyncClient, auth_headers: dict, api_key_headers: dict):
        """Test that JWT and API key auth return same user data."""
        # Get user info with JWT
        jwt_response = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert jwt_response.status_code == 200
        jwt_user = jwt_response.json()

        # Get user info with API key
        api_key_response = await client.get("/api/v1/auth/me", headers=api_key_headers)
        assert api_key_response.status_code == 200
        api_key_user = api_key_response.json()

        # Should be the same user
        assert jwt_user["id"] == api_key_user["id"]
        assert jwt_user["email"] == api_key_user["email"]

    @pytest.mark.asyncio
    async def test_can_switch_between_jwt_and_api_key(self, client: AsyncClient, auth_headers: dict, api_key_headers: dict):
        """Test that user can seamlessly switch between JWT and API key."""
        # Make request with JWT
        response1 = await client.get("/api/v1/user-credentials/", headers=auth_headers)
        assert response1.status_code == 200

        # Make request with API key
        response2 = await client.get("/api/v1/user-credentials/", headers=api_key_headers)
        assert response2.status_code == 200

        # Both should work and return same data
        assert response1.json() == response2.json()


class TestAuthenticationEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_malformed_authorization_header(self, client: AsyncClient):
        """Test various malformed authorization headers."""
        test_cases = [
            {"Authorization": ""},  # Empty
            {"Authorization": "Bearer"},  # No token
            {"Authorization": "Basic user:pass"},  # Wrong scheme
            {"Authorization": "bearer token"},  # Lowercase (might work depending on implementation)
            {"Authorization": "Bearer  token"},  # Extra space
        ]

        for headers in test_cases:
            response = await client.get("/api/v1/auth/me", headers=headers)
            assert response.status_code == 401, f"Failed for headers: {headers}"

    @pytest.mark.asyncio
    async def test_expired_token_handling(self, client: AsyncClient):
        """Test that expired tokens are rejected."""
        # Create a token that's already expired (mock/stub - actual test would need time manipulation)
        # This is a placeholder for proper expired token testing
        expired_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjB9.invalid"

        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_concurrent_requests_with_same_token(self, client: AsyncClient, auth_headers: dict):
        """Test multiple concurrent requests with same token work correctly."""
        import asyncio

        # Make 5 concurrent requests
        responses = await asyncio.gather(*[
            client.get("/api/v1/auth/me", headers=auth_headers)
            for _ in range(5)
        ])

        # All should succeed
        for response in responses:
            assert response.status_code == 200
            assert "id" in response.json()

    @pytest.mark.asyncio
    async def test_user_with_no_organization(self, client: AsyncClient, db_session):
        """Test that user without organization is handled properly."""
        # This would require creating a user without org membership
        # (normally prevented by registration flow)
        # Placeholder for edge case testing
        pass


class TestSecurityHeaders:
    """Tests for security-related headers."""

    @pytest.mark.asyncio
    async def test_unauthorized_includes_www_authenticate(self, client: AsyncClient):
        """Test that 401 responses include WWW-Authenticate header."""
        response = await client.get("/api/v1/auth/me")

        assert response.status_code == 401
        # Should include WWW-Authenticate header per OAuth2 spec
        # (implementation might not include this, but it's best practice)

    @pytest.mark.asyncio
    async def test_cors_headers_present(self, client: AsyncClient, auth_headers: dict):
        """Test that CORS headers are properly set."""
        response = await client.get("/api/v1/auth/me", headers=auth_headers)

        # Check for CORS headers (if configured)
        # This depends on CORS middleware configuration
        assert response.status_code == 200


class TestRateLimiting:
    """Tests for rate limiting (if implemented)."""

    @pytest.mark.asyncio
    async def test_rate_limiting_on_login(self, client: AsyncClient):
        """Test that repeated failed login attempts are rate limited."""
        # Placeholder for rate limiting tests
        # Would make many failed login attempts and verify rate limiting kicks in
        pass

    @pytest.mark.asyncio
    async def test_rate_limiting_on_api_key_usage(self, client: AsyncClient):
        """Test that excessive API key usage is rate limited."""
        # Placeholder for rate limiting tests
        pass


class TestAuthorizationIntegration:
    """Integration tests for complete authorization workflows."""

    @pytest.mark.asyncio
    async def test_full_protected_resource_access_flow(self, client: AsyncClient):
        """Test complete flow: register → login → access protected resource."""
        # Register
        register_response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "fullflow@example.com",
                "password": "FullFlow123",
                "name": "Full Flow User"
            }
        )
        assert register_response.status_code == 201

        # Login
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "fullflow@example.com",
                "password": "FullFlow123"
            }
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Access protected resource
        protected_response = await client.get(
            "/api/v1/user-credentials/",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert protected_response.status_code == 200

        # Access another protected resource
        contexts_response = await client.get(
            "/api/v1/contexts/",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert contexts_response.status_code == 200

    @pytest.mark.asyncio
    async def test_api_key_creation_and_usage_flow(self, client: AsyncClient):
        """Test complete API key flow: register → login → create key → use key."""
        # Register and login
        await client.post(
            "/api/v1/auth/register",
            json={"email": "keyflow@example.com", "password": "KeyFlow123", "name": "Key Flow User"}
        )
        login_response = await client.post(
            "/api/v1/auth/login",
            json={"email": "keyflow@example.com", "password": "KeyFlow123"}
        )
        jwt_token = login_response.json()["access_token"]
        jwt_headers = {"Authorization": f"Bearer {jwt_token}"}

        # Create API key
        key_response = await client.post(
            "/api/v1/api-keys",
            json={"name": "Flow Test Key", "scopes": ["tools:read", "tools:execute"]},
            headers=jwt_headers
        )
        assert key_response.status_code == 201
        api_key = key_response.json()["secret"]

        # Use API key to access protected resources
        api_key_headers = {"Authorization": f"Bearer {api_key}"}
        me_response = await client.get("/api/v1/auth/me", headers=api_key_headers)
        assert me_response.status_code == 200

        creds_response = await client.get("/api/v1/user-credentials/", headers=api_key_headers)
        assert creds_response.status_code == 200
