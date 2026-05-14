"""
OIDC SSO models (Story I.1).

Two tables:

- ``oidc_providers``: configuration of one Identity Provider per row
  (issuer URL, client_id, encrypted client_secret, scopes, where to
  read group claims, fallback policies, …). Multiple providers per
  instance are supported (e.g. AgentConnect-via-Orion + Google for
  external partners).

- ``oidc_group_mappings``: rows mapping an IdP group claim
  (``"cerema-direction-num"``) to a BigMCP team (``Organization``)
  with a role. A user belonging to multiple matching groups gets
  multiple ``OrganizationMember`` rows. A row may also grant
  instance-admin status (``grants_instance_admin``).

Per-user identity is stored on the ``User`` row itself
(``oidc_provider_id`` + ``oidc_subject``), see ``app/models/user.py``.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin, TimestampMixin
from ..db.types import JSONType


class OIDCProvider(Base, UUIDMixin, TimestampMixin):
    """One OIDC Identity Provider configured for this instance.

    The ``client_secret_encrypted`` column stores a Fernet-encrypted
    JSON blob ``{"client_secret": "..."}`` so that key rotation reuses
    the existing ``SecretsManager`` infrastructure.

    Discovery: when ``issuer_url`` is set, the service layer fetches
    ``{issuer_url}/.well-known/openid-configuration`` to learn the
    authorization/token/userinfo endpoints. Manual overrides are
    possible via ``manual_endpoints_json`` for IdPs that don't expose
    discovery (rare, mostly legacy).
    """

    __tablename__ = "oidc_providers"

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        comment="Display name shown to admin (e.g. 'Cerema Orion').",
    )
    display_label: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Button label on LoginPage (e.g. 'Continue with Cerema').",
    )

    # OIDC discovery
    issuer_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="OIDC issuer URL — discovery via /.well-known/openid-configuration.",
    )
    manual_endpoints_json: Mapped[Optional[dict]] = mapped_column(
        JSONType,
        nullable=True,
        comment="Optional override of discovered endpoints (auth/token/userinfo).",
    )

    # Client credentials
    client_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="OIDC client_id registered at the IdP.",
    )
    client_secret_encrypted: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        comment="Fernet-encrypted JSON {'client_secret': '...'}",
    )

    # Scopes & claims
    scopes: Mapped[list] = mapped_column(
        JSONType,
        nullable=False,
        default=lambda: ["openid", "profile", "email"],
        comment="OIDC scopes requested at /authorize.",
    )
    groups_claim_path: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        default="groups",
        comment=(
            "Dot-notation path inside the ID token / userinfo where group "
            "membership claims live. Defaults to 'groups'. Examples: "
            "'realm_access.roles' (Keycloak default), 'https://schemas.bigmcp/groups'."
        ),
    )
    email_claim_path: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="email",
        server_default="email",
        comment="Where to read the user's email (default OIDC standard).",
    )
    name_claim_path: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="name",
        server_default="name",
        comment="Where to read the user's display name.",
    )

    # Provisioning policy
    auto_link_by_verified_email: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment=(
            "If true, when an SSO login matches a local user by email "
            "(and email_verified=true in the token), bind the SSO "
            "identity to that user. Used during legacy→SSO migration. "
            "MUST be off in steady state."
        ),
    )
    require_email_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment=(
            "Reject SSO logins where the IdP does not assert "
            "email_verified=true. Default safe."
        ),
    )
    reject_unmapped_users: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment=(
            "If true, a user whose group claims match no GroupMapping is "
            "rejected at login. False = use fallback_organization/role."
        ),
    )
    fallback_organization_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        comment=(
            "When reject_unmapped_users=false, unmapped users are placed "
            "in this team. Null + reject=false = create PERSONAL org "
            "(SaaS-demo behaviour)."
        ),
    )
    fallback_role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="member",
        server_default="member",
        comment="Role assigned when falling back (owner/admin/member/viewer).",
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="If false, the provider is hidden from LoginPage and login is refused.",
    )

    group_mappings: Mapped[list["OIDCGroupMapping"]] = relationship(
        "OIDCGroupMapping",
        back_populates="provider",
        cascade="all, delete-orphan",
    )

    @property
    def client_secret(self) -> str:
        """Decrypt and return the OIDC client_secret."""
        from ..core.secrets_manager import secrets_manager
        return secrets_manager.decrypt(self.client_secret_encrypted)["client_secret"]

    @client_secret.setter
    def client_secret(self, value: str) -> None:
        """Encrypt and store the OIDC client_secret."""
        from ..core.secrets_manager import secrets_manager
        self.client_secret_encrypted = secrets_manager.encrypt(
            {"client_secret": value}
        )

    def __repr__(self) -> str:
        return f"<OIDCProvider(id={self.id}, name={self.name})>"


class OIDCGroupMapping(Base, UUIDMixin, TimestampMixin):
    """Map one IdP group claim to a BigMCP team membership (or to instance-admin).

    A single user typically matches several rows — the resync code in
    the JIT helper iterates all rows for the provider, intersects with
    the user's group claims, and reconciles ``OrganizationMember``.

    A row with ``grants_instance_admin=true`` and no ``organization_id``
    flips the user's ``preferences['instance_admin']`` flag at login.
    A row with ``organization_id`` set adds an OrganizationMember with
    ``role`` to that org. The two are not mutually exclusive (one row
    can do both — but the cleanest pattern is one row per concern).
    """

    __tablename__ = "oidc_group_mappings"

    provider_id: Mapped[UUID] = mapped_column(
        ForeignKey("oidc_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    idp_group_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Exact value the IdP returns inside the configured groups_claim_path.",
    )
    organization_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        comment="Team to add the user to. Null = mapping only grants instance_admin.",
    )
    role: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Role within the org (owner/admin/member/viewer).",
    )
    grants_instance_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="If true, login with this group flips preferences.instance_admin = true.",
    )

    provider: Mapped["OIDCProvider"] = relationship(
        "OIDCProvider", back_populates="group_mappings"
    )
    organization = relationship("Organization", foreign_keys=[organization_id])

    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "idp_group_name",
            "organization_id",
            name="uq_oidc_mapping_per_provider_group_org",
        ),
        Index("ix_oidc_mappings_provider_group", "provider_id", "idp_group_name"),
    )

    def __repr__(self) -> str:
        return (
            f"<OIDCGroupMapping(provider={self.provider_id}, "
            f"group={self.idp_group_name!r}, org={self.organization_id}, "
            f"role={self.role}, instance_admin={self.grants_instance_admin})>"
        )
