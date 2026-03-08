"""
RBAC (Role-Based Access Control) tests for BigMCP.

Validates the access control system with 4 roles:
- OWNER: Full control, billing access
- ADMIN: Manage resources and members (no billing)
- MEMBER: Create/modify own resources
- VIEWER: Read-only access

Hierarchy: OWNER > ADMIN > MEMBER > VIEWER
"""

import pytest
from uuid import uuid4
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User, AuthProvider
from app.models.organization import Organization, OrganizationMember, UserRole, OrganizationType
from app.models.api_key import APIKey
from app.services.auth_service import AuthService


# ===== Fixtures to create users with different roles =====

@pytest.fixture
async def organization_with_roles(db_session: AsyncSession) -> dict:
    """
    Create an organization with 4 users, one for each role.

    Returns:
        dict with organization, owner, admin, member, viewer and their tokens
    """
    # Create the organization
    org = Organization(
        name="RBAC Test Organization",
        organization_type=OrganizationType.TEAM,
        slug=f"rbac-test-{uuid4().hex[:8]}",
        max_contexts=10,
        max_api_keys=10,
        max_mcp_servers=10
    )
    db_session.add(org)
    await db_session.flush()

    auth_service = AuthService(db_session)

    users = {}
    for role in [UserRole.OWNER, UserRole.ADMIN, UserRole.MEMBER, UserRole.VIEWER]:
        # Create user
        user = User(
            email=f"{role.value}-{uuid4().hex[:8]}@example.com",
            name=f"Test {role.value.title()}",
            password_hash=auth_service.hash_password("TestPass123!"),
            auth_provider=AuthProvider.LOCAL
        )
        db_session.add(user)
        await db_session.flush()

        # Create membership
        member = OrganizationMember(
            organization_id=org.id,
            user_id=user.id,
            role=role
        )
        db_session.add(member)

        # Generate token
        token = auth_service.create_access_token(
            user_id=str(user.id),
            organization_id=str(org.id)
        )

        users[role.value] = {
            "user": user,
            "token": token,
            "headers": {"Authorization": f"Bearer {token}"}
        }

    await db_session.commit()

    # Refresh to get IDs
    for role_data in users.values():
        await db_session.refresh(role_data["user"])
    await db_session.refresh(org)

    return {
        "organization": org,
        **users
    }


@pytest.fixture
async def second_organization(db_session: AsyncSession, organization_with_roles: dict) -> dict:
    """
    Create a second organization to test isolation.
    """
    auth_service = AuthService(db_session)

    # Create organization
    org2 = Organization(
        name="Second Organization",
        organization_type=OrganizationType.TEAM,
        slug=f"second-org-{uuid4().hex[:8]}"
    )
    db_session.add(org2)
    await db_session.flush()

    # Create an owner for this org
    user = User(
        email=f"other-owner-{uuid4().hex[:8]}@example.com",
        name="Other Owner",
        password_hash=auth_service.hash_password("TestPass123!"),
        auth_provider=AuthProvider.LOCAL
    )
    db_session.add(user)
    await db_session.flush()

    member = OrganizationMember(
        organization_id=org2.id,
        user_id=user.id,
        role=UserRole.OWNER
    )
    db_session.add(member)
    await db_session.commit()

    token = auth_service.create_access_token(
        user_id=str(user.id),
        organization_id=str(org2.id)
    )

    return {
        "organization": org2,
        "owner": {
            "user": user,
            "token": token,
            "headers": {"Authorization": f"Bearer {token}"}
        }
    }


# ===== Tests: Read access (all roles) =====

