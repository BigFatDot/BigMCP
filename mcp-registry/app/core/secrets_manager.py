"""
Secrets Manager for encrypting and decrypting sensitive credentials.

Supports key rotation with versioned encryption:
- Multiple encryption keys can be configured (v1, v2, v3, ...)
- New encryptions always use the latest key
- Decryption auto-detects the key version from the ciphertext prefix
- Backwards compatible with unversioned (v1) ciphertext

Environment Variables:
    ENCRYPTION_KEY: Current/latest encryption key (becomes v1 if no version specified)
    ENCRYPTION_KEY_V1: Version 1 key (legacy/fallback)
    ENCRYPTION_KEY_V2: Version 2 key
    ENCRYPTION_KEY_V3: Version 3 key (etc.)

Key Rotation Process:
1. Generate a new key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
2. Add as next version: ENCRYPTION_KEY_V2=<new_key>
3. Update ENCRYPTION_KEY to point to the new key
4. Run migration to re-encrypt existing credentials: python -m app.cli.rotate_keys
5. After migration, old keys can be removed

Security:
- Uses Fernet (AES 128 in CBC mode with PKCS7 padding and HMAC-SHA256)
- Keys must be 32 url-safe base64-encoded bytes
- Key versions are stored as plaintext prefix, ciphertext remains encrypted
"""

import os
import re
import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Version prefix pattern: "v1:", "v2:", etc.
VERSION_PREFIX_PATTERN = re.compile(r'^v(\d+):')


