"""
Credentials tests for BigMCP.

Validates the credential management system:
- Fernet encryption at rest
- Resolution hierarchy: User > Organization
- Isolation by organization
- Complete CRUD
- Audit trail
"""

import pytest
from uuid import uuid4
from datetime import datetime
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.models.user import User, AuthProvider
from app.models.organization import Organization, OrganizationMember, UserRole, OrganizationType
from app.models.mcp_server import MCPServer, InstallType, ServerStatus
from app.models.user_credential import UserCredential, OrganizationCredential
from app.services.auth_service import AuthService
from app.services.credential_service import CredentialService
from app.core.secrets_manager import SecretsManager


# ===== Fixtures =====

@pytest.fixture
async def test_org_with_server(db_session: AsyncSession) -> dict:
    """
    Create an organization with an MCP server and two users.
    """
    auth_service = AuthService(db_session)

    # Create the organization
    org = Organization(
        name="Credential Test Org",
        organization_type=OrganizationType.TEAM,
        slug=f"cred-test-{uuid4().hex[:8]}"
    )
    db_session.add(org)
    await db_session.flush()

    # Create an MCP server
    server = MCPServer(
        name="Test API Server",
        server_id=f"test-api-server-{uuid4().hex[:8]}",
        command="npx",
        args=["test-mcp-server"],
        organization_id=org.id,
        install_type=InstallType.NPM,
        install_package="@test/mcp-server",
        enabled=True,
        status=ServerStatus.RUNNING
    )
    db_session.add(server)
    await db_session.flush()

    # Create an admin
    admin = User(
        email=f"admin-{uuid4().hex[:8]}@example.com",
        name="Test Admin",
        password_hash=auth_service.hash_password("AdminPass123!"),
        auth_provider=AuthProvider.LOCAL
    )
    db_session.add(admin)
    await db_session.flush()

    admin_member = OrganizationMember(
        organization_id=org.id,
        user_id=admin.id,
        role=UserRole.ADMIN
    )
    db_session.add(admin_member)

    # Create a regular member
    member = User(
        email=f"member-{uuid4().hex[:8]}@example.com",
        name="Test Member",
        password_hash=auth_service.hash_password("MemberPass123!"),
        auth_provider=AuthProvider.LOCAL
    )
    db_session.add(member)
    await db_session.flush()

    member_member = OrganizationMember(
        organization_id=org.id,
        user_id=member.id,
        role=UserRole.MEMBER
    )
    db_session.add(member_member)

    await db_session.commit()

    # Generate the tokens
    admin_token = auth_service.create_access_token(
        user_id=str(admin.id),
        organization_id=str(org.id)
    )
    member_token = auth_service.create_access_token(
        user_id=str(member.id),
        organization_id=str(org.id)
    )

    return {
        "organization": org,
        "server": server,
        "admin": {
            "user": admin,
            "token": admin_token,
            "headers": {"Authorization": f"Bearer {admin_token}"}
        },
        "member": {
            "user": member,
            "token": member_token,
            "headers": {"Authorization": f"Bearer {member_token}"}
        }
    }


# ===== Tests: Encryption at rest =====