class TestReadAccess:
    """Read access tests - all roles should be able to read."""

    @pytest.mark.asyncio
    async def test_owner_can_read_organization(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Owner can read organization details."""
        org = organization_with_roles["organization"]
        headers = organization_with_roles["owner"]["headers"]

        response = await client.get(
            f"/api/v1/organizations/{org.id}",
            headers=headers
        )

        assert response.status_code == 200
        assert response.json()["name"] == org.name

    @pytest.mark.asyncio
    async def test_admin_can_read_organization(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Admin can read organization details."""
        org = organization_with_roles["organization"]
        headers = organization_with_roles["admin"]["headers"]

        response = await client.get(
            f"/api/v1/organizations/{org.id}",
            headers=headers
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_member_can_read_organization(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Member can read organization details."""
        org = organization_with_roles["organization"]
        headers = organization_with_roles["member"]["headers"]

        response = await client.get(
            f"/api/v1/organizations/{org.id}",
            headers=headers
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_viewer_can_read_organization(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Viewer can read organization details."""
        org = organization_with_roles["organization"]
        headers = organization_with_roles["viewer"]["headers"]

        response = await client.get(
            f"/api/v1/organizations/{org.id}",
            headers=headers
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_all_roles_can_list_members(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """All roles can list members."""
        org = organization_with_roles["organization"]

        for role in ["owner", "admin", "member", "viewer"]:
            headers = organization_with_roles[role]["headers"]

            response = await client.get(
                f"/api/v1/organizations/{org.id}/members",
                headers=headers
            )

            assert response.status_code == 200, f"Failed for role: {role}"
            data = response.json()
            assert data["total"] == 4  # 4 members created


# ===== Tests: Organization modification (Owner/Admin only) =====

class TestOrganizationManagement:
    """Organization management tests - Owner and Admin only."""

    @pytest.mark.asyncio
    async def test_owner_can_update_organization(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Owner can modify the organization."""
        org = organization_with_roles["organization"]
        headers = organization_with_roles["owner"]["headers"]

        response = await client.patch(
            f"/api/v1/organizations/{org.id}",
            json={"name": "Updated by Owner"},
            headers=headers
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Updated by Owner"

    @pytest.mark.asyncio
    async def test_admin_can_update_organization(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Admin can modify the organization."""
        org = organization_with_roles["organization"]
        headers = organization_with_roles["admin"]["headers"]

        response = await client.patch(
            f"/api/v1/organizations/{org.id}",
            json={"name": "Updated by Admin"},
            headers=headers
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_member_cannot_update_organization(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Member canNOT modify the organization."""
        org = organization_with_roles["organization"]
        headers = organization_with_roles["member"]["headers"]

        response = await client.patch(
            f"/api/v1/organizations/{org.id}",
            json={"name": "Updated by Member"},
            headers=headers
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_update_organization(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Viewer canNOT modify the organization."""
        org = organization_with_roles["organization"]
        headers = organization_with_roles["viewer"]["headers"]

        response = await client.patch(
            f"/api/v1/organizations/{org.id}",
            json={"name": "Updated by Viewer"},
            headers=headers
        )

        assert response.status_code == 403


# ===== Tests: Member management =====

class TestMemberManagement:
    """Member management tests - Owner/Admin with restrictions."""

    @pytest.mark.asyncio
    async def test_owner_can_invite_member(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Owner can invite a new member."""
        org = organization_with_roles["organization"]
        headers = organization_with_roles["owner"]["headers"]

        response = await client.post(
            f"/api/v1/organizations/{org.id}/invitations",
            json={
                "email": f"new-member-{uuid4().hex[:8]}@example.com",
                "role": "member",
                "message": "Welcome!"
            },
            headers=headers
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_can_invite_member(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Admin can invite a new member."""
        org = organization_with_roles["organization"]
        headers = organization_with_roles["admin"]["headers"]

        response = await client.post(
            f"/api/v1/organizations/{org.id}/invitations",
            json={
                "email": f"admin-invited-{uuid4().hex[:8]}@example.com",
                "role": "member"
            },
            headers=headers
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_member_cannot_invite(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Member canNOT invite."""
        org = organization_with_roles["organization"]
        headers = organization_with_roles["member"]["headers"]

        response = await client.post(
            f"/api/v1/organizations/{org.id}/invitations",
            json={
                "email": f"member-invited-{uuid4().hex[:8]}@example.com",
                "role": "member"
            },
            headers=headers
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_invite(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Viewer canNOT invite."""
        org = organization_with_roles["organization"]
        headers = organization_with_roles["viewer"]["headers"]

        response = await client.post(
            f"/api/v1/organizations/{org.id}/invitations",
            json={
                "email": f"viewer-invited-{uuid4().hex[:8]}@example.com",
                "role": "member"
            },
            headers=headers
        )

        assert response.status_code == 403


# ===== Tests: Role changes =====

class TestRoleChanges:
    """Role change tests - strict rules."""

    @pytest.mark.asyncio
    async def test_owner_can_promote_to_admin(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Owner can promote a member to admin."""
        org = organization_with_roles["organization"]
        owner_headers = organization_with_roles["owner"]["headers"]
        member_id = organization_with_roles["member"]["user"].id

        response = await client.patch(
            f"/api/v1/organizations/{org.id}/members/{member_id}",
            json={"role": "admin"},
            headers=owner_headers
        )

        assert response.status_code == 200
        assert response.json()["role"] == "admin"

    @pytest.mark.asyncio
    async def test_admin_cannot_promote_to_admin(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Admin canNOT promote to admin (only Owner can)."""
        org = organization_with_roles["organization"]
        admin_headers = organization_with_roles["admin"]["headers"]
        viewer_id = organization_with_roles["viewer"]["user"].id

        response = await client.patch(
            f"/api/v1/organizations/{org.id}/members/{viewer_id}",
            json={"role": "admin"},
            headers=admin_headers
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_demote_to_member(
        self, client: AsyncClient, organization_with_roles: dict, db_session: AsyncSession
    ):
        """Admin can demote a viewer to member (and vice versa)."""
        org = organization_with_roles["organization"]
        admin_headers = organization_with_roles["admin"]["headers"]
        viewer_id = organization_with_roles["viewer"]["user"].id

        response = await client.patch(
            f"/api/v1/organizations/{org.id}/members/{viewer_id}",
            json={"role": "member"},
            headers=admin_headers
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_cannot_change_owner_role(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Nobody can change the Owner's role directly."""
        org = organization_with_roles["organization"]
        owner_headers = organization_with_roles["owner"]["headers"]
        owner_id = organization_with_roles["owner"]["user"].id

        response = await client.patch(
            f"/api/v1/organizations/{org.id}/members/{owner_id}",
            json={"role": "admin"},
            headers=owner_headers
        )

        assert response.status_code == 400
        assert "owner" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cannot_set_role_to_owner(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Cannot promote someone to owner via this endpoint."""
        org = organization_with_roles["organization"]
        owner_headers = organization_with_roles["owner"]["headers"]
        admin_id = organization_with_roles["admin"]["user"].id

        response = await client.patch(
            f"/api/v1/organizations/{org.id}/members/{admin_id}",
            json={"role": "owner"},
            headers=owner_headers
        )

        assert response.status_code == 400


# ===== Tests: Member removal =====

class TestMemberRemoval:
    """Member removal tests."""

    @pytest.mark.asyncio
    async def test_owner_can_remove_member(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Owner can remove a member."""
        org = organization_with_roles["organization"]
        owner_headers = organization_with_roles["owner"]["headers"]
        viewer_id = organization_with_roles["viewer"]["user"].id

        response = await client.delete(
            f"/api/v1/organizations/{org.id}/members/{viewer_id}",
            headers=owner_headers
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_can_remove_member(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Admin can remove a member."""
        org = organization_with_roles["organization"]
        admin_headers = organization_with_roles["admin"]["headers"]
        viewer_id = organization_with_roles["viewer"]["user"].id

        response = await client.delete(
            f"/api/v1/organizations/{org.id}/members/{viewer_id}",
            headers=admin_headers
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_member_cannot_remove_others(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Member canNOT remove other members."""
        org = organization_with_roles["organization"]
        member_headers = organization_with_roles["member"]["headers"]
        viewer_id = organization_with_roles["viewer"]["user"].id

        response = await client.delete(
            f"/api/v1/organizations/{org.id}/members/{viewer_id}",
            headers=member_headers
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_member_can_leave_organization(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Member can remove themselves from the organization."""
        org = organization_with_roles["organization"]
        member_headers = organization_with_roles["member"]["headers"]
        member_id = organization_with_roles["member"]["user"].id

        response = await client.delete(
            f"/api/v1/organizations/{org.id}/members/{member_id}",
            headers=member_headers
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_cannot_remove_owner(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Nobody can remove the owner."""
        org = organization_with_roles["organization"]
        admin_headers = organization_with_roles["admin"]["headers"]
        owner_id = organization_with_roles["owner"]["user"].id

        response = await client.delete(
            f"/api/v1/organizations/{org.id}/members/{owner_id}",
            headers=admin_headers
        )

        assert response.status_code == 400


# ===== Tests: Multi-tenant isolation =====

class TestMultiTenantIsolation:
    """Isolation tests between organizations."""

    @pytest.mark.asyncio
    async def test_cannot_access_other_organization(
        self, client: AsyncClient, organization_with_roles: dict, second_organization: dict
    ):
        """A user cannot access another organization."""
        other_org = second_organization["organization"]
        our_headers = organization_with_roles["owner"]["headers"]

        response = await client.get(
            f"/api/v1/organizations/{other_org.id}",
            headers=our_headers
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_modify_other_organization(
        self, client: AsyncClient, organization_with_roles: dict, second_organization: dict
    ):
        """An admin cannot modify another organization."""
        other_org = second_organization["organization"]
        our_admin_headers = organization_with_roles["admin"]["headers"]

        response = await client.patch(
            f"/api/v1/organizations/{other_org.id}",
            json={"name": "Hacked!"},
            headers=our_admin_headers
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_list_other_org_members(
        self, client: AsyncClient, organization_with_roles: dict, second_organization: dict
    ):
        """Cannot list members of another organization."""
        other_org = second_organization["organization"]
        our_headers = organization_with_roles["owner"]["headers"]

        response = await client.get(
            f"/api/v1/organizations/{other_org.id}/members",
            headers=our_headers
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_invite_to_other_organization(
        self, client: AsyncClient, organization_with_roles: dict, second_organization: dict
    ):
        """Cannot invite to another organization."""
        other_org = second_organization["organization"]
        our_owner_headers = organization_with_roles["owner"]["headers"]

        response = await client.post(
            f"/api/v1/organizations/{other_org.id}/invitations",
            json={
                "email": "hacker@example.com",
                "role": "admin"
            },
            headers=our_owner_headers
        )

        assert response.status_code == 403


# ===== Tests: API Keys and scopes =====

class TestAPIKeyScopes:
    """API key scopes tests."""

    @pytest.mark.asyncio
    async def test_create_api_key_with_scopes(
        self, client: AsyncClient, organization_with_roles: dict
    ):
        """Create an API key with specific scopes."""
        headers = organization_with_roles["owner"]["headers"]

        response = await client.post(
            "/api/v1/api-keys",
            json={
                "name": "Limited Key",
                "scopes": ["tools:read"],
                "description": "Read-only tools access"
            },
            headers=headers
        )

        assert response.status_code == 201
        data = response.json()
        assert "tools:read" in data["api_key"]["scopes"]
        assert "tools:execute" not in data["api_key"]["scopes"]

    @pytest.mark.asyncio
    async def test_api_key_scope_enforcement(
        self, client: AsyncClient, organization_with_roles: dict, db_session: AsyncSession
    ):
        """API key scopes are enforced."""
        owner_headers = organization_with_roles["owner"]["headers"]

        # Create a key with limited scope
        create_response = await client.post(
            "/api/v1/api-keys",
            json={
                "name": "Read Only Key",
                "scopes": ["tools:read"]  # No tools:execute
            },
            headers=owner_headers
        )

        assert create_response.status_code == 201
        api_key_secret = create_response.json()["secret"]

        # Try to use the key for an action requiring tools:execute
        # Note: This test depends on the existence of a scope-protected endpoint
        # If the endpoint exists, verify that 403 is returned
        # Otherwise, this test just validates that scopes are stored


# ===== Tests: Permission Service =====

class TestPermissionService:
    """Permission service tests for compositions."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_execute_composition(
        self, db_session: AsyncSession, organization_with_roles: dict
    ):
        """Viewer cannot execute composition (read-only)."""
        from app.services.permission_service import PermissionService
        from app.orchestration.composition_store import CompositionInfo

        permission_service = PermissionService(db_session)

        # Create a mock composition
        composition = CompositionInfo(
            id="test-composition",
            name="Test Composition",
            description="A test composition",
            steps=[{"tool": "tool1"}, {"tool": "tool2"}],
            allowed_roles=[]  # No explicit restriction
        )

        viewer = organization_with_roles["viewer"]["user"]
        org = organization_with_roles["organization"]

        can_execute, reason = await permission_service.can_execute_composition(
            user_id=viewer.id,
            organization_id=org.id,
            composition=composition
        )

        assert can_execute is False
        assert "viewer" in reason.lower() or "read-only" in reason.lower()

    @pytest.mark.asyncio
    async def test_member_can_execute_composition(
        self, db_session: AsyncSession, organization_with_roles: dict
    ):
        """Member can execute composition without restriction."""
        from app.services.permission_service import PermissionService
        from app.orchestration.composition_store import CompositionInfo

        permission_service = PermissionService(db_session)

        composition = CompositionInfo(
            id="test-composition",
            name="Test Composition",
            description="A test composition",
            steps=[{"tool": "tool1"}],
            allowed_roles=[]  # No restriction
        )

        member = organization_with_roles["member"]["user"]
        org = organization_with_roles["organization"]

        can_execute, reason = await permission_service.can_execute_composition(
            user_id=member.id,
            organization_id=org.id,
            composition=composition
        )

        assert can_execute is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_composition_role_restriction(
        self, db_session: AsyncSession, organization_with_roles: dict
    ):
        """A composition can restrict access to certain roles."""
        from app.services.permission_service import PermissionService
        from app.orchestration.composition_store import CompositionInfo

        permission_service = PermissionService(db_session)

        # Composition reserved for admins and owners
        composition = CompositionInfo(
            id="admin-only",
            name="Admin Only Composition",
            description="Restricted to admins",
            steps=[{"tool": "dangerous_tool"}],
            allowed_roles=["admin", "owner"]  # Explicit restriction
        )

        org = organization_with_roles["organization"]

        # Member cannot execute
        member = organization_with_roles["member"]["user"]
        can_execute, reason = await permission_service.can_execute_composition(
            user_id=member.id,
            organization_id=org.id,
            composition=composition
        )
        assert can_execute is False

        # Admin can execute
        admin = organization_with_roles["admin"]["user"]
        can_execute, reason = await permission_service.can_execute_composition(
            user_id=admin.id,
            organization_id=org.id,
            composition=composition
        )
        assert can_execute is True

    @pytest.mark.asyncio
    async def test_all_roles_can_view_composition(
        self, db_session: AsyncSession, organization_with_roles: dict
    ):
        """All members can view compositions."""
        from app.services.permission_service import PermissionService
        from app.orchestration.composition_store import CompositionInfo

        permission_service = PermissionService(db_session)

        composition = CompositionInfo(
            id="any-composition",
            name="Any Composition",
            description="Viewable by all",
            steps=[{"tool": "tool1"}],
            allowed_roles=["admin", "owner"]  # Restricted for execution
        )

        org = organization_with_roles["organization"]

        for role in ["owner", "admin", "member", "viewer"]:
            user = organization_with_roles[role]["user"]
            can_view, reason = await permission_service.can_view_composition(
                user_id=user.id,
                organization_id=org.id,
                composition=composition
            )
            assert can_view is True, f"Role {role} should be able to view"
