"""
Row-Level Security (RLS) Context Manager.

Provides utilities for setting PostgreSQL session context variables
that control RLS policy evaluation.

Usage:
    async with set_rls_context(db, organization_id):
        # All queries within this block are RLS-scoped
        results = await db.execute(query)

    # Or as a dependency injection:
    @router.get("/servers")
    async def list_servers(
        db: AsyncSession = Depends(get_db_with_rls)
    ):
        # db session already has RLS context set
        ...
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def set_organization_context(
    db: AsyncSession,
    organization_id: Optional[UUID]
) -> None:
    """
    Set the current organization context for RLS policies.

    This sets the PostgreSQL session variable that RLS policies use
    to filter rows by organization.

    Args:
        db: Database session
        organization_id: Organization UUID to scope queries to

    Note:
        Uses SET LOCAL which is transaction-scoped, so it automatically
        resets when the transaction ends.
    """
    if organization_id:
        # SET LOCAL is transaction-scoped (auto-resets on commit/rollback)
        org_id_str = str(organization_id)
        # Validate UUID format to prevent injection (defensive)
        try:
            UUID(org_id_str)  # Raises if not valid UUID
        except ValueError:
            logger.error(f"Invalid UUID format for RLS context: {org_id_str}")
            return

        # Use set_config() with bind parameters instead of f-string SET LOCAL
        # This prevents SQL injection even if UUID validation is bypassed
        # Third param `true` = LOCAL (transaction-scoped, same as SET LOCAL)
        await db.execute(
            text("SELECT set_config('app.current_organization_id', :org_id, true)"),
            {"org_id": org_id_str}
        )
        logger.debug(f"RLS context set to organization: {organization_id}")
    else:
        # Clear the context (queries will see no rows due to RLS)
        await db.execute(
            text("SELECT set_config('app.current_organization_id', '', true)")
        )
        logger.debug("RLS context cleared")


async def enable_rls_bypass(db: AsyncSession) -> None:
    """
    Enable RLS bypass for admin operations.

    Use this sparingly and only for legitimate admin operations
    like migrations, cross-org reports, or system maintenance.

    Args:
        db: Database session

    Warning:
        This bypasses ALL RLS policies. Use with caution.
    """
    await db.execute(text("SELECT set_config('app.rls_bypass', 'true', true)"))
    logger.warning("RLS bypass enabled - use with caution")


async def disable_rls_bypass(db: AsyncSession) -> None:
    """
    Disable RLS bypass (restore normal RLS behavior).

    Args:
        db: Database session
    """
    await db.execute(text("SELECT set_config('app.rls_bypass', 'false', true)"))
    logger.debug("RLS bypass disabled")


@asynccontextmanager
async def rls_context(
    db: AsyncSession,
    organization_id: Optional[UUID]
) -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for RLS-scoped database operations.

    Sets the organization context at the start and ensures cleanup
    on exit (though SET LOCAL auto-clears on transaction end anyway).

    Args:
        db: Database session
        organization_id: Organization to scope to

    Yields:
        Database session with RLS context set

    Example:
        async with rls_context(db, org_id) as scoped_db:
            servers = await scoped_db.execute(select(MCPServer))
            # Only returns servers for org_id due to RLS
    """
    await set_organization_context(db, organization_id)
    try:
        yield db
    finally:
        # SET LOCAL auto-clears on transaction end, but be explicit
        pass


@asynccontextmanager
async def rls_bypass_context(db: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for bypassing RLS policies.

    Use this for legitimate admin operations that need to see all data.

    Args:
        db: Database session

    Yields:
        Database session with RLS bypass enabled

    Example:
        # Admin cross-org report
        async with rls_bypass_context(db) as admin_db:
            all_servers = await admin_db.execute(select(MCPServer))
    """
    await enable_rls_bypass(db)
    try:
        yield db
    finally:
        await disable_rls_bypass(db)


def is_postgresql(db: AsyncSession) -> bool:
    """
    Check if the database is PostgreSQL.

    RLS features are PostgreSQL-specific. SQLite (used in tests)
    doesn't support RLS, so these operations become no-ops.

    Args:
        db: Database session

    Returns:
        True if PostgreSQL, False otherwise
    """
    dialect_name = db.bind.dialect.name if db.bind else "unknown"
    return dialect_name == "postgresql"


async def set_organization_context_safe(
    db: AsyncSession,
    organization_id: Optional[UUID]
) -> None:
    """
    Safely set organization context, handling non-PostgreSQL databases.

    This is a no-op for SQLite (used in tests).

    Args:
        db: Database session
        organization_id: Organization UUID
    """
    # Check dialect - SQLite doesn't support SET LOCAL
    try:
        if is_postgresql(db):
            await set_organization_context(db, organization_id)
            logger.debug(f"RLS context set successfully for org: {organization_id}")
    except Exception as e:
        # Log at WARNING level so we can see what's happening
        logger.warning(f"RLS context setup failed: {e}", exc_info=True)
        # Don't re-raise - application-level security is the primary layer
