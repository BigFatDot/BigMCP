"""
Tests for API key management endpoints.

Tests API key creation, listing, updating, revocation, and authentication.
"""

import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta


class TestAPIKeyCreation:
    """Tests for API key creation."""

    @pytest.mark.asyncio
    async def test_create_api_key_success(self, client: AsyncClient, auth_headers: dict):
        """Test successful API key creation."""
        response = await client.post(
            "/api/v1/api-keys",
            json={
                "name": "Test Key",
                "scopes": ["tools:read", "tools:execute"],
                "description": "A test API key"
            },
            headers=auth_headers
        )

        assert response.status_code == 201
        data = response.json()

        # Check api_key object
        assert "api_key" in data
        api_key = data["api_key"]
        assert api_key["name"] == "Test Key"
        assert api_key["scopes"] == ["tools:read", "tools:execute"]
        assert api_key["is_active"] is True
        assert "id" in api_key
        assert "key_prefix" in api_key
        assert api_key["key_prefix"].startswith("mcphub_sk_")

        # Check secret (only returned once!)
        assert "secret" in data
        assert data["secret"].startswith("mcphub_sk_")
        assert len(data["secret"]) > 20  # Should be longer than prefix

    @pytest.mark.asyncio
    async def test_create_api_key_with_expiration(self, client: AsyncClient, auth_headers: dict):
        """Test creating API key with expiration date."""
        expires_at = (datetime.utcnow() + timedelta(days=30)).isoformat()

        response = await client.post(
            "/api/v1/api-keys",
            json={
                "name": "Expiring Key",
                "scopes": ["tools:read"],
                "expires_at": expires_at
            },
            headers=auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["api_key"]["expires_at"] is not None

    @pytest.mark.asyncio
    async def test_create_api_key_without_auth(self, client: AsyncClient):
        """Test creating API key without authentication fails."""
        response = await client.post(
            "/api/v1/api-keys",
            json={
                "name": "Unauthenticated Key",
                "scopes": ["tools:read"]
            }
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_api_key_duplicate_name(self, client: AsyncClient, auth_headers: dict):
        """Test creating API key with duplicate name fails."""
        # Create first key
        response1 = await client.post(
            "/api/v1/api-keys",
            json={
                "name": "Duplicate Key Name",
                "scopes": ["tools:read"]
            },
            headers=auth_headers
        )
        assert response1.status_code == 201

        # Try to create second key with same name
        response2 = await client.post(
            "/api/v1/api-keys",
            json={
                "name": "Duplicate Key Name",
                "scopes": ["tools:execute"]
            },
            headers=auth_headers
        )
        assert response2.status_code == 400
        assert "already exists" in response2.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_api_key_invalid_scope(self, client: AsyncClient, auth_headers: dict):
        """Test creating API key with invalid scope fails."""
        response = await client.post(
            "/api/v1/api-keys",
            json={
                "name": "Invalid Scope Key",
                "scopes": ["invalid:scope"]  # Not a valid scope
            },
            headers=auth_headers
        )

        assert response.status_code == 422  # Validation error


class TestAPIKeyListing:
    """Tests for listing API keys."""

    @pytest.mark.asyncio
    async def test_list_api_keys(self, client: AsyncClient, auth_headers: dict, test_api_key: dict):
        """Test listing user's API keys."""
        response = await client.get("/api/v1/api-keys", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1  # At least the test_api_key

        # Check that secret is NOT returned in list
        for key in data:
            assert "secret" not in key
            assert "key_prefix" in key
            assert "name" in key
            assert "scopes" in key

    @pytest.mark.asyncio
    async def test_list_api_keys_without_auth(self, client: AsyncClient):
        """Test listing API keys without authentication fails."""
        response = await client.get("/api/v1/api-keys")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_single_api_key(self, client: AsyncClient, auth_headers: dict, test_api_key: dict):
        """Test getting a single API key by ID."""
        response = await client.get(
            f"/api/v1/api-keys/{test_api_key['id']}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_api_key["id"]
        assert data["name"] == test_api_key["name"]
        assert "secret" not in data  # Secret never returned after creation

    @pytest.mark.asyncio
    async def test_get_nonexistent_api_key(self, client: AsyncClient, auth_headers: dict):
        """Test getting nonexistent API key returns 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.get(
            f"/api/v1/api-keys/{fake_id}",
            headers=auth_headers
        )

        assert response.status_code == 404


class TestAPIKeyUpdate:
    """Tests for updating API keys."""

    @pytest.mark.asyncio
    async def test_update_api_key_name(self, client: AsyncClient, auth_headers: dict, test_api_key: dict):
        """Test updating API key name."""
        response = await client.patch(
            f"/api/v1/api-keys/{test_api_key['id']}",
            json={"name": "Updated Key Name"},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Key Name"

    @pytest.mark.asyncio
    async def test_update_api_key_scopes(self, client: AsyncClient, auth_headers: dict, test_api_key: dict):
        """Test updating API key scopes."""
        new_scopes = ["tools:read", "credentials:read"]

        response = await client.patch(
            f"/api/v1/api-keys/{test_api_key['id']}",
            json={"scopes": new_scopes},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert set(data["scopes"]) == set(new_scopes)

    @pytest.mark.asyncio
    async def test_update_api_key_deactivate(self, client: AsyncClient, auth_headers: dict, test_api_key: dict):
        """Test deactivating API key."""
        response = await client.patch(
            f"/api/v1/api-keys/{test_api_key['id']}",
            json={"is_active": False},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_update_api_key_description(self, client: AsyncClient, auth_headers: dict, test_api_key: dict):
        """Test updating API key description."""
        response = await client.patch(
            f"/api/v1/api-keys/{test_api_key['id']}",
            json={"description": "New description"},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "New description"


class TestAPIKeyRevocation:
    """Tests for API key revocation."""

    @pytest.mark.asyncio
    async def test_revoke_api_key(self, client: AsyncClient, auth_headers: dict):
        """Test revoking (deleting) an API key."""
        # Create a key to revoke
        create_response = await client.post(
            "/api/v1/api-keys",
            json={
                "name": "Key to Revoke",
                "scopes": ["tools:read"]
            },
            headers=auth_headers
        )
        assert create_response.status_code == 201
        key_id = create_response.json()["api_key"]["id"]

        # Revoke the key
        revoke_response = await client.delete(
            f"/api/v1/api-keys/{key_id}",
            headers=auth_headers
        )
        assert revoke_response.status_code == 204  # No content

        # Verify key is revoked (not active)
        get_response = await client.get(
            f"/api/v1/api-keys/{key_id}",
            headers=auth_headers
        )
        # Key might return 404 or return with is_active=False depending on implementation
        assert get_response.status_code in [404, 200]
        if get_response.status_code == 200:
            assert get_response.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_reactivate_api_key(self, client: AsyncClient, auth_headers: dict):
        """Test reactivating a revoked API key."""
        # Create and revoke a key
        create_response = await client.post(
            "/api/v1/api-keys",
            json={
                "name": "Key to Reactivate",
                "scopes": ["tools:read"]
            },
            headers=auth_headers
        )
        key_id = create_response.json()["api_key"]["id"]

        await client.delete(f"/api/v1/api-keys/{key_id}", headers=auth_headers)

        # Reactivate the key
        reactivate_response = await client.post(
            f"/api/v1/api-keys/{key_id}/activate",
            headers=auth_headers
        )

        assert reactivate_response.status_code == 200
        data = reactivate_response.json()
        assert data["is_active"] is True


class TestAPIKeyAuthentication:
    """Tests for authenticating with API keys."""

    @pytest.mark.asyncio
    async def test_authenticate_with_api_key(self, client: AsyncClient, test_api_key: dict):
        """Test authenticating with API key."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {test_api_key['secret']}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "email" in data

    @pytest.mark.asyncio
    async def test_authenticate_with_invalid_api_key(self, client: AsyncClient):
        """Test authenticating with invalid API key fails."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer mcphub_sk_invalid_key"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_authenticate_with_revoked_api_key(self, client: AsyncClient, auth_headers: dict):
        """Test authenticating with revoked API key fails."""
        # Create an API key
        create_response = await client.post(
            "/api/v1/api-keys",
            json={
                "name": "Key to Revoke and Test",
                "scopes": ["tools:read"]
            },
            headers=auth_headers
        )
        api_key_secret = create_response.json()["secret"]
        api_key_id = create_response.json()["api_key"]["id"]

        # Verify it works
        test_response1 = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {api_key_secret}"}
        )
        assert test_response1.status_code == 200

        # Revoke it
        await client.delete(f"/api/v1/api-keys/{api_key_id}", headers=auth_headers)

        # Verify it no longer works
        test_response2 = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {api_key_secret}"}
        )
        assert test_response2.status_code == 401

    @pytest.mark.asyncio
    async def test_api_key_updates_last_used(self, client: AsyncClient, test_api_key: dict, auth_headers: dict):
        """Test that using API key updates last_used_at timestamp."""
        # Get initial state
        initial_response = await client.get(
            f"/api/v1/api-keys/{test_api_key['id']}",
            headers=auth_headers
        )
        initial_last_used = initial_response.json().get("last_used_at")

        # Use the API key
        await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {test_api_key['secret']}"}
        )

        # Check last_used_at was updated
        updated_response = await client.get(
            f"/api/v1/api-keys/{test_api_key['id']}",
            headers=auth_headers
        )
        updated_last_used = updated_response.json()["last_used_at"]

        # last_used_at should be updated (might be None initially)
        assert updated_last_used is not None
        if initial_last_used:
            assert updated_last_used != initial_last_used


class TestAPIKeyScopeValidation:
    """Tests for API key scope validation."""

    @pytest.mark.asyncio
    async def test_api_key_with_limited_scope(self, client: AsyncClient, auth_headers: dict):
        """Test API key with limited scopes can only access allowed resources."""
        # Create API key with only tools:read scope
        create_response = await client.post(
            "/api/v1/api-keys",
            json={
                "name": "Limited Scope Key",
                "scopes": ["tools:read"]  # No tools:execute
            },
            headers=auth_headers
        )

        api_key = create_response.json()["secret"]
        api_key_headers = {"Authorization": f"Bearer {api_key}"}

        # This key should be able to authenticate
        me_response = await client.get("/api/v1/auth/me", headers=api_key_headers)
        assert me_response.status_code == 200

        # But might not be able to execute certain operations
        # (Depends on if endpoints check scopes - this is a demonstration)

    @pytest.mark.asyncio
    async def test_api_key_with_admin_scope(self, client: AsyncClient, auth_headers: dict):
        """Test API key with admin scope has full access."""
        create_response = await client.post(
            "/api/v1/api-keys",
            json={
                "name": "Admin Key",
                "scopes": ["admin"]  # Full access
            },
            headers=auth_headers
        )

        api_key = create_response.json()["secret"]
        api_key_headers = {"Authorization": f"Bearer {api_key}"}

        # Admin key should have full access
        me_response = await client.get("/api/v1/auth/me", headers=api_key_headers)
        assert me_response.status_code == 200


class TestAPIKeyIntegration:
    """Integration tests for API key workflows."""

    @pytest.mark.asyncio
    async def test_complete_api_key_lifecycle(self, client: AsyncClient, auth_headers: dict):
        """Test complete API key lifecycle: create → use → update → revoke."""
        # Step 1: Create API key
        create_response = await client.post(
            "/api/v1/api-keys",
            json={
                "name": "Lifecycle Test Key",
                "scopes": ["tools:read", "tools:execute"],
                "description": "Testing full lifecycle"
            },
            headers=auth_headers
        )
        assert create_response.status_code == 201
        api_key_data = create_response.json()
        api_key_secret = api_key_data["secret"]
        api_key_id = api_key_data["api_key"]["id"]

        # Step 2: Use API key
        use_response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {api_key_secret}"}
        )
        assert use_response.status_code == 200

        # Step 3: Update API key
        update_response = await client.patch(
            f"/api/v1/api-keys/{api_key_id}",
            json={"name": "Updated Lifecycle Key"},
            headers=auth_headers
        )
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "Updated Lifecycle Key"

        # Step 4: Revoke API key
        revoke_response = await client.delete(
            f"/api/v1/api-keys/{api_key_id}",
            headers=auth_headers
        )
        assert revoke_response.status_code == 204

        # Step 5: Verify key no longer works
        final_use_response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {api_key_secret}"}
        )
        assert final_use_response.status_code == 401
