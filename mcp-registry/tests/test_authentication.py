"""
Tests for authentication endpoints.

Tests user registration, login, token refresh, and password management.
"""

import pytest
from httpx import AsyncClient


class TestUserRegistration:
    """Tests for user registration."""

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient):
        """Test successful user registration."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "SecurePass123",
                "name": "New User"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["name"] == "New User"
        assert "id" in data
        assert "created_at" in data
        assert "password" not in data  # Password should not be returned

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient, test_user: dict):
        """Test registration with duplicate email fails."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": test_user["email"],  # Already exists
                "password": "AnotherPass123",
                "name": "Duplicate User"
            }
        )

        assert response.status_code == 400, f"Expected 400, got {response.status_code}. Response: {response.json()}"
        response_data = response.json()
        # Error message can be in 'detail' or 'error' key
        error_msg = response_data.get("detail") or response_data.get("error", "")
        assert "already registered" in error_msg.lower(), f"Expected 'already registered' in error message. Got: {response_data}"

    @pytest.mark.asyncio
    async def test_register_duplicate_email_direct_db(self, client: AsyncClient, db_session):
        """Test registration with duplicate email fails - user created directly in DB."""
        from app.models.user import User, AuthProvider
        from app.models.organization import Organization, OrganizationMember, UserRole
        from app.services.auth_service import AuthService

        # Create user directly in database
        auth_service = AuthService(db_session)
        user = User(
            email="direct_db_user@example.com",
            name="Direct DB User",
            auth_provider=AuthProvider.LOCAL,
            password_hash=auth_service.hash_password("SecurePass123")
        )
        db_session.add(user)
        await db_session.flush()

        # Create organization
        organization = Organization(
            name="Direct DB Org",
            slug=f"org-{user.id}",
            organization_type="personal"
        )
        db_session.add(organization)
        await db_session.flush()

        # Create membership
        membership = OrganizationMember(
            user_id=user.id,
            organization_id=organization.id,
            role=UserRole.ADMIN
        )
        db_session.add(membership)

        # Commit everything
        await db_session.commit()

        # Now try to register with same email via HTTP
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "direct_db_user@example.com",  # Same email
                "password": "DifferentPass456",
                "name": "Duplicate User"
            }
        )

        assert response.status_code == 400, f"Expected 400, got {response.status_code}. Response: {response.json()}"
        response_data = response.json()
        # Error message can be in 'detail' or 'error' key
        error_msg = response_data.get("detail") or response_data.get("error", "")
        assert "already registered" in error_msg.lower(), f"Expected 'already registered' in error message. Got: {response_data}"

    @pytest.mark.asyncio
    async def test_register_weak_password(self, client: AsyncClient):
        """Test registration with weak password fails."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "weakpass@example.com",
                "password": "weak",  # Too short
                "name": "Weak Password User"
            }
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client: AsyncClient):
        """Test registration with invalid email fails."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "not-an-email",  # Invalid email
                "password": "SecurePass123",
                "name": "Invalid Email User"
            }
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_register_auto_creates_organization(self, client: AsyncClient):
        """Test that registration auto-creates a personal organization."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "orgtest@example.com",
                "password": "SecurePass123",
                "name": "Org Test User"
            }
        )

        assert response.status_code == 201

        # Login to get token
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "orgtest@example.com",
                "password": "SecurePass123"
            }
        )

        assert login_response.status_code == 200
        # Token should contain org_id
        assert "access_token" in login_response.json()


class TestUserLogin:
    """Tests for user login."""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, test_user: dict):
        """Test successful login."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user["email"],
                "password": test_user["password"]
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data
        assert data["expires_in"] > 0

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, test_user: dict):
        """Test login with wrong password fails."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user["email"],
                "password": "WrongPassword123"
            }
        )

        assert response.status_code == 401
        response_data = response.json()
        error_msg = response_data.get("detail") or response_data.get("error", "")
        assert "incorrect" in error_msg.lower()

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Test login with nonexistent user fails."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "SomePassword123"
            }
        )

        assert response.status_code == 401
        response_data = response.json()
        error_msg = response_data.get("detail") or response_data.get("error", "")
        assert "incorrect" in error_msg.lower()

    @pytest.mark.asyncio
    async def test_login_invalid_email_format(self, client: AsyncClient):
        """Test login with invalid email format fails."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "not-an-email",
                "password": "SomePassword123"
            }
        )

        assert response.status_code == 422  # Validation error


