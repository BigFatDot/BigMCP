"""Pydantic schemas for the audit-log read API.

Never expose ``signature`` in API responses — that field is meant for
server-side integrity verification and leaking it would help an attacker
forge signed payloads.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    timestamp: datetime
    actor_id: Optional[UUID] = None
    organization_id: Optional[UUID] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    # Optional resolved labels added by the read API to save the UI a
    # second round-trip (user.email, composition.name, …). Always
    # populated by the list endpoint; absent in stored rows.
    actor_email: Optional[str] = None
    resource_label: Optional[str] = None


class AuditLogListResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int
    limit: int
    offset: int
