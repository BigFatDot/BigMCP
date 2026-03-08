"""
PII Detection and Sanitization for RGPD Compliance.

Automatically detects and masks:
- Email addresses
- French phone numbers (mobile and landline)
- French social security numbers (INSEE)
- Credit card numbers (PCI-DSS)
- IPv4 addresses

Integrates with MCPHub's logging and audit system.
"""

import re
import logging
from typing import Any, Dict, List, Union, Set

logger = logging.getLogger(__name__)


class PIIDetector:
    """
    Detects and masks Personal Identifiable Information (PII) per RGPD.

    Used throughout MCPHub to:
    - Sanitize logs before writing
    - Clean audit trail details
    - Protect tool outputs from leaking PII

    Compliant with:
    - RGPD Article 25 (Privacy by Design)
    - RGPD Article 32 (Security of Processing)
    """

    # Compiled regex patterns for performance
    PATTERNS = {
        'email': re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        ),
        'phone_fr': re.compile(
            # Matches: 06 12 34 56 78, +33 6 12 34 56 78, 0033612345678, etc.
            r'(?:(?:\+|00)33|0)\s*[1-9](?:[\s.-]*\d{2}){4}'
        ),
        'credit_card': re.compile(
            # Basic credit card pattern (13-16 digits with optional spaces/dashes)
            r'\b(?:\d[ -]*?){13,16}\b'
        ),
        'insee': re.compile(
            # French social security number: 1 89 05 75 123 456 78
            r'\b[12]\s?\d{2}\s?(?:0[1-9]|1[0-2])\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b'
        ),
        'ipv4': re.compile(
            r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        )
    }

    # Redaction masks
    REDACTION_MASKS = {
        'email': '[EMAIL_MASKED]',
        'phone_fr': '[PHONE_MASKED]',
        'credit_card': '[CARD_MASKED]',
        'insee': '[INSEE_MASKED]',
        'ipv4': '[IP_MASKED]'
    }

    # Sensitive key patterns (case-insensitive)
    # These keys in dictionaries will have their values automatically redacted
    SENSITIVE_KEYS = {
        'password', 'secret', 'token', 'key', 'auth', 'credential',
        'api_key', 'api_secret', 'access_token', 'refresh_token',
        'private_key', 'jwt', 'bearer', 'authorization'
    }

    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """
        Clean a raw text string by masking all detected PII.

        Args:
            text: Raw text that may contain PII

        Returns:
            Sanitized text with PII masked

        Example:
            >>> PIIDetector.sanitize_text("Contact: john@example.com")
            'Contact: [EMAIL_MASKED]'
        """
        if not text or not isinstance(text, str):
            return text

        sanitized = text

        # Apply each pattern sequentially
        for pii_type, pattern in cls.PATTERNS.items():
            sanitized = pattern.sub(cls.REDACTION_MASKS[pii_type], sanitized)

        return sanitized

    @classmethod
    def sanitize_structure(cls, data: Union[Dict, List, str, int, float, bool, None]) -> Any:
        """
        Recursively clean a data structure (JSON/Dict/List).

        This is the main entry point for sanitizing complex objects
        before logging or storing in audit trails.

        Args:
            data: Any data structure (dict, list, primitive)

        Returns:
            Sanitized copy of the data structure

        Example:
            >>> data = {"email": "john@example.com", "phone": "0612345678"}
            >>> PIIDetector.sanitize_structure(data)
            {'email': '[EMAIL_MASKED]', 'phone': '[PHONE_MASKED]'}
        """
        # Handle None and booleans
        if data is None or isinstance(data, bool):
            return data

        # Handle numbers
        if isinstance(data, (int, float)):
            return data

        # Handle strings
        if isinstance(data, str):
            return cls.sanitize_text(data)

        # Handle lists
        if isinstance(data, list):
            return [cls.sanitize_structure(item) for item in data]

        # Handle dictionaries
        if isinstance(data, dict):
            sanitized_dict = {}

            for key, value in data.items():
                # Check if key suggests sensitive data
                if cls._is_sensitive_key(key):
                    sanitized_dict[key] = "***REDACTED***"
                else:
                    sanitized_dict[key] = cls.sanitize_structure(value)

            return sanitized_dict

        # Unknown type: convert to string and sanitize
        try:
            return cls.sanitize_text(str(data))
        except Exception as e:
            logger.warning(f"Failed to sanitize unknown type {type(data)}: {e}")
            return "[SANITIZATION_ERROR]"

    @classmethod
    def _is_sensitive_key(cls, key: str) -> bool:
        """
        Check if a dictionary key indicates sensitive data.

        Args:
            key: Dictionary key to check

        Returns:
            True if key suggests sensitive data
        """
        if not isinstance(key, str):
            return False

        key_lower = key.lower()
        return any(sensitive in key_lower for sensitive in cls.SENSITIVE_KEYS)

    @classmethod
    def detect_pii_types(cls, text: str) -> Set[str]:
        """
        Detect which types of PII are present in text.

        Useful for logging/alerting purposes.

        Args:
            text: Text to analyze

        Returns:
            Set of detected PII types (e.g., {'email', 'phone_fr'})

        Example:
            >>> PIIDetector.detect_pii_types("Call 0612345678 or email me@ex.com")
            {'email', 'phone_fr'}
        """
        if not text or not isinstance(text, str):
            return set()

        detected = set()

        for pii_type, pattern in cls.PATTERNS.items():
            if pattern.search(text):
                detected.add(pii_type)

        return detected

    @classmethod
    def has_pii(cls, text: str) -> bool:
        """
        Quick check if text contains any PII.

        Args:
            text: Text to check

        Returns:
            True if any PII detected
        """
        return len(cls.detect_pii_types(text)) > 0


# Convenience functions for common use cases

def sanitize(data: Any) -> Any:
    """
    Sanitize any data structure (convenience wrapper).

    Usage:
        from app.core.pii_sanitizer import sanitize
        clean_data = sanitize(user_input)
    """
    return PIIDetector.sanitize_structure(data)


def sanitize_text(text: str) -> str:
    """
    Sanitize a text string (convenience wrapper).

    Usage:
        from app.core.pii_sanitizer import sanitize_text
        clean_text = sanitize_text(message)
    """
    return PIIDetector.sanitize_text(text)


# Export main class and convenience functions
__all__ = ['PIIDetector', 'sanitize', 'sanitize_text']
