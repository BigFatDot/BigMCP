"""
Credential Detection Service

Automatically detects required credentials for MCP servers by:
1. Parsing README files for environment variable patterns
2. Analyzing package.json for credential references
3. Using curated knowledge base for popular services
4. Extracting from documentation URLs
"""

import logging
import re
from typing import Dict, List, Optional, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DetectedCredential:
    """A detected credential requirement."""
    name: str
    description: str = ""
    required: bool = True
    type: str = "secret"
    example: Optional[str] = None
    documentation_url: Optional[str] = None


class CredentialDetector:
    """
    Detects required credentials from package metadata and documentation.
    """

    # Known credential patterns to look for in README/docs
    ENV_VAR_PATTERNS = [
        # Direct mentions: API_KEY, GITHUB_TOKEN, etc.
        r'(?:export\s+)?([A-Z][A-Z0-9_]+)\s*=',
        r'process\.env\.([A-Z][A-Z0-9_]+)',
        r'\$\{([A-Z][A-Z0-9_]+)\}',
        r'ENV\[[\'""]([A-Z][A-Z0-9_]+)[\'""]',
        r'os\.environ\.get\([\'"]([A-Z][A-Z0-9_]+)[\'"]',
        # Documentation style: "Set the API_KEY environment variable"
        r'(?:set|configure|provide|require).*?(?:the\s+)?`([A-Z][A-Z0-9_]+)`.*?(?:environment variable|env var)',
        r'`([A-Z][A-Z0-9_]+)`.*?(?:environment variable|env var)',
    ]

    # Curated knowledge base for popular services
    KNOWN_CREDENTIALS: Dict[str, List[Dict]] = {
        "notion": [{
            "name": "NOTION_API_KEY",
            "description": "Notion Integration Token",
            "type": "secret",
            "documentation_url": "https://developers.notion.com/docs/create-a-notion-integration"
        }],
        "github": [{
            "name": "GITHUB_PERSONAL_ACCESS_TOKEN",
            "description": "GitHub Personal Access Token with repo permissions",
            "type": "secret",
            "documentation_url": "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token"
        }],
        "gitlab": [{
            "name": "GITLAB_TOKEN",
            "description": "GitLab Personal Access Token",
            "type": "secret",
            "documentation_url": "https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html"
        }, {
            "name": "GITLAB_URL",
            "description": "GitLab instance URL",
            "type": "url",
            "required": False,
            "example": "https://gitlab.com"
        }],
        "slack": [{
            "name": "SLACK_BOT_TOKEN",
            "description": "Slack Bot User OAuth Token",
            "type": "secret",
            "documentation_url": "https://api.slack.com/authentication/token-types#bot"
        }, {
            "name": "SLACK_TEAM_ID",
            "description": "Slack Workspace/Team ID",
            "type": "string"
        }],
        "postgres": [{
            "name": "DATABASE_URL",
            "description": "PostgreSQL connection string",
            "type": "connection_string",
            "example": "postgresql://user:password@localhost:5432/database"
        }],
        "sqlite": [{
            "name": "DATABASE_PATH",
            "description": "Path to SQLite database file",
            "type": "path",
            "example": "/path/to/database.db"
        }],
        "google-drive": [{
            "name": "GDRIVE_CLIENT_ID",
            "description": "Google OAuth Client ID",
            "type": "oauth",
            "documentation_url": "https://developers.google.com/drive/api/quickstart/python"
        }, {
            "name": "GDRIVE_CLIENT_SECRET",
            "description": "Google OAuth Client Secret",
            "type": "secret"
        }],
        "google-calendar": [{
            "name": "GOOGLE_CLIENT_ID",
            "description": "Google OAuth Client ID",
            "type": "oauth"
        }, {
            "name": "GOOGLE_CLIENT_SECRET",
            "description": "Google OAuth Client Secret",
            "type": "secret"
        }],
        "brave-search": [{
            "name": "BRAVE_API_KEY",
            "description": "Brave Search API key",
            "type": "secret",
            "documentation_url": "https://brave.com/search/api/"
        }],
        "aws": [{
            "name": "AWS_ACCESS_KEY_ID",
            "description": "AWS Access Key ID",
            "type": "secret"
        }, {
            "name": "AWS_SECRET_ACCESS_KEY",
            "description": "AWS Secret Access Key",
            "type": "secret"
        }, {
            "name": "AWS_REGION",
            "description": "AWS Region",
            "type": "string",
            "required": False,
            "example": "us-east-1"
        }],
        "linear": [{
            "name": "LINEAR_API_KEY",
            "description": "Linear API key",
            "type": "secret",
            "documentation_url": "https://linear.app/settings/api"
        }],
        "todoist": [{
            "name": "TODOIST_API_TOKEN",
            "description": "Todoist API token",
            "type": "secret",
            "documentation_url": "https://developer.todoist.com/guides/#developing-with-todoist"
        }],
        "sentry": [{
            "name": "SENTRY_AUTH_TOKEN",
            "description": "Sentry authentication token",
            "type": "secret",
            "documentation_url": "https://docs.sentry.io/api/auth/"
        }, {
            "name": "SENTRY_ORG",
            "description": "Sentry organization slug",
            "type": "string"
        }],
        "grist": [{
            "name": "GRIST_API_KEY",
            "description": "Grist API key",
            "type": "secret",
            "documentation_url": "https://support.getgrist.com/api/#authentication"
        }, {
            "name": "GRIST_API_URL",
            "description": "Grist instance URL",
            "type": "url",
            "required": False,
            "example": "https://docs.getgrist.com/api"
        }],
    }

    def detect_from_name(self, server_name: str, package_name: str = "") -> List[DetectedCredential]:
        """
        Detect credentials based on server/package name using curated knowledge base.

        Args:
            server_name: Display name of the server
            package_name: Package name (e.g., @modelcontextprotocol/server-github)

        Returns:
            List of detected credentials
        """
        # Normalize names for matching
        name_lower = server_name.lower()
        package_lower = package_name.lower()

        credentials = []

        # Check against known services
        for service_key, creds_data in self.KNOWN_CREDENTIALS.items():
            if service_key in name_lower or service_key in package_lower:
                for cred_data in creds_data:
                    credentials.append(DetectedCredential(
                        name=cred_data["name"],
                        description=cred_data.get("description", ""),
                        required=cred_data.get("required", True),
                        type=cred_data.get("type", "secret"),
                        example=cred_data.get("example"),
                        documentation_url=cred_data.get("documentation_url")
                    ))
                logger.info(f"Matched known service '{service_key}' for {server_name}")
                return credentials

        return credentials

    def detect_from_readme(self, readme_content: str) -> List[DetectedCredential]:
        """
        Parse README content to detect environment variables and credentials.

        Args:
            readme_content: README file content (markdown)

        Returns:
            List of detected credentials
        """
        if not readme_content:
            return []

        detected_vars: Set[str] = set()

        # Apply all regex patterns
        for pattern in self.ENV_VAR_PATTERNS:
            matches = re.finditer(pattern, readme_content, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                var_name = match.group(1)
                # Filter out common non-credential variables
                if self._is_likely_credential(var_name):
                    detected_vars.add(var_name)

        # Convert to DetectedCredential objects
        credentials = []
        for var_name in detected_vars:
            cred_type = self._infer_credential_type(var_name)
            description = self._generate_description(var_name)

            credentials.append(DetectedCredential(
                name=var_name,
                description=description,
                type=cred_type,
                required=True  # Assume required unless proven otherwise
            ))

        logger.info(f"Detected {len(credentials)} credentials from README")
        return credentials

    def detect_from_package_json(self, package_json: Dict) -> List[DetectedCredential]:
        """
        Analyze package.json for credential references.

        Args:
            package_json: Parsed package.json contents

        Returns:
            List of detected credentials
        """
        credentials = []

        # Check scripts for environment variable usage
        scripts = package_json.get("scripts", {})
        env_vars: Set[str] = set()

        for script_content in scripts.values():
            # Find $VAR_NAME or ${VAR_NAME} patterns
            matches = re.finditer(r'\$\{?([A-Z][A-Z0-9_]+)\}?', script_content)
            for match in matches:
                var_name = match.group(1)
                if self._is_likely_credential(var_name):
                    env_vars.add(var_name)

        for var_name in env_vars:
            credentials.append(DetectedCredential(
                name=var_name,
                description=self._generate_description(var_name),
                type=self._infer_credential_type(var_name),
                required=True
            ))

        return credentials

    def merge_credentials(
        self,
        detected_list: List[List[DetectedCredential]]
    ) -> List[Dict]:
        """
        Merge multiple credential detection results, removing duplicates.

        Args:
            detected_list: List of credential lists from different sources

        Returns:
            Merged and deduplicated credentials as dicts
        """
        # Use dict to deduplicate by name (keep first occurrence)
        merged: Dict[str, DetectedCredential] = {}

        for cred_list in detected_list:
            for cred in cred_list:
                if cred.name not in merged:
                    merged[cred.name] = cred
                else:
                    # Merge metadata (prefer more detailed)
                    existing = merged[cred.name]
                    if not existing.description and cred.description:
                        existing.description = cred.description
                    if not existing.documentation_url and cred.documentation_url:
                        existing.documentation_url = cred.documentation_url
                    if not existing.example and cred.example:
                        existing.example = cred.example

        # Convert to dict format
        return [
            {
                "name": cred.name,
                "description": cred.description,
                "required": cred.required,
                "type": cred.type,
                **({"example": cred.example} if cred.example else {}),
                **({"documentationUrl": cred.documentation_url} if cred.documentation_url else {})
            }
            for cred in merged.values()
        ]

    def _is_likely_credential(self, var_name: str) -> bool:
        """Check if variable name looks like a credential."""
        var_lower = var_name.lower()

        # Exclude common non-credential variables
        exclude_patterns = [
            'node_env', 'path', 'home', 'user', 'shell', 'lang', 'pwd',
            'port', 'host', 'debug', 'env', 'npm_', 'yarn_'
        ]

        for pattern in exclude_patterns:
            if pattern in var_lower:
                return False

        # Include if contains credential keywords
        credential_keywords = [
            'key', 'token', 'secret', 'password', 'auth', 'credential',
            'api', 'oauth', 'client_id', 'client_secret', 'access',
            'database_url', 'db_', '_url', '_uri', 'connection'
        ]

        for keyword in credential_keywords:
            if keyword in var_lower:
                return True

        return False

    def _infer_credential_type(self, var_name: str) -> str:
        """Infer credential type from variable name."""
        var_lower = var_name.lower()

        if 'oauth' in var_lower or 'client_id' in var_lower:
            return 'oauth'
        elif any(x in var_lower for x in ['secret', 'password', 'token', 'key']):
            return 'secret'
        elif '_url' in var_lower or '_uri' in var_lower or 'endpoint' in var_lower:
            return 'url'
        elif 'path' in var_lower or 'dir' in var_lower or 'file' in var_lower:
            return 'path'
        elif 'connection' in var_lower or 'database_url' in var_lower:
            return 'connection_string'
        else:
            return 'string'

    def _generate_description(self, var_name: str) -> str:
        """Generate a human-readable description from variable name."""
        # Convert SNAKE_CASE to Title Case
        words = var_name.replace('_', ' ').lower().split()
        description = ' '.join(word.capitalize() for word in words)

        # Add context based on type
        var_lower = var_name.lower()
        if 'token' in var_lower or 'key' in var_lower:
            if 'api' in var_lower:
                description += " (API authentication)"
            else:
                description += " (authentication)"
        elif 'url' in var_lower:
            description += " (endpoint URL)"
        elif 'path' in var_lower:
            description += " (file path)"

        return description
