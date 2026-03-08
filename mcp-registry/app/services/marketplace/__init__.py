"""
Marketplace Module - MCP Server Discovery and Sync.

This module is being incrementally refactored from a monolithic
marketplace_service.py (212KB) into smaller, focused modules.

Current structure (partial migration):
- models.py: Enums and dataclasses (extracted)
- known_credentials.py: Service credential templates (extracted)
- sources/base.py: MarketplaceSource ABC (extracted)
- sources/: Concrete sources (planned)
- curation/: LLM curation (planned)
- service.py: Main orchestrator (planned)

IMPORTANT: Imports from marketplace_service.py are done lazily to avoid
circular imports. Use getter functions or import from submodules directly.
"""

# Import from new modular structure (no circular dependency)
from .models import (
    InstallationType,
    ServerSource,
    CredentialSpec,
    MarketplaceServer,
)
from .known_credentials import KNOWN_SERVICE_CREDENTIALS


def get_marketplace_service():
    """Lazy import to avoid circular dependency."""
    from ..marketplace_service import get_marketplace_service as _get
    return _get()


def get_marketplace_sync_service_class():
    """Lazy import to avoid circular dependency."""
    from ..marketplace_service import MarketplaceSyncService
    return MarketplaceSyncService


__all__ = [
    # From models.py (extracted)
    "InstallationType",
    "ServerSource",
    "CredentialSpec",
    "MarketplaceServer",
    # From known_credentials.py (extracted)
    "KNOWN_SERVICE_CREDENTIALS",
    # Lazy accessors
    "get_marketplace_service",
    "get_marketplace_sync_service_class",
]
