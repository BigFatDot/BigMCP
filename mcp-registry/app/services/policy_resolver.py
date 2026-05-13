"""PolicyResolver — composes instance, org and env-default policies.

There are three layers, ordered by precedence (lower wins for stricter
fields):

1. Env-var defaults  — set at boot from ``Settings`` (lowest authority).
2. Instance row      — ``instance_settings.client_control`` (DSI control).
3. Org override      — ``organizations.settings["client_control"]`` (chef
                       d'équipe local tightening).

Org can only ever **shrink** what the instance allows. PolicyResolver
enforces this so business code never has to think about the algebra.

Invariant: ``resolve_effective_policy()`` always returns a fully populated
``ClientControlPolicy`` — no None fields, no missing keys.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models.instance_settings import InstanceSettings
from ..models.organization import Organization
from ..schemas.policy import (
    ClientControlPolicy,
    intersect_lists,
    stricter_dcr,
)


class PolicyResolver:
    """Single entry point for "what is the effective policy for org X?".

    The resolver is stateless — instantiate it with the current
    ``AsyncSession`` and call ``resolve_effective_policy()``. Repeated
    calls within a request hit the DB twice (instance + org); add a
    request-scoped cache only if profiling shows it matters.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----- raw layers ------------------------------------------------------

    @staticmethod
    def env_defaults() -> ClientControlPolicy:
        """Boot-time defaults sourced from settings. Lowest authority.

        Reads:
        - ``DEFAULT_DCR_POLICY`` (open/admin_approval/denied)
        - ``GLOBAL_TRUSTED_CIMD_URLS`` (comma-separated, optional)
        - ``ENFORCE_CLIENT_PROVENANCE`` (bool — flips ``enabled``)
        """
        dcr = getattr(settings, "DEFAULT_DCR_POLICY", "open") or "open"
        if dcr not in ("open", "admin_approval", "denied"):
            dcr = "open"

        trusted_urls_raw = getattr(settings, "GLOBAL_TRUSTED_CIMD_URLS", "") or ""
        trusted = [u.strip() for u in trusted_urls_raw.split(",") if u.strip()]

        enabled = bool(getattr(settings, "ENFORCE_CLIENT_PROVENANCE", False))

        return ClientControlPolicy(
            enabled=enabled,
            dcr_policy=dcr,
            require_cimd=False,
            trusted_cimd_urls=trusted,
            allowed_redirect_domains=[],
            auto_approve_cimd=True,
            notify_admins_on_new_client=True,
        )

    async def get_instance_policy(self) -> ClientControlPolicy:
        """Return the instance-level policy.

        Layers stored fields over env defaults; any field absent from the
        stored JSON falls back to its env default.
        """
        defaults = self.env_defaults()
        row = await self.db.get(InstanceSettings, 1)
        if row is None or not row.client_control:
            return defaults

        merged = defaults.model_dump()
        merged.update(row.client_control)
        return ClientControlPolicy(**merged)

    async def get_org_policy(
        self, organization_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Return the org override (raw dict) or None if no override."""
        org = await self.db.get(Organization, organization_id)
        if org is None or not org.settings:
            return None
        return org.settings.get("client_control")

    # ----- composition -----------------------------------------------------

    async def resolve_effective_policy(
        self, organization_id: Optional[UUID]
    ) -> ClientControlPolicy:
        """Compose instance and org policies into the effective one.

        If ``organization_id`` is None (e.g. instance-wide context), the
        instance policy is returned unchanged.
        """
        instance = await self.get_instance_policy()
        if organization_id is None:
            return instance

        override_raw = await self.get_org_policy(organization_id)
        if not override_raw:
            return instance

        # Build the override as a partial policy — keys absent from the
        # JSON simply mean "inherit from instance".
        return self._compose(instance, override_raw)

    @staticmethod
    def _compose(
        instance: ClientControlPolicy, org_override: Dict[str, Any]
    ) -> ClientControlPolicy:
        """Apply the monotone-decreasing composition rules.

        Org can only shrink: stricter dcr_policy, OR-strict booleans
        (True from either side stays True), intersected whitelists.
        """
        composed = instance.model_copy(deep=True)

        # enabled: OR (if either layer enables, it's enabled)
        if "enabled" in org_override:
            composed.enabled = bool(instance.enabled or org_override["enabled"])

        # dcr_policy: take the stricter of the two
        if "dcr_policy" in org_override:
            composed.dcr_policy = stricter_dcr(
                instance.dcr_policy, org_override["dcr_policy"]
            )

        # require_cimd: OR — org cannot turn off instance's requirement
        if "require_cimd" in org_override:
            composed.require_cimd = bool(
                instance.require_cimd or org_override["require_cimd"]
            )

        # trusted_cimd_urls: intersection — org can shrink but never grow
        if "trusted_cimd_urls" in org_override:
            composed.trusted_cimd_urls = intersect_lists(
                instance.trusted_cimd_urls, org_override.get("trusted_cimd_urls")
            )

        # allowed_redirect_domains: intersection
        if "allowed_redirect_domains" in org_override:
            composed.allowed_redirect_domains = intersect_lists(
                instance.allowed_redirect_domains,
                org_override.get("allowed_redirect_domains"),
            )

        # auto_approve_cimd: AND — both must agree to auto-approve
        if "auto_approve_cimd" in org_override:
            composed.auto_approve_cimd = bool(
                instance.auto_approve_cimd and org_override["auto_approve_cimd"]
            )

        # notify_admins_on_new_client: OR — either can require notice
        if "notify_admins_on_new_client" in org_override:
            composed.notify_admins_on_new_client = bool(
                instance.notify_admins_on_new_client
                or org_override["notify_admins_on_new_client"]
            )

        return composed


def get_policy_resolver(db: AsyncSession) -> PolicyResolver:
    """FastAPI dependency factory."""
    return PolicyResolver(db)
