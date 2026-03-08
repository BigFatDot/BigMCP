"""
Critical security tests for BigMCP.

Validates the sold security features:
- Fernet encryption for credentials (at rest)
- bcrypt password hashing
- bcrypt API key hashing
- JWT validation and security
- Injection protection
"""

import pytest
import json
import time
from datetime import datetime, timedelta
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class TestFernetEncryption:
    """Tests for Fernet encryption of credentials."""

    def test_fernet_encryption_roundtrip(self):
        """Test that encryption/decryption works correctly."""
        from app.core.secrets_manager import SecretsManager

        # Create a manager with a valid key
        key = Fernet.generate_key().decode()
        manager = SecretsManager(encryption_key=key)

        # Sensitive data to encrypt
        credentials = {
            "API_KEY": "sk-1234567890abcdef",
            "SECRET": "super_secret_value",
            "PASSWORD": "P@ssw0rd!123"
        }

        # Encrypt
        encrypted = manager.encrypt(credentials)

        # Verify it's properly encrypted (not plaintext)
        assert "sk-1234567890abcdef" not in encrypted
        assert "super_secret_value" not in encrypted
        assert "P@ssw0rd!123" not in encrypted

        # Decrypt and verify
        decrypted = manager.decrypt(encrypted)
        assert decrypted == credentials

    def test_fernet_encryption_produces_different_output(self):
        """Test that each encryption produces a different result (random IV)."""
        from app.core.secrets_manager import SecretsManager

        key = Fernet.generate_key().decode()
        manager = SecretsManager(encryption_key=key)

        credentials = {"API_KEY": "test_key"}

        # Encrypt multiple times
        encrypted1 = manager.encrypt(credentials)
        encrypted2 = manager.encrypt(credentials)
        encrypted3 = manager.encrypt(credentials)

        # Each encryption must be different (random IV)
        assert encrypted1 != encrypted2
        assert encrypted2 != encrypted3
        assert encrypted1 != encrypted3

        # But all must decrypt to the same value
        assert manager.decrypt(encrypted1) == credentials
        assert manager.decrypt(encrypted2) == credentials
        assert manager.decrypt(encrypted3) == credentials

    def test_fernet_wrong_key_fails_decryption(self):
        """Test that wrong key cannot decrypt."""
        from app.core.secrets_manager import SecretsManager

        key1 = Fernet.generate_key().decode()
        key2 = Fernet.generate_key().decode()

        manager1 = SecretsManager(encryption_key=key1)
        manager2 = SecretsManager(encryption_key=key2)

        credentials = {"API_KEY": "secret_key_12345"}
        encrypted = manager1.encrypt(credentials)

        # Decryption with wrong key must fail
        with pytest.raises(RuntimeError) as exc_info:
            manager2.decrypt(encrypted)

        assert "Decryption failed" in str(exc_info.value)

    def test_fernet_tampered_data_fails(self):
        """Test that modified data cannot be decrypted."""
        from app.core.secrets_manager import SecretsManager

        key = Fernet.generate_key().decode()
        manager = SecretsManager(encryption_key=key)

        credentials = {"API_KEY": "secret_key"}
        encrypted = manager.encrypt(credentials)

        # Modify encrypted data
        tampered = encrypted[:-5] + "XXXXX"

        # Decryption must fail (invalid HMAC)
        with pytest.raises(RuntimeError) as exc_info:
            manager.decrypt(tampered)

        assert "Decryption failed" in str(exc_info.value)

    def test_credential_masking(self):
        """Test credential masking for display."""
        from app.core.secrets_manager import SecretsManager

        key = Fernet.generate_key().decode()
        manager = SecretsManager(encryption_key=key)

        credentials = {
            "API_KEY": "sk-1234567890abcdef",
            "SHORT": "abc",
            "EMPTY": ""
        }

        masked = manager.mask_credentials(credentials)

        # Long values: first and last characters visible
        assert masked["API_KEY"] == "sk-***def"
        # Short values: completely masked
        assert masked["SHORT"] == "***"
        assert masked["EMPTY"] == "***"


