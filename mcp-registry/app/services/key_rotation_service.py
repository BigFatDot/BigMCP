"""
Key Rotation Service - Migrate credentials to new encryption key.

Provides automated key rotation for credentials stored in the database.
Supports batch processing with progress tracking and rollback capability.

Process:
1. Set up new key version in environment (ENCRYPTION_KEY_V{N})
2. Update ENCRYPTION_KEY to point to the new key
3. Run migration to re-encrypt all credentials
4. Verify migration success
5. Optionally remove old key versions

Usage:
    # From CLI
    python -m app.cli.rotate_keys migrate --dry-run
    python -m app.cli.rotate_keys migrate
    python -m app.cli.rotate_keys status

    # From API (admin endpoint)
    GET /api/v1/admin/encryption-status
    POST /api/v1/admin/rotate-keys

Security:
    - Only instance admins can trigger rotation
    - All operations are logged for audit
    - Supports dry-run mode for validation
    - Atomic batch commits for consistency
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user_credential import UserCredential, OrganizationCredential
from ..core.secrets_manager import get_secrets_manager, VERSION_PREFIX_PATTERN

logger = logging.getLogger(__name__)


@dataclass
class RotationStats:
    """Statistics for a rotation operation."""
    table_name: str
    total: int = 0
    migrated: int = 0
    already_current: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)


@dataclass
class RotationReport:
    """Complete report of a rotation operation."""
    started_at: datetime
    completed_at: Optional[datetime] = None
    dry_run: bool = False
    from_versions: List[int] = field(default_factory=list)
    to_version: int = 0
    user_credentials: RotationStats = field(default_factory=lambda: RotationStats("user_credentials"))
    org_credentials: RotationStats = field(default_factory=lambda: RotationStats("organization_credentials"))
    success: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "dry_run": self.dry_run,
            "from_versions": self.from_versions,
            "to_version": self.to_version,
            "user_credentials": {
                "total": self.user_credentials.total,
                "migrated": self.user_credentials.migrated,
                "already_current": self.user_credentials.already_current,
                "failed": self.user_credentials.failed,
                "errors": self.user_credentials.errors[:10]  # Limit error list
            },
            "org_credentials": {
                "total": self.org_credentials.total,
                "migrated": self.org_credentials.migrated,
                "already_current": self.org_credentials.already_current,
                "failed": self.org_credentials.failed,
                "errors": self.org_credentials.errors[:10]
            },
            "success": self.success,
            "error": self.error
        }


@dataclass
class EncryptionStatus:
    """Current encryption status of the system."""
    current_version: int
    available_versions: List[int]
    is_dev_mode: bool
    user_credentials_by_version: Dict[int, int]
    org_credentials_by_version: Dict[int, int]
    total_credentials: int
    credentials_needing_rotation: int

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "current_version": self.current_version,
            "available_versions": self.available_versions,
            "is_dev_mode": self.is_dev_mode,
            "user_credentials_by_version": self.user_credentials_by_version,
            "org_credentials_by_version": self.org_credentials_by_version,
            "total_credentials": self.total_credentials,
            "credentials_needing_rotation": self.credentials_needing_rotation,
            "rotation_recommended": self.credentials_needing_rotation > 0
        }


class KeyRotationService:
    """
    Service for rotating encryption keys and migrating credentials.

    Key rotation is essential for:
    - Security best practices (periodic rotation)
    - Incident response (compromised key)
    - Compliance requirements (key lifecycle)

    Example:
        service = KeyRotationService(db)

        # Check current status
        status = await service.get_encryption_status()
        print(f"Current version: {status.current_version}")
        print(f"Needs rotation: {status.credentials_needing_rotation}")

        # Perform rotation
        report = await service.rotate_all_credentials(dry_run=True)
        if report.success:
            report = await service.rotate_all_credentials(dry_run=False)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.secrets = get_secrets_manager()

    async def get_encryption_status(self) -> EncryptionStatus:
        """
        Get current encryption status and credential version distribution.

        Returns:
            EncryptionStatus with version info and credential counts
        """
        user_by_version: Dict[int, int] = {}
        org_by_version: Dict[int, int] = {}

        # Count user credentials by version
        user_creds = await self.db.execute(select(UserCredential.credentials_encrypted))
        for row in user_creds.scalars().all():
            if row:
                version = self._extract_version(row)
                user_by_version[version] = user_by_version.get(version, 0) + 1

        # Count organization credentials by version
        org_creds = await self.db.execute(select(OrganizationCredential.credentials_encrypted))
        for row in org_creds.scalars().all():
            if row:
                version = self._extract_version(row)
                org_by_version[version] = org_by_version.get(version, 0) + 1

        current_version = self.secrets.current_version
        total = sum(user_by_version.values()) + sum(org_by_version.values())

        # Count credentials needing rotation (not on current version)
        needs_rotation = 0
        for version, count in user_by_version.items():
            if version < current_version:
                needs_rotation += count
        for version, count in org_by_version.items():
            if version < current_version:
                needs_rotation += count

        return EncryptionStatus(
            current_version=current_version,
            available_versions=self.secrets.available_versions,
            is_dev_mode=self.secrets.is_dev_mode,
            user_credentials_by_version=user_by_version,
            org_credentials_by_version=org_by_version,
            total_credentials=total,
            credentials_needing_rotation=needs_rotation
        )

    def _extract_version(self, encrypted_data: str) -> int:
        """Extract version number from encrypted data."""
        match = VERSION_PREFIX_PATTERN.match(encrypted_data)
        if match:
            return int(match.group(1))
        return 1  # Legacy format = v1

    async def rotate_all_credentials(
        self,
        batch_size: int = 100,
        dry_run: bool = False
    ) -> RotationReport:
        """
        Re-encrypt all credentials with the current (latest) key version.

        Args:
            batch_size: Number of credentials to process per batch
            dry_run: If True, simulate rotation without making changes

        Returns:
            RotationReport with detailed statistics
        """
        report = RotationReport(
            started_at=datetime.utcnow(),
            dry_run=dry_run,
            to_version=self.secrets.current_version
        )

        # Collect versions that will be migrated
        status = await self.get_encryption_status()
        report.from_versions = [
            v for v in status.available_versions
            if v < self.secrets.current_version
        ]

        try:
            # Migrate user credentials
            await self._migrate_table(
                UserCredential,
                report.user_credentials,
                batch_size,
                dry_run
            )

            # Migrate organization credentials
            await self._migrate_table(
                OrganizationCredential,
                report.org_credentials,
                batch_size,
                dry_run
            )

            report.success = True

        except Exception as e:
            logger.error(f"Key rotation failed: {e}")
            report.error = str(e)
            report.success = False

        report.completed_at = datetime.utcnow()
        return report

    async def _migrate_table(
        self,
        model,
        stats: RotationStats,
        batch_size: int,
        dry_run: bool
    ) -> None:
        """Migrate all credentials in a table."""
        offset = 0
        current_version = self.secrets.current_version

        while True:
            # Fetch batch
            query = select(model).offset(offset).limit(batch_size)
            result = await self.db.execute(query)
            credentials = result.scalars().all()

            if not credentials:
                break

            stats.total += len(credentials)
            batch_migrated = 0

            for cred in credentials:
                try:
                    encrypted = cred.credentials_encrypted
                    if not encrypted:
                        continue

                    version = self._extract_version(encrypted)

                    if version >= current_version:
                        # Already on current or newer version
                        stats.already_current += 1
                        continue

                    if not dry_run:
                        # Re-encrypt with current version
                        new_encrypted = self.secrets.re_encrypt(encrypted)
                        cred.credentials_encrypted = new_encrypted

                    stats.migrated += 1
                    batch_migrated += 1

                except Exception as e:
                    error_msg = f"Failed to migrate {model.__tablename__} {cred.id}: {e}"
                    logger.error(error_msg)
                    stats.errors.append(error_msg)
                    stats.failed += 1

            if not dry_run and batch_migrated > 0:
                await self.db.commit()

            logger.info(
                f"[{model.__tablename__}] Progress: {stats.migrated + stats.already_current + stats.failed}/{stats.total} "
                f"(migrated: {stats.migrated}, current: {stats.already_current}, failed: {stats.failed})"
            )

            offset += batch_size

    async def rotate_single_credential(
        self,
        credential_id: UUID,
        credential_type: str = "user"
    ) -> bool:
        """
        Rotate a single credential to the current key version.

        Args:
            credential_id: ID of the credential to rotate
            credential_type: "user" or "organization"

        Returns:
            True if rotation was successful
        """
        model = UserCredential if credential_type == "user" else OrganizationCredential

        cred = await self.db.get(model, credential_id)
        if not cred:
            raise ValueError(f"Credential {credential_id} not found")

        if not cred.credentials_encrypted:
            return True  # Nothing to rotate

        version = self._extract_version(cred.credentials_encrypted)
        if version >= self.secrets.current_version:
            return True  # Already current

        try:
            new_encrypted = self.secrets.re_encrypt(cred.credentials_encrypted)
            cred.credentials_encrypted = new_encrypted
            await self.db.commit()

            logger.info(f"Rotated {credential_type} credential {credential_id} from v{version} to v{self.secrets.current_version}")
            return True

        except Exception as e:
            logger.error(f"Failed to rotate credential {credential_id}: {e}")
            await self.db.rollback()
            raise


# Dependency injection helper
async def get_key_rotation_service(db: AsyncSession) -> KeyRotationService:
    """Get KeyRotationService instance with database session."""
    return KeyRotationService(db)