class TestCredentialEncryption:
    """Tests that credentials are encrypted in the database."""

    @pytest.mark.asyncio
    async def test_user_credential_encrypted_in_db(
        self, db_session: AsyncSession, test_org_with_server: dict
    ):
        """User credentials are encrypted in the DB."""
        service = CredentialService(db_session)
        org = test_org_with_server["organization"]
        server = test_org_with_server["server"]
        user = test_org_with_server["member"]["user"]

        # Create credentials
        secret_data = {
            "API_KEY": "sk-super-secret-key-12345",
            "API_SECRET": "very-secret-value-67890"
        }

        credential = await service.create_user_credential(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id,
            credentials=secret_data,
            name="My Personal API Key"
        )

        # Verify it is stored encrypted
        assert credential.credentials_encrypted is not None

        # The encrypted value should not contain the secrets in plain text
        assert "sk-super-secret-key-12345" not in credential.credentials_encrypted
        assert "very-secret-value-67890" not in credential.credentials_encrypted

        # But decryption should work
        decrypted = credential.credentials
        assert decrypted["API_KEY"] == "sk-super-secret-key-12345"
        assert decrypted["API_SECRET"] == "very-secret-value-67890"

    @pytest.mark.asyncio
    async def test_org_credential_encrypted_in_db(
        self, db_session: AsyncSession, test_org_with_server: dict
    ):
        """Organization credentials are encrypted in the DB."""
        service = CredentialService(db_session)
        org = test_org_with_server["organization"]
        server = test_org_with_server["server"]
        admin = test_org_with_server["admin"]["user"]

        secret_data = {
            "SHARED_API_KEY": "org-shared-key-abcdef",
            "SHARED_SECRET": "org-shared-secret-123456"
        }

        credential = await service.create_org_credential(
            organization_id=org.id,
            server_id=server.id,
            credentials=secret_data,
            name="Organization Shared Key",
            created_by=admin.id
        )

        # Verify encryption
        assert "org-shared-key-abcdef" not in credential.credentials_encrypted
        assert "org-shared-secret-123456" not in credential.credentials_encrypted

        # Decryption
        decrypted = credential.credentials
        assert decrypted["SHARED_API_KEY"] == "org-shared-key-abcdef"

    @pytest.mark.asyncio
    async def test_raw_query_cannot_read_secrets(
        self, db_session: AsyncSession, test_org_with_server: dict
    ):
        """A direct SQL query cannot read secrets."""
        service = CredentialService(db_session)
        org = test_org_with_server["organization"]
        server = test_org_with_server["server"]
        user = test_org_with_server["member"]["user"]

        secret = "this-should-never-appear-in-raw-query"

        await service.create_user_credential(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id,
            credentials={"SECRET": secret},
            name="Raw Query Test"
        )

        # Direct SQL query
        result = await db_session.execute(
            text("SELECT credentials_encrypted FROM user_credentials WHERE user_id = :user_id"),
            {"user_id": str(user.id)}
        )
        row = result.fetchone()

        assert row is not None
        encrypted_value = row[0]

        # The secret should not be visible
        assert secret not in encrypted_value


# ===== Tests: Resolution hierarchy =====

class TestCredentialHierarchy:
    """Tests for resolution hierarchy: User > Organization."""

    @pytest.mark.asyncio
    async def test_user_credentials_take_priority(
        self, db_session: AsyncSession, test_org_with_server: dict
    ):
        """User credentials take priority over organization credentials."""
        service = CredentialService(db_session)
        org = test_org_with_server["organization"]
        server = test_org_with_server["server"]
        user = test_org_with_server["member"]["user"]
        admin = test_org_with_server["admin"]["user"]

        # Create organization credentials
        await service.create_org_credential(
            organization_id=org.id,
            server_id=server.id,
            credentials={"API_KEY": "org-level-key"},
            name="Org Key",
            created_by=admin.id
        )

        # Create user credentials
        await service.create_user_credential(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id,
            credentials={"API_KEY": "user-level-key"},
            name="User Key"
        )

        # Resolve - should return user credentials
        resolved = await service.resolve_credentials(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id
        )

        assert resolved is not None
        assert resolved["API_KEY"] == "user-level-key"

    @pytest.mark.asyncio
    async def test_org_credentials_as_fallback(
        self, db_session: AsyncSession, test_org_with_server: dict
    ):
        """Organization credentials are used if no user credentials exist."""
        service = CredentialService(db_session)
        org = test_org_with_server["organization"]
        server = test_org_with_server["server"]
        user = test_org_with_server["member"]["user"]
        admin = test_org_with_server["admin"]["user"]

        # Create only organization credentials
        await service.create_org_credential(
            organization_id=org.id,
            server_id=server.id,
            credentials={"API_KEY": "org-fallback-key"},
            name="Org Fallback",
            created_by=admin.id
        )

        # No user credentials created

        # Resolve - should return organization credentials
        resolved = await service.resolve_credentials(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id
        )

        assert resolved is not None
        assert resolved["API_KEY"] == "org-fallback-key"

    @pytest.mark.asyncio
    async def test_no_credentials_returns_none(
        self, db_session: AsyncSession, test_org_with_server: dict
    ):
        """Returns None if no credentials exist."""
        service = CredentialService(db_session)
        org = test_org_with_server["organization"]
        server = test_org_with_server["server"]
        user = test_org_with_server["member"]["user"]

        # No credentials at all

        resolved = await service.resolve_credentials(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id
        )

        assert resolved is None

    @pytest.mark.asyncio
    async def test_resolve_with_mode_user_priority(
        self, db_session: AsyncSession, test_org_with_server: dict
    ):
        """resolve_credentials_with_mode returns the correct source."""
        service = CredentialService(db_session)
        org = test_org_with_server["organization"]
        server = test_org_with_server["server"]
        user = test_org_with_server["member"]["user"]
        admin = test_org_with_server["admin"]["user"]

        # Create both types
        await service.create_org_credential(
            organization_id=org.id,
            server_id=server.id,
            credentials={"API_KEY": "org-key"},
            name="Org",
            created_by=admin.id
        )

        await service.create_user_credential(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id,
            credentials={"API_KEY": "user-key"},
            name="User"
        )

        # Normal mode - user priority
        creds, source, owner_id = await service.resolve_credentials_with_mode(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id,
            force_org_only=False
        )

        assert creds["API_KEY"] == "user-key"
        assert source == "user"
        assert owner_id == user.id

    @pytest.mark.asyncio
    async def test_resolve_with_mode_force_org_only(
        self, db_session: AsyncSession, test_org_with_server: dict
    ):
        """force_org_only ignores user credentials."""
        service = CredentialService(db_session)
        org = test_org_with_server["organization"]
        server = test_org_with_server["server"]
        user = test_org_with_server["member"]["user"]
        admin = test_org_with_server["admin"]["user"]

        # Create both types
        await service.create_org_credential(
            organization_id=org.id,
            server_id=server.id,
            credentials={"API_KEY": "org-only-key"},
            name="Org",
            created_by=admin.id
        )

        await service.create_user_credential(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id,
            credentials={"API_KEY": "user-ignored-key"},
            name="User"
        )

        # force_org_only mode - ignores user credentials
        creds, source, owner_id = await service.resolve_credentials_with_mode(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id,
            force_org_only=True
        )

        assert creds["API_KEY"] == "org-only-key"
        assert source == "organization"
        assert owner_id == admin.id  # Creator of org credentials


