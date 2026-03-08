"""
Pytest configuration and fixtures for MCPHub tests.

Provides shared fixtures for database, client, and authentication.
"""

import asyncio
import pytest
import sys
from typing import AsyncGenerator, Generator
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool, StaticPool
from sqlalchemy import text, event

# Ensure UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Import app
from app.main import app
from app.db.base import Base
from app.db.database import get_async_session
from app.core.config import settings

# Import all models to ensure they're registered with Base.metadata
# This must happen before create_all() is called
from app.models.user import User
from app.models.organization import Organization, OrganizationMember
from app.models.api_key import APIKey
from app.models.mcp_server import MCPServer
from app.models.context import Context
from app.models.tool import Tool, ToolBinding
from app.models.tool_group import ToolGroup, ToolGroupItem
from app.models.user_credential import UserCredential, OrganizationCredential
from app.models.subscription import Subscription  # Cloud SaaS subscription


# Test database URL (use in-memory SQLite with StaticPool for shared connection)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """
    Create an event loop for the test session.

    Required for async tests to work properly.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_engine():
    """
    Create a test database engine for the entire test session.

    Uses in-memory SQLite with StaticPool to share the same connection
    across all tests. This ensures the in-memory database persists.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=StaticPool,  # StaticPool keeps a single connection for all tests
        connect_args={"check_same_thread": False}  # Required for SQLite
    )

    # Event listener to enable foreign keys for EVERY connection
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        """Enable foreign keys for SQLite connections."""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    # Create all tables once at session start
    async with engine.begin() as conn:
        # Create tables
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Clean up after all tests
    await engine.dispose()


@pytest.fixture(scope="function", autouse=True)
async def clean_db(db_engine):
    """
    Clean database between tests while keeping schema.

    This ensures test isolation without recreating the entire schema.
    """
    yield

    # After each test, truncate all tables
    async with db_engine.begin() as conn:
        # Disable foreign keys temporarily
        await conn.execute(text("PRAGMA foreign_keys = OFF"))

        # Delete all data from all tables in reverse order (respects FK constraints)
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f"DELETE FROM {table.name}"))

        # Re-enable foreign keys
        await conn.execute(text("PRAGMA foreign_keys = ON"))


@pytest.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create a test database session.

    Provides a fresh database session for each test.
    """
    async_session_maker = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Create a test HTTP client.

    Overrides the database dependency to use the test database.
    """
    from httpx import ASGITransport

    # Override database dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_async_session] = override_get_db

    # Use ASGITransport for httpx 0.25+
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Clear overrides
    app.dependency_overrides.clear()


@pytest.fixture
async def test_user(client: AsyncClient) -> dict:
    """
    Create a test user and return authentication data.

    Returns:
        dict: {
            "email": str,
            "password": str,
            "access_token": str,
            "refresh_token": str,
            "user": dict
        }
    """
    # Register user
    register_data = {
        "email": "testuser@example.com",
        "password": "SecurePass123",
        "name": "Test User"
    }

    response = await client.post("/api/v1/auth/register", json=register_data)
    assert response.status_code == 201
    user_data = response.json()

    # Login to get tokens
    login_data = {
        "email": register_data["email"],
        "password": register_data["password"]
    }

    response = await client.post("/api/v1/auth/login", json=login_data)
    assert response.status_code == 200
    token_data = response.json()

    return {
        "email": register_data["email"],
        "password": register_data["password"],
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "user": user_data
    }


@pytest.fixture
async def auth_headers(test_user: dict) -> dict:
    """
    Get authorization headers with JWT token.

    Returns:
        dict: {"Authorization": "Bearer <token>"}
    """
    return {"Authorization": f"Bearer {test_user['access_token']}"}


@pytest.fixture
async def test_api_key(client: AsyncClient, auth_headers: dict) -> dict:
    """
    Create a test API key.

    Returns:
        dict: {
            "id": str,
            "secret": str,  # Full API key
            "key_prefix": str,
            "name": str,
            "scopes": list
        }
    """
    api_key_data = {
        "name": "Test API Key",
        "scopes": ["tools:read", "tools:execute"],
        "description": "API key for automated tests"
    }

    response = await client.post(
        "/api/v1/api-keys",
        json=api_key_data,
        headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()

    return {
        "id": data["api_key"]["id"],
        "secret": data["secret"],
        "key_prefix": data["api_key"]["key_prefix"],
        "name": data["api_key"]["name"],
        "scopes": data["api_key"]["scopes"]
    }


@pytest.fixture
async def api_key_headers(test_api_key: dict) -> dict:
    """
    Get authorization headers with API key.

    Returns:
        dict: {"Authorization": "Bearer mcphub_sk_xxx"}
    """
    return {"Authorization": f"Bearer {test_api_key['secret']}"}
