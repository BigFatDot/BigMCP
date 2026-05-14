"""End-to-end tests for OIDC SSO foundation (Story I.1).

Coverage:

- Group claim extraction (array, CSV, scalar, missing, dotted path)
- ``provision_or_update_user`` happy path → JIT-create + membership resync
- Email-collision auto-link toggle (off → 403, on → link)
- ``email_verified=false`` rejected when policy requires
- ``status != ACTIVE`` blocks SSO login (lifecycle gate covers SSO too)
- ``reject_unmapped_users=true`` + 0 mappings + no fallback → reject
- ``reject_unmapped_users=false`` + fallback_organization_id set → assign
- Admin guard refuses to save a config that would lock everyone out
- ``force-SSO-only`` toggle refuses to enable without break-glass admin
- ``/auth/sso-providers`` public endpoint returns active providers only
- ``/auth/login`` rejected with 403 force_sso_only when toggle is on
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLog
from app.models.instance_settings import InstanceSettings
from app.models.oidc import OIDCGroupMapping, OIDCProvider
from app.models.organization import Organization, OrganizationMember, UserRole
from app.models.user import User, UserStatus
from app.services.oidc_service import OIDCError, OIDCService, extract_groups


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _promote(db: AsyncSession, email: str) -> None:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    prefs = dict(user.preferences or {})
    prefs["instance_admin"] = True
    user.preferences = prefs
    await db.commit()


async def _make_provider(
    db: AsyncSession,
    *,
    name: str = "Test IdP",
    auto_link: bool = False,
    require_verified: bool = True,
    reject_unmapped: bool = True,
    fallback_org_id=None,
    fallback_role: str = "member",
    groups_path: str = "groups",
) -> OIDCProvider:
    p = OIDCProvider(
        name=name,
        display_label=f"Continue with {name}",
        issuer_url="https://idp.example.com",
        client_id="test-client",
        scopes=["openid", "profile", "email"],
        groups_claim_path=groups_path,
        email_claim_path="email",
        name_claim_path="name",
        auto_link_by_verified_email=auto_link,
        require_email_verified=require_verified,
        reject_unmapped_users=reject_unmapped,
        fallback_organization_id=fallback_org_id,
        fallback_role=fallback_role,
        is_active=True,
    )
    p.client_secret = "test-secret"
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def _make_org(db: AsyncSession, name: str = "Engineering") -> Organization:
    org = Organization(name=name, slug=name.lower().replace(" ", "-"))
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org


# ---------------------------------------------------------------------------
# Group extraction
# ---------------------------------------------------------------------------


async def test_extract_groups_handles_array():
    assert extract_groups({"groups": ["a", "b"]}, "groups") == ["a", "b"]


async def test_extract_groups_handles_csv():
    assert extract_groups({"groups": "a, b,c"}, "groups") == ["a", "b", "c"]


async def test_extract_groups_handles_scalar():
    assert extract_groups({"groups": "a"}, "groups") == ["a"]


async def test_extract_groups_handles_missing():
    assert extract_groups({}, "groups") == []


async def test_extract_groups_handles_null():
    assert extract_groups({"groups": None}, "groups") == []


async def test_extract_groups_handles_dotted_path():
    claims = {"realm_access": {"roles": ["admin", "user"]}}
    assert extract_groups(claims, "realm_access.roles") == ["admin", "user"]


async def test_extract_groups_handles_missing_dotted_path():
    assert extract_groups({"realm_access": {}}, "realm_access.roles") == []


# ---------------------------------------------------------------------------
# JIT provisioning
# ---------------------------------------------------------------------------


async def test_jit_creates_user_in_fallback_org(db_session: AsyncSession):
    org = await _make_org(db_session, "Fallback Team")
    p = await _make_provider(
        db_session,
        reject_unmapped=False,
        fallback_org_id=org.id,
        fallback_role="member",
    )

    svc = OIDCService(db_session)
    user = await svc.provision_or_update_user(
        provider=p,
        id_token_claims={"sub": "user-123", "email_verified": True, "nonce": "x"},
        userinfo={"email": "alice@example.com", "name": "Alice"},
    )
    assert user.email == "alice@example.com"
    assert user.oidc_provider_id == p.id
    assert user.oidc_subject == "user-123"
    assert user.password_hash is None
    assert user.email_verified is True

    members = (
        await db_session.execute(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        )
    ).scalars().all()
    assert len(members) == 1
    assert members[0].organization_id == org.id


async def test_reject_unverified_email_when_required(db_session: AsyncSession):
    p = await _make_provider(db_session)
    svc = OIDCService(db_session)
    with pytest.raises(OIDCError, match="email_verified"):
        await svc.provision_or_update_user(
            provider=p,
            id_token_claims={"sub": "x", "email_verified": False},
            userinfo={"email": "a@b.com"},
        )


async def test_email_collision_without_auto_link_is_rejected(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    # test_user owns testuser@example.com locally
    p = await _make_provider(db_session, auto_link=False)
    svc = OIDCService(db_session)
    with pytest.raises(OIDCError, match="already exists"):
        await svc.provision_or_update_user(
            provider=p,
            id_token_claims={"sub": "sso-1", "email_verified": True},
            userinfo={"email": test_user["email"]},
        )


async def test_email_collision_with_auto_link_binds_existing_user(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    p = await _make_provider(
        db_session, auto_link=True, reject_unmapped=False
    )
    org = await _make_org(db_session, "Auto-link Team")
    p.fallback_organization_id = org.id
    await db_session.commit()

    svc = OIDCService(db_session)
    user = await svc.provision_or_update_user(
        provider=p,
        id_token_claims={"sub": "sso-bound", "email_verified": True},
        userinfo={"email": test_user["email"]},
    )
    assert user.email == test_user["email"]
    assert user.oidc_provider_id == p.id
    assert user.oidc_subject == "sso-bound"

    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == AuditAction.OIDC_AUTO_LINK_USER.value
            )
        )
    ).scalars().all()
    assert any(a.actor_id == user.id for a in audit)


async def test_suspended_user_blocked_via_sso(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    p = await _make_provider(db_session, auto_link=True, reject_unmapped=False)

    # First successful login binds the SSO identity
    svc = OIDCService(db_session)
    user = await svc.provision_or_update_user(
        provider=p,
        id_token_claims={"sub": "sso-life", "email_verified": True},
        userinfo={"email": test_user["email"]},
    )

    # Suspend user
    user.status = UserStatus.SUSPENDED.value
    await db_session.commit()

    # Next login should be refused
    with pytest.raises(OIDCError, match="suspended"):
        await OIDCService(db_session).provision_or_update_user(
            provider=p,
            id_token_claims={"sub": "sso-life", "email_verified": True},
            userinfo={"email": test_user["email"]},
        )


async def test_reject_unmapped_users_blocks_login(db_session: AsyncSession):
    p = await _make_provider(db_session, reject_unmapped=True)
    svc = OIDCService(db_session)
    with pytest.raises(OIDCError, match="No IdP group matches"):
        await svc.provision_or_update_user(
            provider=p,
            id_token_claims={
                "sub": "u",
                "email_verified": True,
                "groups": ["unknown"],
            },
            userinfo={"email": "u@example.com"},
        )


async def test_group_mapping_assigns_team_membership(db_session: AsyncSession):
    p = await _make_provider(db_session, reject_unmapped=True)
    org = await _make_org(db_session, "Direction Numérique")
    db_session.add(
        OIDCGroupMapping(
            provider_id=p.id,
            idp_group_name="engineering-admin",
            organization_id=org.id,
            role=UserRole.ADMIN.value,
        )
    )
    await db_session.commit()

    svc = OIDCService(db_session)
    user = await svc.provision_or_update_user(
        provider=p,
        id_token_claims={
            "sub": "alice",
            "email_verified": True,
            "groups": ["engineering-admin", "other-group"],
        },
        userinfo={"email": "alice@example.com", "name": "Alice"},
    )
    members = (
        await db_session.execute(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        )
    ).scalars().all()
    assert len(members) == 1
    assert members[0].organization_id == org.id
    assert members[0].role == UserRole.ADMIN


async def test_resync_removes_obsolete_membership_when_group_disappears(
    db_session: AsyncSession,
):
    p = await _make_provider(db_session, reject_unmapped=False)
    org_old = await _make_org(db_session, "Pôle Old")
    org_new = await _make_org(db_session, "Pôle New")
    db_session.add_all(
        [
            OIDCGroupMapping(
                provider_id=p.id,
                idp_group_name="pole-old",
                organization_id=org_old.id,
                role=UserRole.MEMBER.value,
            ),
            OIDCGroupMapping(
                provider_id=p.id,
                idp_group_name="pole-new",
                organization_id=org_new.id,
                role=UserRole.MEMBER.value,
            ),
        ]
    )
    await db_session.commit()
    svc = OIDCService(db_session)

    # First login: in pole-old
    await svc.provision_or_update_user(
        provider=p,
        id_token_claims={
            "sub": "bob",
            "email_verified": True,
            "groups": ["pole-old"],
        },
        userinfo={"email": "bob@example.com"},
    )

    # Second login: switched to pole-new
    user = await OIDCService(db_session).provision_or_update_user(
        provider=p,
        id_token_claims={
            "sub": "bob",
            "email_verified": True,
            "groups": ["pole-new"],
        },
        userinfo={"email": "bob@example.com"},
    )
    members = (
        await db_session.execute(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        )
    ).scalars().all()
    assert len(members) == 1
    assert members[0].organization_id == org_new.id


async def test_grants_instance_admin_via_group(db_session: AsyncSession):
    p = await _make_provider(db_session, reject_unmapped=False)
    db_session.add(
        OIDCGroupMapping(
            provider_id=p.id,
            idp_group_name="bigmcp-admins",
            grants_instance_admin=True,
        )
    )
    org = await _make_org(db_session, "Default")
    p.fallback_organization_id = org.id
    await db_session.commit()

    svc = OIDCService(db_session)
    user = await svc.provision_or_update_user(
        provider=p,
        id_token_claims={
            "sub": "admin-1",
            "email_verified": True,
            "groups": ["bigmcp-admins"],
        },
        userinfo={"email": "admin@example.com"},
    )
    assert (user.preferences or {}).get("instance_admin") is True


# ---------------------------------------------------------------------------
# Admin endpoints — guards
# ---------------------------------------------------------------------------


async def test_create_provider_refuses_lockout_config(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    await _promote(db_session, test_user["email"])
    payload = {
        "name": "Locked",
        "display_label": "Locked",
        "issuer_url": "https://idp.example.com",
        "client_id": "x",
        "client_secret": "y",
        "reject_unmapped_users": True,
        "fallback_organization_id": None,
    }
    resp = await client.post(
        "/api/v1/admin/sso/providers", json=payload, headers=auth_headers
    )
    assert resp.status_code == 400
    assert "lock out" in resp.text.lower()


async def test_create_provider_succeeds_with_fallback(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    await _promote(db_session, test_user["email"])
    org = await _make_org(db_session, "Fallback")
    payload = {
        "name": "OK",
        "display_label": "OK",
        "issuer_url": "https://idp.example.com",
        "client_id": "x",
        "client_secret": "y",
        "reject_unmapped_users": True,
        "fallback_organization_id": str(org.id),
    }
    resp = await client.post(
        "/api/v1/admin/sso/providers", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text


async def test_force_sso_only_refused_without_break_glass(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    """The only instance-admin is the test user, who has password_hash set,
    so this should *succeed*. We test the rejection path by also clearing
    his password hash.
    """
    await _promote(db_session, test_user["email"])

    # First — succeeds because test_user has password_hash
    ok = await client.put(
        "/api/v1/admin/sso/force-sso-only",
        json={"enabled": True},
        headers=auth_headers,
    )
    assert ok.status_code == 200

    # Now strip the only admin's password and try to re-enable from scratch
    user = (
        await db_session.execute(
            select(User).where(User.email == test_user["email"])
        )
    ).scalar_one()
    user.password_hash = None
    await db_session.commit()

    # Reset the toggle so the next call goes through the guard
    settings_row = await db_session.get(InstanceSettings, 1)
    if settings_row:
        cc = dict(settings_row.client_control or {})
        cc["force_sso_only"] = False
        settings_row.client_control = cc
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(settings_row, "client_control")
        await db_session.commit()

    # Second — fails because no admin has password_hash
    ko = await client.put(
        "/api/v1/admin/sso/force-sso-only",
        json={"enabled": True},
        headers=auth_headers,
    )
    assert ko.status_code == 400
    assert "break-glass" in ko.text.lower()


async def test_local_login_blocked_when_force_sso_on(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    await _promote(db_session, test_user["email"])
    # Enable force-SSO-only
    enable = await client.put(
        "/api/v1/admin/sso/force-sso-only",
        json={"enabled": True},
        headers=auth_headers,
    )
    assert enable.status_code == 200

    # Now try to login locally
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert resp.status_code == 403
    assert "sso" in resp.text.lower()


async def test_public_sso_providers_endpoint_is_public(
    client: AsyncClient, db_session: AsyncSession
):
    p = await _make_provider(db_session, name="Visible IdP")
    inactive = await _make_provider(
        db_session, name="Hidden IdP", reject_unmapped=False
    )
    inactive.is_active = False
    await db_session.commit()

    resp = await client.get("/api/v1/auth/sso-providers")
    assert resp.status_code == 200
    body = resp.json()
    names = [p["name"] for p in body["providers"]]
    assert "Visible IdP" in names
    assert "Hidden IdP" not in names

    # Make sure no secrets leak
    for entry in body["providers"]:
        assert "client_secret" not in entry
        assert "client_secret_encrypted" not in entry


# ---------------------------------------------------------------------------
# Presets (Story I.2)
# ---------------------------------------------------------------------------


async def test_presets_endpoint_lists_all_vendors(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    await _promote(db_session, test_user["email"])
    resp = await client.get("/api/v1/admin/sso/presets", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "presets" in body
    ids = {p["id"] for p in body["presets"]}
    assert {"keycloak", "google", "microsoft-entra", "agentconnect", "generic"} <= ids


async def test_presets_endpoint_requires_instance_admin(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    # test_user is auto-promoted to instance admin (first user). Register a
    # second non-admin user and verify the endpoint refuses their request.
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "non-admin@example.com",
            "password": "NonAdmin123!",
            "name": "Non Admin",
        },
    )
    assert register.status_code in (201, 202)
    from sqlalchemy import update
    await db_session.execute(
        update(User)
        .where(User.email == "non-admin@example.com")
        .values(email_verified=True)
    )
    await db_session.commit()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "non-admin@example.com", "password": "NonAdmin123!"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get("/api/v1/admin/sso/presets", headers=headers)
    assert resp.status_code == 403


async def test_presets_payload_shape_is_complete(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    await _promote(db_session, test_user["email"])
    resp = await client.get("/api/v1/admin/sso/presets", headers=auth_headers)
    body = resp.json()
    required_fields = {
        "id",
        "label",
        "default_name",
        "default_display_label",
        "issuer_url_template",
        "issuer_url_placeholder",
        "scopes",
        "groups_claim_path",
        "email_claim_path",
        "name_claim_path",
        "require_email_verified",
        "notes",
        "docs_url",
    }
    for preset in body["presets"]:
        missing = required_fields - set(preset.keys())
        assert not missing, f"Preset {preset.get('id')} missing fields: {missing}"


async def test_create_provider_using_preset_data(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    """Sanity check: a payload built straight from a preset (admin only
    has to add client_id + client_secret) creates a usable provider."""
    await _promote(db_session, test_user["email"])
    org = await _make_org(db_session, "Default for SSO")

    # Pull the Keycloak preset
    presets = (
        await client.get("/api/v1/admin/sso/presets", headers=auth_headers)
    ).json()["presets"]
    keycloak = next(p for p in presets if p["id"] == "keycloak")

    payload = {
        "name": keycloak["default_name"],
        "display_label": keycloak["default_display_label"],
        "issuer_url": "https://auth.example.com/realms/yourorg",
        "client_id": "bigmcp",
        "client_secret": "supersecret",
        "scopes": keycloak["scopes"],
        "groups_claim_path": keycloak["groups_claim_path"],
        "email_claim_path": keycloak["email_claim_path"],
        "name_claim_path": keycloak["name_claim_path"],
        "require_email_verified": keycloak["require_email_verified"],
        "reject_unmapped_users": False,
        "fallback_organization_id": str(org.id),
    }
    resp = await client.post(
        "/api/v1/admin/sso/providers", json=payload, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Keycloak"
    assert body["groups_claim_path"] == "realm_access.roles"
    assert body["fallback_organization_id"] == str(org.id)