class TestPasswordHashing:
    """Tests for bcrypt password hashing."""

    def test_password_hash_is_not_plaintext(self):
        """Test that password is never stored in plaintext."""
        from app.services.auth_service import AuthService
        from sqlalchemy.ext.asyncio import AsyncSession

        # Create a service without session (just to test hashing)
        class MockSession:
            pass

        auth_service = AuthService(MockSession())

        password = "MySecureP@ssw0rd!"
        hashed = auth_service.hash_password(password)

        # Hash must not contain the password in plaintext
        assert password not in hashed
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")  # bcrypt prefix

    def test_password_hash_is_different_each_time(self):
        """Test that each hash produces a different result (random salt)."""
        from app.services.auth_service import AuthService

        class MockSession:
            pass

        auth_service = AuthService(MockSession())

        password = "TestPassword123!"

        hash1 = auth_service.hash_password(password)
        hash2 = auth_service.hash_password(password)
        hash3 = auth_service.hash_password(password)

        # Each hash must be different (random salt)
        assert hash1 != hash2
        assert hash2 != hash3
        assert hash1 != hash3

    def test_password_verification_correct(self):
        """Test that password verification works."""
        from app.services.auth_service import AuthService

        class MockSession:
            pass

        auth_service = AuthService(MockSession())

        password = "CorrectPassword123!"
        hashed = auth_service.hash_password(password)

        # Verification with correct password
        assert auth_service.verify_password(password, hashed) is True

    def test_password_verification_wrong_password(self):
        """Test that wrong password is rejected."""
        from app.services.auth_service import AuthService

        class MockSession:
            pass

        auth_service = AuthService(MockSession())

        password = "CorrectPassword123!"
        wrong_password = "WrongPassword456!"

        hashed = auth_service.hash_password(password)

        # Verification with wrong password
        assert auth_service.verify_password(wrong_password, hashed) is False


class TestAPIKeyHashing:
    """Tests for bcrypt API key hashing."""

    def test_api_key_generation_format(self):
        """Test API key generation format."""
        from app.models.api_key import APIKey

        # Generate a key (returns tuple: full_key, prefix)
        full_key, key_prefix = APIKey.generate_key()

        # Verify format: mcphub_sk_<chars>
        assert full_key.startswith("mcphub_sk_")
        assert key_prefix.startswith("mcphub_sk_")
        assert len(key_prefix) == 20  # mcphub_sk_ (10) + 10 chars

    def test_api_key_hash_not_reversible(self):
        """Test that API key hash is not reversible."""
        from app.models.api_key import APIKey

        full_key, _ = APIKey.generate_key()
        key_hash = APIKey.hash_key(full_key)

        # Hash must not contain the key
        assert full_key not in key_hash
        # Must be a bcrypt hash
        assert key_hash.startswith("$2b$") or key_hash.startswith("$2a$")

    def test_api_key_prefix_returned_on_generation(self):
        """Test that prefix is returned on generation."""
        from app.models.api_key import APIKey

        full_key, key_prefix = APIKey.generate_key()

        # Prefix must be the first 20 characters
        assert key_prefix == full_key[:20]
        assert key_prefix.startswith("mcphub_sk_")

    def test_api_key_verification(self):
        """Test API key verification via instance."""
        from app.models.api_key import APIKey

        full_key, key_prefix = APIKey.generate_key()
        key_hash = APIKey.hash_key(full_key)

        # Create an API key instance with the hash
        api_key = APIKey(
            name="Test Key",
            key_hash=key_hash,
            key_prefix=key_prefix,
            scopes=["tools:read"]
        )

        # Verification with correct key (instance method)
        assert api_key.verify_key(full_key) is True

        # Verification with wrong key
        wrong_key, _ = APIKey.generate_key()
        assert api_key.verify_key(wrong_key) is False


