"""Instance branding endpoints.

Two surfaces:

- **GET /api/v1/instance/branding** — public. Returned at boot by the
  frontend to hydrate its ``BrandingContext``. Also used by the login
  page (before auth) so the brand applies everywhere.
- **PATCH /api/v1/admin/instance/branding** — instance admin only.
  Mutates the singleton row; partial updates ("send only the fields you
  want to change", empty string clears back to defaults).

A small sibling endpoint marks the setup wizard as complete so the
first-run redirect stops firing.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import require_instance_admin
from ...db.database import get_async_session
from ...models.user import User
from ...schemas.branding import (
    BrandingResponse,
    BrandingUpdate,
    SetupCompletionResponse,
)
from ...services.branding import get_or_create_settings, resolve_branding


logger = logging.getLogger(__name__)


# Public (no auth) — runs as bootstrap fetch on the login page.
public_router = APIRouter(prefix="/instance", tags=["Instance"])


@public_router.get(
    "/branding",
    response_model=BrandingResponse,
    summary="Public instance branding",
    description=(
        "Merged view of the instance branding (DB row → env vars → "
        "built-in defaults). The frontend hydrates BrandingContext "
        "with this at app boot — no auth required so the login page "
        "can show the right logo too."
    ),
)
async def get_branding(
    db: AsyncSession = Depends(get_async_session),
) -> BrandingResponse:
    branding = await resolve_branding(db)
    return BrandingResponse(**branding.to_dict())


# Admin (instance admin only) — wired alongside the existing /admin
# routes so the auth model stays consistent.
admin_router = APIRouter(prefix="/admin/instance", tags=["Instance Admin - Branding"])


@admin_router.patch(
    "/branding",
    response_model=BrandingResponse,
    summary="Update instance branding (instance admin)",
    description=(
        "Partial update. Only fields present in the payload are "
        "written; pass an empty string to clear a field back to the "
        "env-var / built-in fallback."
    ),
)
async def update_branding(
    payload: BrandingUpdate,
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_async_session),
) -> BrandingResponse:
    row = await get_or_create_settings(db)

    # Apply only the fields actually sent. Empty string means "clear"
    # (store NULL so the merge layer falls back to env/default).
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if isinstance(value, str) and value == "":
            setattr(row, field, None)
        else:
            setattr(row, field, value)

    row.updated_at = datetime.utcnow()
    row.updated_by_user_id = admin_user.id
    await db.commit()

    branding = await resolve_branding(db)
    logger.info(
        "Instance branding updated by %s — instance_name=%r customized=%s",
        admin_user.email,
        branding.instance_name,
        branding.customized,
    )
    return BrandingResponse(**branding.to_dict())


@admin_router.post(
    "/complete-setup",
    response_model=SetupCompletionResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark the first-run setup wizard as complete",
    description=(
        "Idempotent. Sets ``setup_completed = true`` on the singleton "
        "so the wizard redirect stops firing for the instance admin. "
        "Called by the wizard's final step."
    ),
)
async def complete_setup(
    admin_user: User = Depends(require_instance_admin),
    db: AsyncSession = Depends(get_async_session),
) -> SetupCompletionResponse:
    row = await get_or_create_settings(db)
    if not row.setup_completed:
        row.setup_completed = True
        row.updated_at = datetime.utcnow()
        row.updated_by_user_id = admin_user.id
        await db.commit()
        logger.info("Instance setup wizard marked complete by %s", admin_user.email)
    return SetupCompletionResponse(setup_completed=True)
