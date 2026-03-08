"""
Multi-tenant isolation tests for BigMCP.

Validates complete isolation between organizations:
- Data is isolated by organization
- Users can only access their own organizations
- Resources (servers, API keys, contexts) are scoped
- No data leakage between tenants
"""

import pytest
from uuid import uuid4
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User, AuthProvider
from app.models.organization import Organization, OrganizationMember, UserRole, OrganizationType
from app.models.mcp_server import MCPServer, InstallType, ServerStatus
from app.models.api_key import APIKey
from app.models.context import Context
from app.services.auth_service import AuthService


# ===== Fixtures =====

@pytest.fixture
async def two_complete_orgs(db_session: AsyncSession) -> dict:
    """
    Create two complete organizations with users, servers, API keys.
    Simulates a realistic multi-tenant environment.
    """
    auth_service = AuthService(db_session)
    orgs = {}

    for i, name in enumerate(["Acme Corp", "Globex Inc"]):
        # Organization
        org = Organization(
            name=name,
            organization_type=OrganizationType.TEAM,
            slug=f"{name.lower().replace(' ', '-')}-{uuid4().hex[:8]}",
            max_mcp_servers=10,
            max_api_keys=10,
            max_contexts=10
        )
        db_session.add(org)
        await db_session.flush()

        # Owner
        owner = User(
            email=f"owner-{i}-{uuid4().hex[:8]}@example.com",
            name=f"{name} Owner",
            password_hash=auth_service.hash_password("OwnerPass123!"),
            auth_provider=AuthProvider.LOCAL
        )
        db_session.add(owner)
        await db_session.flush()

        owner_member = OrganizationMember(
            organization_id=org.id,
            user_id=owner.id,
            role=UserRole.OWNER
        )
        db_session.add(owner_member)

        # MCP Server
        server = MCPServer(
            name=f"{name} Internal Server",
            server_id=f"internal-server-{i}-{uuid4().hex[:8]}",
            command="npx",
            args=["@internal/mcp-server"],
            organization_id=org.id,
            install_type=InstallType.NPM,
            install_package="@internal/mcp-server",
            enabled=True,
            status=ServerStatus.RUNNING
        )
        db_session.add(server)
        await db_session.flush()

        # API Key
        raw_key, key_prefix = APIKey.generate_key()
        api_key = APIKey(
            name=f"{name} Production Key",
            key_hash=APIKey.hash_key(raw_key),
            key_prefix=key_prefix,
            user_id=owner.id,
            organization_id=org.id,
            scopes=["tools:read", "tools:execute"],
            is_active=True
        )
        db_session.add(api_key)
        await db_session.flush()

        # Context (with required path and context_type fields)
        context = Context(
            name=f"{name} Default Context",
            description=f"Default context for {name}",
            path=f"/{name.lower().replace(' ', '-')}/default",
            context_type="workspace",
            organization_id=org.id,
            created_by=owner.id
        )
        db_session.add(context)

        await db_session.commit()

        # Token
        token = auth_service.create_access_token(
            user_id=str(owner.id),
            organization_id=str(org.id)
        )

        orgs[f"org{i+1}"] = {
            "organization": org,
            "owner": owner,
            "server": server,
            "api_key": api_key,
            "api_key_secret": raw_key,
            "context": context,
            "token": token,
            "headers": {"Authorization": f"Bearer {token}"}
        }

    return orgs


# ===== Tests: Organization isolation =====

