"""
Tool and ToolBinding models.

Tools are discovered from MCP servers and can be bound to contexts
with pre-filled parameters for simplified usage.
"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import String, Text, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin, TimestampMixin
from ..db.types import JSONType, ArrayType


class Tool(Base, UUIDMixin, TimestampMixin):
    """
    Tool discovered from an MCP server.

    Each tool:
    - Belongs to an MCP server
    - Has a schema (parameters, returns)
    - Can be bound to contexts with pre-filled parameters
    - Has metadata for search and discovery
    """

    __tablename__ = "tools"

    # Server relationship
    server_id: Mapped[UUID] = mapped_column(
        ForeignKey("mcp_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Tool identification
    tool_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Original tool name from MCP server"
    )
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Schema (JSON Schema format)
    parameters_schema: Mapped[dict] = mapped_column(
        JSONType,
        nullable=False,
        comment="JSON Schema for parameters"
    )
    returns_schema: Mapped[Optional[dict]] = mapped_column(
        JSONType,
        nullable=True,
        comment="JSON Schema for return value"
    )

    # Metadata for discovery
    tags: Mapped[Optional[List[str]]] = mapped_column(
        ArrayType,
        nullable=True
    )
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Renamed to meta to avoid SQLAlchemy reserved keyword
    meta: Mapped[dict] = mapped_column(JSONType, default={}, nullable=False)
    is_visible_to_oauth_clients: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="If False, tool is hidden from OAuth clients but available via API keys"
    )

    # Vector embedding for semantic search
    # Note: Using JSONB for now, can migrate to pgvector later
    embedding: Mapped[Optional[dict]] = mapped_column(
        JSONType,
        nullable=True,
        comment="Vector embedding for semantic search"
    )

    # Relationships
    server: Mapped["MCPServer"] = relationship(
        "MCPServer",
        back_populates="tools"
    )

    tool_bindings: Mapped[List["ToolBinding"]] = relationship(
        "ToolBinding",
        back_populates="tool",
        cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("server_id", "tool_name", name="uq_server_tool"),
    )

    def __repr__(self) -> str:
        return f"<Tool(id={self.id}, name={self.tool_name}, server={self.server_id})>"

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "server_id": str(self.server_id),
            "organization_id": str(self.organization_id),
            "tool_name": self.tool_name,
            "display_name": self.display_name,
            "description": self.description,
            "parameters_schema": self.parameters_schema,
            "returns_schema": self.returns_schema,
            "tags": self.tags,
            "category": self.category,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


class ToolBinding(Base, UUIDMixin, TimestampMixin):
    """
    Context-specific tool configuration with pre-filled parameters.

    Tool bindings simplify tool usage by:
    - Pre-filling common parameters (API keys, base URLs, etc.)
    - Locking sensitive parameters (preventing user override)
    - Creating context-specific tool variants

    Example:
        Tool: create_document(base_url, project_id, title, content)

        Binding in "project_x" context:
        - base_url: "https://docs.colaig.fr" (locked)
        - project_id: "project-x-uuid" (locked)
        - title: (user provides)
        - content: (user provides)

        User calls: create_doc(title="Meeting Notes", content="...")
        Executed as: create_document(
            base_url="https://docs.colaig.fr",
            project_id="project-x-uuid",
            title="Meeting Notes",
            content="..."
        )
    """

    __tablename__ = "tool_bindings"

    # Relationships
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    context_id: Mapped[UUID] = mapped_column(
        ForeignKey("contexts.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    tool_id: Mapped[UUID] = mapped_column(
        ForeignKey("tools.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Binding configuration
    binding_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="User-friendly name for this binding"
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Parameter configuration
    default_parameters: Mapped[dict] = mapped_column(
        JSONType,
        default={},
        nullable=False,
        comment="Pre-filled parameters merged with user params"
    )
    locked_parameters: Mapped[List[str]] = mapped_column(
        ArrayType,
        default=[],
        nullable=False,
        comment="Parameters that cannot be overridden by user"
    )

    # Validation
    custom_validation: Mapped[Optional[dict]] = mapped_column(
        JSONType,
        nullable=True,
        comment="Additional validation rules"
    )

    # Metadata
    created_by: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    context: Mapped["Context"] = relationship(
        "Context",
        back_populates="tool_bindings"
    )

    tool: Mapped["Tool"] = relationship(
        "Tool",
        back_populates="tool_bindings"
    )

    creator: Mapped[Optional["User"]] = relationship("User")

    # Constraints
    __table_args__ = (
        UniqueConstraint("context_id", "binding_name", name="uq_context_binding"),
    )

    def __repr__(self) -> str:
        return f"<ToolBinding(id={self.id}, name={self.binding_name}, context={self.context_id})>"

    def merge_parameters(self, user_parameters: dict) -> dict:
        """
        Merge default parameters with user parameters.

        Args:
            user_parameters: Parameters provided by user

        Returns:
            Merged parameters dict

        Raises:
            ValueError: If user tries to override locked parameters
        """
        # Check for locked parameter violations
        for locked_param in self.locked_parameters:
            if locked_param in user_parameters:
                raise ValueError(
                    f"Parameter '{locked_param}' is locked and cannot be overridden"
                )

        # Merge: default_parameters as base, user_parameters override
        merged = {**self.default_parameters, **user_parameters}

        return merged

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "context_id": str(self.context_id),
            "tool_id": str(self.tool_id),
            "binding_name": self.binding_name,
            "description": self.description,
            "default_parameters": self.default_parameters,
            "locked_parameters": self.locked_parameters,
            "custom_validation": self.custom_validation,
            "created_by": str(self.created_by) if self.created_by else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
