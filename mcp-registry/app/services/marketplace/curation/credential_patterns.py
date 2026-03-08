"""
Credential Patterns - Constants and detection logic for credential identification.

Extracted from marketplace_service.py for better modularity.

Used to distinguish real credentials (API keys, tokens) from configuration
variables (ports, URLs, paths) during static analysis.
"""

from __future__ import annotations

from typing import List, Set, Tuple


# Patterns that indicate a variable is likely a credential (secret)
CREDENTIAL_PATTERNS: Tuple[str, ...] = (
    "API_KEY", "APIKEY", "API_TOKEN",
    "TOKEN", "SECRET", "PASSWORD", "PASSWD",
    "AUTH", "AUTHORIZATION",
    "PRIVATE_KEY", "ACCESS_KEY", "CLIENT_SECRET",
    "BEARER", "CREDENTIAL", "APITOKEN",
    "ACCOUNT_SID",  # Twilio-style
    "CONNECTION_STRING",  # Database connection strings often contain credentials
    "APP_PASSWORD",  # Application-specific passwords
    "REFRESH_TOKEN",  # OAuth refresh tokens
    "CLIENT_ID",  # OAuth client identification (often paired with secret)
)

# Patterns that indicate a variable is configuration (not a secret)
CONFIG_PATTERNS: Tuple[str, ...] = (
    "PORT", "HOST", "URL", "ENDPOINT", "BASE_URL", "API_URL",
    "PROXY", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
    "PATH", "DIR", "DIRECTORY", "FILE", "FOLDER",
    "VERSION", "NODE_ENV", "ENV", "DEBUG", "LOG", "LEVEL",
    "MODE", "TIMEOUT", "LIMIT", "MAX", "MIN", "SIZE",
    "ENABLED", "DISABLED", "ALLOW", "RESPONSE", "REQUEST",
    "FORMAT", "CONTENT", "HEADERS", "DOMAIN", "REGION",
    "PREFIX", "SUFFIX", "NAME", "ID", "INDEX", "COUNT",
    "INTERVAL", "DELAY", "RETRY", "CACHE", "TTL",
    "TELEMETRY", "ANALYTICS", "METRICS", "TRACE", "DIAGNOSTICS",
    "HOME", "HOMEDRIVE", "HOMEPATH", "USER", "USERNAME",
    "OSTYPE", "OS", "SHELL", "TERM", "LANG", "LOCALE",
    "PLATFORM", "ARCH", "PROCESSOR", "MEMORY", "MBYTES",
    "RUNTIME", "WORKER", "STARTED_AT", "BUILD_NUMBER", "ORIGIN",
    "RESOURCE_GROUP", "WEBSITE", "FUNCTIONS", "ACTOR", "AT_HOME",
    "FEATURE", "SCENARIO", "INTERNAL", "TOOLSUITE", "LANDSCAPE",
    "FORCE_COLOR", "NO_COLOR", "COLOR", "DEPRECATION",
    "BUFFER", "READABLE", "STREAM", "GRACEFUL",
    "INSTRUCTIONS", "MESSAGE", "EFFORT", "RELEASE",
)


def is_credential_variable(name: str, min_length: int = 4) -> bool:
    """
    Determine if a variable name looks like a credential.

    Args:
        name: Variable name to check
        min_length: Minimum length to consider (default 4)

    Returns:
        True if the variable looks like a credential, False otherwise
    """
    if len(name) < min_length:
        return False

    name_upper = name.upper()

    # Check if this looks like a credential
    is_credential = any(pattern in name_upper for pattern in CREDENTIAL_PATTERNS)

    # Check if it's purely configuration (no credential patterns)
    is_pure_config = (
        any(pattern in name_upper for pattern in CONFIG_PATTERNS)
        and not is_credential
    )

    return is_credential and not is_pure_config


def detect_credentials_from_env_vars(
    detected_env_vars: List[str],
    existing_names: Set[str]
) -> List[dict]:
    """
    Filter environment variables to identify real credentials.

    Args:
        detected_env_vars: List of detected environment variable names
        existing_names: Set of already-known credential names to skip

    Returns:
        List of credential dicts with name, description, required, type
    """
    credentials = []

    for env_var in detected_env_vars:
        if env_var in existing_names:
            continue

        if is_credential_variable(env_var):
            credentials.append({
                "name": env_var,
                "description": f"Environment variable: {env_var}",
                "required": True,
                "type": "secret"
            })

    return credentials


def detect_credentials_from_cli_args(
    detected_cli_args: List[str],
    existing_names: Set[str]
) -> List[dict]:
    """
    Filter CLI arguments to identify real credentials.

    Args:
        detected_cli_args: List of detected CLI argument names
        existing_names: Set of already-known credential names to skip

    Returns:
        List of credential dicts with name, description, required, type
    """
    credentials = []

    for cli_arg in detected_cli_args:
        arg_name = cli_arg.upper().replace("-", "_")

        if arg_name in existing_names:
            continue

        if is_credential_variable(arg_name):
            credentials.append({
                "name": arg_name,
                "description": f"CLI argument: --{cli_arg}",
                "required": True,
                "type": "secret"
            })

    return credentials


def detect_all_credentials(
    detected_env_vars: List[str],
    detected_cli_args: List[str],
    existing_names: Set[str]
) -> List[dict]:
    """
    Detect credentials from both environment variables and CLI arguments.

    Args:
        detected_env_vars: List of detected environment variable names
        detected_cli_args: List of detected CLI argument names
        existing_names: Set of already-known credential names to skip

    Returns:
        List of credential dicts with name, description, required, type
    """
    credentials = detect_credentials_from_env_vars(detected_env_vars, existing_names)

    # Update existing_names with newly found credentials to avoid duplicates
    updated_names = existing_names | {c["name"] for c in credentials}

    credentials.extend(
        detect_credentials_from_cli_args(detected_cli_args, updated_names)
    )

    return credentials
