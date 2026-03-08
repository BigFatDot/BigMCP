"""
Composition Store
=================

Storage and management of workflow compositions.
Supports in-memory storage with TTL and disk persistence.
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("orchestration.composition_store")


@dataclass
class CompositionInfo:
    """Complete representation of a workflow composition."""

    # Identity
    id: str
    name: str
    description: str

    # Multi-tenancy (required for database sync)
    organization_id: Optional[str] = None
    created_by: Optional[str] = None
    visibility: str = "private"  # private | organization | public

    # Workflow
    steps: List[Dict[str, Any]] = field(default_factory=list)
    data_mappings: List[Dict[str, Any]] = field(default_factory=list)

    # Schemas
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Optional[Dict[str, Any]] = None

    # Server Bindings (Maps server_id → server_uuid)
    # Example: {"notion": "abc-123-uuid", "grist-mcp": "def-456-uuid"}
    # This allows the composition to know which specific server instances to use
    server_bindings: Dict[str, str] = field(default_factory=dict)

    # IAM & Delegation (Identity Delegation / Service Account Mode)
    force_org_credentials: bool = False
    """
    If True, ignores user credentials and uses ONLY organization credentials.

    Use Case: Service Account Mode
    - Admin configures org credentials
    - Users execute without seeing keys
    - Instant revocation via RBAC

    Example:
        Composition "Refund Customer" uses Stripe org key configured by admin.
        Support agents can execute it without knowing the Stripe API key.
    """

    allowed_roles: List[str] = field(default_factory=list)
    """
    Roles authorized to execute this composition (empty = all roles).

    Possible values: ["owner", "admin", "member", "viewer"]

    Example:
        ["admin", "member"] → Only admins and members can execute
        [] → All roles can execute (default)

    Note: "viewer" role is typically excluded from execution by default
    """

    requires_approval: bool = False
    """
    If True, execution requires prior approval (Phase 2 feature).

    For now, this field is informational only.
    Future: Trigger approval workflow before execution.
    """

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Status
    status: str = "temporary"  # temporary | validated | production
    ttl: Optional[int] = None  # Time-to-live in seconds

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompositionInfo":
        """Create from dictionary."""
        return cls(**data)


class CompositionStore:
    """
    Storage and management of compositions.

    Features:
    - In-memory storage with TTL for temporary compositions
    - Disk persistence for validated compositions
    - Auto-expiration of temporary compositions
    - Usage statistics
    """

    def __init__(self, storage_dir: str = "/app/compositions"):
        """
        Initialize the store.

        Args:
            storage_dir: Directory for persistence
        """
        self.storage_dir = Path(storage_dir)
        self.temporary: Dict[str, CompositionInfo] = {}
        self.permanent: Dict[str, CompositionInfo] = {}
        self.ttl_tasks: Dict[str, asyncio.Task] = {}
        self._loaded = False  # Flag to track if compositions were loaded from disk

        # Create directories
        self._ensure_directories()

        # Note: _load_from_disk() will be called lazily on first access
        # to avoid RuntimeError when no event loop is running

    def _ensure_directories(self):
        """Create the directory structure."""
        (self.storage_dir / "temporary").mkdir(parents=True, exist_ok=True)
        (self.storage_dir / "validated").mkdir(parents=True, exist_ok=True)
        (self.storage_dir / "production").mkdir(parents=True, exist_ok=True)

    async def _ensure_loaded(self):
        """Ensure compositions are loaded from disk (lazy loading)."""
        if not self._loaded:
            await self._load_from_disk()
            self._loaded = True

    async def save_temporary(
        self,
        composition: CompositionInfo,
        ttl: int = 3600
    ) -> str:
        """
        Save a temporary composition with TTL.

        Args:
            composition: Composition to save
            ttl: Time-to-live in seconds (default: 1 hour)

        Returns:
            Composition ID
        """
        composition.status = "temporary"
        composition.ttl = ttl
        composition.created_at = datetime.now().isoformat()
        composition.updated_at = datetime.now().isoformat()

        self.temporary[composition.id] = composition

        # Schedule expiration
        if composition.id in self.ttl_tasks:
            self.ttl_tasks[composition.id].cancel()

        self.ttl_tasks[composition.id] = asyncio.create_task(
            self._expire_after(composition.id, ttl)
        )

        logger.info(f"📦 Temporary composition saved: {composition.id} (TTL: {ttl}s)")

        return composition.id

    async def save_permanent(self, composition: CompositionInfo) -> str:
        """
        Save a permanent composition.

        Args:
            composition: Composition to save

        Returns:
            Composition ID
        """
        composition.ttl = None
        composition.updated_at = datetime.now().isoformat()

        self.permanent[composition.id] = composition

        # Persist to disk
        await self._persist_to_disk(composition)

        logger.info(f"💾 Permanent composition saved: {composition.id}")

        return composition.id

    async def get(self, composition_id: str) -> Optional[CompositionInfo]:
        """
        Retrieve a composition by ID.

        Args:
            composition_id: Composition ID

        Returns:
            Composition or None if not found
        """
        # Search first in temporary
        if composition_id in self.temporary:
            return self.temporary[composition_id]

        # Then in permanent
        if composition_id in self.permanent:
            return self.permanent[composition_id]

        return None

    async def list_all(
        self,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[CompositionInfo]:
        """
        List all compositions.

        Args:
            status: Filter by status (optional)
            tags: Filter by tags (optional)

        Returns:
            List of compositions
        """
        # Ensure compositions are loaded from disk
        await self._ensure_loaded()

        compositions = list(self.temporary.values()) + list(self.permanent.values())

        # Filter by status
        if status:
            compositions = [c for c in compositions if c.status == status]

        # Filter by tags
        if tags:
            compositions = [
                c for c in compositions
                if any(tag in c.metadata.get("tags", []) for tag in tags)
            ]

        return compositions

    async def delete(self, composition_id: str) -> bool:
        """
        Delete a composition.

        Args:
            composition_id: Composition ID

        Returns:
            True if deleted, False otherwise
        """
        # Delete from memory
        deleted = False

        if composition_id in self.temporary:
            del self.temporary[composition_id]
            deleted = True

            # Cancel the TTL
            if composition_id in self.ttl_tasks:
                self.ttl_tasks[composition_id].cancel()
                del self.ttl_tasks[composition_id]

        if composition_id in self.permanent:
            comp = self.permanent[composition_id]
            del self.permanent[composition_id]
            deleted = True

            # Delete from disk
            await self._delete_from_disk(comp)

        if deleted:
            logger.info(f"🗑️  Composition deleted: {composition_id}")

        return deleted

    async def promote_to_permanent(
        self,
        composition_id: str,
        new_status: str = "validated"
    ) -> Optional[CompositionInfo]:
        """
        Promote a temporary composition to permanent.

        Args:
            composition_id: Composition ID
            new_status: New status (validated or production)

        Returns:
            Promoted composition or None
        """
        comp = self.temporary.pop(composition_id, None)
        if not comp:
            logger.warning(f"Temporary composition not found: {composition_id}")
            return None

        # Cancel expiration
        if composition_id in self.ttl_tasks:
            self.ttl_tasks[composition_id].cancel()
            del self.ttl_tasks[composition_id]

        # Change status
        comp.status = new_status
        comp.ttl = None
        comp.updated_at = datetime.now().isoformat()

        # Save as permanent
        await self.save_permanent(comp)

        logger.info(f"⬆️  Composition promoted to {new_status}: {composition_id}")

        return comp

    async def update_stats(
        self,
        composition_id: str,
        execution_result: Dict[str, Any]
    ):
        """
        Update composition statistics.

        Args:
            composition_id: Composition ID
            execution_result: Execution result
        """
        comp = await self.get(composition_id)
        if not comp:
            return

        # Initialize stats if necessary
        if "execution_count" not in comp.metadata:
            comp.metadata["execution_count"] = 0
            comp.metadata["successes"] = 0
            comp.metadata["failures"] = 0
            comp.metadata["total_duration_ms"] = 0

        # Update
        comp.metadata["execution_count"] += 1

        if execution_result.get("status") == "success":
            comp.metadata["successes"] += 1
        else:
            comp.metadata["failures"] += 1

        # Calculate success rate
        comp.metadata["success_rate"] = (
            comp.metadata["successes"] / comp.metadata["execution_count"]
        )

        # Average duration
        duration = execution_result.get("total_duration_ms", 0)
        comp.metadata["total_duration_ms"] += duration
        comp.metadata["avg_duration_ms"] = (
            comp.metadata["total_duration_ms"] / comp.metadata["execution_count"]
        )

        # Last execution
        comp.metadata["last_executed_at"] = datetime.now().isoformat()

        comp.updated_at = datetime.now().isoformat()

        # Persist if permanent composition
        if composition_id in self.permanent:
            await self._persist_to_disk(comp)

        logger.debug(f"📊 Stats updated for {composition_id}")

    async def _expire_after(self, composition_id: str, ttl: int):
        """Expire a composition after the TTL."""
        try:
            await asyncio.sleep(ttl)

            if composition_id in self.temporary:
                del self.temporary[composition_id]
                logger.info(f"⏰ Composition expired: {composition_id}")

            if composition_id in self.ttl_tasks:
                del self.ttl_tasks[composition_id]

        except asyncio.CancelledError:
            # TTL cancelled (promotion or deletion)
            pass

    async def _persist_to_disk(self, composition: CompositionInfo):
        """Persist a composition to disk."""
        try:
            # Determine subdirectory
            subdir = composition.status  # validated or production
            file_path = self.storage_dir / subdir / f"{composition.id}.json"

            # Save
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(composition.to_dict(), f, indent=2, ensure_ascii=False)

            logger.debug(f"💾 Composition persisted: {file_path}")

        except Exception as e:
            logger.error(f"Error persisting {composition.id}: {e}")

    async def _delete_from_disk(self, composition: CompositionInfo):
        """Delete a composition from disk."""
        try:
            file_path = self.storage_dir / composition.status / f"{composition.id}.json"
            if file_path.exists():
                file_path.unlink()
                logger.debug(f"🗑️  Composition deleted from disk: {file_path}")

        except Exception as e:
            logger.error(f"Error deleting {composition.id}: {e}")

    async def _load_from_disk(self):
        """Load persistent compositions from disk."""
        try:
            for subdir in ["validated", "production"]:
                dir_path = self.storage_dir / subdir

                if not dir_path.exists():
                    continue

                for file_path in dir_path.glob("*.json"):
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            data = json.load(f)

                        composition = CompositionInfo.from_dict(data)
                        self.permanent[composition.id] = composition

                        logger.debug(f"📂 Composition loaded: {composition.id}")

                    except Exception as e:
                        logger.error(f"Error loading {file_path}: {e}")

            logger.info(f"✅ {len(self.permanent)} compositions loaded from disk")

        except Exception as e:
            logger.error(f"Error loading compositions: {e}")


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_composition_store_instance: Optional[CompositionStore] = None


def get_composition_store() -> CompositionStore:
    """
    Return the singleton instance of CompositionStore.

    Guarantees that only one instance exists in the entire application,
    allowing state sharing in memory between all modules.
    """
    global _composition_store_instance

    if _composition_store_instance is None:
        _composition_store_instance = CompositionStore()
        logger.info("🔧 CompositionStore singleton instance created")

    return _composition_store_instance