# ===== Tests: User Credential CRUD =====

class TestUserCredentialCRUD:
    """CRUD tests for user credentials."""

    @pytest.mark.asyncio
    async def test_create_user_credential(
        self, db_session: AsyncSession, test_org_with_server: dict
    ):
        """Create user credentials."""
        service = CredentialService(db_session)
        org = test_org_with_server["organization"]
        server = test_org_with_server["server"]
        user = test_org_with_server["member"]["user"]

        credential = await service.create_user_credential(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id,
            credentials={"API_KEY": "my-key"},
            name="My API Key",
            description="Personal API key for testing"
        )

        assert credential.id is not None
        assert credential.name == "My API Key"
        assert credential.is_active is True
        assert credential.credentials["API_KEY"] == "my-key"

    @pytest.mark.asyncio
    async def test_update_user_credential(
        self, db_session: AsyncSession, test_org_with_server: dict
    ):
        """Update user credentials."""
        service = CredentialService(db_session)
        org = test_org_with_server["organization"]
        server = test_org_with_server["server"]
        user = test_org_with_server["member"]["user"]

        # Create
        await service.create_user_credential(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id,
            credentials={"API_KEY": "old-key"},
            name="Original Name"
        )

        # Update
        updated = await service.update_user_credential(
            user_id=user.id,
            server_id=server.id,
            credentials={"API_KEY": "new-key"},
            name="Updated Name"
        )

        assert updated.name == "Updated Name"
        assert updated.credentials["API_KEY"] == "new-key"

    @pytest.mark.asyncio
    async def test_delete_user_credential(
        self, db_session: AsyncSession, test_org_with_server: dict
    ):
        """Delete user credentials."""
        service = CredentialService(db_session)
        org = test_org_with_server["organization"]
        server = test_org_with_server["server"]
        user = test_org_with_server["member"]["user"]

        # Create
        await service.create_user_credential(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id,
            credentials={"API_KEY": "to-delete"},
            name="To Delete"
        )

        # Delete
        await service.delete_user_credential(
            user_id=user.id,
            server_id=server.id
        )

        # Verify deletion
        credentials = await service.get_user_credentials(user.id, org.id)
        assert len(credentials) == 0

    @pytest.mark.asyncio
    async def test_list_user_credentials(
        self, db_session: AsyncSession, test_org_with_server: dict
    ):
        """List a user's credentials."""
        service = CredentialService(db_session)
        org = test_org_with_server["organization"]
        server = test_org_with_server["server"]
        user = test_org_with_server["member"]["user"]

        # Create a credential
        await service.create_user_credential(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id,
            credentials={"API_KEY": "listed-key"},
            name="Listed Key"
        )

        # List
        credentials = await service.get_user_credentials(user.id, org.id)

        assert len(credentials) == 1
        assert credentials[0].name == "Listed Key"

    @pytest.mark.asyncio
    async def test_duplicate_credential_rejected(
        self, db_session: AsyncSession, test_org_with_server: dict
    ):
        """Cannot create two credentials for the same server."""
        service = CredentialService(db_session)
        org = test_org_with_server["organization"]
        server = test_org_with_server["server"]
        user = test_org_with_server["member"]["user"]

        # First credential
        await service.create_user_credential(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id,
            credentials={"API_KEY": "first"},
            name="First"
        )

        # Second credential for the same server - should fail
        with pytest.raises(ValueError) as exc_info:
            await service.create_user_credential(
                user_id=user.id,
                server_id=server.id,
                organization_id=org.id,
                credentials={"API_KEY": "second"},
                name="Second"
            )

        assert "already exist" in str(exc_info.value)


