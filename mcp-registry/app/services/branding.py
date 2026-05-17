"""Instance branding resolver — white-label for self-hosted deploys.

Three-layer merge with explicit precedence:

1. **InstanceSettings row** (DB) — what the admin set via the UI.
2. **Env vars** (``INSTANCE_NAME``, ``INSTANCE_LOGO_URL``, ...) — what
   the operator hardcoded in compose / k8s manifests.
3. **Built-in defaults** — BigMCP branding so the platform stays usable
   on a fresh deploy with zero config.

The merged view is what the public ``GET /api/v1/instance/branding``
returns; the frontend hydrates its ``BrandingContext`` from it at boot.

Why this layering: the DB lets a non-technical instance admin rebrand
from the UI without touching infra; env vars give ops a way to ship a
pre-branded image; defaults keep us safe if neither is set.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.instance_settings import InstanceSettings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Built-in defaults — the BigMCP brand. Anything you change here changes the
# experience for instances that have set neither DB row nor env vars.
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "instance_name": "BigMCP",
    "instance_tagline": "Unified MCP Gateway for AI Agents",
    "logo_url": None,             # None → frontend renders <BigMCPLogo />
    "favicon_url": None,          # None → frontend keeps /favicon.ico
    "primary_color": "#D97757",   # Orange (matches existing CSS)
    "support_email": None,
    "instance_url": None,         # None → frontend uses window.location.origin
    "legal_entity": None,
}


@dataclass
class Branding:
    """Frozen view of an instance's branding for one request.

    The dataclass mirrors the response payload one-to-one so adding a
    field is a single change here.
    """

    instance_name: str
    instance_tagline: str
    logo_url: Optional[str]
    favicon_url: Optional[str]
    primary_color: str
    support_email: Optional[str]
    instance_url: Optional[str]
    legal_entity: Optional[str]
    setup_completed: bool
    # ``customized`` tells the frontend whether to keep the built-in
    # BigMCP look (False) or render the custom one (True). Cheap signal
    # for the navbar / login page to decide "show 'powered by BigMCP'
    # footer or not".
    customized: bool

    def to_dict(self) -> dict:
        return asdict(self)


_ENV_KEYS = {
    "instance_name": "INSTANCE_NAME",
    "instance_tagline": "INSTANCE_TAGLINE",
    "logo_url": "INSTANCE_LOGO_URL",
    "favicon_url": "INSTANCE_FAVICON_URL",
    "primary_color": "INSTANCE_PRIMARY_COLOR",
    "support_email": "INSTANCE_SUPPORT_EMAIL",
    "instance_url": "INSTANCE_URL",
    "legal_entity": "INSTANCE_LEGAL_ENTITY",
}


def _from_env(field: str) -> Optional[str]:
    raw = os.environ.get(_ENV_KEYS[field])
    if raw is None:
        return None
    raw = raw.strip()
    return raw or None


async def get_or_create_settings(db: AsyncSession) -> InstanceSettings:
    """Return the singleton row, creating it on the fly if missing.

    A brand-new instance won't have the row yet (it's lazy-created by
    the policy resolver on first admin write). We need it for branding
    reads on boot too, so this helper materialises an empty row if
    needed — same singleton ``id=1`` guarded by the table's
    CheckConstraint.
    """
    row = await db.get(InstanceSettings, 1)
    if row is None:
        row = InstanceSettings(id=1, client_control={}, setup_completed=False)
        db.add(row)
        await db.flush()
    return row


async def resolve_branding(db: AsyncSession) -> Branding:
    """Compute the merged branding view for this request."""
    row = await db.get(InstanceSettings, 1)

    def _pick(field: str, default_value):
        # DB → env → built-in
        db_val = getattr(row, field, None) if row is not None else None
        if db_val:
            return db_val
        env_val = _from_env(field)
        if env_val:
            return env_val
        return default_value

    instance_name = _pick("instance_name", _DEFAULTS["instance_name"])
    instance_tagline = _pick("instance_tagline", _DEFAULTS["instance_tagline"])
    primary_color = _pick("primary_color", _DEFAULTS["primary_color"])
    logo_url = _pick("logo_url", _DEFAULTS["logo_url"])
    favicon_url = _pick("favicon_url", _DEFAULTS["favicon_url"])
    support_email = _pick("support_email", _DEFAULTS["support_email"])
    instance_url = _pick("instance_url", _DEFAULTS["instance_url"])
    legal_entity = _pick("legal_entity", _DEFAULTS["legal_entity"])
    setup_completed = bool(getattr(row, "setup_completed", True)) if row else True

    # "Customized" = anything beyond defaults is set. We compare each
    # field to its built-in default to decide.
    customized = (
        instance_name != _DEFAULTS["instance_name"]
        or instance_tagline != _DEFAULTS["instance_tagline"]
        or primary_color != _DEFAULTS["primary_color"]
        or bool(logo_url)
        or bool(favicon_url)
        or bool(support_email)
        or bool(instance_url)
        or bool(legal_entity)
    )

    return Branding(
        instance_name=instance_name,
        instance_tagline=instance_tagline,
        logo_url=logo_url,
        favicon_url=favicon_url,
        primary_color=primary_color,
        support_email=support_email,
        instance_url=instance_url,
        legal_entity=legal_entity,
        setup_completed=setup_completed,
        customized=customized,
    )