class SecretsManager:
    """
    Manages encryption and decryption of sensitive credentials with key rotation support.

    Encryption Format:
        v{N}:{fernet_ciphertext}

    Where:
        - N is the key version number (1, 2, 3, ...)
        - fernet_ciphertext is the Fernet-encrypted data

    Legacy format (no prefix) is treated as v1 for backwards compatibility.

    Example:
        # Single key (simple setup)
        ENCRYPTION_KEY=abc123...

        # Multi-key rotation setup
        ENCRYPTION_KEY=xyz789...      # Current key for new encryptions
        ENCRYPTION_KEY_V1=abc123...   # Old key for decrypting old data
        ENCRYPTION_KEY_V2=xyz789...   # Current key (same as ENCRYPTION_KEY)
    """

    def __init__(
        self,
        encryption_key: Optional[str] = None,
        key_versions: Optional[Dict[int, str]] = None
    ):
        """
        Initialize the secrets manager with support for multiple key versions.

        Args:
            encryption_key: Primary encryption key (for new encryptions)
            key_versions: Dict mapping version numbers to keys, e.g., {1: "key1", 2: "key2"}
                         If not provided, reads from environment variables.
        """
        self._keys: Dict[int, Fernet] = {}
        self._current_version: int = 1
        self._dev_mode: bool = False

        if key_versions:
            # Use provided key versions
            self._init_from_dict(key_versions)
        else:
            # Load from environment
            self._init_from_env(encryption_key)

        if not self._keys:
            # Check if we're in debug/dev mode
            debug_mode = os.getenv("DEBUG", "false").lower() == "true"
            if debug_mode:
                # Generate a temporary key for development only
                logger.warning(
                    "No ENCRYPTION_KEY found in environment. "
                    "Generating a temporary key for development. "
                    "DO NOT USE IN PRODUCTION - credentials will be lost on restart!"
                )
                temp_key = Fernet.generate_key()
                self._keys[1] = Fernet(temp_key)
                self._current_version = 1
                self._dev_mode = True
            else:
                raise RuntimeError(
                    "CRITICAL: ENCRYPTION_KEY must be set in production. "
                    "Without it, encrypted credentials cannot be stored or retrieved. "
                    "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
                )

    def _init_from_dict(self, key_versions: Dict[int, str]) -> None:
        """Initialize keys from a dictionary."""
        for version, key in key_versions.items():
            try:
                self._keys[version] = Fernet(key.encode() if isinstance(key, str) else key)
                if version > self._current_version:
                    self._current_version = version
            except Exception as e:
                logger.error(f"Failed to initialize key version {version}: {e}")
                raise ValueError(f"Invalid encryption key for version {version}")

    def _init_from_env(self, primary_key: Optional[str] = None) -> None:
        """
        Initialize keys from environment variables.

        Looks for:
        - ENCRYPTION_KEY: Primary key (assigned to highest version or v1)
        - ENCRYPTION_KEY_V1, ENCRYPTION_KEY_V2, etc.: Versioned keys
        """
        # Collect versioned keys from environment
        versioned_keys: Dict[int, str] = {}

        for key, value in os.environ.items():
            if key.startswith("ENCRYPTION_KEY_V"):
                try:
                    version = int(key.replace("ENCRYPTION_KEY_V", ""))
                    versioned_keys[version] = value
                except ValueError:
                    logger.warning(f"Invalid encryption key env var: {key}")

        # Add primary key
        primary = primary_key or os.getenv("ENCRYPTION_KEY")
        if primary:
            if versioned_keys:
                # Use highest version + 1 for primary, or match existing
                max_version = max(versioned_keys.keys())
                # Check if primary matches any existing version
                for v, k in versioned_keys.items():
                    if k == primary:
                        # Primary matches an existing version, use that
                        self._current_version = v
                        break
                else:
                    # Primary is new, assign to highest version
                    self._current_version = max_version
                    # Ensure primary is in versioned keys
                    if primary not in versioned_keys.values():
                        versioned_keys[max_version + 1] = primary
                        self._current_version = max_version + 1
            else:
                # No versioned keys, primary becomes v1
                versioned_keys[1] = primary
                self._current_version = 1

        # Initialize Fernet instances
        for version, key in versioned_keys.items():
            try:
                self._keys[version] = Fernet(key.encode() if isinstance(key, str) else key)
            except Exception as e:
                logger.error(f"Failed to initialize key version {version}: {e}")
                raise ValueError(f"Invalid encryption key for version {version}")

        if self._keys:
            self._current_version = max(self._keys.keys())

    @property
    def current_version(self) -> int:
        """Get the current (latest) key version used for encryption."""
        return self._current_version

    @property
    def available_versions(self) -> List[int]:
        """Get list of available key versions."""
        return sorted(self._keys.keys())

    @property
    def is_dev_mode(self) -> bool:
        """Check if running with auto-generated dev key."""
        return self._dev_mode

    def encrypt(self, data: Dict[str, Any]) -> str:
        """
        Encrypt a dictionary of credentials using the current key version.

        Args:
            data: Dictionary containing credentials (e.g., {"API_KEY": "secret123"})

        Returns:
            Versioned encrypted string: "v{N}:{ciphertext}"

        Example:
            >>> manager = SecretsManager()
            >>> encrypted = manager.encrypt({"API_KEY": "secret123"})
            >>> print(encrypted)  # v1:gAAAAABf...
        """
        if self._current_version not in self._keys:
            raise RuntimeError("No encryption key available")

        try:
            # Convert dict to JSON string
            json_str = json.dumps(data)

            # Encrypt with current version key
            fernet = self._keys[self._current_version]
            encrypted_bytes = fernet.encrypt(json_str.encode())

            # Return with version prefix
            return f"v{self._current_version}:{encrypted_bytes.decode()}"

        except Exception as e:
            logger.error(f"Failed to encrypt credentials: {e}")
            raise RuntimeError(f"Encryption failed: {e}")

    def decrypt(self, encrypted_data: str) -> Dict[str, Any]:
        """
        Decrypt an encrypted credentials string, auto-detecting key version.

        Supports both versioned format (v1:xxx) and legacy format (no prefix).
        Legacy format is treated as v1 for backwards compatibility.

        Args:
            encrypted_data: Encrypted string (with or without version prefix)

        Returns:
            Dictionary containing decrypted credentials

        Example:
            >>> manager = SecretsManager()
            >>> credentials = manager.decrypt("v1:gAAAAABf...")
            >>> print(credentials)  # {"API_KEY": "secret123"}
        """
        version, ciphertext = self._parse_versioned_ciphertext(encrypted_data)

        if version not in self._keys:
            raise RuntimeError(
                f"Decryption failed: key version {version} not available. "
                f"Available versions: {self.available_versions}"
            )

        try:
            fernet = self._keys[version]
            decrypted_bytes = fernet.decrypt(ciphertext.encode())
            json_str = decrypted_bytes.decode()
            return json.loads(json_str)

        except InvalidToken:
            # Try other versions as fallback (for corrupted version prefix)
            for v, f in self._keys.items():
                if v == version:
                    continue
                try:
                    decrypted_bytes = f.decrypt(ciphertext.encode())
                    json_str = decrypted_bytes.decode()
                    logger.warning(
                        f"Decrypted with key v{v} instead of claimed v{version}. "
                        f"Consider re-encrypting this credential."
                    )
                    return json.loads(json_str)
                except InvalidToken:
                    continue

            raise RuntimeError(
                f"Decryption failed: invalid ciphertext or key mismatch. "
                f"Tried versions: {self.available_versions}"
            )

        except Exception as e:
            logger.error(f"Failed to decrypt credentials: {e}")
            raise RuntimeError(f"Decryption failed: {e}")

    def _parse_versioned_ciphertext(self, encrypted_data: str) -> Tuple[int, str]:
        """
        Parse version prefix from encrypted data.

        Args:
            encrypted_data: Encrypted string with optional version prefix

        Returns:
            Tuple of (version, ciphertext)
        """
        match = VERSION_PREFIX_PATTERN.match(encrypted_data)
        if match:
            version = int(match.group(1))
            ciphertext = encrypted_data[match.end():]
            return version, ciphertext
        else:
            # Legacy format (no prefix) = v1
            return 1, encrypted_data

    def re_encrypt(self, encrypted_data: str) -> str:
        """
        Re-encrypt data with the current (latest) key version.

        Use this during key rotation to migrate old ciphertexts.

        Args:
            encrypted_data: Old encrypted data (any version)

        Returns:
            Newly encrypted data with current version

        Example:
            # During key rotation migration
            old_ciphertext = "v1:gAAAAABf..."
            new_ciphertext = manager.re_encrypt(old_ciphertext)
            # new_ciphertext = "v2:gAAAAABx..."
        """
        # Decrypt with whatever version it was encrypted with
        plaintext = self.decrypt(encrypted_data)

        # Re-encrypt with current version
        return self.encrypt(plaintext)

    def needs_rotation(self, encrypted_data: str) -> bool:
        """
        Check if encrypted data needs rotation to the current key version.

        Args:
            encrypted_data: Encrypted data to check

        Returns:
            True if data is encrypted with an older key version
        """
        version, _ = self._parse_versioned_ciphertext(encrypted_data)
        return version < self._current_version

    def mask_credentials(self, credentials: Dict[str, Any]) -> Dict[str, str]:
        """
        Mask credentials for safe display in logs/API responses.

        Args:
            credentials: Dictionary containing credentials

        Returns:
            Dictionary with masked values

        Example:
            >>> manager = SecretsManager()
            >>> masked = manager.mask_credentials({"API_KEY": "secret123456"})
            >>> print(masked)  # {"API_KEY": "sec***456"}
        """
        masked = {}
        for key, value in credentials.items():
            if isinstance(value, str) and len(value) > 6:
                # Show first 3 and last 3 characters
                masked[key] = f"{value[:3]}***{value[-3:]}"
            elif isinstance(value, str):
                masked[key] = "***"
            else:
                masked[key] = "***"
        return masked


# Singleton instance
_secrets_manager_instance: Optional[SecretsManager] = None


def get_secrets_manager() -> SecretsManager:
    """
    Get the singleton secrets manager instance.

    Returns:
        SecretsManager instance
    """
    global _secrets_manager_instance
    if _secrets_manager_instance is None:
        _secrets_manager_instance = SecretsManager()
    return _secrets_manager_instance


def reset_secrets_manager() -> None:
    """
    Reset the singleton instance.

    Useful for testing or after environment changes.
    """
    global _secrets_manager_instance
    _secrets_manager_instance = None


# Convenience reference for use in models
# Note: This is initialized lazily on first access in production
secrets_manager = get_secrets_manager()