# ===== Tests: Organization Credential CRUD =====

class TestOrgCredentialCRUD:
    """CRUD tests for organization credentials."""

    @pytest.mark.asyncio
    async def test_create_org_credential(
        self, db_session: AsyncSession, test_org_with_server: dict
    ):
        """Create organization credentials."""
        service = CredentialService(db_session)
        org = test_org_with_server["organization"]
        server = test_org_with_server["server"]
        admin = test_org_with_server["admin"]["user"]

        credential = await service.create_org_credential(
            organization_id=org.id,
            server_id=server.id,
            credentials={"SHARED_KEY": "org-shared"},
            name="Shared Organization Key",
            description="Shared across all members",
            visible_to_users=True,
            created_by=admin.id
        )

        assert credential.id is not None
        assert credential.name == "Shared Organization Key"
        assert credential.visible_to_users is True
        assert credential.created_by == admin.id

    @pytest.mark.asyncio
    async def test_org_credential_usage_tracking(
        self, db_session: AsyncSession, test_org_with_server: dict
    ):
        """Organization credentials track their usage."""
        service = CredentialService(db_session)
        org = test_org_with_server["organization"]
        server = test_org_with_server["server"]
        admin = test_org_with_server["admin"]["user"]
        member = test_org_with_server["member"]["user"]

        # Create org credentials
        await service.create_org_credential(
            organization_id=org.id,
            server_id=server.id,
            credentials={"KEY": "tracked"},
            name="Tracked Key",
            created_by=admin.id
        )

        # Use credentials (via resolve)
        await service.resolve_credentials(member.id, server.id, org.id)
        await service.resolve_credentials(member.id, server.id, org.id)
        await service.resolve_credentials(member.id, server.id, org.id)

        # Verify the counter
        credentials = await service.get_org_credentials(org.id)
        assert credentials[0].usage_count == 3
        assert credentials[0].last_used_at is not None


# ===== Tests: Multi-Tenant Isolation =====

