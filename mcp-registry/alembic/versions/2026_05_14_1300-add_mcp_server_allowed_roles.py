"""add_mcp_server_allowed_roles

Revision ID: add_mcp_allowed_roles
Revises: align_api_keys_revoke
Create Date: 2026-05-14 13:00

Generalises the Composition.allowed_roles pattern (N1) to MCPServer
(N2.3 of the access-control roadmap). Lets org admins restrict which
roles can use a sensitive server at runtime — e.g. an admin-only
"customer-data" MCP server even though MEMBERs can see other servers
in the same org.

Empty list = inherit default behaviour (everyone except VIEWER).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_mcp_allowed_roles"
down_revision: Union[str, None] = "align_api_keys_revoke"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mcp_servers",
        sa.Column(
            "allowed_roles",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar[]"),
        ),
    )


def downgrade() -> None:
    op.drop_column("mcp_servers", "allowed_roles")
