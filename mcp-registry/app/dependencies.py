"""
Shared dependencies for the MCP Registry application.

This module provides a single, shared instance of MCPRegistry
to prevent multiple instances from being created across different modules.
"""

import logging
from .core.registry import MCPRegistry

logger = logging.getLogger(__name__)

# Single, shared instance of MCPRegistry
# This instance will be initialized once at application startup
# and shared across all routers and modules
_registry_instance = None


def get_registry() -> MCPRegistry:
    """
    Get the shared MCPRegistry instance.

    Returns:
        The shared MCPRegistry instance

    Raises:
        RuntimeError: If the registry has not been initialized
    """
    global _registry_instance

    if _registry_instance is None:
        # Create the instance if it doesn't exist
        logger.info("Creating shared MCPRegistry instance")
        _registry_instance = MCPRegistry()

    return _registry_instance


def reset_registry():
    """
    Reset the registry instance (mainly for testing purposes).
    """
    global _registry_instance
    _registry_instance = None