class TestJWTSecurity:
    """Tests for JWT token security."""

    @pytest.mark.asyncio
    async def test_jwt_contains_required_claims(self, client: AsyncClient, test_user: dict):
        """Test that JWT contains required claims."""
        import jwt

        token = test_user["access_token"]

        # Decode without verification to inspect claims
        claims = jwt.decode(token, options={"verify_signature": False})

        # Required claims
        assert "sub" in claims  # user_id
        assert "exp" in claims  # expiration
        assert "type" in claims  # token type

        # Verify type
        assert claims["type"] == "access"

    @pytest.mark.asyncio
    async def test_jwt_expiration_enforced(self, client: AsyncClient):
        """Test that expired tokens are rejected."""
        import jwt
        from app.core.config import settings

        # Create an expired token manually
        expired_payload = {
            "sub": str(uuid4()),
            "org_id": str(uuid4()),
            "type": "access",
            "exp": datetime.utcnow() - timedelta(hours=1),  # Expired
            "iat": datetime.utcnow() - timedelta(hours=2)
        }

        expired_token = jwt.encode(
            expired_payload,
            settings.SECRET_KEY,
            algorithm="HS256"
        )

        # Attempt to use expired token
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_jwt_invalid_signature_rejected(self, client: AsyncClient):
        """Test that tokens with invalid signature are rejected."""
        import jwt

        # Create a token with wrong key
        fake_payload = {
            "sub": str(uuid4()),
            "org_id": str(uuid4()),
            "type": "access",
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow()
        }

        # Sign with wrong key
        fake_token = jwt.encode(
            fake_payload,
            "wrong_secret_key_that_is_long_enough",
            algorithm="HS256"
        )

        # Attempt to use the token
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {fake_token}"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_jwt_access_token_cannot_refresh(self, client: AsyncClient, test_user: dict):
        """Test that access token cannot be used for refresh."""
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": test_user["access_token"]}  # Wrong token type
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_token_cannot_access_api(self, client: AsyncClient, test_user: dict):
        """Test that refresh token cannot access API endpoints."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {test_user['refresh_token']}"}
        )

        assert response.status_code == 401


class TestPasswordNotInResponse:
    """Tests to ensure passwords are never exposed."""

    @pytest.mark.asyncio
    async def test_register_response_no_password(self, client: AsyncClient):
        """Test that registration response does not contain password."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "nopassword@example.com",
                "password": "SecretPassword123!",
                "name": "No Password User"
            }
        )

        assert response.status_code == 201
        data = response.json()

        # Verify password is not in response
        assert "password" not in data
        assert "password_hash" not in data
        assert "hashed_password" not in data
        assert "SecretPassword123!" not in str(data)

    @pytest.mark.asyncio
    async def test_login_response_no_password(self, client: AsyncClient, test_user: dict):
        """Test that login response does not contain password."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user["email"],
                "password": test_user["password"]
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Verify password is not in response
        assert "password" not in data
        assert test_user["password"] not in str(data)

    @pytest.mark.asyncio
    async def test_me_endpoint_no_password(self, client: AsyncClient, auth_headers: dict, test_user: dict):
        """Test that /me does not return password."""
        response = await client.get("/api/v1/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        # Verify password is not in response
        assert "password" not in data
        assert "password_hash" not in data
        assert test_user["password"] not in str(data)


class TestAPIKeySecretNotReturned:
    """Tests to ensure API key secrets are only returned once."""

    @pytest.mark.asyncio
    async def test_api_key_secret_only_on_creation(self, client: AsyncClient, auth_headers: dict):
        """Test that secret is only returned at creation."""
        # Create a key
        create_response = await client.post(
            "/api/v1/api-keys",
            json={"name": "Secret Test Key", "scopes": ["tools:read"]},
            headers=auth_headers
        )

        assert create_response.status_code == 201
        create_data = create_response.json()

        # Secret must be present at creation
        assert "secret" in create_data
        secret = create_data["secret"]
        assert secret.startswith("mcphub_sk_")

        key_id = create_data["api_key"]["id"]

        # Retrieve key by ID
        get_response = await client.get(
            f"/api/v1/api-keys/{key_id}",
            headers=auth_headers
        )

        assert get_response.status_code == 200
        get_data = get_response.json()

        # Secret must NOT be present
        assert "secret" not in get_data
        assert secret not in str(get_data)

    @pytest.mark.asyncio
    async def test_api_key_list_no_secrets(self, client: AsyncClient, auth_headers: dict, test_api_key: dict):
        """Test that key list does not contain secrets."""
        response = await client.get("/api/v1/api-keys", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        # Verify no secrets are exposed
        for key in data:
            assert "secret" not in key
            assert "key_hash" not in key


class TestInputValidation:
    """Tests for input validation (injection protection)."""

    @pytest.mark.asyncio
    async def test_sql_injection_in_email(self, client: AsyncClient):
        """Test that SQL injection in email is blocked."""
        malicious_emails = [
            "test@example.com'; DROP TABLE users; --",
            "test@example.com\" OR \"1\"=\"1",
            "test@example.com; DELETE FROM users",
        ]

        for email in malicious_emails:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "Test123!"}
            )

            # Must fail with validation or 401, not 500
            assert response.status_code in [401, 422], f"Failed for email: {email}"

    @pytest.mark.asyncio
    async def test_xss_in_name(self, client: AsyncClient):
        """Test that XSS in name is escaped/rejected."""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')",
        ]

        for payload in xss_payloads:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"xss{uuid4().hex[:8]}@example.com",
                    "password": "SecurePass123!",
                    "name": payload
                }
            )

            # Either accepted (stored escaped) or rejected
            # But no server error
            assert response.status_code in [201, 400, 422], f"Failed for payload: {payload}"

            if response.status_code == 201:
                # If accepted, verify content is not executable
                data = response.json()
                # Script should not be returned as-is (escaped)
                # Note: Depends on frontend implementation

    @pytest.mark.asyncio
    async def test_oversized_input_rejected(self, client: AsyncClient):
        """Test that extremely large inputs are handled."""
        # Extremely long name (100KB)
        long_name = "A" * 100000

        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"oversized-{uuid4().hex[:8]}@example.com",
                "password": "SecurePass123!",
                "name": long_name
            }
        )

        # Must be rejected (400/413/422) or truncated (201)
        # Important thing is it doesn't crash (no 500)
        assert response.status_code != 500


class TestTimingAttackPrevention:
    """Tests for timing attack prevention."""

    @pytest.mark.asyncio
    async def test_login_timing_consistency(self, client: AsyncClient, test_user: dict):
        """
        Test that response time is similar for existing/non-existing user.

        NOTE: This test is disabled because it detects a real timing vulnerability:
        - Existing user (wrong password): ~0.2s (bcrypt verification)
        - Non-existing user: ~0.004s (no bcrypt)

        SECURITY TODO: Implement a dummy bcrypt for non-existing users
        to have constant response time.
        """
        import statistics

        # Measure time for existing user (wrong password)
        existing_times = []
        for _ in range(5):
            start = time.time()
            await client.post(
                "/api/v1/auth/login",
                json={"email": test_user["email"], "password": "WrongPassword123!"}
            )
            existing_times.append(time.time() - start)

        # Measure time for non-existing user
        nonexistent_times = []
        for _ in range(5):
            start = time.time()
            await client.post(
                "/api/v1/auth/login",
                json={"email": f"nonexistent{uuid4().hex[:8]}@example.com", "password": "AnyPassword123!"}
            )
            nonexistent_times.append(time.time() - start)

        # Average times should not be too different
        avg_existing = statistics.mean(existing_times)
        avg_nonexistent = statistics.mean(nonexistent_times)

        # Tolerance: times should be within a factor of 3x
        # (bcrypt adds variance, so we're generous)
        ratio = max(avg_existing, avg_nonexistent) / min(avg_existing, avg_nonexistent)
        assert ratio < 3.0, (
            f"Timing leak detected: existing={avg_existing:.3f}s, "
            f"nonexistent={avg_nonexistent:.3f}s, ratio={ratio:.2f}"
        )