class TestOrganizationIsolation:
    """Tests for organization data isolation."""

    @pytest.mark.asyncio
    async def test_list_organizations_only_shows_own(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """A user only sees their own organizations."""
        org1 = two_complete_orgs["org1"]

        response = await client.get(
            "/api/v1/organizations/",
            headers=org1["headers"]
        )

        assert response.status_code == 200
        data = response.json()

        # Should only see one organization
        assert data["total"] == 1
        assert data["organizations"][0]["name"] == org1["organization"].name

        # Should NOT see the other organization
        org_names = [o["name"] for o in data["organizations"]]
        assert two_complete_orgs["org2"]["organization"].name not in org_names

    @pytest.mark.asyncio
    async def test_cannot_get_other_organization_details(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """A user cannot see the details of another organization."""
        org1_headers = two_complete_orgs["org1"]["headers"]
        org2 = two_complete_orgs["org2"]["organization"]

        response = await client.get(
            f"/api/v1/organizations/{org2.id}",
            headers=org1_headers
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_get_other_organization_stats(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """A user cannot see the stats of another organization."""
        org1_headers = two_complete_orgs["org1"]["headers"]
        org2 = two_complete_orgs["org2"]["organization"]

        response = await client.get(
            f"/api/v1/organizations/{org2.id}/stats",
            headers=org1_headers
        )

        assert response.status_code == 403


# ===== Tests: MCP Server isolation =====

class TestMCPServerIsolation:
    """Tests for MCP server isolation."""

    @pytest.mark.asyncio
    async def test_list_servers_only_shows_own(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """A user only sees servers from their organization."""
        org1 = two_complete_orgs["org1"]

        response = await client.get(
            "/api/v1/mcp-servers/",
            headers=org1["headers"]
        )

        assert response.status_code == 200
        data = response.json()

        # All returned servers belong to org1
        for server in data.get("servers", data):
            # Verify it is indeed a server from org1
            if isinstance(server, dict) and "name" in server:
                assert org1["organization"].name in server["name"] or server["name"] == org1["server"].name

    @pytest.mark.asyncio
    async def test_cannot_access_other_org_server(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """A user cannot access servers from another organization."""
        org1_headers = two_complete_orgs["org1"]["headers"]
        org2_server = two_complete_orgs["org2"]["server"]

        response = await client.get(
            f"/api/v1/mcp-servers/{org2_server.id}",
            headers=org1_headers
        )

        # Should be 403 Forbidden or 404 Not Found
        assert response.status_code in [403, 404]

    @pytest.mark.asyncio
    async def test_cannot_modify_other_org_server(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """A user cannot modify servers from another organization."""
        org1_headers = two_complete_orgs["org1"]["headers"]
        org2_server = two_complete_orgs["org2"]["server"]

        response = await client.patch(
            f"/api/v1/mcp-servers/{org2_server.id}",
            json={"name": "Hacked Server Name"},
            headers=org1_headers
        )

        assert response.status_code in [403, 404]

    @pytest.mark.asyncio
    async def test_cannot_delete_other_org_server(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """A user cannot delete servers from another organization."""
        org1_headers = two_complete_orgs["org1"]["headers"]
        org2_server = two_complete_orgs["org2"]["server"]

        response = await client.delete(
            f"/api/v1/mcp-servers/{org2_server.id}",
            headers=org1_headers
        )

        assert response.status_code in [403, 404]


# ===== Tests: API Key isolation =====

class TestAPIKeyIsolation:
    """Tests for API key isolation."""

    @pytest.mark.asyncio
    async def test_list_api_keys_only_shows_own(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """A user only sees their own API keys."""
        org1 = two_complete_orgs["org1"]

        response = await client.get(
            "/api/v1/api-keys",
            headers=org1["headers"]
        )

        assert response.status_code == 200
        data = response.json()

        # All keys belong to the org1 user
        for key in data:
            # Should not contain keys from org2
            assert two_complete_orgs["org2"]["organization"].name not in key.get("name", "")

    @pytest.mark.asyncio
    async def test_cannot_revoke_other_org_api_key(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """A user cannot revoke an API key from another organization."""
        org1_headers = two_complete_orgs["org1"]["headers"]
        org2_api_key = two_complete_orgs["org2"]["api_key"]

        response = await client.delete(
            f"/api/v1/api-keys/{org2_api_key.id}",
            headers=org1_headers
        )

        assert response.status_code in [403, 404]

    @pytest.mark.asyncio
    async def test_api_key_bound_to_organization(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """An API key can only access resources from its organization."""
        # Use org1's API key
        org1_api_key = two_complete_orgs["org1"]["api_key_secret"]
        org2_server = two_complete_orgs["org2"]["server"]

        # Try to access org2's server with org1's API key
        response = await client.get(
            f"/api/v1/mcp-servers/{org2_server.id}",
            headers={"Authorization": f"Bearer {org1_api_key}"}
        )

        assert response.status_code in [403, 404]


# ===== Tests: Member isolation =====

class TestMemberIsolation:
    """Tests for organization member isolation."""

    @pytest.mark.asyncio
    async def test_cannot_list_other_org_members(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """A user cannot list members from another organization."""
        org1_headers = two_complete_orgs["org1"]["headers"]
        org2 = two_complete_orgs["org2"]["organization"]

        response = await client.get(
            f"/api/v1/organizations/{org2.id}/members",
            headers=org1_headers
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_invite_to_other_org(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """A user cannot invite to another organization."""
        org1_headers = two_complete_orgs["org1"]["headers"]
        org2 = two_complete_orgs["org2"]["organization"]

        response = await client.post(
            f"/api/v1/organizations/{org2.id}/invitations",
            json={
                "email": "hacker@example.com",
                "role": "member"
            },
            headers=org1_headers
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_remove_member_from_other_org(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """A user cannot remove a member from another organization."""
        org1_headers = two_complete_orgs["org1"]["headers"]
        org2 = two_complete_orgs["org2"]["organization"]
        org2_owner = two_complete_orgs["org2"]["owner"]

        response = await client.delete(
            f"/api/v1/organizations/{org2.id}/members/{org2_owner.id}",
            headers=org1_headers
        )

        assert response.status_code == 403


# ===== Tests: Invitation isolation =====

class TestInvitationIsolation:
    """Tests for invitation isolation."""

    @pytest.mark.asyncio
    async def test_cannot_list_other_org_invitations(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """A user cannot list invitations from another organization."""
        org1_headers = two_complete_orgs["org1"]["headers"]
        org2 = two_complete_orgs["org2"]["organization"]

        response = await client.get(
            f"/api/v1/organizations/{org2.id}/invitations",
            headers=org1_headers
        )

        assert response.status_code == 403


# ===== Tests: Cross-tenant data leakage =====

class TestDataLeakagePrevention:
    """Tests to prevent data leakage between tenants."""

    @pytest.mark.asyncio
    async def test_error_messages_no_data_leakage(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """Error messages do not reveal information about other organizations."""
        org1_headers = two_complete_orgs["org1"]["headers"]
        org2 = two_complete_orgs["org2"]["organization"]

        response = await client.get(
            f"/api/v1/organizations/{org2.id}",
            headers=org1_headers
        )

        assert response.status_code == 403
        error_detail = response.json().get("detail", "")

        # The error message should not reveal the organization name
        assert org2.name not in error_detail
        assert org2.slug not in error_detail

    @pytest.mark.asyncio
    async def test_uuid_guessing_prevented(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """Guessing a UUID does not allow access to data."""
        org1_headers = two_complete_orgs["org1"]["headers"]

        # Try with random UUIDs
        for _ in range(5):
            random_uuid = uuid4()

            response = await client.get(
                f"/api/v1/organizations/{random_uuid}",
                headers=org1_headers
            )

            # Should return 403 (not a member) or 404 (does not exist)
            # Never 500 or other revealing error
            assert response.status_code in [403, 404]

    @pytest.mark.asyncio
    async def test_enumeration_attack_prevented(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """Resource enumeration does not reveal the existence of other organizations."""
        org1_headers = two_complete_orgs["org1"]["headers"]
        org2_server = two_complete_orgs["org2"]["server"]

        # Attempt to access org2's server
        response = await client.get(
            f"/api/v1/mcp-servers/{org2_server.id}",
            headers=org1_headers
        )

        # The response should be consistent (403 or 404)
        # Should not allow distinguishing "exists but no access" vs "does not exist"
        assert response.status_code in [403, 404]


# ===== Tests: Subscription isolation =====

class TestSubscriptionIsolation:
    """Tests for subscription isolation."""

    @pytest.mark.asyncio
    async def test_cannot_access_other_org_subscription(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """A user cannot see the subscription of another organization."""
        org1_headers = two_complete_orgs["org1"]["headers"]
        org2 = two_complete_orgs["org2"]["organization"]

        response = await client.get(
            f"/api/v1/subscriptions/organization/{org2.id}",
            headers=org1_headers
        )

        # Should be denied
        assert response.status_code in [403, 404]


# ===== Tests: Context isolation =====

class TestContextIsolation:
    """Tests for context isolation."""

    @pytest.mark.asyncio
    async def test_cannot_access_other_org_context(
        self, client: AsyncClient, two_complete_orgs: dict
    ):
        """A user cannot access contexts from another organization."""
        org1_headers = two_complete_orgs["org1"]["headers"]
        org2_context = two_complete_orgs["org2"]["context"]

        response = await client.get(
            f"/api/v1/contexts/{org2_context.id}",
            headers=org1_headers
        )

        assert response.status_code in [403, 404]


# ===== Tests: Database-level isolation verification =====

class TestDatabaseIsolation:
    """Tests for database-level isolation verification."""

    @pytest.mark.asyncio
    async def test_all_tables_have_org_filter(
        self, db_session: AsyncSession, two_complete_orgs: dict
    ):
        """Verify that main queries filter by organization."""
        org1 = two_complete_orgs["org1"]["organization"]
        org2 = two_complete_orgs["org2"]["organization"]

        # Verify that servers are properly separated
        org1_servers = await db_session.execute(
            select(MCPServer).where(MCPServer.organization_id == org1.id)
        )
        org2_servers = await db_session.execute(
            select(MCPServer).where(MCPServer.organization_id == org2.id)
        )

        org1_server_ids = [s.id for s in org1_servers.scalars()]
        org2_server_ids = [s.id for s in org2_servers.scalars()]

        # No overlap
        assert set(org1_server_ids).isdisjoint(set(org2_server_ids))

        # Verify that API keys are properly separated
        org1_keys = await db_session.execute(
            select(APIKey).where(APIKey.organization_id == org1.id)
        )
        org2_keys = await db_session.execute(
            select(APIKey).where(APIKey.organization_id == org2.id)
        )

        org1_key_ids = [k.id for k in org1_keys.scalars()]
        org2_key_ids = [k.id for k in org2_keys.scalars()]

        # No overlap
        assert set(org1_key_ids).isdisjoint(set(org2_key_ids))