class TestCredentialIsolation:
    """Tests for credential isolation between organizations."""

    @pytest.fixture
    async def two_orgs_with_servers(self, db_session: AsyncSession) -> dict:
        """Create two distinct organizations with their servers."""
        auth_service = AuthService(db_session)

        orgs = {}
        for i in range(2):
            org = Organization(
                name=f"Org {i+1}",
                organization_type=OrganizationType.TEAM,
                slug=f"isolation-org-{i}-{uuid4().hex[:8]}"
            )
            db_session.add(org)
            await db_session.flush()

            server = MCPServer(
                name=f"Server {i+1}",
                server_id=f"server-{i}-{uuid4().hex[:8]}",
                command="npx",
                args=[f"server-{i}"],
                organization_id=org.id,
                install_type=InstallType.NPM,
                install_package=f"@test/server-{i}",
                enabled=True,
                status=ServerStatus.RUNNING
            )
            db_session.add(server)
            await db_session.flush()

            user = User(
                email=f"user-org{i}-{uuid4().hex[:8]}@example.com",
                name=f"User Org {i+1}",
                password_hash=auth_service.hash_password("Pass123!"),
                auth_provider=AuthProvider.LOCAL
            )
            db_session.add(user)
            await db_session.flush()

            member = OrganizationMember(
                organization_id=org.id,
                user_id=user.id,
                role=UserRole.ADMIN
            )
            db_session.add(member)

            orgs[f"org{i+1}"] = {
                "organization": org,
                "server": server,
                "user": user
            }

        await db_session.commit()
        return orgs

    @pytest.mark.asyncio
    async def test_cannot_access_other_org_credentials(
        self, db_session: AsyncSession, two_orgs_with_servers: dict
    ):
        """A user cannot access credentials from another org."""
        service = CredentialService(db_session)

        org1 = two_orgs_with_servers["org1"]
        org2 = two_orgs_with_servers["org2"]

        # Create credentials in org1
        await service.create_org_credential(
            organization_id=org1["organization"].id,
            server_id=org1["server"].id,
            credentials={"SECRET": "org1-secret"},
            name="Org1 Secret",
            created_by=org1["user"].id
        )

        # User from org2 should not be able to resolve org1's credentials
        resolved = await service.resolve_credentials(
            user_id=org2["user"].id,
            server_id=org1["server"].id,
            organization_id=org2["organization"].id
        )

        # Should return None (not org1's credentials)
        assert resolved is None

    @pytest.mark.asyncio
    async def test_credentials_scoped_to_organization(
        self, db_session: AsyncSession, two_orgs_with_servers: dict
    ):
        """Credential lists are scoped by organization."""
        service = CredentialService(db_session)

        org1 = two_orgs_with_servers["org1"]
        org2 = two_orgs_with_servers["org2"]

        # Create credentials in both orgs
        await service.create_org_credential(
            organization_id=org1["organization"].id,
            server_id=org1["server"].id,
            credentials={"KEY": "org1"},
            name="Org1 Key",
            created_by=org1["user"].id
        )

        await service.create_org_credential(
            organization_id=org2["organization"].id,
            server_id=org2["server"].id,
            credentials={"KEY": "org2"},
            name="Org2 Key",
            created_by=org2["user"].id
        )

        # Each org only sees its own credentials
        org1_creds = await service.get_org_credentials(org1["organization"].id)
        org2_creds = await service.get_org_credentials(org2["organization"].id)

        assert len(org1_creds) == 1
        assert org1_creds[0].name == "Org1 Key"

        assert len(org2_creds) == 1
        assert org2_creds[0].name == "Org2 Key"


# ===== Tests: Credential masking =====

class TestCredentialMasking:
    """Tests for credential masking for display."""

    @pytest.mark.asyncio
    async def test_get_masked_credentials(
        self, db_session: AsyncSession, test_org_with_server: dict
    ):
        """Credentials can be masked for secure display."""
        service = CredentialService(db_session)
        org = test_org_with_server["organization"]
        server = test_org_with_server["server"]
        user = test_org_with_server["member"]["user"]

        # Create credentials
        await service.create_user_credential(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id,
            credentials={
                "API_KEY": "sk-1234567890abcdef",
                "SHORT": "abc"
            },
            name="Masked Test"
        )

        # Get masked credentials
        masked = await service.get_masked_credentials(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id
        )

        assert masked is not None
        # Long values are partially masked
        assert masked["API_KEY"] == "sk-***def"
        # Short values are fully masked
        assert masked["SHORT"] == "***"


# ===== Tests: Credential validation =====

class TestCredentialValidation:
    """Tests for credential validation."""

    @pytest.mark.asyncio
    async def test_validate_credentials(
        self, db_session: AsyncSession, test_org_with_server: dict
    ):
        """Credentials can be marked as validated."""
        service = CredentialService(db_session)
        org = test_org_with_server["organization"]
        server = test_org_with_server["server"]
        user = test_org_with_server["member"]["user"]

        # Create credentials
        credential = await service.create_user_credential(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id,
            credentials={"API_KEY": "to-validate"},
            name="To Validate"
        )

        assert credential.is_validated is False
        assert credential.validated_at is None

        # Validate
        await service.validate_credentials(
            credential_id=credential.id,
            is_user_credential=True
        )

        # Refresh and verify
        await db_session.refresh(credential)
        assert credential.is_validated is True
        assert credential.validated_at is not None

    @pytest.mark.asyncio
    async def test_inactive_credentials_not_resolved(
        self, db_session: AsyncSession, test_org_with_server: dict
    ):
        """Inactive credentials are not resolved."""
        service = CredentialService(db_session)
        org = test_org_with_server["organization"]
        server = test_org_with_server["server"]
        user = test_org_with_server["member"]["user"]

        # Create and deactivate
        await service.create_user_credential(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id,
            credentials={"API_KEY": "inactive-key"},
            name="Inactive"
        )

        await service.update_user_credential(
            user_id=user.id,
            server_id=server.id,
            is_active=False
        )

        # Resolve - should return None
        resolved = await service.resolve_credentials(
            user_id=user.id,
            server_id=server.id,
            organization_id=org.id
        )

        assert resolved is None
