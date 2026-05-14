"""
OIDC presets — pre-filled configuration templates per common IdP (Story I.2).

Each preset captures the IdP-specific bits the admin would otherwise have
to look up in vendor docs: discovery issuer URL, recommended scopes,
where the groups claim lives, default claim paths for email and name.
The admin still has to provide ``client_id`` and ``client_secret`` —
those are tenant-specific and never bundled.

The presets are exposed via ``GET /admin/sso/presets`` so the frontend
can populate a "Configure {Vendor}" button that pre-fills the form.

Adding a new preset:
1. Append a new entry to ``PRESETS``.
2. Test the issuer URL responds to ``/.well-known/openid-configuration``.
3. Note any vendor-specific gotcha in the ``notes`` field.
"""

from __future__ import annotations

from typing import List, Dict, Any


PRESETS: List[Dict[str, Any]] = [
    # ----- Keycloak (covers Red Hat SSO, custom Keycloak deployments)
    {
        "id": "keycloak",
        "label": "Keycloak (auto-discovery)",
        "default_name": "Keycloak",
        "default_display_label": "Continue with Keycloak",
        "issuer_url_template": "https://{hostname}/realms/{realm}",
        "issuer_url_placeholder": "https://auth.example.com/realms/your-realm",
        "scopes": ["openid", "profile", "email"],
        "groups_claim_path": "realm_access.roles",
        "email_claim_path": "email",
        "name_claim_path": "name",
        "require_email_verified": True,
        "notes": (
            "The issuer URL must include the realm path "
            "(/realms/{realm-name}). Discovery picks up the rest. "
            "Default groups claim is 'realm_access.roles'; switch to "
            "'groups' if your realm has a custom group mapper."
        ),
        "docs_url": "https://www.keycloak.org/docs/latest/server_admin/#con-oidc_server_administration_guide",
    },
    # ----- Google Workspace
    {
        "id": "google",
        "label": "Google Workspace",
        "default_name": "Google",
        "default_display_label": "Continue with Google",
        "issuer_url_template": "https://accounts.google.com",
        "issuer_url_placeholder": "https://accounts.google.com",
        "scopes": ["openid", "profile", "email"],
        "groups_claim_path": "groups",
        "email_claim_path": "email",
        "name_claim_path": "name",
        "require_email_verified": True,
        "notes": (
            "Standard Google OIDC. The 'groups' claim is NOT emitted by "
            "default — Workspace admins must enable it via the Directory "
            "API + custom claim mapping, or rely on email-domain "
            "matching in fallback_organization_id."
        ),
        "docs_url": "https://developers.google.com/identity/openid-connect/openid-connect",
    },
    # ----- Microsoft Entra (Azure AD)
    {
        "id": "microsoft-entra",
        "label": "Microsoft Entra (Azure AD)",
        "default_name": "Microsoft Entra",
        "default_display_label": "Continue with Microsoft",
        "issuer_url_template": "https://login.microsoftonline.com/{tenant_id}/v2.0",
        "issuer_url_placeholder": (
            "https://login.microsoftonline.com/00000000-0000-0000-0000-000000000000/v2.0"
        ),
        "scopes": ["openid", "profile", "email"],
        "groups_claim_path": "groups",
        "email_claim_path": "email",
        "name_claim_path": "name",
        "require_email_verified": True,
        "notes": (
            "Tenant ID must be in the issuer URL ({tenant_id}/v2.0). "
            "For 'groups' claim emission, configure the app registration's "
            "token configuration to add 'groups' as a security group claim. "
            "Without it, only fallback_organization_id will assign teams."
        ),
        "docs_url": "https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc",
    },
    # ----- AgentConnect / ProConnect (French gov)
    {
        "id": "agentconnect",
        "label": "AgentConnect / ProConnect (French gov)",
        "default_name": "AgentConnect",
        "default_display_label": "Continue with AgentConnect",
        "issuer_url_template": "https://auth.agentconnect.gouv.fr",
        "issuer_url_placeholder": "https://auth.agentconnect.gouv.fr",
        "scopes": [
            "openid",
            "given_name",
            "usual_name",
            "email",
            "uid",
            "siret",
        ],
        "groups_claim_path": "belonging_population",
        "email_claim_path": "email",
        "name_claim_path": "usual_name",
        "require_email_verified": True,
        "notes": (
            "Identity proofer for French state agents. Most agencies "
            "consume AgentConnect via their internal Keycloak (Orion at "
            "via an internal broker) — use the Keycloak preset in that case. "
            "Direct integration is for orgs without an intermediate broker. "
            "Group mapping is limited; rely on fallback_organization_id."
        ),
        "docs_url": "https://github.com/numerique-gouv/proconnect-documentation",
    },
    # ----- Generic OIDC (fully custom)
    {
        "id": "generic",
        "label": "Generic OIDC (custom)",
        "default_name": "OIDC Provider",
        "default_display_label": "Continue with SSO",
        "issuer_url_template": "",
        "issuer_url_placeholder": "https://your-idp.example.com",
        "scopes": ["openid", "profile", "email"],
        "groups_claim_path": "groups",
        "email_claim_path": "email",
        "name_claim_path": "name",
        "require_email_verified": True,
        "notes": (
            "For any standard OIDC provider not covered by the other "
            "presets. Discovery via /.well-known/openid-configuration. "
            "Override claim paths if the IdP uses non-standard names."
        ),
        "docs_url": "https://openid.net/specs/openid-connect-core-1_0.html",
    },
]


def get_preset(preset_id: str) -> Dict[str, Any] | None:
    """Return the preset matching ``preset_id`` or None."""
    for p in PRESETS:
        if p["id"] == preset_id:
            return p
    return None
