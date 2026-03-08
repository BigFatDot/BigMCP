"""
Database connection and session management.

Provides async SQLAlchemy engine, sessionmaker, and dependency injection.
"""

import os
import logging
from typing import AsyncGenerator

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine
)
from sqlalchemy.pool import NullPool
from sqlalchemy import event, text

logger = logging.getLogger(__name__)

# Database URL from environment variable
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://mcphub:mcphub_dev_password@localhost:5432/mcphub"
)

# Determine if we're using PostgreSQL (pool parameters not supported by SQLite)
is_postgresql = "postgresql" in DATABASE_URL

# Build engine kwargs based on database type
engine_kwargs = {
    "echo": os.environ.get("SQL_ECHO", "false").lower() == "true",
}

# Add PostgreSQL-specific pooling parameters
if is_postgresql:
    engine_kwargs.update({
        "pool_pre_ping": True,  # Verify connections before using them
        "pool_size": 5,  # Connection pool size
        "max_overflow": 10,  # Max connections beyond pool_size (total: 15 max)
        "pool_recycle": 300,  # Recycle connections after 5 minutes (prevents stale TCP)
        "pool_timeout": 30,  # Wait max 30s for a connection from pool
        "connect_args": {
            "timeout": 10,  # Connection establishment timeout (seconds)
            "command_timeout": 30,  # Default query timeout (seconds)
            "server_settings": {
                "tcp_keepalives_idle": "300",  # Start keepalive after 5min idle
                "tcp_keepalives_interval": "10",  # Probe every 10s
                "tcp_keepalives_count": "5",  # 5 failed probes = dead
            },
        },
    })
else:
    # SQLite uses NullPool for better compatibility
    engine_kwargs["poolclass"] = NullPool

# Create async engine
engine: AsyncEngine = create_async_engine(DATABASE_URL, **engine_kwargs)

# Create async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Don't expire objects after commit
    autocommit=False,
    autoflush=False
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for async database sessions.

    Yields an async session and ensures it's properly closed.

    Usage:
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_async_session)):
            result = await db.execute(select(User))
            return result.scalars().all()
    """
    async with async_session_maker() as session:
        try:
            yield session
        except HTTPException:
            # HTTP exceptions (401, 403, etc.) are normal control flow, not DB errors
            raise
        except Exception as e:
            logger.error(f"Database session error: {e}", exc_info=True)
            await session.rollback()
            raise
        finally:
            await session.close()


# Alias for backwards compatibility
get_db = get_async_session


async def init_db():
    """
    Initialize database.

    - Creates all tables defined in Base metadata
    - Runs migrations if needed
    - Sets up extensions (ltree, uuid-ossp)

    Note: In production, use Alembic migrations instead of create_all()
    """
    from .base import Base

    logger.info("Initializing database...")

    try:
        async with engine.begin() as conn:
            # Enable extensions (only for PostgreSQL)
            # SQLite doesn't support extensions like ltree and uuid-ossp
            if "postgresql" in str(engine.url):
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS ltree"))
                await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
                logger.info("PostgreSQL extensions enabled")

            # Create all tables
            # WARNING: In production, use Alembic migrations instead
            await conn.run_sync(Base.metadata.create_all)

        logger.info("Database initialized successfully")

    except Exception as e:
        logger.error(f"Error initializing database: {e}", exc_info=True)
        raise


async def close_db():
    """
    Close database connections.

    Should be called on application shutdown.
    """
    logger.info("Closing database connections...")
    await engine.dispose()
    logger.info("Database connections closed")


# Event listeners for debugging and monitoring
@event.listens_for(engine.sync_engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    """Log new database connections."""
    logger.debug("New database connection established")


@event.listens_for(engine.sync_engine, "close")
def receive_close(dbapi_conn, connection_record):
    """Log database connection closures."""
    logger.debug("Database connection closed")
