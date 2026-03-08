"""
SQLAlchemy declarative base and common model mixins.

All database models should inherit from Base.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, func
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .types import UUIDType


class Base(DeclarativeBase):
    """
    Base class for all database models.

    Provides common functionality for all tables.
    """

    # Generate __tablename__ automatically from class name
    @declared_attr.directive
    def __tablename__(cls) -> str:
        # Convert CamelCase to snake_case
        import re
        name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', cls.__name__)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()


class TimestampMixin:
    """
    Mixin for created_at and updated_at timestamps.

    Automatically manages creation and update times.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )


class UUIDMixin:
    """
    Mixin for UUID primary keys.

    Uses database-agnostic UUID type with automatic generation.
    """

    id: Mapped[UUID] = mapped_column(
        UUIDType,
        primary_key=True,
        default=uuid4,
        nullable=False
    )


# Import all models here to ensure they're registered with Base.metadata
# This is required for create_all() and Alembic migrations to work

# Import all models
from ..models.organization import Organization, OrganizationMember  # noqa: F401
from ..models.user import User  # noqa: F401
from ..models.mcp_server import MCPServer  # noqa: F401
from ..models.context import Context  # noqa: F401
from ..models.tool import Tool, ToolBinding  # noqa: F401
from ..models.user_credential import UserCredential, OrganizationCredential  # noqa: F401
from ..models.api_key import APIKey  # noqa: F401
from ..models.tool_group import ToolGroup, ToolGroupItem  # noqa: F401
from ..models.license import License, LicenseValidation  # noqa: F401
from ..models.subscription import Subscription  # noqa: F401
from ..models.token_blacklist import TokenBlacklist  # noqa: F401
from ..models.invitation import Invitation  # noqa: F401
