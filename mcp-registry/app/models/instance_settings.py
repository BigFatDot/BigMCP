"""InstanceSettings model — singleton storage for instance-wide configuration.

This is the first instance-scoped configuration table in BigMCP. It is a
true singleton (enforced by ``CheckConstraint(id = 1)``) intended to hold
JSON blobs of policy that the instance admin (DSI) can mutate at runtime
without redeploying.

For Phase 1 of the access-control roadmap (N1.1), only ``client_control``
is stored. Future N1.x phases (audit retention, kill-switch defaults,
suspend reasons) will add columns here rather than spawning new singletons.

Composition with org-level overrides happens in
``app/services/policy_resolver.py`` — never read this table directly from
business code; always go through ``PolicyResolver`` so that the monotone
``instance ⋂ org`` contract is preserved.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base
from ..db.types import JSONType


class InstanceSettings(Base):
    """Singleton row holding instance-wide configuration.

    Always referenced by ``id = 1``. The ``CheckConstraint`` ensures no
    second row can ever exist; readers should fetch with
    ``db.get(InstanceSettings, 1)``.
    """

    __tablename__ = "instance_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # Client-control policy — see schemas/policy.py for the structure.
    # An empty dict means "use env-var defaults"; PolicyResolver layers
    # env-var defaults under whatever is stored here.
    client_control: Mapped[Dict[str, Any]] = mapped_column(
        JSONType, nullable=False, default=dict
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    updated_by_user_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_instance_settings_singleton"),
    )
