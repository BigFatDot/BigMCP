"""
Database-agnostic type definitions.

Provides types that work across different databases (PostgreSQL, SQLite).
"""

from sqlalchemy import JSON, String, TypeDecorator
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import CHAR
from uuid import UUID as PyUUID


class JSONType(TypeDecorator):
    """
    Database-agnostic JSON type.

    Uses JSONB for PostgreSQL and JSON for other databases (like SQLite).
    This allows tests to run with SQLite while production uses PostgreSQL.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        """Load dialect-specific implementation."""
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(postgresql.JSONB())
        else:
            return dialect.type_descriptor(JSON())


class UUIDType(TypeDecorator):
    """
    Database-agnostic UUID type.

    Uses PostgreSQL UUID for PostgreSQL and CHAR(36) for SQLite.
    Automatically converts between string and UUID objects.
    """

    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        """Load dialect-specific implementation."""
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(postgresql.UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        """Convert UUID to string for SQLite."""
        if value is None:
            return value
        if dialect.name == 'postgresql':
            return value
        else:
            # For SQLite, store as string
            if isinstance(value, PyUUID):
                return str(value)
            return value

    def process_result_value(self, value, dialect):
        """Convert string to UUID for SQLite."""
        if value is None:
            return value
        if dialect.name == 'postgresql':
            return value
        else:
            # For SQLite, convert string back to UUID
            if isinstance(value, str):
                return PyUUID(value)
            return value


class ArrayType(TypeDecorator):
    """
    Database-agnostic Array type for strings.

    Uses PostgreSQL ARRAY for PostgreSQL and JSON for SQLite.
    Always stores list of strings.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        """Load dialect-specific implementation."""
        if dialect.name == 'postgresql':
            from sqlalchemy import String
            return dialect.type_descriptor(postgresql.ARRAY(String))
        else:
            return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        """Convert list to appropriate format."""
        if value is None:
            return value
        if dialect.name == 'postgresql':
            return value
        else:
            # For SQLite, store as JSON
            return value if isinstance(value, list) else []

    def process_result_value(self, value, dialect):
        """Convert from storage format to list."""
        if value is None:
            return []
        if dialect.name == 'postgresql':
            return value if value is not None else []
        else:
            # For SQLite, parse JSON
            return value if isinstance(value, list) else []


# Aliases for convenience
JSON_TYPE = JSONType
UUID_TYPE = UUIDType
ARRAY_TYPE = ArrayType
