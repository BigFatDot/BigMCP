"""
Public Sector Program Service.

Manages domain verification for free Enterprise licenses
to government, education, and healthcare organizations.
"""

import logging
from typing import Optional, List
from datetime import datetime

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.public_sector import (
    PublicDomainWhitelist,
    PublicSectorCategory,
    INITIAL_WHITELIST
)

logger = logging.getLogger(__name__)


class PublicSectorService:
    """Service for Public Sector Program domain verification."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def is_domain_whitelisted(self, email: str) -> bool:
        """
        Check if an email domain is in the public sector whitelist.

        Supports both exact match and parent domain matching:
        - "paris.fr" → exact match
        - "dsi.paris.fr" → matches parent "paris.fr"
        - "education.gouv.fr" → matches parent "gouv.fr"
        - "user@mail.gov" → matches TLD "gov"

        Args:
            email: User's email address

        Returns:
            True if domain is whitelisted, False otherwise
        """
        if not email or "@" not in email:
            return False

        domain = email.split("@")[1].lower()
        parts = domain.split(".")

        # Build list of domains to check (exact + all parent domains)
        domains_to_check = []

        # Exact domain match
        domains_to_check.append(domain)

        # Parent domain matches (e.g., "dsi.paris.fr" → ["paris.fr", "fr"])
        for i in range(len(parts) - 1):
            parent = ".".join(parts[i + 1:])
            domains_to_check.append(parent)

        # Check against whitelist
        result = await self.db.execute(
            select(PublicDomainWhitelist)
            .where(PublicDomainWhitelist.domain.in_(domains_to_check))
            .where(PublicDomainWhitelist.is_active == True)
            .limit(1)
        )
        match = result.scalar_one_or_none()

        if match:
            logger.info(
                f"Public sector match: {email} → {match.domain} "
                f"({match.organization_name})"
            )
            return True

        return False

    async def get_domain_info(self, email: str) -> Optional[PublicDomainWhitelist]:
        """
        Get whitelist entry for an email domain.

        Args:
            email: User's email address

        Returns:
            PublicDomainWhitelist entry if found, None otherwise
        """
        if not email or "@" not in email:
            return None

        domain = email.split("@")[1].lower()
        parts = domain.split(".")

        domains_to_check = [domain]
        for i in range(len(parts) - 1):
            parent = ".".join(parts[i + 1:])
            domains_to_check.append(parent)

        result = await self.db.execute(
            select(PublicDomainWhitelist)
            .where(PublicDomainWhitelist.domain.in_(domains_to_check))
            .where(PublicDomainWhitelist.is_active == True)
            .order_by(PublicDomainWhitelist.domain.desc())  # Prefer most specific match
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def add_domain(
        self,
        domain: str,
        organization_name: str,
        country: str,
        category: PublicSectorCategory,
        added_by: str,
        notes: Optional[str] = None
    ) -> PublicDomainWhitelist:
        """
        Add a domain to the whitelist.

        Args:
            domain: Domain to whitelist (e.g., "paris.fr")
            organization_name: Name of the organization
            country: ISO 3166-1 alpha-2 country code
            category: Public sector category
            added_by: Email of admin adding the entry
            notes: Optional notes

        Returns:
            Created PublicDomainWhitelist entry

        Raises:
            ValueError: If domain already exists
        """
        # Check if already exists
        existing = await self.db.execute(
            select(PublicDomainWhitelist)
            .where(PublicDomainWhitelist.domain == domain.lower())
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Domain {domain} already in whitelist")

        entry = PublicDomainWhitelist(
            domain=domain.lower(),
            organization_name=organization_name,
            country=country.upper(),
            category=category,
            added_by=added_by,
            verified_at=datetime.utcnow(),
            notes=notes,
            is_active=True
        )

        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)

        logger.info(
            f"Added to whitelist: {domain} ({organization_name}) by {added_by}"
        )

        return entry

    async def remove_domain(self, domain: str) -> bool:
        """
        Deactivate a domain from the whitelist.

        Soft delete - sets is_active=False for audit trail.

        Args:
            domain: Domain to remove

        Returns:
            True if domain was found and deactivated, False otherwise
        """
        result = await self.db.execute(
            select(PublicDomainWhitelist)
            .where(PublicDomainWhitelist.domain == domain.lower())
        )
        entry = result.scalar_one_or_none()

        if not entry:
            return False

        entry.is_active = False
        await self.db.commit()

        logger.info(f"Deactivated from whitelist: {domain}")
        return True

    async def list_domains(
        self,
        country: Optional[str] = None,
        category: Optional[PublicSectorCategory] = None,
        active_only: bool = True
    ) -> List[PublicDomainWhitelist]:
        """
        List whitelisted domains with optional filtering.

        Args:
            country: Filter by country code
            category: Filter by category
            active_only: Only return active entries

        Returns:
            List of matching whitelist entries
        """
        query = select(PublicDomainWhitelist)

        if active_only:
            query = query.where(PublicDomainWhitelist.is_active == True)

        if country:
            query = query.where(PublicDomainWhitelist.country == country.upper())

        if category:
            query = query.where(PublicDomainWhitelist.category == category)

        query = query.order_by(
            PublicDomainWhitelist.country,
            PublicDomainWhitelist.domain
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def seed_initial_whitelist(self, added_by: str = "system@bigmcp.cloud") -> int:
        """
        Seed the whitelist with initial public sector domains.

        Idempotent - skips domains that already exist.

        Args:
            added_by: Email to record as the adder

        Returns:
            Number of domains added
        """
        added_count = 0

        for entry_data in INITIAL_WHITELIST:
            # Check if already exists
            existing = await self.db.execute(
                select(PublicDomainWhitelist)
                .where(PublicDomainWhitelist.domain == entry_data["domain"].lower())
            )
            if existing.scalar_one_or_none():
                continue

            entry = PublicDomainWhitelist(
                domain=entry_data["domain"].lower(),
                organization_name=entry_data["organization_name"],
                country=entry_data["country"],
                category=entry_data["category"],
                added_by=added_by,
                verified_at=datetime.utcnow(),
                is_active=True
            )
            self.db.add(entry)
            added_count += 1

        if added_count > 0:
            await self.db.commit()
            logger.info(f"Seeded {added_count} domains to public sector whitelist")

        return added_count


# Convenience function for quick checks
async def is_public_sector_email(db: AsyncSession, email: str) -> bool:
    """
    Quick check if an email is from a public sector domain.

    Args:
        db: Database session
        email: Email to check

    Returns:
        True if email domain is whitelisted
    """
    service = PublicSectorService(db)
    return await service.is_domain_whitelisted(email)
