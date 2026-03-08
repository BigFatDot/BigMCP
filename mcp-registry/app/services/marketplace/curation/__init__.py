"""
Marketplace Curation - LLM-based server curation.

Handles:
- Static analysis of MCP server packages
- LLM-based metadata curation
- Credential detection and normalization

Extracted from marketplace_service.py for better modularity.
"""

from .prompts import (
    get_curation_system_prompt,
    build_curation_prompt,
)
from .credential_patterns import (
    CREDENTIAL_PATTERNS,
    CONFIG_PATTERNS,
    is_credential_variable,
    detect_credentials_from_env_vars,
    detect_credentials_from_cli_args,
    detect_all_credentials,
)

__all__ = [
    "get_curation_system_prompt",
    "build_curation_prompt",
    "CREDENTIAL_PATTERNS",
    "CONFIG_PATTERNS",
    "is_credential_variable",
    "detect_credentials_from_env_vars",
    "detect_credentials_from_cli_args",
    "detect_all_credentials",
]
