"""Schemas for the admin users-list / lifecycle API.

Public surface intentionally narrow: enough for the admin UI to draw a
table and trigger lifecycle actions, never enough to leak PII like
password hashes, MFA secrets or full preferences blobs.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AdminUserListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: Optional[str] = None
    status: str
    status_changed_at: Optional[datetime] = None
    status_reason: Optional[str] = None
    deleted_at: Optional[datetime] = None
    email_verified: bool
    last_login_at: Optional[datetime] = None
    tokens_revoked_at: Optional[datetime] = None
    is_instance_admin: bool = False
    created_at: datetime


class AdminUserListResponse(BaseModel):
    items: List[AdminUserListItem]
    total: int
    limit: int
    offset: int
