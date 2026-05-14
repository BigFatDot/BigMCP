"""Pydantic schemas for the instance/org client-control policy.

The same schema is used at all three layers (env defaults, instance row,
org override) so the PolicyResolver can compose them with a single algebra.

Composition rule (monotone decreasing in privileges):
- ``dcr_policy`` — take the strictest of (instance, org), order:
  ``open < admin_approval < denied``.
- ``require_cimd`` — OR (org cannot relax instance's True).
- ``trusted_cimd_urls`` — intersection (org can shrink but not grow).
- ``allowed_redirect_domains`` — intersection.
- ``auto_approve_cimd`` — AND (both must agree to auto-approve).
- ``notify_admins_on_new_client`` — OR (either side can require notice).
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

DcrPolicy = Literal["open", "admin_approval", "denied"]

# Used by the resolver to pick the strictest policy across layers.
_DCR_RANK = {"open": 0, "admin_approval": 1, "denied": 2}


class ClientControlPolicy(BaseModel):
    """Policy that governs how OAuth clients can register and connect.

    All fields are optional at the org-override layer (a missing value
    means "inherit from instance"). At the resolved layer every field is
    populated; PolicyResolver guarantees this contract.
    """

    enabled: bool = Field(
        default=False,
        description="If False, the policy is dormant and DCR remains fully open.",
    )

    dcr_policy: DcrPolicy = Field(
        default="open",
        description=(
            "How Dynamic Client Registration is treated. "
            "open=auto-approved, admin_approval=pending until instance admin "
            "approves, denied=DCR rejected outright."
        ),
    )

    require_cimd: bool = Field(
        default=False,
        description=(
            "If True, only clients presenting a valid Client ID Metadata "
            "Document (SEP-991) URL as client_id are accepted."
        ),
    )

    trusted_cimd_urls: List[str] = Field(
        default_factory=list,
        description=(
            "HTTPS URLs of CIMDs auto-approved on first registration. "
            "Empty list means 'no pre-trust; every CIMD goes through "
            "admin_approval or open per dcr_policy'."
        ),
    )

    allowed_redirect_domains: List[str] = Field(
        default_factory=list,
        description=(
            "Glob patterns (e.g. '*.example.com') of accepted redirect_uri "
            "host parts. Empty list means 'any domain accepted'."
        ),
    )

    auto_approve_cimd: bool = Field(
        default=True,
        description=(
            "When require_cimd=True and a CIMD is valid+trusted, skip "
            "the admin_approval gate."
        ),
    )

    notify_admins_on_new_client: bool = Field(
        default=True,
        description=(
            "Email instance admins (and org admins for org-scoped clients) "
            "whenever a new client is registered."
        ),
    )


def stricter_dcr(a: DcrPolicy, b: DcrPolicy) -> DcrPolicy:
    """Pick the stricter of two DCR policies."""
    return a if _DCR_RANK[a] >= _DCR_RANK[b] else b


def intersect_lists(instance: List[str], org: Optional[List[str]]) -> List[str]:
    """Intersect two whitelists. Org can shrink but never grow."""
    if not org:
        return list(instance)
    if not instance:
        # If instance has no whitelist, treat as "any" — org override wins.
        return list(org)
    instance_set = set(instance)
    return [x for x in org if x in instance_set]
