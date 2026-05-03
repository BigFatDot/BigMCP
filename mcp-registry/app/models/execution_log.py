"""ExecutionLog model.

Audit trail of `execute` MCP tool calls. Each row is written asynchronously
(fire-and-forget) and is intended for debugging, cost tracking, and tuning
of the shortcut heuristics. Rows older than 30 days are pruned by a
periodic job.
"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, UUIDMixin, TimestampMixin
from ..db.types import JSONType, ArrayType


class ExecutionLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "execution_log"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    goal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    shortcut_level: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    llm_calls_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    plan: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    step_results: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    composition_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("compositions.id", ondelete="SET NULL"), nullable=True
    )
    tools_called: Mapped[Optional[List[str]]] = mapped_column(ArrayType, nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_execution_log_user_created", "user_id", "created_at"),
        Index("ix_execution_log_org_created", "organization_id", "created_at"),
    )