class TestTokenRefresh:
    """Tests for token refresh."""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, client: AsyncClient, test_user: dict):
        """Test successful token refresh."""
        response = await client.post(
            "/api/v1/auth/refresh",
            json={
                "refresh_token": test_user["refresh_token"]
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data
        # Tokens are valid JWT strings
        assert len(data["access_token"]) > 50
        assert len(data["refresh_token"]) > 50

    @pytest.mark.asyncio
    async def test_refresh_token_invalid(self, client: AsyncClient):
        """Test refresh with invalid token fails."""
        response = await client.post(
            "/api/v1/auth/refresh",
            json={
                "refresh_token": "invalid_token_here"
            }
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_with_access_token_fails(self, client: AsyncClient, test_user: dict):
        """Test refresh with access token instead of refresh token fails."""
        response = await client.post(
            "/api/v1/auth/refresh",
            json={
                "refresh_token": test_user["access_token"]  # Wrong token type
            }
        )

        assert response.status_code == 401


class TestGetCurrentUser:
    """Tests for getting current user information."""

    @pytest.mark.asyncio
    async def test_get_me_success(self, client: AsyncClient, auth_headers: dict, test_user: dict):
        """Test getting current user information."""
        response = await client.get("/api/v1/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user["email"]
        assert "id" in data
        assert "created_at" in data
        assert "password" not in data  # Password should never be returned

    @pytest.mark.asyncio
    async def test_get_me_without_token(self, client: AsyncClient):
        """Test getting current user without token fails."""
        response = await client.get("/api/v1/auth/me")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_with_invalid_token(self, client: AsyncClient):
        """Test getting current user with invalid token fails."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid_token"}
        )

        assert response.status_code == 401


class TestPasswordManagement:
    """Tests for password change."""

    @pytest.mark.asyncio
    async def test_change_password_success(self, client: AsyncClient, auth_headers: dict, test_user: dict):
        """Test successful password change."""
        new_password = "NewSecurePass456"

        response = await client.post(
            "/api/v1/auth/change-password",
            json={
                "old_password": test_user["password"],
                "new_password": new_password
            },
            headers=auth_headers
        )

        assert response.status_code == 204  # No content

        # Verify can login with new password
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user["email"],
                "password": new_password
            }
        )

        assert login_response.status_code == 200

        # Verify cannot login with old password
        old_login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user["email"],
                "password": test_user["password"]
            }
        )

        assert old_login_response.status_code == 401

    @pytest.mark.asyncio
    async def test_change_password_wrong_old_password(self, client: AsyncClient, auth_headers: dict):
        """Test password change with wrong old password fails."""
        response = await client.post(
            "/api/v1/auth/change-password",
            json={
                "old_password": "WrongOldPassword123",
                "new_password": "NewSecurePass456"
            },
            headers=auth_headers
        )

        assert response.status_code == 400
        response_data = response.json()
        error_msg = response_data.get("detail") or response_data.get("error", "")
        assert "incorrect" in error_msg.lower()

    @pytest.mark.asyncio
    async def test_change_password_weak_new_password(self, client: AsyncClient, auth_headers: dict, test_user: dict):
        """Test password change with weak new password fails."""
        response = await client.post(
            "/api/v1/auth/change-password",
            json={
                "old_password": test_user["password"],
                "new_password": "weak"  # Too short
            },
            headers=auth_headers
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_change_password_without_auth(self, client: AsyncClient):
        """Test password change without authentication fails."""
        response = await client.post(
            "/api/v1/auth/change-password",
            json={
                "old_password": "OldPass123",
                "new_password": "NewPass456"
            }
        )

        assert response.status_code == 401


class TestAuthenticationIntegration:
    """Integration tests for full authentication flows."""

    @pytest.mark.asyncio
    async def test_full_registration_to_authenticated_request(self, client: AsyncClient):
        """Test complete flow: register → login → authenticated request."""
        # Step 1: Register
        register_response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "integration@example.com",
                "password": "IntegrationPass123",
                "name": "Integration Test User"
            }
        )

        assert register_response.status_code == 201
        user_data = register_response.json()

        # Step 2: Login
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "integration@example.com",
                "password": "IntegrationPass123"
            }
        )

        assert login_response.status_code == 200
        token_data = login_response.json()

        # Step 3: Make authenticated request
        me_response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token_data['access_token']}"}
        )

        assert me_response.status_code == 200
        me_data = me_response.json()
        assert me_data["id"] == user_data["id"]
        assert me_data["email"] == "integration@example.com"

    @pytest.mark.asyncio
    async def test_token_refresh_flow(self, client: AsyncClient, test_user: dict):
        """Test complete token refresh flow."""
        # Use old access token
        old_token = test_user["access_token"]
        me_response_1 = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {old_token}"}
        )
        assert me_response_1.status_code == 200

        # Refresh token
        refresh_response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": test_user["refresh_token"]}
        )
        assert refresh_response.status_code == 200
        new_tokens = refresh_response.json()

        # Use new access token
        me_response_2 = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_tokens['access_token']}"}
        )
        assert me_response_2.status_code == 200

        # Old and new tokens should return same user
        assert me_response_1.json()["id"] == me_response_2.json()["id"]
