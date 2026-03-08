"""
Icon Resolver - Dynamic icon resolution service with validation.

Extracted from marketplace_service.py for better modularity.

NO hardcoded mappings - uses LLM-provided search terms.
Tests each term against CDNs in reliability order.
Keeps the first working URL found.

CDN priority (by reliability):
1. SimpleIcons CDN (largest icon database, most reliable)
2. LobeHub CDN (AI/tech brands)
3. Avatar fallback (always works)
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class IconResolver:
    """
    Dynamic icon resolution service with validation.

    NO hardcoded mappings - uses LLM-provided search terms.
    Tests each term against CDNs in reliability order.
    Keeps the first working URL found.

    CDN priority (by reliability):
    1. SimpleIcons CDN (largest icon database, most reliable)
    2. LobeHub CDN (AI/tech brands)
    3. Avatar fallback (always works)
    """

    # CDN base URLs ordered by reliability
    SIMPLEICONS_CDN = "https://cdn.simpleicons.org"
    LOBEHUB_CDN = "https://unpkg.com/@lobehub/icons-static-svg@latest/icons"
    AVATAR_FALLBACK = "https://ui-avatars.com/api"

    # Cache for validated icons: term -> (working_url, cdn_source) or None
    _validation_cache: Dict[str, Optional[tuple]] = {}

    @classmethod
    def resolve(cls, icon_hint: str, service_name: str = "") -> str:
        """
        Resolve icon URL for a service (simple, no validation).

        Args:
            icon_hint: LLM-suggested icon name
            service_name: Display name for fallback avatar

        Returns:
            Primary icon URL (frontend handles 404 fallback)
        """
        if not icon_hint:
            return cls.get_fallback_avatar(service_name or "MCP")

        hint = icon_hint.lower().strip().replace(" ", "").replace("-", "").replace("_", "")
        return f"{cls.SIMPLEICONS_CDN}/{hint}"

    @classmethod
    def get_icon_urls(cls, icon_hint: str, service_name: str = "") -> Dict[str, str]:
        """
        Get multiple icon URL options for frontend fallback chain.
        """
        hint = (icon_hint or "").lower().strip().replace(" ", "").replace("-", "").replace("_", "")

        return {
            "primary": f"{cls.SIMPLEICONS_CDN}/{hint}" if hint else None,
            "secondary": f"{cls.LOBEHUB_CDN}/{hint}.svg" if hint else None,
            "fallback": cls.get_fallback_avatar(service_name or icon_hint or "MCP")
        }

    @classmethod
    async def resolve_validated(
        cls,
        search_terms: List[str],
        service_name: str = "",
        http_client: Optional[httpx.AsyncClient] = None
    ) -> Dict[str, Any]:
        """
        Resolve icon by testing multiple LLM-provided search terms against CDNs.

        Tests each term on SimpleIcons first, then LobeHub.
        Returns the first working URL found.

        Args:
            search_terms: List of icon slugs to try (LLM provides these)
                         e.g., ["postgresql", "postgres", "pg"]
            service_name: Display name for fallback avatar
            http_client: HTTP client for validation (required)

        Returns:
            Dict with validated icon URLs
        """
        fallback = cls.get_fallback_avatar(service_name or "MCP")

        if not search_terms:
            return {
                "primary": None,
                "secondary": None,
                "fallback": fallback,
                "validated": False,
                "matched_term": None
            }

        # Normalize terms (preserve order from LLM - first is best guess)
        candidates = []
        seen = set()
        for term in search_terms:
            normalized = term.lower().strip().replace(" ", "").replace("-", "").replace("_", "")
            if normalized and normalized not in seen:
                candidates.append(normalized)
                seen.add(normalized)

        if not candidates:
            return {
                "primary": None,
                "secondary": None,
                "fallback": fallback,
                "validated": False,
                "matched_term": None
            }

        # Test SimpleIcons first (most reliable CDN)
        for term in candidates:
            cache_key = f"si_{term}"

            # Check cache
            if cache_key in cls._validation_cache:
                cached = cls._validation_cache[cache_key]
                if cached:
                    return {
                        "primary": cached[0],
                        "secondary": f"{cls.LOBEHUB_CDN}/{term}.svg",
                        "fallback": fallback,
                        "validated": True,
                        "matched_term": term,
                        "source": "simpleicons"
                    }
                continue  # Skip known invalid

            # Validate with HTTP HEAD
            if http_client:
                url = f"{cls.SIMPLEICONS_CDN}/{term}"
                try:
                    response = await http_client.head(url, timeout=5.0)
                    if response.status_code == 200:
                        cls._validation_cache[cache_key] = (url, "simpleicons")
                        logger.info(f"Icon validated: {term} -> {url}")
                        return {
                            "primary": url,
                            "secondary": f"{cls.LOBEHUB_CDN}/{term}.svg",
                            "fallback": fallback,
                            "validated": True,
                            "matched_term": term,
                            "source": "simpleicons"
                        }
                    else:
                        cls._validation_cache[cache_key] = None
                except Exception:
                    cls._validation_cache[cache_key] = None

        # Try LobeHub as fallback CDN
        for term in candidates:
            cache_key = f"lh_{term}"

            if cache_key in cls._validation_cache:
                cached = cls._validation_cache[cache_key]
                if cached:
                    return {
                        "primary": cached[0],
                        "secondary": None,
                        "fallback": fallback,
                        "validated": True,
                        "matched_term": term,
                        "source": "lobehub"
                    }
                continue

            if http_client:
                url = f"{cls.LOBEHUB_CDN}/{term}.svg"
                try:
                    response = await http_client.head(url, timeout=5.0)
                    if response.status_code == 200:
                        cls._validation_cache[cache_key] = (url, "lobehub")
                        logger.info(f"Icon validated (LobeHub): {term} -> {url}")
                        return {
                            "primary": url,
                            "secondary": None,
                            "fallback": fallback,
                            "validated": True,
                            "matched_term": term,
                            "source": "lobehub"
                        }
                    else:
                        cls._validation_cache[cache_key] = None
                except Exception:
                    cls._validation_cache[cache_key] = None

        # No valid icon found - return first term as best guess
        best = candidates[0]
        logger.warning(f"No valid icon found for terms: {candidates}")
        return {
            "primary": f"{cls.SIMPLEICONS_CDN}/{best}",
            "secondary": f"{cls.LOBEHUB_CDN}/{best}.svg",
            "fallback": fallback,
            "validated": False,
            "matched_term": None
        }

    @classmethod
    def get_fallback_avatar(cls, name: str, size: int = 64) -> str:
        """Generate fallback avatar URL using UI Avatars service."""
        if not name:
            name = "MCP"
        words = name.split()
        if len(words) >= 2:
            initials = (words[0][0] + words[1][0]).upper()
        else:
            initials = name[:2].upper()

        return f"{cls.AVATAR_FALLBACK}/?name={initials}&size={size}&background=random&color=fff&bold=true"


def generate_icon_search_terms(
    server_name: str,
    install_package: str,
    service_id: Optional[str] = None
) -> List[str]:
    """
    Generate multiple icon search terms to try against SimpleIcons CDN.

    Returns terms sorted by likelihood to match (shorter/simpler first).
    SimpleIcons uses simple slugs like "youtube", "xero", "tailscale".

    Examples:
        - graphlit-mcp-server -> ["graphlit"]
        - @hubspot/mcp-server -> ["hubspot"]
        - @hexsleeves/tailscale-mcp-server -> ["tailscale"]
        - @xeroapi/xero-mcp-server -> ["xero", "xeroapi"]
        - youtube-data-mcp-server -> ["youtube", "youtubedata"]
    """
    candidates = set()

    def add_candidate(term: str):
        """Add normalized term to candidates."""
        normalized = term.lower().strip().replace(" ", "").replace("-", "").replace("_", "")
        normalized = re.sub(r'[^a-z0-9]', '', normalized)
        if normalized and len(normalized) > 1 and normalized not in ['mcp', 'server', 'mcpserver']:
            candidates.add(normalized)

    # Explicit service_id is always a strong candidate
    if service_id:
        add_candidate(service_id)

    # Extract from package name
    package_lower = install_package.lower() if install_package else ""

    # Handle npm scope (e.g., @hubspot/mcp-server)
    scope_match = re.match(r"@([^/]+)/(.+)", package_lower)
    scope_name = None
    if scope_match:
        scope_name = scope_match.group(1)
        package_base = scope_match.group(2)
        # Skip generic scopes
        excluded_scopes = {'modelcontextprotocol', 'anthropic', 'negokaz', 'arabold',
                          'anthropics', 'anthropic-ai', 'hexsleeves'}
        if scope_name not in excluded_scopes:
            add_candidate(scope_name)
    else:
        package_base = package_lower

    # Clean package base: remove common suffixes
    cleaned_pkg = package_base
    for suffix in ['-mcp-server', '-mcp', '-server', 'mcp-server', '-client']:
        if cleaned_pkg.endswith(suffix):
            cleaned_pkg = cleaned_pkg[:-len(suffix)]
            break

    # Remove common prefixes
    for prefix in ['mcp-', 'server-']:
        if cleaned_pkg.startswith(prefix):
            cleaned_pkg = cleaned_pkg[len(prefix):]
            break

    # Add cleaned package name
    if cleaned_pkg:
        add_candidate(cleaned_pkg)
        # Also add first segment (e.g., "youtube" from "youtube-data")
        first_segment = cleaned_pkg.split('-')[0] if '-' in cleaned_pkg else None
        if first_segment and len(first_segment) > 2:
            add_candidate(first_segment)

    # Server name variations
    if server_name:
        # First word is often the brand (e.g., "YouTube Data" -> "youtube")
        first_word = server_name.split()[0].lower() if server_name.split() else ""
        if first_word and len(first_word) > 2:
            add_candidate(first_word)
        # Full name concatenated (e.g., "YouTube Data" -> "youtubedata")
        add_candidate(server_name)

    # Sort by length (shorter = more likely to be a valid SimpleIcons slug)
    sorted_terms = sorted(candidates, key=len)

    return sorted_terms[:3] if sorted_terms else ["mcp"]


def resolve_icon_url(
    server_name: str,
    install_package: str,
    service_id: Optional[str] = None
) -> Optional[str]:
    """
    Resolve icon URL for a server based on its name or package.

    Uses IconResolver with the best generated search term.

    Args:
        server_name: Display name of the server
        install_package: Package name (npm/pip)
        service_id: Explicit service identifier (highest priority, matches SimpleIcons slugs)
    """
    terms = generate_icon_search_terms(server_name, install_package, service_id)
    # Use the first (best) term
    best_term = terms[0] if terms else "mcp"
    return IconResolver.resolve(best_term, server_name)
