"""
Marketplace Service - Dynamic MCP Server Discovery and Sync.

Aggregates MCP servers from multiple sources:
- npm registry (@modelcontextprotocol/* packages)
- GitHub (modelcontextprotocol/servers repository)
- Local curated registry (fallback/overrides)

Future sources (commented for now to avoid overloading):
- Glama.ai (community registry with 11k+ servers)
- Smithery.ai (marketplace with 3k+ integrations)

Provides caching, deduplication, and normalization.
"""

import asyncio
import json
import logging
import os
import re
# import xml.etree.ElementTree as ET  # For Glama XML parsing (commented)
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import httpx

from ..core.vector_store import VectorStore
from ..config.settings import EmbeddingConfig
from .credential_detector import CredentialDetector
from .static_tool_extractor import StaticToolExtractor, PackageType

# Import from modular structure (Phase 2-3)
from .marketplace.sources import (
    MarketplaceSource,
    NPMSource,
    GitHubSource,
    BigMCPSource,
)
from .marketplace.icon_resolver import (
    IconResolver,
    generate_icon_search_terms,
    resolve_icon_url,
)
from .marketplace.curation import (
    get_curation_system_prompt,
    build_curation_prompt,
    detect_all_credentials,
)

logger = logging.getLogger(__name__)


class InstallationType(str, Enum):
    """Installation method for MCP servers."""
    NPM = "npm"
    PIP = "pip"
    GITHUB = "github"
    DOCKER = "docker"
    LOCAL = "local"
    REMOTE = "remote"  # SSE-based remote server


class ServerSource(str, Enum):
    """Source registry for the server."""
    CUSTOM = "custom"  # User-added (priority 1)
    BIGMCP = "bigmcp"  # BigMCP curated list (priority 2)
    OFFICIAL = "official"  # modelcontextprotocol org (priority 3)
    NPM = "npm"  # npm registry (priority 4, LLM curated)
    GITHUB = "github"  # GitHub repos (priority 5, LLM curated)
    GLAMA = "glama"  # Glama.ai registry (disabled)
    SMITHERY = "smithery"  # Smithery.ai marketplace (disabled)


@dataclass
class CredentialSpec:
    """Specification for a required credential."""
    name: str
    description: str
    required: bool = True
    type: str = "secret"  # secret, string, url, path, oauth
    config_type: str = "remote"  # remote (API keys), local (localhost configs)
    default: Optional[str] = None
    example: Optional[str] = None
    documentation_url: Optional[str] = None


@dataclass
class MarketplaceServer:
    """
    Normalized MCP server entry from marketplace.

    Combines data from multiple sources into a unified format.
    """
    id: str
    name: str
    description: str

    # Installation
    install_type: InstallationType
    install_package: str  # npm package, pip package, github repo, docker image
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)  # Environment variables (from local registry)

    # Source & metadata
    source: ServerSource = ServerSource.BIGMCP
    source_url: Optional[str] = None
    repository: Optional[str] = None
    author: Optional[str] = None
    version: Optional[str] = None
    icon_url: Optional[str] = None  # URL to server/service icon

    # Credentials
    credentials: List[CredentialSpec] = field(default_factory=list)

    # Categorization
    category: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    # Quality indicators
    verified: bool = False
    popularity: int = 0  # 0-100 score
    downloads_weekly: Optional[int] = None

    # Tools - full details from static analysis
    tools: List[Dict[str, Any]] = field(default_factory=list)  # [{name, description, ...}]
    tools_preview: List[str] = field(default_factory=list)  # Just names for quick display

    # SaaS compatibility (from static analysis)
    requires_local_access: bool = False  # True if server needs local filesystem/docker/etc

    # Curation flag - True if loaded from bigmcp_source.json (curated data shouldn't be overwritten)
    is_curated: bool = False

    # Service identification for deduplication (e.g., "slack", "github", "datadog")
    # Multiple packages can implement the same service - they should share the same service_id
    service_id: Optional[str] = None

    # Availability (from static analysis - package exists and is downloadable)
    is_available: bool = True  # False if package doesn't exist (404)
    availability_reason: Optional[str] = None  # Reason if unavailable

    # Dynamic tools flag (tools are loaded at runtime, static analysis incomplete)
    has_dynamic_tools: bool = False

    # Timestamps
    last_updated: Optional[datetime] = None
    discovered_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        # Convert enums to strings
        data['install_type'] = self.install_type.value
        data['source'] = self.source.value
        # Convert credentials
        data['credentials'] = [asdict(c) for c in self.credentials]

        # Analyze credentials: separate required vs optional
        required_creds = [c for c in self.credentials if c.required]
        optional_creds = [c for c in self.credentials if not c.required]

        # Analyze credentials: separate local vs remote
        local_creds = [c for c in self.credentials if c.config_type == "local"]
        remote_creds = [c for c in self.credentials if c.config_type != "local"]

        # Set credential flags for frontend
        data['requires_credentials'] = len(required_creds) > 0  # Has required credentials
        data['has_optional_credentials'] = len(optional_creds) > 0  # Has optional credentials
        data['required_credentials_count'] = len(required_creds)
        data['optional_credentials_count'] = len(optional_creds)

        # Local vs remote credential flags
        data['has_local_credentials'] = len(local_creds) > 0  # Has local config (like OLLAMA_HOST)
        data['has_remote_credentials'] = len(remote_creds) > 0  # Has remote API keys

        # Add is_official and is_verified flags for frontend
        # Official = from vendor or modelcontextprotocol (has official: true in bigmcp_source.json)
        # Community = from bigmcp curated but not official (no badge)
        data['is_official'] = self.source == ServerSource.OFFICIAL
        data['is_verified'] = self.verified
        # Add tools_count for display
        data['tools_count'] = len(self.tools) if self.tools else len(self.tools_preview)
        # Convert datetimes
        if self.last_updated:
            data['last_updated'] = self.last_updated.isoformat()
        if self.discovered_at:
            data['discovered_at'] = self.discovered_at.isoformat()
        return data


# ============================================================================
# Known Service Credentials - Canonical credentials for popular services
# ============================================================================
#
# When a server's service_id matches a known service, use these templates
# instead of relying on static analysis or LLM curation. This ensures:
# - Users see exactly the right credential(s) for each service
# - No duplicates (e.g., Notion shows only NOTION_API_KEY, not 3 variants)
# - Accurate descriptions with documentation links
#
# Format: service_id -> list of canonical credentials

KNOWN_SERVICE_CREDENTIALS: Dict[str, List[Dict[str, Any]]] = {
    # === AI/LLM Services ===
    "openai": [{
        "name": "OPENAI_API_KEY",
        "description": "OpenAI API key for GPT models and embeddings",
        "required": True,
        "type": "secret",
        "documentation_url": "https://platform.openai.com/api-keys"
    }],
    "anthropic": [{
        "name": "ANTHROPIC_API_KEY",
        "description": "Anthropic API key for Claude models",
        "required": True,
        "type": "secret",
        "documentation_url": "https://console.anthropic.com/settings/keys"
    }],
    "google-ai": [{
        "name": "GOOGLE_AI_API_KEY",
        "description": "Google AI API key (Gemini)",
        "required": True,
        "type": "secret",
        "documentation_url": "https://aistudio.google.com/apikey"
    }],
    "azure-openai": [{
        "name": "AZURE_OPENAI_API_KEY",
        "description": "Azure OpenAI API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://portal.azure.com/"
    }, {
        "name": "AZURE_OPENAI_ENDPOINT",
        "description": "Azure OpenAI endpoint URL",
        "required": True,
        "type": "url",
        "documentation_url": "https://portal.azure.com/"
    }],
    "mistral": [{
        "name": "MISTRAL_API_KEY",
        "description": "Mistral AI API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://console.mistral.ai/api-keys/"
    }],
    "cohere": [{
        "name": "COHERE_API_KEY",
        "description": "Cohere API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://dashboard.cohere.com/api-keys"
    }],
    "perplexity": [{
        "name": "PERPLEXITY_API_KEY",
        "description": "Perplexity API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://www.perplexity.ai/settings/api"
    }],
    "groq": [{
        "name": "GROQ_API_KEY",
        "description": "Groq API key for fast inference",
        "required": True,
        "type": "secret",
        "documentation_url": "https://console.groq.com/keys"
    }],
    "deepseek": [{
        "name": "DEEPSEEK_API_KEY",
        "description": "DeepSeek API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://platform.deepseek.com/api_keys"
    }],

    # === Developer Tools ===
    "github": [{
        "name": "GITHUB_TOKEN",
        "description": "GitHub Personal Access Token with repo permissions",
        "required": True,
        "type": "secret",
        "documentation_url": "https://github.com/settings/tokens"
    }],
    "gitlab": [{
        "name": "GITLAB_TOKEN",
        "description": "GitLab Personal Access Token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://gitlab.com/-/profile/personal_access_tokens"
    }],
    "bitbucket": [{
        "name": "BITBUCKET_APP_PASSWORD",
        "description": "Bitbucket App Password",
        "required": True,
        "type": "secret",
        "documentation_url": "https://bitbucket.org/account/settings/app-passwords/"
    }],
    "jira": [{
        "name": "JIRA_API_TOKEN",
        "description": "Jira/Atlassian API token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://id.atlassian.com/manage-profile/security/api-tokens"
    }],
    "confluence": [{
        "name": "CONFLUENCE_API_TOKEN",
        "description": "Confluence/Atlassian API token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://id.atlassian.com/manage-profile/security/api-tokens"
    }],
    "linear": [{
        "name": "LINEAR_API_KEY",
        "description": "Linear API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://linear.app/settings/api"
    }],
    "sentry": [{
        "name": "SENTRY_AUTH_TOKEN",
        "description": "Sentry Auth Token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://sentry.io/settings/auth-tokens/"
    }],
    "datadog": [{
        "name": "DATADOG_API_KEY",
        "description": "Datadog API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://app.datadoghq.com/organization-settings/api-keys"
    }],
    "vercel": [{
        "name": "VERCEL_TOKEN",
        "description": "Vercel access token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://vercel.com/account/tokens"
    }],
    "netlify": [{
        "name": "NETLIFY_AUTH_TOKEN",
        "description": "Netlify personal access token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://app.netlify.com/user/applications#personal-access-tokens"
    }],
    "cloudflare": [{
        "name": "CLOUDFLARE_API_TOKEN",
        "description": "Cloudflare API token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://dash.cloudflare.com/profile/api-tokens"
    }],

    # === Productivity & Collaboration ===
    "notion": [{
        "name": "NOTION_API_KEY",
        "description": "Notion Integration Token (Internal Integration)",
        "required": True,
        "type": "secret",
        "documentation_url": "https://www.notion.so/my-integrations"
    }],
    "slack": [{
        "name": "SLACK_BOT_TOKEN",
        "description": "Slack Bot User OAuth Token (xoxb-...)",
        "required": True,
        "type": "secret",
        "documentation_url": "https://api.slack.com/apps"
    }],
    "discord": [{
        "name": "DISCORD_BOT_TOKEN",
        "description": "Discord Bot Token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://discord.com/developers/applications"
    }],
    "asana": [{
        "name": "ASANA_ACCESS_TOKEN",
        "description": "Asana Personal Access Token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://app.asana.com/0/developer-console"
    }],
    "trello": [{
        "name": "TRELLO_API_KEY",
        "description": "Trello API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://trello.com/power-ups/admin"
    }, {
        "name": "TRELLO_TOKEN",
        "description": "Trello token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://trello.com/power-ups/admin"
    }],
    "monday": [{
        "name": "MONDAY_API_KEY",
        "description": "Monday.com API token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://monday.com/developers/apps"
    }],
    "airtable": [{
        "name": "AIRTABLE_API_KEY",
        "description": "Airtable Personal Access Token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://airtable.com/create/tokens"
    }],
    "google-drive": [{
        "name": "GOOGLE_DRIVE_CREDENTIALS",
        "description": "Google Drive OAuth credentials (JSON)",
        "required": True,
        "type": "secret",
        "documentation_url": "https://console.cloud.google.com/apis/credentials"
    }],
    "google-calendar": [{
        "name": "GOOGLE_CALENDAR_CREDENTIALS",
        "description": "Google Calendar OAuth credentials (JSON)",
        "required": True,
        "type": "secret",
        "documentation_url": "https://console.cloud.google.com/apis/credentials"
    }],
    "google-sheets": [{
        "name": "GOOGLE_SHEETS_CREDENTIALS",
        "description": "Google Sheets OAuth credentials (JSON)",
        "required": True,
        "type": "secret",
        "documentation_url": "https://console.cloud.google.com/apis/credentials"
    }],
    "dropbox": [{
        "name": "DROPBOX_ACCESS_TOKEN",
        "description": "Dropbox access token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://www.dropbox.com/developers/apps"
    }],
    "todoist": [{
        "name": "TODOIST_API_TOKEN",
        "description": "Todoist API token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://todoist.com/app/settings/integrations/developer"
    }],
    "evernote": [{
        "name": "EVERNOTE_API_KEY",
        "description": "Evernote API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://dev.evernote.com/"
    }],
    "clickup": [{
        "name": "CLICKUP_API_KEY",
        "description": "ClickUp API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://app.clickup.com/settings/apps"
    }],
    "basecamp": [{
        "name": "BASECAMP_ACCESS_TOKEN",
        "description": "Basecamp OAuth access token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://launchpad.37signals.com/integrations"
    }],
    "zoom": [{
        "name": "ZOOM_API_KEY",
        "description": "Zoom API credentials",
        "required": True,
        "type": "secret",
        "documentation_url": "https://marketplace.zoom.us/develop/create"
    }],
    "microsoft-teams": [{
        "name": "TEAMS_BOT_TOKEN",
        "description": "Microsoft Teams Bot token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://dev.teams.microsoft.com/"
    }],

    # === CRM & Sales ===
    "salesforce": [{
        "name": "SALESFORCE_ACCESS_TOKEN",
        "description": "Salesforce OAuth access token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://developer.salesforce.com/"
    }],
    "hubspot": [{
        "name": "HUBSPOT_API_KEY",
        "description": "HubSpot private app access token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://developers.hubspot.com/docs/api/private-apps"
    }],
    "pipedrive": [{
        "name": "PIPEDRIVE_API_TOKEN",
        "description": "Pipedrive API token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://developers.pipedrive.com/"
    }],
    "zendesk": [{
        "name": "ZENDESK_API_TOKEN",
        "description": "Zendesk API token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://developer.zendesk.com/"
    }],
    "intercom": [{
        "name": "INTERCOM_ACCESS_TOKEN",
        "description": "Intercom access token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://developers.intercom.com/"
    }],
    "freshdesk": [{
        "name": "FRESHDESK_API_KEY",
        "description": "Freshdesk API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://developers.freshdesk.com/"
    }],

    # === Cloud & Infrastructure ===
    "aws": [{
        "name": "AWS_ACCESS_KEY_ID",
        "description": "AWS access key ID",
        "required": True,
        "type": "secret",
        "documentation_url": "https://console.aws.amazon.com/iam/"
    }, {
        "name": "AWS_SECRET_ACCESS_KEY",
        "description": "AWS secret access key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://console.aws.amazon.com/iam/"
    }],
    "gcp": [{
        "name": "GOOGLE_APPLICATION_CREDENTIALS",
        "description": "Path to GCP service account JSON file",
        "required": True,
        "type": "path",
        "documentation_url": "https://console.cloud.google.com/iam-admin/serviceaccounts"
    }],
    "azure": [{
        "name": "AZURE_CLIENT_ID",
        "description": "Azure Active Directory application ID",
        "required": True,
        "type": "string",
        "documentation_url": "https://portal.azure.com/"
    }, {
        "name": "AZURE_CLIENT_SECRET",
        "description": "Azure Active Directory client secret",
        "required": True,
        "type": "secret",
        "documentation_url": "https://portal.azure.com/"
    }, {
        "name": "AZURE_TENANT_ID",
        "description": "Azure Active Directory tenant ID",
        "required": True,
        "type": "string",
        "documentation_url": "https://portal.azure.com/"
    }],
    "digitalocean": [{
        "name": "DIGITALOCEAN_TOKEN",
        "description": "DigitalOcean API token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://cloud.digitalocean.com/account/api/tokens"
    }],
    "linode": [{
        "name": "LINODE_TOKEN",
        "description": "Linode API token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://cloud.linode.com/profile/tokens"
    }],

    # === Databases ===
    "supabase": [{
        "name": "SUPABASE_URL",
        "description": "Supabase project URL",
        "required": True,
        "type": "url",
        "documentation_url": "https://supabase.com/dashboard"
    }, {
        "name": "SUPABASE_KEY",
        "description": "Supabase anon/service role key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://supabase.com/dashboard"
    }],
    "firebase": [{
        "name": "FIREBASE_SERVICE_ACCOUNT",
        "description": "Firebase service account JSON",
        "required": True,
        "type": "secret",
        "documentation_url": "https://console.firebase.google.com/"
    }],
    "mongodb": [{
        "name": "MONGODB_URI",
        "description": "MongoDB connection string",
        "required": True,
        "type": "secret",
        "documentation_url": "https://cloud.mongodb.com/"
    }],
    "postgres": [{
        "name": "POSTGRES_URL",
        "description": "PostgreSQL connection string (postgres://user:pass@host:port/db)",
        "required": True,
        "type": "secret",
        "documentation_url": "https://www.postgresql.org/docs/current/libpq-connect.html"
    }],
    "postgresql": [{
        "name": "POSTGRES_URL",
        "description": "PostgreSQL connection string",
        "required": True,
        "type": "secret",
        "documentation_url": "https://www.postgresql.org/docs/current/libpq-connect.html"
    }],
    "mysql": [{
        "name": "MYSQL_URL",
        "description": "MySQL connection string",
        "required": True,
        "type": "secret",
        "documentation_url": "https://dev.mysql.com/doc/"
    }],
    "sqlite": [],  # Local file, no credentials
    "redis": [{
        "name": "REDIS_URL",
        "description": "Redis connection URL",
        "required": True,
        "type": "secret",
        "documentation_url": "https://redis.io/docs/"
    }],
    "planetscale": [{
        "name": "DATABASE_URL",
        "description": "PlanetScale database connection string",
        "required": True,
        "type": "secret",
        "documentation_url": "https://planetscale.com/docs"
    }],
    "neon": [{
        "name": "DATABASE_URL",
        "description": "Neon PostgreSQL connection string",
        "required": True,
        "type": "secret",
        "documentation_url": "https://neon.tech/docs"
    }],
    "upstash": [{
        "name": "UPSTASH_REDIS_REST_URL",
        "description": "Upstash Redis REST URL",
        "required": True,
        "type": "url",
        "documentation_url": "https://console.upstash.com/"
    }, {
        "name": "UPSTASH_REDIS_REST_TOKEN",
        "description": "Upstash Redis REST token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://console.upstash.com/"
    }],

    # === Email & Messaging ===
    "sendgrid": [{
        "name": "SENDGRID_API_KEY",
        "description": "SendGrid API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://app.sendgrid.com/settings/api_keys"
    }],
    "mailgun": [{
        "name": "MAILGUN_API_KEY",
        "description": "Mailgun API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://app.mailgun.com/app/account/security/api_keys"
    }],
    "postmark": [{
        "name": "POSTMARK_SERVER_TOKEN",
        "description": "Postmark server token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://account.postmarkapp.com/"
    }],
    "twilio": [{
        "name": "TWILIO_ACCOUNT_SID",
        "description": "Twilio Account SID",
        "required": True,
        "type": "string",
        "documentation_url": "https://console.twilio.com/"
    }, {
        "name": "TWILIO_AUTH_TOKEN",
        "description": "Twilio Auth Token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://console.twilio.com/"
    }],
    "resend": [{
        "name": "RESEND_API_KEY",
        "description": "Resend API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://resend.com/api-keys"
    }],

    # === Payments ===
    "stripe": [{
        "name": "STRIPE_SECRET_KEY",
        "description": "Stripe secret API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://dashboard.stripe.com/apikeys"
    }],
    "paypal": [{
        "name": "PAYPAL_CLIENT_ID",
        "description": "PayPal client ID",
        "required": True,
        "type": "string",
        "documentation_url": "https://developer.paypal.com/"
    }, {
        "name": "PAYPAL_CLIENT_SECRET",
        "description": "PayPal client secret",
        "required": True,
        "type": "secret",
        "documentation_url": "https://developer.paypal.com/"
    }],
    "square": [{
        "name": "SQUARE_ACCESS_TOKEN",
        "description": "Square access token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://developer.squareup.com/"
    }],

    # === Media & Content ===
    "youtube": [{
        "name": "YOUTUBE_API_KEY",
        "description": "YouTube Data API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://console.cloud.google.com/apis/credentials"
    }],
    "spotify": [{
        "name": "SPOTIFY_CLIENT_ID",
        "description": "Spotify client ID",
        "required": True,
        "type": "string",
        "documentation_url": "https://developer.spotify.com/dashboard"
    }, {
        "name": "SPOTIFY_CLIENT_SECRET",
        "description": "Spotify client secret",
        "required": True,
        "type": "secret",
        "documentation_url": "https://developer.spotify.com/dashboard"
    }],
    "unsplash": [{
        "name": "UNSPLASH_ACCESS_KEY",
        "description": "Unsplash API access key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://unsplash.com/developers"
    }],
    "cloudinary": [{
        "name": "CLOUDINARY_URL",
        "description": "Cloudinary environment variable URL",
        "required": True,
        "type": "secret",
        "documentation_url": "https://cloudinary.com/console"
    }],
    "imgur": [{
        "name": "IMGUR_CLIENT_ID",
        "description": "Imgur API client ID",
        "required": True,
        "type": "secret",
        "documentation_url": "https://api.imgur.com/oauth2/addclient"
    }],

    # === Search & Analytics ===
    "algolia": [{
        "name": "ALGOLIA_APP_ID",
        "description": "Algolia Application ID",
        "required": True,
        "type": "string",
        "documentation_url": "https://dashboard.algolia.com/account/api-keys"
    }, {
        "name": "ALGOLIA_API_KEY",
        "description": "Algolia API key (Admin or Search-only)",
        "required": True,
        "type": "secret",
        "documentation_url": "https://dashboard.algolia.com/account/api-keys"
    }],
    "elasticsearch": [{
        "name": "ELASTICSEARCH_URL",
        "description": "Elasticsearch cluster URL",
        "required": True,
        "type": "url",
        "documentation_url": "https://www.elastic.co/guide/en/elasticsearch/reference/current/setup.html"
    }, {
        "name": "ELASTICSEARCH_API_KEY",
        "description": "Elasticsearch API key",
        "required": False,
        "type": "secret",
        "documentation_url": "https://www.elastic.co/guide/en/elasticsearch/reference/current/security-api-create-api-key.html"
    }],
    "google-analytics": [{
        "name": "GA_TRACKING_ID",
        "description": "Google Analytics Measurement ID",
        "required": True,
        "type": "string",
        "documentation_url": "https://analytics.google.com/"
    }],
    "mixpanel": [{
        "name": "MIXPANEL_TOKEN",
        "description": "Mixpanel project token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://mixpanel.com/settings/project"
    }],
    "amplitude": [{
        "name": "AMPLITUDE_API_KEY",
        "description": "Amplitude API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://analytics.amplitude.com/"
    }],
    "segment": [{
        "name": "SEGMENT_WRITE_KEY",
        "description": "Segment write key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://segment.com/docs/"
    }],

    # === Automation & Workflow ===
    "zapier": [{
        "name": "ZAPIER_NLA_API_KEY",
        "description": "Zapier Natural Language Actions API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://nla.zapier.com/docs/"
    }],
    "make": [{
        "name": "MAKE_API_KEY",
        "description": "Make (Integromat) API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://www.make.com/en/api-documentation"
    }],
    "n8n": [{
        "name": "N8N_API_KEY",
        "description": "n8n API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://docs.n8n.io/api/"
    }],

    # === Web Scraping & Browser ===
    "browserless": [{
        "name": "BROWSERLESS_API_KEY",
        "description": "Browserless API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://www.browserless.io/"
    }],
    "firecrawl": [{
        "name": "FIRECRAWL_API_KEY",
        "description": "Firecrawl API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://firecrawl.dev/"
    }],
    "apify": [{
        "name": "APIFY_TOKEN",
        "description": "Apify API token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://console.apify.com/account/integrations"
    }],
    "scrapingbee": [{
        "name": "SCRAPINGBEE_API_KEY",
        "description": "ScrapingBee API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://www.scrapingbee.com/"
    }],
    "bright-data": [{
        "name": "BRIGHT_DATA_TOKEN",
        "description": "Bright Data API token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://brightdata.com/"
    }],
    "browserbase": [{
        "name": "BROWSERBASE_API_KEY",
        "description": "Browserbase API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://www.browserbase.com/"
    }],
    "playwright": [],  # No credentials required - local tool

    # === Monitoring & Observability ===
    "dynatrace": [{
        "name": "DYNATRACE_API_TOKEN",
        "description": "Dynatrace API token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://www.dynatrace.com/support/help/dynatrace-api"
    }],
    "newrelic": [{
        "name": "NEW_RELIC_API_KEY",
        "description": "New Relic API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://docs.newrelic.com/docs/apis/intro-apis/new-relic-api-keys/"
    }],
    "pagerduty": [{
        "name": "PAGERDUTY_API_KEY",
        "description": "PagerDuty API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://support.pagerduty.com/docs/api-access-keys"
    }],
    "opsgenie": [{
        "name": "OPSGENIE_API_KEY",
        "description": "Opsgenie API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://support.atlassian.com/opsgenie/docs/api-key-management/"
    }],
    "grafana": [{
        "name": "GRAFANA_API_KEY",
        "description": "Grafana API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://grafana.com/docs/grafana/latest/http_api/auth/"
    }],
    "prometheus": [],  # Usually no credentials, just URL

    # === Finance & Fintech ===
    "plaid": [{
        "name": "PLAID_CLIENT_ID",
        "description": "Plaid client ID",
        "required": True,
        "type": "string",
        "documentation_url": "https://dashboard.plaid.com/"
    }, {
        "name": "PLAID_SECRET",
        "description": "Plaid secret key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://dashboard.plaid.com/"
    }],
    "coinbase": [{
        "name": "COINBASE_API_KEY",
        "description": "Coinbase API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://www.coinbase.com/settings/api"
    }, {
        "name": "COINBASE_API_SECRET",
        "description": "Coinbase API secret",
        "required": True,
        "type": "secret",
        "documentation_url": "https://www.coinbase.com/settings/api"
    }],
    "binance": [{
        "name": "BINANCE_API_KEY",
        "description": "Binance API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://www.binance.com/en/my/settings/api-management"
    }, {
        "name": "BINANCE_API_SECRET",
        "description": "Binance API secret",
        "required": True,
        "type": "secret",
        "documentation_url": "https://www.binance.com/en/my/settings/api-management"
    }],

    # === Weather & Location ===
    "openweather": [{
        "name": "OPENWEATHER_API_KEY",
        "description": "OpenWeather API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://home.openweathermap.org/api_keys"
    }],
    "google-maps": [{
        "name": "GOOGLE_MAPS_API_KEY",
        "description": "Google Maps API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://console.cloud.google.com/google/maps-apis/credentials"
    }],
    "mapbox": [{
        "name": "MAPBOX_ACCESS_TOKEN",
        "description": "Mapbox access token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://account.mapbox.com/access-tokens/"
    }],

    # === E-commerce ===
    "shopify": [{
        "name": "SHOPIFY_ACCESS_TOKEN",
        "description": "Shopify Admin API access token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://shopify.dev/docs/apps/auth"
    }],
    "woocommerce": [{
        "name": "WOOCOMMERCE_KEY",
        "description": "WooCommerce consumer key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://woocommerce.github.io/woocommerce-rest-api-docs/#authentication"
    }, {
        "name": "WOOCOMMERCE_SECRET",
        "description": "WooCommerce consumer secret",
        "required": True,
        "type": "secret",
        "documentation_url": "https://woocommerce.github.io/woocommerce-rest-api-docs/#authentication"
    }],

    # === Knowledge & Documentation ===
    "wikipedia": [],  # No credentials required
    "wolfram-alpha": [{
        "name": "WOLFRAM_APP_ID",
        "description": "Wolfram Alpha App ID",
        "required": True,
        "type": "secret",
        "documentation_url": "https://developer.wolframalpha.com/portal/myapps/"
    }],

    # === Social Media ===
    "twitter": [{
        "name": "TWITTER_BEARER_TOKEN",
        "description": "Twitter API v2 Bearer token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://developer.twitter.com/en/portal/dashboard"
    }],
    "linkedin": [{
        "name": "LINKEDIN_ACCESS_TOKEN",
        "description": "LinkedIn OAuth access token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://www.linkedin.com/developers/"
    }],
    "reddit": [{
        "name": "REDDIT_CLIENT_ID",
        "description": "Reddit app client ID",
        "required": True,
        "type": "string",
        "documentation_url": "https://www.reddit.com/prefs/apps"
    }, {
        "name": "REDDIT_CLIENT_SECRET",
        "description": "Reddit app client secret",
        "required": True,
        "type": "secret",
        "documentation_url": "https://www.reddit.com/prefs/apps"
    }],
    "facebook": [{
        "name": "FACEBOOK_ACCESS_TOKEN",
        "description": "Facebook Graph API access token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://developers.facebook.com/"
    }],
    "instagram": [{
        "name": "INSTAGRAM_ACCESS_TOKEN",
        "description": "Instagram Graph API access token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://developers.facebook.com/docs/instagram-api"
    }],

    # === Design ===
    "figma": [{
        "name": "FIGMA_ACCESS_TOKEN",
        "description": "Figma personal access token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://www.figma.com/developers/api#access-tokens"
    }],
    "canva": [{
        "name": "CANVA_ACCESS_TOKEN",
        "description": "Canva Connect API access token",
        "required": True,
        "type": "secret",
        "documentation_url": "https://www.canva.dev/"
    }],

    # === Local/No credentials ===
    "filesystem": [],
    "time": [],
    "memory": [],
    "puppeteer": [],  # Browser automation - local Chromium
    "fetch": [],      # HTTP client - no credentials needed
    "docker": [],     # Local Docker access

    # === Spreadsheet & Data ===
    "grist": [{
        "name": "GRIST_API_KEY",
        "description": "Grist API key for document access",
        "required": True,
        "type": "secret",
        "documentation_url": "https://support.getgrist.com/api/"
    }, {
        "name": "GRIST_API_URL",
        "description": "Grist instance API URL",
        "required": True,
        "type": "url",
        "documentation_url": "https://support.getgrist.com/api/"
    }],
    "brave-search": [{
        "name": "BRAVE_API_KEY",
        "description": "Brave Search API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://brave.com/search/api/"
    }],
    "tavily": [{
        "name": "TAVILY_API_KEY",
        "description": "Tavily Search API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://tavily.com/"
    }],
    "exa": [{
        "name": "EXA_API_KEY",
        "description": "Exa Search API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://exa.ai/"
    }],
    "serper": [{
        "name": "SERPER_API_KEY",
        "description": "Serper (Google Search) API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://serper.dev/"
    }],
    "serpapi": [{
        "name": "SERPAPI_KEY",
        "description": "SerpAPI key for search results",
        "required": True,
        "type": "secret",
        "documentation_url": "https://serpapi.com/"
    }],

    # === SAP ===
    "sap": [{
        "name": "SAP_API_KEY",
        "description": "SAP API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://api.sap.com/"
    }],
    "sap-fiori": [{
        "name": "SAP_FIORI_API_KEY",
        "description": "SAP Fiori API key",
        "required": True,
        "type": "secret",
        "documentation_url": "https://api.sap.com/"
    }],
}


# =============================================================================
# NOTE: IconResolver has been extracted to marketplace/icon_resolver.py
# =============================================================================
# - IconResolver class -> icon_resolver.py
# - generate_icon_search_terms() -> icon_resolver.py
# - resolve_icon_url() -> icon_resolver.py
#
# All icon functions are imported from .marketplace.icon_resolver at the top.
# =============================================================================


# [REMOVED: IconResolver class - now in icon_resolver.py]
# [REMOVED: generate_icon_search_terms() - now in icon_resolver.py]
# [REMOVED: resolve_icon_url() - now in icon_resolver.py]
# [REMOVED: ~310 lines of icon resolution code - see marketplace/icon_resolver.py]


# =============================================================================
# NOTE: Source classes have been extracted to marketplace/sources/
# =============================================================================
# - MarketplaceSource ABC -> sources/base.py
# - NPMSource -> sources/npm_source.py
# - GitHubSource -> sources/github_source.py
# - BigMCPSource -> sources/bigmcp_source.py
#
# All sources are imported from .marketplace.sources at the top of this file.
# The original class definitions below have been removed.
# =============================================================================


# [REMOVED: NPMSource class - now in sources/npm_source.py]
# [REMOVED: GlamaSource class (commented) - not extracted]
# [REMOVED: GitHubSource class - now in sources/github_source.py]
# [REMOVED: BigMCPSource class - now in sources/bigmcp_source.py]
# [REMOVED: ~500 lines of source class implementations - see sources/*.py]


# =============================================================================
# NOTE: Source classes have been extracted to marketplace/sources/
# =============================================================================
# - MarketplaceSource ABC -> sources/base.py
# - NPMSource -> sources/npm_source.py
# - GitHubSource -> sources/github_source.py
# - BigMCPSource -> sources/bigmcp_source.py
#
# All sources are imported from .marketplace.sources at the top of this file.
# The original class definitions below have been removed.
# =============================================================================


# [REMOVED: NPMSource class - now in sources/npm_source.py]
# [REMOVED: GlamaSource class (commented) - not extracted]
# [REMOVED: GitHubSource class - now in sources/github_source.py]
# [REMOVED: BigMCPSource class - now in sources/bigmcp_source.py]
# [REMOVED: ~500 lines of source class implementations - see sources/*.py]


# =============================================================================
# Custom Server Loading (Local Registry)
# =============================================================================


async def load_custom_servers_from_registry(registry_path: Optional[Path] = None) -> List[MarketplaceServer]:
    """
    Load custom servers from mcp_servers.json (Local Registry).

    This function is called AFTER all marketplace processing to ensure
    custom server credentials are never overwritten by deduplication or analysis.

    Format in mcp_servers.json:
    {
        "mcpServers": {
            "server_id": {
                "command": "...",
                "args": [...],
                "env": {"VAR": "${VAR}"},
                "_metadata": {
                    "name": "...",
                    "description": "...",
                    "credentials": [...],
                    "install": {...}
                }
            }
        }
    }
    """
    servers = []
    path = registry_path or Path(__file__).parent.parent.parent / "conf" / "mcp_servers.json"

    try:
        if not path.exists():
            logger.debug(f"Custom registry not found: {path}")
            return servers

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        mcp_servers = data.get("mcpServers", {})

        for server_id, server_data in mcp_servers.items():
            metadata = server_data.get("_metadata", {})

            # Skip servers not visible in marketplace
            if not metadata.get("visible_in_marketplace", True):
                continue

            # Parse credentials from _metadata (authoritative source)
            credentials = []
            for cred_data in metadata.get("credentials", []):
                credentials.append(CredentialSpec(
                    name=cred_data.get("name", ""),
                    description=cred_data.get("description", ""),
                    required=cred_data.get("required", True),
                    type=cred_data.get("type", "secret"),
                    config_type=cred_data.get("configType", "remote"),
                    default=cred_data.get("default"),
                    example=cred_data.get("example"),
                    documentation_url=cred_data.get("documentationUrl")
                ))

            # Get install info
            install_info = metadata.get("install", {})
            install_type_str = install_info.get("type", "pip")
            try:
                install_type = InstallationType(install_type_str)
            except ValueError:
                install_type = InstallationType.NPM

            server = MarketplaceServer(
                id=server_id,
                name=metadata.get("name", server_id),
                description=metadata.get("description", ""),
                install_type=install_type,
                install_package=install_info.get("package", install_info.get("image", "")),
                command=server_data.get("command"),
                args=server_data.get("args", []),
                env=server_data.get("env", {}),  # Copy env from local registry
                source=ServerSource.CUSTOM,
                source_url=metadata.get("repository"),
                repository=metadata.get("repository"),
                author=metadata.get("author"),
                icon_url=metadata.get("iconUrl"),
                credentials=credentials,
                category=metadata.get("category"),
                tags=metadata.get("tags", []),
                verified=metadata.get("verified", False),
                popularity=metadata.get("popularity", 50),
                tools=[],
                tools_preview=metadata.get("toolsPreview", []),
                requires_local_access=not metadata.get("saas_compatible", True),
                discovered_at=datetime.utcnow(),
                is_curated=True  # Custom servers are admin-defined, preserve their data
            )
            servers.append(server)

        if servers:
            logger.info(f"Loaded {len(servers)} custom servers from Local Registry")

    except Exception as e:
        logger.error(f"Error loading custom servers from registry: {e}", exc_info=True)

    return servers


class MarketplaceSyncService:
    """
    Main service for marketplace synchronization and management.

    Features:
    - Multi-source aggregation (npm, GitHub, local)
    - Deduplication and normalization
    - Caching with TTL
    - Search and filtering
    - Background sync scheduling

    Future sources (commented for development):
    - Glama.ai (11k+ servers)
    - Smithery.ai (3k+ integrations)
    """

    def __init__(
        self,
        cache_ttl: int = 3600,  # 1 hour default
        sync_interval: int = 86400,  # 24 hours default
        enable_npm: bool = True,
        enable_github: bool = True,
        enable_glama: bool = False,  # Disabled by default
        enable_smithery: bool = False,  # Disabled by default
    ):
        self.cache_ttl = cache_ttl
        self.sync_interval = sync_interval

        # Source toggles
        self._enable_npm = enable_npm
        self._enable_github = enable_github
        self._enable_glama = enable_glama
        self._enable_smithery = enable_smithery

        # In-memory cache
        self._servers: Dict[str, MarketplaceServer] = {}
        self._categories: Dict[str, Dict] = {}
        self._last_sync: Optional[datetime] = None
        self._cache_expires: Optional[datetime] = None

        # Lock to prevent concurrent sync operations
        self._sync_lock = asyncio.Lock()
        self._syncing = False

        # HTTP client
        self.http_client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "MCPHub-Marketplace/1.0"}
        )

        # Build sources list based on configuration
        self.sources: List[MarketplaceSource] = self._build_sources()

        # Vector store for semantic search
        embedding_config = EmbeddingConfig()
        self.vector_store = VectorStore(config=embedding_config)
        logger.info("Initialized vector store for marketplace semantic search")

        # Source priority (lower = higher priority for deduplication)
        self.source_priority = {
            ServerSource.BIGMCP: 0,
            ServerSource.OFFICIAL: 1,
            ServerSource.NPM: 2,
            ServerSource.GITHUB: 3,
            ServerSource.GLAMA: 4,
            ServerSource.SMITHERY: 5,
            ServerSource.CUSTOM: 6,
        }

    def invalidate_cache(self):
        """
        Invalidate the marketplace cache.

        This forces a fresh sync on the next request, ensuring that
        any changes to local registry servers are immediately visible.
        """
        logger.info("Invalidating marketplace cache")
        self._cache_expires = None
        self._last_sync = None

    async def load_from_cache_file(self) -> bool:
        """
        Load marketplace from cache file (marketplace_registry.json) if it exists.

        Returns:
            True if cache was loaded successfully, False otherwise
        """
        registry_path = self._get_marketplace_registry_path()

        if not registry_path.exists():
            logger.info("No marketplace cache file found at %s", registry_path)
            return False

        try:
            with open(registry_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Parse metadata
            last_updated = data.get("lastUpdated")
            servers_data = data.get("servers", {})
            categories_data = data.get("categories", {})

            if not servers_data:
                logger.warning("Cache file has no servers, skipping load")
                return False

            # Parse each server entry back into MarketplaceServer
            loaded_count = 0
            for server_id, server_entry in servers_data.items():
                try:
                    server = self._parse_server_from_registry(server_entry)
                    self._servers[server_id] = server
                    loaded_count += 1
                except Exception as e:
                    logger.warning(f"Failed to parse server {server_id}: {e}")
                    continue

            # Load categories
            self._categories = categories_data

            # Set cache expiration
            self._last_sync = datetime.fromisoformat(last_updated) if last_updated else datetime.utcnow()
            self._cache_expires = datetime.utcnow() + timedelta(seconds=self.cache_ttl)

            logger.info(f"✅ Loaded {loaded_count}/{len(servers_data)} servers from marketplace cache")
            logger.info(f"Cache expires in {self.cache_ttl} seconds")

            return True

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse marketplace cache: {e}")
            return False
        except Exception as e:
            logger.error(f"Error loading marketplace cache: {e}", exc_info=True)
            return False

    def _parse_server_from_registry(self, entry: Dict[str, Any]) -> MarketplaceServer:
        """
        Parse a server entry from registry JSON format back to MarketplaceServer.

        This is the inverse of _server_to_registry_format().
        """
        # Parse install config
        install_config = entry.get("install", {})
        install_type = InstallationType(install_config.get("type", "npm"))
        install_package = install_config.get("package", "")

        # Parse credentials
        # Note: JSON uses camelCase keys (configType, documentationUrl)
        credentials = []
        for cred_data in entry.get("credentials", []):
            credentials.append(CredentialSpec(
                name=cred_data.get("name", ""),
                description=cred_data.get("description", ""),
                required=cred_data.get("required", True),
                type=cred_data.get("type", "secret"),
                config_type=cred_data.get("configType", cred_data.get("config_type", "remote")),
                default=cred_data.get("default"),
                example=cred_data.get("example"),
                documentation_url=cred_data.get("documentationUrl", cred_data.get("documentation_url"))
            ))

        # Parse source
        source_str = entry.get("source", "npm")
        try:
            source = ServerSource(source_str)
        except ValueError:
            source = ServerSource.NPM

        # Create MarketplaceServer object
        return MarketplaceServer(
            id=entry.get("id", ""),
            name=entry.get("name", ""),
            description=entry.get("description", ""),
            install_type=install_type,
            install_package=install_package,
            command=entry.get("command"),
            args=entry.get("args", []),
            env=entry.get("env", {}),
            source=source,
            source_url=entry.get("sourceUrl"),
            repository=entry.get("repository"),
            author=entry.get("author"),
            version=entry.get("version"),
            icon_url=entry.get("iconUrl"),
            credentials=credentials,
            category=entry.get("category"),
            tags=entry.get("tags", []),
            verified=entry.get("verified", False),
            popularity=entry.get("popularity", 0),
            downloads_weekly=entry.get("downloadsWeekly"),
            tools=entry.get("tools", []),
            tools_preview=entry.get("toolsPreview", []),
            requires_local_access=entry.get("requiresLocalAccess", False),
            is_curated=(source == ServerSource.BIGMCP or entry.get("serviceId") is not None),
            service_id=entry.get("serviceId")
        )

    async def add_custom_server_to_cache(self, server_id: str) -> bool:
        """
        Add a single custom server directly to the in-memory cache.

        This avoids a full resync when a new custom server is added.
        The server is loaded from mcp_servers.json and added to self._servers.

        Args:
            server_id: The ID of the custom server to add

        Returns:
            True if server was added successfully, False otherwise
        """
        try:
            # Load fresh custom servers from registry
            custom_servers = await load_custom_servers_from_registry()

            # Find the specific server
            server = next((s for s in custom_servers if s.id == server_id), None)

            if server:
                self._servers[server_id] = server
                logger.info(f"Added custom server '{server_id}' directly to marketplace cache")
                return True
            else:
                logger.warning(f"Custom server '{server_id}' not found in registry")
                return False

        except Exception as e:
            logger.error(f"Error adding custom server to cache: {e}", exc_info=True)
            return False

    def remove_server_from_cache(self, server_id: str) -> bool:
        """
        Remove a server from the in-memory cache.

        Args:
            server_id: The ID of the server to remove

        Returns:
            True if server was removed, False if not found
        """
        if server_id in self._servers:
            del self._servers[server_id]
            logger.info(f"Removed server '{server_id}' from marketplace cache")
            return True
        return False

    def _deduplicate_credentials(self, credentials: List[Dict[str, Any]], service_name: str = "") -> List[Dict[str, Any]]:
        """
        Deduplicate credentials that refer to the same underlying secret.

        For example: NOTION_API_KEY, NOTION_TOKEN, AUTH_TOKEN → Keep only NOTION_API_KEY

        Priority order (higher = keep):
        1. SERVICE_API_KEY (e.g., NOTION_API_KEY)
        2. SERVICE_TOKEN (e.g., NOTION_TOKEN)
        3. SERVICE_SECRET (e.g., NOTION_SECRET)
        4. Generic names (TOKEN, AUTH_TOKEN, API_KEY)
        """
        if not credentials:
            return []

        # Extract service prefix from service_name
        service_prefix = service_name.upper().replace(" ", "_").replace("-", "_") if service_name else ""

        # Group credentials by their "service" (prefix before _API_KEY, _TOKEN, etc.)
        groups: Dict[str, List[Dict[str, Any]]] = {}

        for cred in credentials:
            name = cred.get("name", "").upper()

            # Determine the service this credential belongs to
            service = None

            # Check if it starts with the expected service prefix
            if service_prefix and name.startswith(service_prefix):
                service = service_prefix
            else:
                # Try to extract service from the credential name
                # E.g., NOTION_API_KEY -> NOTION, GITHUB_TOKEN -> GITHUB
                for suffix in ["_API_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_KEY", "_AUTH"]:
                    if name.endswith(suffix):
                        service = name[:-len(suffix)]
                        break

                # If still no service, check if it's a generic credential
                if not service:
                    if name in ["TOKEN", "AUTH_TOKEN", "API_KEY", "SECRET", "PASSWORD"]:
                        service = "GENERIC"
                    else:
                        service = name  # Keep as unique

            if service not in groups:
                groups[service] = []
            groups[service].append(cred)

        # Select the best credential from each group
        result = []
        for service, creds in groups.items():
            if len(creds) == 1:
                result.append(creds[0])
            else:
                # Sort by priority (most descriptive first)
                def priority(c):
                    n = c.get("name", "").upper()
                    if "_API_KEY" in n:
                        return 0  # Best
                    if "_TOKEN" in n and "AUTH" not in n:
                        return 1
                    if "_SECRET" in n:
                        return 2
                    if n in ["TOKEN", "AUTH_TOKEN", "API_KEY"]:
                        return 10  # Generic - worst
                    return 5  # Default

                creds.sort(key=priority)
                result.append(creds[0])  # Keep the best one

        return result

    def _normalize_service_id(self, raw_service_id: str) -> Optional[str]:
        """
        Normalize service_id to match KNOWN_SERVICE_CREDENTIALS keys.

        Handles variations like:
        - "supabase-mcp" -> "supabase"
        - "server-github" -> "github"
        - "mcp-notion" -> "notion"
        - "openai-api" -> "openai"

        Returns the matched template key or None if no match.
        """
        if not raw_service_id:
            return None

        service_id = raw_service_id.lower().strip()

        # 1. Exact match
        if service_id in KNOWN_SERVICE_CREDENTIALS:
            return service_id

        # 2. Remove common prefixes/suffixes
        prefixes_to_remove = ["mcp-", "server-", "@modelcontextprotocol/server-", "mcp_"]
        suffixes_to_remove = ["-mcp", "-server", "-api", "-sdk", "-client", "_mcp", "_server"]

        normalized = service_id
        for prefix in prefixes_to_remove:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
        for suffix in suffixes_to_remove:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)]

        if normalized in KNOWN_SERVICE_CREDENTIALS:
            return normalized

        # 3. Check if any known service is contained in the service_id
        # e.g., "my-supabase-integration" contains "supabase"
        for known_service in KNOWN_SERVICE_CREDENTIALS.keys():
            if known_service in service_id:
                return known_service

        # 4. Check server name as fallback
        return None

    def _apply_credential_template(
        self,
        server_dict: Dict[str, Any],
        curation: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Apply credential templates ONLY if no credentials exist from source.

        Priority (source credentials are ALWAYS preserved):
        1. Source credentials (bigmcp_source.json, mcp_servers.json) - NEVER overwritten
        2. KNOWN_SERVICE_CREDENTIALS template (fallback for servers without credentials)
        3. LLM-curated credentials (fallback for unknown services)

        Modifies server_dict in place.
        """
        # If server already has credentials from source, preserve them
        existing_creds = server_dict.get("credentials", [])
        if existing_creds and len(existing_creds) > 0:
            # Source credentials exist - just update metadata, don't overwrite
            server_dict["requires_credentials"] = any(
                c.get("required", False) for c in existing_creds
            )
            server_dict["credentials_source"] = "source"
            return

        # No source credentials - try fallbacks
        raw_service_id = server_dict.get("service_id", "")
        server_id = server_dict.get("id", "")
        server_name = server_dict.get("name", "")

        # Try to match against known services (with normalization)
        matched_service = self._normalize_service_id(raw_service_id)
        if not matched_service:
            matched_service = self._normalize_service_id(server_id)
        if not matched_service:
            matched_service = self._normalize_service_id(server_name)

        if matched_service:
            # Use template as fallback for servers without source credentials
            template_creds = KNOWN_SERVICE_CREDENTIALS[matched_service]
            server_dict["credentials"] = template_creds
            server_dict["requires_credentials"] = any(
                c.get("required", False) for c in template_creds
            )
            server_dict["credentials_source"] = "template"
            server_dict["matched_service"] = matched_service
        elif curation and "credentials" in curation:
            # Use LLM-curated credentials for unknown services
            server_dict["credentials"] = curation["credentials"]
            server_dict["requires_credentials"] = any(
                c.get("required", False) for c in curation["credentials"]
            )
            server_dict["credentials_source"] = "llm_curated"

    def _build_sources(self) -> List[MarketplaceSource]:
        """Build list of enabled sources."""
        sources = [
            # BigMCP source always enabled (curated base)
            BigMCPSource(self.http_client),
        ]

        if self._enable_github:
            sources.append(GitHubSource(self.http_client))

        if self._enable_npm:
            sources.append(NPMSource(self.http_client))

        # Future: Uncomment when ready for production
        # if self._enable_glama:
        #     sources.append(GlamaSource(self.http_client))
        # if self._enable_smithery:
        #     sources.append(SmitherySource(self.http_client))

        return sources

    async def sync(
        self,
        force: bool = False,
        run_curation: bool = True,
        curation_batch_size: int = 5,
        curation_max_servers: int = 50,
        auto_persist: bool = True
    ) -> Dict[str, Any]:
        """
        Synchronize servers from all sources with integrated curation.

        Pipeline order:
        1. Fetch from all sources
        2. Curate new servers (generates service_id)
        3. Deduplicate by service_id
        4. Static analysis (tool descriptions for ALL npm/pip servers)
        5. Resolve icons
        6. Load custom servers (LAST - never deduplicated)
        7. Build vector index
        8. Auto-persist to marketplace_registry.json (if enabled)

        Args:
            force: Force sync even if cache is valid
            run_curation: Run LLM curation on new servers (default: True)
            curation_batch_size: Number of servers to curate per LLM batch
            curation_max_servers: Maximum new servers to curate in one sync
            auto_persist: Persist to marketplace_registry.json after sync (default: True)

        Returns:
            Sync statistics
        """
        # Check if sync needed (before acquiring lock for quick return)
        if not force and self._cache_expires and datetime.utcnow() < self._cache_expires:
            logger.info("Cache still valid, skipping sync")
            return {
                "status": "cached",
                "servers_count": len(self._servers),
                "cache_expires": self._cache_expires.isoformat()
            }

        # Use lock to prevent concurrent sync operations
        async with self._sync_lock:
            # Double-check cache after acquiring lock (another sync might have completed)
            if not force and self._cache_expires and datetime.utcnow() < self._cache_expires:
                logger.info("Cache became valid while waiting for lock, skipping sync")
                return {
                    "status": "cached",
                    "servers_count": len(self._servers),
                    "cache_expires": self._cache_expires.isoformat()
                }

            if self._syncing:
                logger.info("Sync already in progress, waiting...")
                return {
                    "status": "in_progress",
                    "servers_count": len(self._servers)
                }

            self._syncing = True
            try:
                result = await self._do_sync(
                    force=force,
                    run_curation=run_curation,
                    curation_batch_size=curation_batch_size,
                    curation_max_servers=curation_max_servers
                )

                # Auto-persist to marketplace_registry.json after successful sync
                if auto_persist and result.get("status") == "synced":
                    try:
                        persist_result = await self.persist_validated_servers()
                        result["auto_persisted"] = True
                        result["persistence"] = persist_result
                        logger.info(f"Auto-persisted {persist_result.get('servers_saved', 0)} servers to marketplace_registry.json")
                    except Exception as e:
                        logger.warning(f"Auto-persist failed (non-fatal): {e}")
                        result["auto_persisted"] = False
                        result["persistence_error"] = str(e)

                return result
            finally:
                self._syncing = False

    async def _do_sync(
        self,
        force: bool = False,
        run_curation: bool = True,
        curation_batch_size: int = 5,
        curation_max_servers: int = 50
    ) -> Dict[str, Any]:
        """
        Internal sync implementation with integrated curation pipeline.

        Pipeline order:
        1. Fetch from all sources
        2. Curate new servers (generates service_id)
        3. Deduplicate by service_id
        4. Static analysis (tool descriptions for ALL npm/pip servers)
        5. Resolve icons
        6. Load custom servers (LAST - never deduplicated)
        7. Build vector index

        Args:
            force: Force sync even if cache is valid
            run_curation: Run LLM curation on new servers (default True)
            curation_batch_size: Number of servers to curate per LLM batch
            curation_max_servers: Maximum new servers to curate in one sync
        """
        logger.info("Starting marketplace sync with integrated curation...")
        stats = {
            "status": "synced",
            "sources": {},
            "total_fetched": 0,
            "total_after_dedup": 0,
            "curation": {"new_curated": 0, "from_cache": 0, "errors": []},
            "deduplication": {"duplicates_removed": 0, "unique_services": 0},
            "sync_time": None
        }

        start_time = datetime.utcnow()
        all_servers: List[MarketplaceServer] = []

        # ========================================
        # STEP 1: Fetch from all sources in parallel
        # ========================================
        logger.info("Step 1/6: Fetching servers from all sources...")
        tasks = [source.fetch_servers() for source in self.sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for source, result in zip(self.sources, results):
            source_name = source.__class__.__name__

            if isinstance(result, Exception):
                logger.error(f"Source {source_name} failed: {result}")
                stats["sources"][source_name] = {"error": str(result)}
            else:
                all_servers.extend(result)
                stats["sources"][source_name] = {"count": len(result)}
                stats["total_fetched"] += len(result)

        logger.info(f"Fetched {stats['total_fetched']} servers from {len(self.sources)} sources")

        # ========================================
        # STEP 2: Curate servers (before deduplication)
        # ========================================
        logger.info("Step 2/6: Running curation pipeline...")
        self._init_llm_curation()

        # Build temporary dict for identification
        temp_servers = self._deduplicate(all_servers)  # Initial dedup by package_key

        if run_curation:
            # Identify servers not yet curated
            new_servers = self._identify_new_servers(temp_servers)

            if new_servers:
                # Limit to max_servers
                to_curate = new_servers[:curation_max_servers]
                curated_count = 0
                errors = []

                logger.info(f"Curating {len(to_curate)} new servers (max {curation_max_servers})...")

                # Process in batches
                for i in range(0, len(to_curate), curation_batch_size):
                    batch = to_curate[i:i + curation_batch_size]

                    curation_tasks = [self._curate_server_with_llm(s) for s in batch]
                    curation_results = await asyncio.gather(*curation_tasks, return_exceptions=True)

                    for server, result in zip(batch, curation_results):
                        if isinstance(result, Exception):
                            errors.append(f"{server.id}: {str(result)}")
                        else:
                            # Store in cache
                            cache_key = result.get("package_key", self._get_dedup_key(server))
                            self._curated_cache[cache_key] = result
                            curated_count += 1

                            # Apply curation to server
                            self._apply_curation_to_server(server, result)

                    logger.info(f"Curated batch {i//curation_batch_size + 1}/{(len(to_curate) + curation_batch_size - 1)//curation_batch_size}")

                    # Rate limiting between batches
                    if i + curation_batch_size < len(to_curate):
                        await asyncio.sleep(2)

                # Save updated cache
                self._save_curated_cache()

                stats["curation"]["new_curated"] = curated_count
                stats["curation"]["errors"] = errors
                logger.info(f"Curated {curated_count} new servers, {len(errors)} errors")
            else:
                logger.info("No new servers to curate")

        # Apply existing curation data to servers that need it
        # Skip BIGMCP (already curated in bigmcp_source.json) and CUSTOM (admin-defined)
        # OFFICIAL/NPM/GITHUB are external sources that need curation enrichment
        curated_cache = self._load_curated_cache()
        for server in temp_servers.values():
            # Skip servers that don't need curation:
            # - BIGMCP: already curated in bigmcp_source.json
            # - CUSTOM: admin-defined metadata is authoritative
            if server.source in (ServerSource.BIGMCP, ServerSource.CUSTOM):
                continue

            cache_key = self._get_dedup_key(server)
            if cache_key in curated_cache:
                self._apply_curation_to_server(server, curated_cache[cache_key])
                stats["curation"]["from_cache"] += 1

        # ========================================
        # STEP 3: Deduplicate by service_id
        # ========================================
        logger.info("Step 3/7: Deduplicating by service_id...")
        self._servers, dedup_stats = self._deduplicate_by_service_integrated(temp_servers, curated_cache)
        stats["total_after_dedup"] = len(self._servers)
        stats["deduplication"] = dedup_stats
        logger.info(f"After dedup: {len(self._servers)} servers ({dedup_stats['duplicates_removed']} removed)")

        # ========================================
        # STEP 4: Static analysis for ALL npm/pip servers
        # ========================================
        # This runs on ALL servers (including BIGMCP) to get tool descriptions
        # The analysis enriches tools with descriptions without overwriting curated data
        logger.info("Step 4/7: Running static analysis on all npm/pip servers...")
        static_stats = await self._run_static_analysis_on_new_servers(limit=0)  # 0 = no limit
        stats["static_analysis"] = static_stats
        logger.info(
            f"Static analysis: {static_stats['analyzed']} analyzed, "
            f"{static_stats['tools_found']} tools found"
        )

        # ========================================
        # STEP 5: Resolve icons
        # ========================================
        logger.info("Step 5/7: Resolving icons...")
        self._resolve_icons(self._servers)

        # Update cache timestamps
        self._last_sync = datetime.utcnow()
        self._cache_expires = self._last_sync + timedelta(seconds=self.cache_ttl)

        # ========================================
        # STEP 6: Add custom servers (AFTER all processing)
        # ========================================
        logger.info("Step 6/7: Loading custom servers from registry...")
        try:
            custom_servers = await load_custom_servers_from_registry()
            custom_needing_analysis = []
            for server in custom_servers:
                existing = self._servers.get(server.id)
                if existing:
                    # Merge: preserve tools from existing server if custom has none
                    if existing.tools and not server.tools:
                        server.tools = existing.tools
                        logger.info(f"Preserved {len(server.tools)} tools from BigMCP for custom server {server.id}")
                    if existing.tools_preview and not server.tools_preview:
                        server.tools_preview = existing.tools_preview
                elif not server.tools:
                    # Custom server without existing match and no tools - needs static analysis
                    custom_needing_analysis.append(server)
                self._servers[server.id] = server

            # Run static analysis on custom servers that need it
            for server in custom_needing_analysis:
                if server.install_type in (InstallationType.NPM, InstallationType.PIP):
                    try:
                        result = await self._run_static_analysis(server)
                        if result and result.get("tools_count", 0) > 0:
                            logger.info(f"Static analysis added {result['tools_count']} tools to custom server {server.id}")
                    except Exception as e:
                        logger.warning(f"Static analysis failed for custom server {server.id}: {e}")

            if custom_servers:
                stats["custom_servers"] = len(custom_servers)
                logger.info(f"Loaded {len(custom_servers)} custom servers")
        except Exception as e:
            logger.error(f"Error loading custom servers: {e}", exc_info=True)

        # ========================================
        # STEP 7: Build vector index
        # ========================================
        logger.info("Step 7/7: Building vector index...")
        try:
            servers_list = []
            for server in self._servers.values():
                server_dict = {
                    "id": server.id,
                    "name": server.name,
                    "description": server.description,
                    "tags": " ".join(server.tags),
                    "category": server.category or "",
                    "tools_preview": " ".join(server.tools_preview)
                }
                servers_list.append(server_dict)

            self.vector_store.build_index(servers_list)
            logger.info(f"✅ Vector index built with {len(servers_list)} servers")
        except Exception as e:
            logger.error(f"Error building vector index: {e}", exc_info=True)

        stats["sync_time"] = (datetime.utcnow() - start_time).total_seconds()
        stats["cache_expires"] = self._cache_expires.isoformat()

        logger.info(
            f"Sync complete: {stats['total_fetched']} fetched, "
            f"{stats['curation']['new_curated']} curated, "
            f"{stats['total_after_dedup']} after dedup, "
            f"{stats['sync_time']:.2f}s"
        )

        return stats

    def _deduplicate_by_service_integrated(
        self,
        servers: Dict[str, MarketplaceServer],
        curated_cache: Dict[str, Any]
    ) -> tuple[Dict[str, MarketplaceServer], Dict[str, Any]]:
        """
        Deduplicate servers by service_id from curation data.

        Keeps the highest quality variant for each unique service.

        Args:
            servers: Dict of servers (already deduplicated by package_key)
            curated_cache: Dict of curation data with service_id

        Returns:
            Tuple of (deduplicated servers dict, stats dict)
        """
        stats = {
            "unique_services": 0,
            "duplicates_removed": 0,
            "by_package_key": 0  # Servers without service_id (use package_key)
        }

        # Group servers by service_id
        services: Dict[str, List[MarketplaceServer]] = {}

        # First pass: collect BigMCP service identifiers for matching
        # Includes both explicit service_id (if set) and dedup_key (fallback)
        bigmcp_service_ids: Set[str] = set()
        bigmcp_id_to_key: Dict[str, str] = {}  # server.id -> service_id mapping
        for server in servers.values():
            if server.source in (ServerSource.BIGMCP, ServerSource.OFFICIAL):
                # Prefer explicit service_id, fallback to dedup_key
                if server.service_id:
                    bigmcp_service_ids.add(server.service_id)
                    bigmcp_id_to_key[server.id] = server.service_id
                else:
                    dedup_key = self._get_dedup_key(server)
                    bigmcp_service_ids.add(dedup_key)
                    bigmcp_id_to_key[server.id] = dedup_key

        logger.info(f"Dedup: collected {len(bigmcp_service_ids)} BigMCP/Official service IDs")
        # Log some examples for debugging
        sample_ids = sorted(list(bigmcp_service_ids))[:10]
        logger.debug(f"Dedup: sample BigMCP services: {sample_ids}")

        for server_id, server in servers.items():
            cache_key = self._get_dedup_key(server)
            curation = curated_cache.get(cache_key, {})

            # Determine service_id with priority:
            # 1. Explicit service_id from source data (bigmcp_source.json)
            # 2. Curated service_id from LLM curation
            # 3. For BigMCP/Official: use dedup_key
            # 4. Substring match against BigMCP services
            # 5. Fallback: use package_key
            service_id = None

            # Priority 1: Explicit service_id from source data
            if server.service_id:
                service_id = server.service_id
            # Priority 2: Curated service_id from LLM curation
            elif curation.get("service_id"):
                service_id = curation["service_id"]
            # Priority 3: BigMCP/Official without explicit service_id
            elif server.source in (ServerSource.BIGMCP, ServerSource.OFFICIAL):
                service_id = cache_key
            else:
                # Try to match package_key against known BigMCP services
                # This handles NPM servers like "@nexus2520/bitbucket-mcp-server" → "bitbucket"
                if cache_key in bigmcp_service_ids:
                    service_id = cache_key
                else:
                    # Check if any BigMCP service is a substring of the package key
                    for bigmcp_svc in bigmcp_service_ids:
                        if bigmcp_svc in cache_key or cache_key in bigmcp_svc:
                            service_id = bigmcp_svc
                            logger.debug(f"Dedup: {server.id} (key={cache_key}) matched BigMCP service: {bigmcp_svc}")
                            break

            if not service_id:
                # Final fallback - use package_key
                service_id = f"_pkg:{cache_key}"
                stats["by_package_key"] += 1

            if service_id not in services:
                services[service_id] = []
            services[service_id].append(server)

        stats["unique_services"] = len(services)

        # For each service, keep the best variant
        deduped: Dict[str, MarketplaceServer] = {}

        for service_id, variants in services.items():
            if len(variants) == 1:
                # No duplicates
                server = variants[0]
                deduped[server.id] = server
            else:
                # Multiple variants - keep the best one
                stats["duplicates_removed"] += len(variants) - 1

                # Sort by: source_priority > is_official > quality_score > popularity
                # Source priority: BIGMCP (0) > OFFICIAL (1) > NPM (2) > GITHUB (3)
                def sort_key(s: MarketplaceServer):
                    cache_key = self._get_dedup_key(s)
                    curation = curated_cache.get(cache_key, {})
                    # Lower source priority = better (BIGMCP=0 is best)
                    source_priority = self.source_priority.get(s.source, 99)
                    # Invert so higher is better for sorting
                    source_score = 100 - source_priority
                    return (
                        source_score,  # BIGMCP (100) > OFFICIAL (99) > NPM (98) > GITHUB (97)
                        curation.get("is_official", s.source in (ServerSource.OFFICIAL, ServerSource.BIGMCP)),
                        curation.get("quality_score", 0),
                        s.popularity
                    )

                variants.sort(key=sort_key, reverse=True)
                best = variants[0]
                deduped[best.id] = best

                # Log which variant was kept for debugging
                removed_names = [v.name for v in variants[1:]]
                logger.info(
                    f"Dedup service '{service_id}': kept '{best.name}' ({best.source.value}), "
                    f"removed {len(variants) - 1}: {removed_names}"
                )

        return deduped, stats

    def _deduplicate(self, servers: List[MarketplaceServer]) -> Dict[str, MarketplaceServer]:
        """
        Deduplicate servers, keeping highest priority source.

        Uses install_package as primary dedup key, but preserves server.id as dict key.
        This allows lookups by original server ID while still deduplicating by package.
        """
        deduped: Dict[str, MarketplaceServer] = {}
        package_to_server: Dict[str, MarketplaceServer] = {}  # Track by package for dedup

        # Sort by source priority (lower = higher priority)
        servers_sorted = sorted(
            servers,
            key=lambda s: self.source_priority.get(s.source, 99)
        )

        for server in servers_sorted:
            # Generate dedup key based on package
            package_key = self._get_dedup_key(server)

            if package_key not in package_to_server:
                # First time seeing this package
                package_to_server[package_key] = server
                deduped[server.id] = server  # Use server.id as dict key for lookups
            else:
                # Merge metadata from lower priority source
                existing = package_to_server[package_key]
                self._merge_server_metadata(existing, server)

        return deduped

    def _get_dedup_key(self, server: MarketplaceServer) -> str:
        """
        Generate deduplication key for a server.

        Extracts the core server name to match packages like:
        - @modelcontextprotocol/server-slack
        - slack-mcp-server
        - mcp-server-slack
        - mcp_server_slack
        All should deduplicate to "slack"
        """
        # Normalize package name
        package = server.install_package.lower()

        # Step 1: Normalize separators FIRST (before pattern matching)
        # Replace @ / _ with - so all patterns use consistent separator
        package = package.replace("@", "").replace("/", "-").replace("_", "-")

        # Remove duplicate dashes
        while "--" in package:
            package = package.replace("--", "-")
        package = package.strip("-")

        # Step 2: Remove common prefixes and suffixes
        remove_patterns = [
            "modelcontextprotocol-server-",
            "modelcontextprotocol-",
            "-mcp-server",
            "mcp-server-",
            "mcp-",
            "-mcp",
            "-server",
            "server-",
        ]

        for pattern in remove_patterns:
            package = package.replace(pattern, "")

        # Step 3: Final cleanup - remove all separators for final key
        package = package.replace("-", "")

        # Remove common suffixes that remain
        for suffix in ["server", "mcp"]:
            if package.endswith(suffix) and len(package) > len(suffix):
                package = package[:-len(suffix)]

        return package

    def _merge_server_metadata(self, target: MarketplaceServer, source: MarketplaceServer):
        """
        Merge metadata from source into target (if target is missing data).

        This ensures we get the most complete server information by combining
        data from multiple sources (local registry, npm, GitHub, etc.)
        """
        # Fill in missing description (prefer longer descriptions)
        if not target.description and source.description:
            target.description = source.description
        elif target.description and source.description and len(source.description) > len(target.description):
            target.description = source.description

        # Merge tags (union) - keep unique tags from all sources
        target.tags = list(set(target.tags) | set(source.tags))

        # Take higher popularity score
        if source.popularity > target.popularity:
            target.popularity = source.popularity

        # Merge credentials - prefer local/curated credentials, but add any missing ones
        if not target.credentials and source.credentials:
            target.credentials = source.credentials
        elif target.credentials and source.credentials:
            # Merge credentials by name (avoid duplicates)
            target_cred_names = {c.name for c in target.credentials}
            for src_cred in source.credentials:
                if src_cred.name not in target_cred_names:
                    target.credentials.append(src_cred)

        # Merge tools preview - prefer longer list
        if not target.tools_preview and source.tools_preview:
            target.tools_preview = source.tools_preview
        elif target.tools_preview and source.tools_preview:
            # Merge tool lists (union)
            target.tools_preview = list(set(target.tools_preview) | set(source.tools_preview))

        # Fill in missing version
        if not target.version and source.version:
            target.version = source.version

        # Fill in missing repository URL
        if not target.repository and source.repository:
            target.repository = source.repository

        # Fill in missing source URL
        if not target.source_url and source.source_url:
            target.source_url = source.source_url

        # Fill in missing author
        if not target.author and source.author:
            target.author = source.author

        # Fill in missing category (prefer curated categories)
        if not target.category and source.category:
            target.category = source.category

        # Take higher download count
        if source.downloads_weekly and (not target.downloads_weekly or source.downloads_weekly > target.downloads_weekly):
            target.downloads_weekly = source.downloads_weekly

        # Keep most recent update timestamp
        if source.last_updated and (not target.last_updated or source.last_updated > target.last_updated):
            target.last_updated = source.last_updated

        # Fill in missing icon_url
        if not target.icon_url and source.icon_url:
            target.icon_url = source.icon_url

    def _resolve_icons(self, servers: Dict[str, MarketplaceServer]):
        """
        Resolve icon URLs for all servers that need better icons.

        Processes servers that:
        - Have no icon_url
        - Have the generic /mcp fallback icon

        Uses cascading search terms from multiple sources:
        1. Existing icon_search_terms from curated cache (LLM-validated slugs)
        2. server.service_id (explicit, matches SimpleIcons slugs)
        3. Extracted from package name
        4. Derived from server name
        """
        for server in servers.values():
            # Process servers without icon OR with generic /mcp fallback
            needs_icon = not server.icon_url or server.icon_url.endswith('/mcp')

            if needs_icon:
                # Try to get existing icon_search_terms from curated cache
                cache_key = self._get_dedup_key(server)
                curation = self._curated_cache.get(cache_key, {})

                # Priority 1: Use cached icon_search_terms (already validated by LLM)
                icon_search_terms = curation.get("icon_search_terms", [])
                if icon_search_terms:
                    # Use first (best) term from cached search terms
                    server.icon_url = IconResolver.resolve(icon_search_terms[0], server.name)
                else:
                    # Fall back to service_id or extraction
                    server.icon_url = resolve_icon_url(
                        server.name,
                        server.install_package,
                        service_id=server.service_id
                    )

    async def list_servers(
        self,
        category: Optional[str] = None,
        search: Optional[str] = None,
        source: Optional[ServerSource] = None,
        verified_only: bool = False,
        include_duplicates: bool = False,
        saas_compatible: bool = False,
        respect_visibility: bool = True,
        offset: int = 0,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        List available servers with filtering and pagination.

        Args:
            category: Filter by category
            search: Search in name/description
            source: Filter by source
            verified_only: Only return verified servers
            include_duplicates: Include servers marked as duplicates (default: False)
            saas_compatible: Only return servers that work in SaaS mode (no local access required)
            respect_visibility: Filter out hidden servers (default: True, set False for admin)
            offset: Pagination offset
            limit: Maximum results to return

        Returns:
            Paginated list of servers
        """
        # Ensure synced
        if not self._servers:
            await self.sync()

        # Load curated cache to check for duplicates
        self._init_llm_curation()
        self._load_curated_cache()

        # Filter servers
        filtered = list(self._servers.values())

        # Filter out duplicates unless explicitly requested
        if not include_duplicates and self._curated_cache:
            filtered = [
                s for s in filtered
                if not self._curated_cache.get(self._get_dedup_key(s), {}).get("is_duplicate", False)
            ]

        # Filter out unavailable servers (package not found on registry)
        filtered = [s for s in filtered if s.is_available]

        # Filter for SaaS compatibility (exclude servers requiring local access)
        if saas_compatible:
            def is_saas_compatible(s):
                # Check server's requires_local_access flag
                if s.requires_local_access:
                    return False
                # Also check curated cache
                curation = self._curated_cache.get(self._get_dedup_key(s), {})
                if curation.get("requires_local_access", False):
                    return False
                return True

            filtered = [s for s in filtered if is_saas_compatible(s)]

        if category:
            # Use curated category if available, otherwise fall back to original
            def get_effective_category(s):
                curation = self._curated_cache.get(self._get_dedup_key(s), {})
                return curation.get("category") or s.category or "other"

            if category == "other":
                # Match servers with no category (None) or explicitly "other"
                filtered = [s for s in filtered if get_effective_category(s) in [None, "other"]]
            else:
                filtered = [s for s in filtered if get_effective_category(s) == category]

        if source:
            filtered = [s for s in filtered if s.source == source]

        if verified_only:
            filtered = [s for s in filtered if s.verified]

        if search:
            search_lower = search.lower()
            filtered = [
                s for s in filtered
                if search_lower in s.name.lower()
                or search_lower in s.description.lower()
                or any(search_lower in tag.lower() for tag in s.tags)
            ]

        # Filter out hidden servers based on admin visibility config
        if respect_visibility:
            try:
                visibility_path = Path(__file__).parent.parent.parent / "conf" / "server_visibility.json"
                if visibility_path.exists():
                    with open(visibility_path, 'r', encoding='utf-8') as f:
                        visibility_config = json.load(f)
                    filtered = [
                        s for s in filtered
                        if visibility_config.get(s.id, {}).get("visible", True)
                    ]
            except Exception as e:
                logger.warning(f"Failed to load visibility config: {e}")

        # Sort by: official first, then tools count, then quality_score, then popularity
        def sort_key(s):
            key = self._get_dedup_key(s)
            curation = self._curated_cache.get(key, {})
            # Priority 1: Official/LOCAL sources (curated) come first
            is_curated = 1 if s.source in (ServerSource.OFFICIAL, ServerSource.BIGMCP) else 0
            # Priority 2: Has actual tools defined
            tools_count = len(s.tools) if s.tools else 0
            # Priority 3: Quality score from curation
            quality = curation.get("quality_score", 0)
            # Priority 4: Popularity
            pop = s.popularity
            # Penalize generic "Mcp Server" names
            name_penalty = 0 if "mcp server" not in s.name.lower() else -1000
            return (is_curated, tools_count + name_penalty, quality, pop)

        filtered.sort(key=sort_key, reverse=True)

        # Paginate
        total = len(filtered)
        paginated = filtered[offset:offset + limit]

        # Enrich with curation data
        enriched = []
        for server in paginated:
            server_dict = server.to_dict()
            key = self._get_dedup_key(server)
            curation = self._curated_cache.get(key, {})
            if curation:
                # Add curated metadata
                server_dict["service_id"] = curation.get("service_id")
                server_dict["service_display_name"] = curation.get("service_display_name")
                server_dict["icon_urls"] = curation.get("icon_urls")
                server_dict["quality_score"] = curation.get("quality_score")
                server_dict["curated_summary"] = curation.get("summary")
                server_dict["use_cases"] = curation.get("use_cases")
                server_dict["maintenance_status"] = curation.get("maintenance_status")
                # Update category from curation (fixes None categories)
                # BUT: CUSTOM servers keep their admin-defined category
                if curation.get("category") and server.source != ServerSource.CUSTOM:
                    server_dict["category"] = curation["category"]
                # Update tags from curation (only if not CUSTOM source)
                if curation.get("tags") and server.source != ServerSource.CUSTOM:
                    server_dict["tags"] = curation["tags"]
                # Update icon_url from curation if better
                # BUT: CUSTOM servers preserve their original icon_url (admin-defined)
                # AND: data: URLs (base64) are always preserved (guaranteed to work)
                original_icon = server_dict.get("icon_url", "")
                curated_icon = curation.get("icon_url", "")
                if curated_icon and server.source != ServerSource.CUSTOM:
                    # Keep original if it's a data: URL (base64, always works)
                    if not (original_icon and original_icon.startswith("data:")):
                        server_dict["icon_url"] = curated_icon
                # Update author from curation if better (not Unknown)
                # BUT: CUSTOM servers keep their admin-defined author
                curated_author = curation.get("author")
                original_author = server_dict.get("author", "")
                if curated_author and curated_author.lower() not in ["unknown", "none", ""]:
                    # For CUSTOM servers, only supplement if original is empty/unknown
                    if server.source == ServerSource.CUSTOM:
                        if not original_author or original_author.lower() in ["unknown", "none", ""]:
                            server_dict["author"] = curated_author
                    else:
                        server_dict["author"] = curated_author

                # Replace generic names with curated service_display_name
                # BUT: CUSTOM servers always keep their admin-defined name
                if server.source != ServerSource.CUSTOM:
                    original_name = server_dict.get("name", "")
                    display_name = curation.get("service_display_name", "")
                    generic_patterns = ["mcp server", "mcp-server", "server", "local mcp", "api mcp", "ai mcp"]

                    # Check if original name is generic
                    is_generic = any(pattern in original_name.lower() for pattern in generic_patterns)

                    # Use display_name if original is generic and display_name is better
                    if is_generic and display_name and display_name.lower() not in generic_patterns:
                        server_dict["original_name"] = original_name  # Keep original for reference
                        server_dict["name"] = display_name

            # Ensure author is never null/empty - use service_id as fallback
            if not server_dict.get("author") or server_dict["author"] in [None, "", "null", "Unknown"]:
                # Try to extract from package name or use service_id
                service_id = server_dict.get("service_id", "")
                if service_id:
                    server_dict["author"] = service_id
                else:
                    server_dict["author"] = "Community"

            # Apply credential templates (template-first approach)
            self._apply_credential_template(server_dict, curation)

            enriched.append(server_dict)

        return {
            "servers": enriched,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < total
        }

    async def semantic_search(
        self,
        query: str,
        limit: int = 20,
        category: Optional[str] = None,
        verified_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Semantic search using vector store for intelligent server discovery.

        This method uses embeddings and cosine similarity to find servers
        that match the user's natural language query, even if they don't
        contain exact keyword matches.

        Args:
            query: Natural language query (e.g., "synchroniser Notion vers Grist")
            limit: Maximum number of results
            category: Optional category filter
            verified_only: Only return verified servers

        Returns:
            List of matching servers sorted by relevance
        """
        # Ensure synced and indexed
        if not self._servers:
            await self.sync()

        try:
            # Use vector store for semantic search
            server_ids = self.vector_store.search(query, limit=limit * 2)  # Get more for filtering

            # Retrieve full server objects
            results = []
            for server_id in server_ids:
                if server_id in self._servers:
                    server = self._servers[server_id]

                    # Apply filters
                    if category:
                        if category == "other":
                            if server.category is not None and server.category != "other":
                                continue
                        elif server.category != category:
                            continue
                    if verified_only and not server.verified:
                        continue

                    # Convert to dict and apply credential template
                    server_dict = server.to_dict()
                    key = self._get_dedup_key(server)
                    curation = self._curated_cache.get(key, {})

                    # Apply service_id from curation if available
                    if curation.get("service_id"):
                        server_dict["service_id"] = curation["service_id"]

                    # Apply credential template
                    self._apply_credential_template(server_dict, curation)

                    results.append(server_dict)

                    if len(results) >= limit:
                        break

            logger.info(f"Semantic search for '{query}' returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Error in semantic search: {e}", exc_info=True)
            # Fallback to regular substring search
            logger.warning("Falling back to substring search")
            result = await self.list_servers(search=query, limit=limit)
            return result['servers']

    async def get_server(self, server_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed info for a specific server."""
        # Ensure synced
        if not self._servers:
            await self.sync()

        server = self._servers.get(server_id)
        if not server:
            # Try to find by partial match
            for key, srv in self._servers.items():
                if server_id in key or key in server_id:
                    server = srv
                    break

        if server:
            # Convert to dict and apply credential template
            server_dict = server.to_dict()
            key = self._get_dedup_key(server)
            curation = self._curated_cache.get(key, {})

            # Apply service_id from curation if available
            if curation.get("service_id"):
                server_dict["service_id"] = curation["service_id"]

            # Apply credential template
            self._apply_credential_template(server_dict, curation)

            return server_dict

        return None

    async def get_categories(self) -> List[Dict[str, Any]]:
        """Get list of server categories with counts (using curated data, excluding duplicates)."""
        # Ensure synced and curated
        if not self._servers:
            await self.sync()

        self._init_llm_curation()
        self._load_curated_cache()

        category_counts: Dict[str, int] = {}
        for server in self._servers.values():
            key = self._get_dedup_key(server)
            curation = self._curated_cache.get(key, {})

            # Skip duplicates
            if curation.get("is_duplicate"):
                continue

            # Use curated category if available, otherwise original
            cat = curation.get("category") or server.category or "other"
            category_counts[cat] = category_counts.get(cat, 0) + 1

        return [
            {"id": cat, "name": cat.title(), "count": count}
            for cat, count in sorted(category_counts.items(), key=lambda x: -x[1])
        ]

    async def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status and statistics."""
        cache_valid = False
        if self._cache_expires:
            cache_valid = datetime.utcnow() < self._cache_expires
        return {
            "servers_count": len(self._servers),
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            "cache_expires": self._cache_expires.isoformat() if self._cache_expires else None,
            "cache_valid": cache_valid,
            "sources_enabled": {
                "local": True,
                "github": self._enable_github,
                "npm": self._enable_npm,
                "glama": self._enable_glama,
                "smithery": self._enable_smithery,
            },
            "sources_active": [s.__class__.__name__ for s in self.sources]
        }

    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()
        if hasattr(self, 'llm_client'):
            await self.llm_client.aclose()

    # =========================================================================
    # Marketplace Persistence - Save enriched marketplace to registry file
    # =========================================================================

    def _get_marketplace_registry_path(self) -> Path:
        """Get path to marketplace registry file (persistent cache)."""
        return Path(__file__).parent.parent.parent / "conf" / "marketplace_registry.json"

    async def sync_and_persist(
        self,
        force: bool = False,
        persist: bool = True
    ) -> Dict[str, Any]:
        """
        Sync marketplace from all sources and persist to marketplace_registry.json.

        This is the recommended sync method for production:
        1. Fetches servers from all sources (bigmcp, official, npm, github)
        2. Deduplicates external sources (not custom servers)
        3. Applies curated enrichments (icons, service_id, etc.)
        4. Adds custom servers (never deduplicated)
        5. Persists result to marketplace_registry.json

        Note: bigmcp_source.json is READ-ONLY (source of truth).
        marketplace_registry.json is the editable output cache.

        Args:
            force: Force sync even if cache is valid
            persist: Whether to persist to marketplace_registry.json

        Returns:
            Combined sync and persistence statistics
        """
        # First run the normal sync
        sync_stats = await self.sync(force=force)

        persistence_stats = {
            "persisted": False,
            "servers_saved": 0,
            "registry_path": str(self._get_marketplace_registry_path())
        }

        if persist and sync_stats.get("status") in ("synced", "cached"):
            try:
                persistence_stats = await self.persist_validated_servers()
            except Exception as e:
                logger.error(f"Error persisting marketplace: {e}", exc_info=True)
                persistence_stats["error"] = str(e)

        return {
            "sync": sync_stats,
            "persistence": persistence_stats
        }

    async def persist_validated_servers(self) -> Dict[str, Any]:
        """
        Persist current marketplace state to marketplace_registry.json.

        Saves all servers (enriched with curation data) to the registry file.
        This file can be edited and will be used as a cache on next startup.

        Returns:
            Persistence statistics
        """
        registry_path = self._get_marketplace_registry_path()

        if not self._servers:
            return {
                "persisted": False,
                "error": "No servers in memory to persist",
                "servers_saved": 0
            }

        # Load curation data for enrichment
        self._init_llm_curation()
        curated_cache = self._load_curated_cache()

        # Convert servers to registry format
        servers_data = {}
        categories_data = {}

        for server_id, server in self._servers.items():
            # Get curation data for enrichment
            cache_key = self._get_dedup_key(server)
            curation = curated_cache.get(cache_key, {})

            # Convert to registry format
            server_entry = self._server_to_registry_format(server, curation)
            servers_data[server_id] = server_entry

            # Track categories
            cat = server_entry.get("category", "other") or "other"
            if cat not in categories_data:
                categories_data[cat] = {
                    "name": cat.replace("-", " ").title(),
                    "description": f"Servers in {cat} category",
                    "count": 0
                }
            categories_data[cat]["count"] += 1

        # Build registry structure
        registry_data = {
            "$schema": "./marketplace_registry.schema.json",
            "version": "1.0.0",
            "lastUpdated": datetime.utcnow().isoformat(),
            "lastSyncedFrom": {
                "bigmcp_source": True,
                "official": self._enable_github,
                "npm": self._enable_npm,
                "github": self._enable_github,
                "custom": True
            },
            "statistics": {
                "total_servers": len(servers_data),
                "by_source": self._count_servers_by_source(),
                "by_category": {cat: data["count"] for cat, data in categories_data.items()}
            },
            "categories": categories_data,
            "servers": servers_data
        }

        # Save to file
        try:
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            with open(registry_path, 'w', encoding='utf-8') as f:
                json.dump(registry_data, f, indent=2, ensure_ascii=False, default=str)

            logger.info(f"Persisted {len(servers_data)} servers to {registry_path}")

            return {
                "persisted": True,
                "servers_saved": len(servers_data),
                "registry_path": str(registry_path),
                "categories_count": len(categories_data)
            }

        except Exception as e:
            logger.error(f"Error saving marketplace registry: {e}", exc_info=True)
            return {
                "persisted": False,
                "error": str(e),
                "servers_saved": 0
            }

    def _server_to_registry_format(
        self,
        server: MarketplaceServer,
        curation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Convert MarketplaceServer to registry JSON format.

        Merges server data with curation enrichments, respecting source-based rules:
        - CUSTOM: preserve admin-defined values (never override)
        - BIGMCP: already curated in bigmcp_source.json (preserve as-is)
        - OFFICIAL/NPM/GITHUB: external sources, apply curation enrichments
        """
        is_custom = server.source == ServerSource.CUSTOM
        is_curated = server.is_curated  # Loaded from bigmcp_source.json (may have official/bigmcp source)

        # Source-based enrichment rules:
        # - CUSTOM: preserve admin-defined values (never override)
        # - is_curated: already curated in bigmcp_source.json (preserve as-is)
        # - OFFICIAL/NPM/GITHUB: external sources, apply curation enrichments
        if is_custom or is_curated:
            # Preserve original values - no curation override
            name = server.name
            category = server.category or "other"
            tags = server.tags
            author = server.author or "Community"
            icon_url = server.icon_url
        else:
            # Apply curation enrichments for external sources (OFFICIAL, NPM, GITHUB)
            name = curation.get("service_display_name") or server.name
            category = curation.get("category") or server.category or "other"
            tags = curation.get("tags") or server.tags
            author = curation.get("author") or server.author or "Community"
            icon_url = curation.get("icon_url") or server.icon_url

        # Start with base server data
        entry = {
            "id": server.id,
            "name": name,
            "description": server.description,
            "shortDescription": server.description[:200] if server.description else "",
            "author": author,
            "repository": server.repository,
            "category": category,
            "tags": tags,
            "install": {
                "type": server.install_type.value if server.install_type else "npm",
                "package": server.install_package
            },
            "command": server.command,
            "args": server.args,
            "env": server.env,
            "iconUrl": icon_url,
            "iconHint": curation.get("icon_hint") if not is_custom else None,
            "toolsPreview": server.tools_preview,
            "popularity": server.popularity,
            "verified": server.verified,
            "source": server.source.value if server.source else "npm",
            "serviceId": curation.get("service_id"),
            "qualityScore": curation.get("quality_score"),
            "maintenanceStatus": curation.get("maintenance_status"),
            "requiresLocalAccess": server.requires_local_access
        }

        # Add credentials (from server or curation)
        if server.credentials:
            entry["credentials"] = [
                {
                    "name": c.name,
                    "description": c.description,
                    "required": c.required,
                    "type": c.type,
                    "configType": c.config_type,
                    "default": c.default,
                    "example": c.example,
                    "documentationUrl": c.documentation_url
                }
                for c in server.credentials
            ]
        elif curation.get("credentials"):
            entry["credentials"] = curation["credentials"]

        # Add full tools data if available
        if server.tools:
            entry["tools"] = server.tools

        # Clean up None values
        return {k: v for k, v in entry.items() if v is not None}

    def _count_servers_by_source(self) -> Dict[str, int]:
        """Count servers by source type."""
        counts = {}
        for server in self._servers.values():
            source_name = server.source.value if server.source else "unknown"
            counts[source_name] = counts.get(source_name, 0) + 1
        return counts

    # =========================================================================
    # LLM Curation - Analyze and enhance servers with AI
    # =========================================================================

    def _init_llm_curation(self):
        """Initialize LLM curation capabilities (lazy init)."""
        if hasattr(self, '_llm_initialized'):
            return

        # LLM Configuration
        self.llm_url = os.environ.get("LLM_API_URL", "https://api.mistral.ai/v1")
        self.llm_api_key = os.environ.get("LLM_API_KEY", "")
        self.llm_model = os.environ.get("LLM_MODEL", "mistral-small-latest")

        # HTTP client for LLM
        self.llm_client = httpx.AsyncClient(
            timeout=120.0,
            headers={
                "Authorization": f"Bearer {self.llm_api_key}",
                "Content-Type": "application/json"
            }
        )

        # Curated cache file path
        self.curated_cache_path = Path(__file__).parent.parent.parent / "conf" / "curated_servers_cache.json"

        # In-memory curated cache
        self._curated_cache: Dict[str, Dict[str, Any]] = {}

        self._llm_initialized = True
        logger.info("LLM curation initialized")

    def _load_curated_cache(self) -> Dict[str, Dict[str, Any]]:
        """Load previously curated servers from disk."""
        self._init_llm_curation()

        if self._curated_cache:
            return self._curated_cache

        try:
            if self.curated_cache_path.exists():
                with open(self.curated_cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._curated_cache = data.get("servers", {})
                    logger.info(f"Loaded {len(self._curated_cache)} curated servers from cache")
        except Exception as e:
            logger.error(f"Error loading curated cache: {e}")
            self._curated_cache = {}

        return self._curated_cache

    def _save_curated_cache(self):
        """Save curated servers to disk."""
        try:
            # Ensure directory exists
            self.curated_cache_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "version": "1.0.0",
                "lastUpdated": datetime.utcnow().isoformat(),
                "totalServers": len(self._curated_cache),
                "servers": self._curated_cache
            }

            with open(self.curated_cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)

            logger.info(f"Saved {len(self._curated_cache)} curated servers to cache")
        except Exception as e:
            logger.error(f"Error saving curated cache: {e}")

    def _identify_new_servers(self, servers: Dict[str, MarketplaceServer]) -> List[MarketplaceServer]:
        """Identify servers that haven't been curated yet.

        Skips:
        - BIGMCP: already curated in bigmcp_source.json
        - CUSTOM: admin-defined metadata, no LLM curation needed

        Curates:
        - OFFICIAL/NPM/GITHUB: external sources that need enrichment
        """
        curated = self._load_curated_cache()
        new_servers = []

        for server_id, server in servers.items():
            # Skip servers that don't need LLM curation:
            # - BIGMCP: already curated in bigmcp_source.json
            # - CUSTOM: admin-defined metadata is authoritative
            if server.source in (ServerSource.BIGMCP, ServerSource.CUSTOM):
                continue

            # Use package name as stable key
            cache_key = self._get_dedup_key(server)
            if cache_key not in curated:
                new_servers.append(server)

        logger.info(f"Found {len(new_servers)} new servers to curate (out of {len(servers)}, skipped BIGMCP/CUSTOM)")
        return new_servers

    async def _run_static_analysis_on_new_servers(
        self,
        limit: int = 0  # 0 = no limit
    ) -> Dict[str, Any]:
        """
        Run static analysis on servers that don't have tools_preview populated.

        This is called during sync to extract factual data from new servers.

        Args:
            limit: Maximum number of servers to analyze per sync (0 = no limit)

        Returns:
            Statistics about the analysis run
        """
        stats = {"analyzed": 0, "tools_found": 0, "local_access": 0, "errors": 0}

        # Find all analyzable servers (npm/pip packages)
        servers_to_analyze = []
        for server in self._servers.values():
            # Analyze all npm/pip packages to get full tool details
            if server.install_type in (InstallationType.NPM, InstallationType.PIP):
                servers_to_analyze.append(server)

        if not servers_to_analyze:
            logger.info("No new servers need static analysis")
            return stats

        # Apply limit if specified (0 = no limit)
        if limit > 0:
            servers_to_analyze = servers_to_analyze[:limit]
        logger.info(f"Running static analysis on {len(servers_to_analyze)} servers")

        for server in servers_to_analyze:
            try:
                result = await self._run_static_analysis(server)
                if result:
                    stats["analyzed"] += 1
                    stats["tools_found"] += result.get("tools_count", 0)
                    if result.get("requires_local_access"):
                        stats["local_access"] += 1
            except Exception as e:
                logger.warning(f"Static analysis failed for {server.name}: {e}")
                stats["errors"] += 1

        logger.info(
            f"Static analysis complete: {stats['analyzed']} servers, "
            f"{stats['tools_found']} tools, "
            f"{stats['local_access']} local-only"
        )
        return stats

    async def _run_static_analysis(self, server: MarketplaceServer) -> Optional[Dict[str, Any]]:
        """
        Run static code analysis to extract factual data from package source.

        Returns extracted data or None if analysis fails/not applicable.
        This data is FACTUAL and should NOT be modified by LLM.
        """
        # Only analyze npm/pip packages
        if server.install_type not in (InstallationType.NPM, InstallationType.PIP):
            return None

        try:
            extractor = StaticToolExtractor()

            if server.install_type == InstallationType.NPM:
                result = await extractor.extract_from_npm(server.install_package)
            else:
                result = await extractor.extract_from_pip(server.install_package)

            # Check if package doesn't exist - mark server as unavailable
            if result.package_not_found:
                logger.warning(f"Package not found for {server.name}: {server.install_package}")
                server.is_available = False
                server.availability_reason = "Package not found on registry"
                return {
                    "package_not_found": True,
                    "tools_count": 0,
                }

            # Build factual data dict
            static_data = {
                "tools": [{"name": t.name, "description": t.description} for t in result.tools],
                "tools_count": len(result.tools),
                "tools_preview": [t.name for t in result.tools],
                "detected_env_vars": result.detected_env_vars,
                "detected_cli_args": result.detected_cli_args,
                "requires_local_access": result.requires_local_access,
                "has_dynamic_tools": result.has_dynamic_tools,
                "extraction_time_ms": result.extraction_time_ms,
            }

            # Apply factual data to server object
            # Check if server already has tools with descriptions (curated)
            has_curated_tools = server.tools and len(server.tools) > 0
            has_described_tools = has_curated_tools and any(
                t.get("description") for t in server.tools
            )

            if result.tools:
                # Static analysis found tools
                if has_described_tools:
                    # Server has curated tools with descriptions - enrich missing descriptions only
                    existing_by_name = {t.get("name"): t for t in server.tools}
                    static_by_name = {t.name: t for t in result.tools}

                    for tool in server.tools:
                        tool_name = tool.get("name")
                        if not tool.get("description") and tool_name in static_by_name:
                            # Add description from static analysis
                            tool["description"] = static_by_name[tool_name].description or ""
                elif has_curated_tools:
                    # Server has curated tools but no descriptions - enrich with static analysis
                    existing_by_name = {t.get("name"): t for t in server.tools}
                    static_by_name = {t.name: t for t in result.tools}

                    # Add descriptions to existing tools
                    for tool in server.tools:
                        tool_name = tool.get("name")
                        if tool_name in static_by_name:
                            tool["description"] = static_by_name[tool_name].description or ""

                    # Add any new tools found by static analysis that aren't in curated list
                    for t in result.tools:
                        if t.name not in existing_by_name:
                            server.tools.append({
                                "name": t.name,
                                "description": t.description or "",
                                "is_read_only": t.is_read_only,
                                "is_destructive": t.is_destructive,
                                "is_idempotent": t.is_idempotent,
                            })
                else:
                    # No curated tools - use static analysis results entirely
                    server.tools = [
                        {
                            "name": t.name,
                            "description": t.description or "",
                            "is_read_only": t.is_read_only,
                            "is_destructive": t.is_destructive,
                            "is_idempotent": t.is_idempotent,
                        }
                        for t in result.tools
                    ]
                    # Also store preview (just names) for quick display
                    server.tools_preview = [t.name for t in result.tools]

            elif server.tools_preview and not server.tools:
                # Fallback: convert existing tools_preview to tools format
                # This preserves tools from local registry when static analysis fails
                server.tools = [
                    {
                        "name": name,
                        "description": "",  # No description from preview
                        "is_read_only": False,
                        "is_destructive": False,
                        "is_idempotent": False,
                    }
                    for name in server.tools_preview
                ]

            # Only overwrite requires_local_access if not curated
            # Curated data (bigmcp_source.json) should be preserved
            if not server.is_curated:
                server.requires_local_access = result.requires_local_access

            # Set has_dynamic_tools flag from static analysis
            if result.has_dynamic_tools:
                server.has_dynamic_tools = True

            # Add detected credentials (merge with existing) - ONLY real credentials
            # Skip credential detection for curated servers (they have hand-curated credentials)
            if server.is_curated:
                # Curated servers have authoritative, hand-curated credentials
                # Don't add auto-detected credentials that might be wrong
                logger.debug(f"Skipping credential detection for curated server {server.name}")
            else:
                # Non-BIGMCP servers: detect credentials from static analysis
                # Uses extracted credential detection logic from curation module
                existing_names = {c.name for c in server.credentials}
                detected_creds = detect_all_credentials(
                    result.detected_env_vars,
                    result.detected_cli_args,
                    existing_names
                )
                for cred_data in detected_creds:
                    server.credentials.append(CredentialSpec(
                        name=cred_data["name"],
                        description=cred_data["description"],
                        required=cred_data["required"],
                        type=cred_data["type"]
                    ))

                has_required_credentials = any(c.required for c in server.credentials)
                server.requires_credentials = has_required_credentials

            logger.info(
                f"Static analysis for {server.name}: "
                f"{len(result.tools)} tools, "
                f"local={result.requires_local_access}, "
                f"{result.extraction_time_ms}ms"
            )

            return static_data

        except Exception as e:
            logger.warning(f"Static analysis failed for {server.name}: {e}")
            return None

    async def _curate_server_with_llm(
        self,
        server: MarketplaceServer,
        max_retries: int = 5,
        base_delay: float = 2.0
    ) -> Dict[str, Any]:
        """
        Hybrid curation: Static analysis for facts + LLM for presentation.

        Pipeline:
        1. Run static analysis → factual data (tools, credentials, local_access)
        2. If LLM available → enrich presentation (summary, SEO, use_cases)
        3. If no LLM → use static data with basic formatting

        The static data is NEVER modified by LLM - it only adds presentation value.
        """
        self._init_llm_curation()

        # Step 1: Run static analysis (always, for factual data)
        static_data = await self._run_static_analysis(server)

        # Step 2: If no LLM, use static-enhanced basic curation
        if not self.llm_api_key:
            logger.info(f"No LLM configured, using static-enhanced curation for {server.name}")
            return self._basic_curation(server, static_data)

        # Step 3: Build prompt with static data for LLM enrichment
        prompt = self._build_curation_prompt(server, static_data)
        chat_url = f"{self.llm_url}/chat/completions"

        last_error = None

        for attempt in range(max_retries + 1):
            try:
                response = await self.llm_client.post(
                    chat_url,
                    json={
                        "model": self.llm_model,
                        "messages": [
                            {"role": "system", "content": self._get_curation_system_prompt()},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.2,
                        "max_tokens": 1000
                    }
                )

                if response.status_code == 200:
                    # Success - parse and return
                    result = response.json()
                    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return await self._parse_curation_response(content, server)

                elif response.status_code == 429:
                    # Rate limited - retry with exponential backoff
                    if attempt < max_retries:
                        # Parse retry-after header if available
                        retry_after = response.headers.get("retry-after")
                        if retry_after:
                            try:
                                delay = float(retry_after)
                            except ValueError:
                                delay = base_delay * (2 ** attempt)
                        else:
                            delay = base_delay * (2 ** attempt)

                        # Cap delay at 60 seconds
                        delay = min(delay, 60.0)

                        logger.warning(
                            f"Rate limited (429) for {server.name}, "
                            f"attempt {attempt + 1}/{max_retries + 1}, "
                            f"waiting {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        last_error = f"Rate limit exceeded after {max_retries + 1} attempts"
                        logger.error(f"Rate limit exhausted for {server.name}: {last_error}")

                elif response.status_code >= 500:
                    # Server error - retry with backoff
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            f"Server error ({response.status_code}) for {server.name}, "
                            f"attempt {attempt + 1}/{max_retries + 1}, "
                            f"waiting {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        last_error = f"Server error {response.status_code} after {max_retries + 1} attempts"
                        logger.error(f"Server errors exhausted for {server.name}: {last_error}")

                else:
                    # Other client errors (400, 401, 403, etc.) - don't retry
                    last_error = f"LLM API error: {response.status_code}"
                    logger.warning(f"{last_error} for {server.name}")
                    break

            except httpx.TimeoutException:
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"Timeout for {server.name}, "
                        f"attempt {attempt + 1}/{max_retries + 1}, "
                        f"waiting {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    last_error = f"Timeout after {max_retries + 1} attempts"
                    logger.error(f"Timeouts exhausted for {server.name}")

            except Exception as e:
                last_error = str(e)
                logger.error(f"LLM curation error for {server.id}: {e}")
                break

        # All retries exhausted - fall back to basic curation as last resort
        logger.warning(f"Falling back to basic curation for {server.name}: {last_error}")
        return self._basic_curation(server)

    def _get_curation_system_prompt(self) -> str:
        """System prompt for server curation. Delegated to curation.prompts module."""
        return get_curation_system_prompt()

    def _build_curation_prompt(
        self,
        server: MarketplaceServer,
        static_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build curation prompt. Delegated to curation.prompts module."""
        return build_curation_prompt(server, static_data, ServerSource.OFFICIAL)

    async def _parse_curation_response(self, content: str, server: MarketplaceServer) -> Dict[str, Any]:
        """Parse LLM curation response with validated icons."""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                data = json.loads(json_match.group())

                # Extract service_id - critical for deduplication
                service_id = data.get("service_id", "").lower().strip()
                if not service_id:
                    # Fallback: derive from server name
                    service_id = server.name.lower().replace(" ", "-").replace("_", "-")
                    service_id = re.sub(r'[^a-z0-9-]', '', service_id)
                    service_id = re.sub(r'-+', '-', service_id).strip('-')

                # Get icon search terms from LLM (new field - list of slugs to try)
                icon_search_terms = data.get("icon_search_terms", [])
                # Fallback to old icon_hint if present (backwards compatibility)
                if not icon_search_terms and data.get("icon_hint"):
                    icon_search_terms = [data.get("icon_hint")]
                # Ultimate fallback: use service_id
                if not icon_search_terms:
                    icon_search_terms = [service_id]

                # Validate icons against CDNs - test each term, keep first that works
                icon_result = await IconResolver.resolve_validated(
                    search_terms=icon_search_terms,
                    service_name=server.name,
                    http_client=self.http_client
                )

                # Extract author - use LLM's verified author or fallback to original
                curated_author = data.get("author", "").strip()
                if not curated_author or curated_author.lower() in ["unknown", "none", ""]:
                    curated_author = server.author or "Unknown"

                # Use credentials from LLM (validated/filtered) if available
                # Fallback to server credentials from static analysis
                llm_credentials = data.get("credentials", [])
                if llm_credentials:
                    # LLM provided validated credentials - use them
                    credentials = []
                    for cred in llm_credentials:
                        credentials.append({
                            "name": cred.get("name", ""),
                            "description": cred.get("description", ""),
                            "required": cred.get("required", True),
                            "type": cred.get("type", "secret"),
                            "default": cred.get("default"),
                            "example": cred.get("example"),
                            "documentation_url": cred.get("documentation_url")
                        })
                else:
                    # Fallback to static analysis credentials
                    credentials = [asdict(c) for c in server.credentials] if server.credentials else []

                # Compute requires_credentials based on validated credentials
                has_required_credentials = any(c.get("required", False) for c in credentials)

                # Extract tool descriptions if provided by LLM
                tool_descriptions = data.get("tool_descriptions", [])
                # Normalize: can be list of dicts or dict mapping name->description
                if isinstance(tool_descriptions, dict):
                    tool_descriptions = [
                        {"name": k, "description": v}
                        for k, v in tool_descriptions.items()
                    ]

                return {
                    "package_key": self._get_dedup_key(server),
                    "server_id": server.id,
                    "service_id": service_id,
                    "service_display_name": data.get("service_display_name", server.name),
                    "author": curated_author,
                    "icon_search_terms": icon_search_terms,
                    "icon_hint": icon_result.get("matched_term"),
                    "icon_url": icon_result.get("primary"),
                    "icon_urls": {
                        "primary": icon_result.get("primary"),
                        "secondary": icon_result.get("secondary"),
                        "fallback": icon_result.get("fallback")
                    },
                    "icon_validated": icon_result.get("validated", False),
                    "icon_source": icon_result.get("source"),
                    "category": data.get("category", server.category or "other"),
                    "tags": data.get("tags", server.tags or []),
                    # FACTUAL - tools from static analysis
                    "tools_preview": server.tools_preview,
                    "tools_count": len(server.tools_preview),
                    # ENRICHED - tool descriptions from LLM
                    "tool_descriptions": tool_descriptions,
                    # VALIDATED - credentials filtered by LLM
                    "credentials": credentials,
                    "requires_credentials": has_required_credentials,
                    "requires_local_access": server.requires_local_access,
                    # Presentation from LLM
                    "quality_score": min(100, max(0, data.get("quality_score", 50))),
                    "quality_notes": data.get("quality_notes", ""),
                    "summary": data.get("summary", server.description[:200] if server.description else ""),
                    "use_cases": data.get("use_cases", []),
                    "is_official": data.get("is_official", server.source == ServerSource.OFFICIAL),
                    "maintenance_status": data.get("maintenance_status", "unknown"),
                    "curated_at": datetime.utcnow().isoformat(),
                    "curated_by": "llm+static"
                }
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response for {server.id}: {e}")

        return self._basic_curation(server)

    def _basic_curation(
        self,
        server: MarketplaceServer,
        static_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Static-enhanced fallback curation when LLM is unavailable.

        With static_data, this provides COMPLETE curation:
        - Factual: tools, credentials, requires_local_access (from static analysis)
        - Basic: category, tags, summary (derived from data)

        Without static_data, falls back to minimal curation.
        """
        # Derive service_id from server name
        service_id = server.name.lower().replace(" ", "-").replace("_", "-")
        service_id = re.sub(r'[^a-z0-9-]', '', service_id)
        service_id = re.sub(r'-+', '-', service_id).strip('-')

        # Clean up common suffixes
        for suffix in ['-mcp-server', '-mcp', '-server', 'server-']:
            if service_id.endswith(suffix):
                service_id = service_id[:-len(suffix)]
            elif service_id.startswith(suffix):
                service_id = service_id[len(suffix):]

        # Generate display name from service_id
        display_name = service_id.replace("-", " ").title()

        # Get icon URLs
        icon_urls = IconResolver.get_icon_urls(service_id, display_name)

        # Build tools preview and tags from static data
        if static_data:
            tools_preview = static_data.get("tools_preview", [])
            tools_count = static_data.get("tools_count", 0)
            requires_local = static_data.get("requires_local_access", False)

            # Generate tags from tool names
            tags = list(set(
                server.tags +
                [t.split("_")[0] for t in tools_preview[:5]] +
                static_data.get("detected_env_vars", [])[:3]
            ))[:10]

            # Quality score based on tools count
            if tools_count >= 10:
                quality_score = 70
            elif tools_count >= 5:
                quality_score = 55
            elif tools_count >= 1:
                quality_score = 40
            else:
                quality_score = 25

            curated_by = "static"
            needs_recuration = False  # Static data is complete
        else:
            tools_preview = server.tools_preview
            tools_count = len(tools_preview)
            requires_local = server.requires_local_access
            tags = server.tags or []
            quality_score = max(10, server.popularity // 2)
            curated_by = "basic"
            needs_recuration = True

        # Boost quality for official servers
        if server.source == ServerSource.OFFICIAL:
            quality_score = min(100, quality_score + 20)

        # Generate summary from description or tools
        if server.description:
            summary = server.description[:200]
        elif tools_preview:
            summary = f"MCP server providing {len(tools_preview)} tools: {', '.join(tools_preview[:5])}"
        else:
            summary = f"MCP server: {server.name}"

        return {
            "package_key": self._get_dedup_key(server),
            "server_id": server.id,
            "service_id": service_id,
            "service_display_name": display_name,
            "author": server.author or "Unknown",
            "icon_hint": service_id,
            "icon_search_terms": [service_id],
            "icon_url": icon_urls["primary"],
            "icon_urls": icon_urls,
            "icon_validated": False,
            "category": server.category or "other",
            "tags": tags,
            "tools_preview": tools_preview,
            "tools_count": tools_count,
            "tool_descriptions": [],  # No LLM available for enrichment in basic curation
            "credentials": [asdict(c) for c in server.credentials] if server.credentials else [],
            "requires_local_access": requires_local,
            "quality_score": quality_score,
            "quality_notes": f"Curated by {curated_by} analysis",
            "summary": summary,
            "use_cases": [],
            "is_official": server.source == ServerSource.OFFICIAL,
            "maintenance_status": "unknown",
            "curated_at": datetime.utcnow().isoformat(),
            "curated_by": curated_by,
            "needs_recuration": needs_recuration
        }

    def deduplicate_by_service(self) -> Dict[str, Any]:
        """
        Deduplicate curated servers by service_id, keeping highest quality.

        Returns statistics about deduplication.
        """
        self._init_llm_curation()
        self._load_curated_cache()

        if not self._curated_cache:
            return {"status": "no_data", "message": "No curated servers to deduplicate"}

        # Group by service_id
        services: Dict[str, List[Dict[str, Any]]] = {}
        for key, curation in self._curated_cache.items():
            service_id = curation.get("service_id", key)
            if service_id not in services:
                services[service_id] = []
            services[service_id].append(curation)

        # Find duplicates and select best
        duplicates_found = 0
        servers_removed = 0
        dedup_report = []

        for service_id, variants in services.items():
            if len(variants) > 1:
                duplicates_found += 1
                # Sort by quality_score descending, then by is_official
                variants.sort(
                    key=lambda x: (
                        x.get("is_official", False),
                        x.get("quality_score", 0)
                    ),
                    reverse=True
                )
                best = variants[0]
                alternatives = variants[1:]
                servers_removed += len(alternatives)

                # Mark alternatives in cache
                for alt in alternatives:
                    alt_key = alt.get("package_key")
                    if alt_key in self._curated_cache:
                        self._curated_cache[alt_key]["is_duplicate"] = True
                        self._curated_cache[alt_key]["primary_server"] = best.get("package_key")
                        self._curated_cache[alt_key]["duplicate_reason"] = f"Lower quality variant of {service_id}"

                dedup_report.append({
                    "service_id": service_id,
                    "kept": best.get("package_key"),
                    "kept_score": best.get("quality_score"),
                    "removed": [a.get("package_key") for a in alternatives],
                    "removed_scores": [a.get("quality_score") for a in alternatives]
                })

        # Save updated cache
        self._save_curated_cache()

        return {
            "status": "completed",
            "unique_services": len(services),
            "duplicates_found": duplicates_found,
            "servers_marked_duplicate": servers_removed,
            "report": dedup_report[:20]  # Limit report size
        }

    async def curate_new_servers(
        self,
        batch_size: int = 5,
        max_servers: int = 50
    ) -> Dict[str, Any]:
        """
        Curate only NEW servers (not already in cache).

        This is the main curation method - efficient and incremental.

        Args:
            batch_size: Number of servers to process per LLM batch
            max_servers: Maximum new servers to curate in one run

        Returns:
            Curation statistics
        """
        self._init_llm_curation()

        # Ensure servers are synced first
        if not self._servers:
            await self.sync()

        # Identify new servers
        new_servers = self._identify_new_servers(self._servers)

        if not new_servers:
            return {
                "status": "up_to_date",
                "message": "All servers already curated",
                "total_curated": len(self._curated_cache),
                "new_curated": 0
            }

        # Limit to max_servers
        to_curate = new_servers[:max_servers]
        curated_count = 0
        errors = []

        logger.info(f"Starting LLM curation for {len(to_curate)} new servers")

        # Process in batches
        for i in range(0, len(to_curate), batch_size):
            batch = to_curate[i:i + batch_size]

            tasks = [self._curate_server_with_llm(s) for s in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for server, result in zip(batch, results):
                if isinstance(result, Exception):
                    errors.append(f"{server.id}: {str(result)}")
                else:
                    # Store in cache
                    cache_key = result.get("package_key", self._get_dedup_key(server))
                    self._curated_cache[cache_key] = result
                    curated_count += 1

                    # Update server with curated data
                    self._apply_curation_to_server(server, result)

            logger.info(f"Curated batch {i//batch_size + 1}/{(len(to_curate) + batch_size - 1)//batch_size}")

            # Rate limiting
            if i + batch_size < len(to_curate):
                await asyncio.sleep(2)

        # Save updated cache
        self._save_curated_cache()

        # Run deduplication after new servers are curated
        dedup_result = self.deduplicate_by_service()

        return {
            "status": "completed",
            "total_curated": len(self._curated_cache),
            "new_curated": curated_count,
            "remaining": len(new_servers) - len(to_curate),
            "errors": errors,
            "deduplication": dedup_result
        }

    async def force_full_curation(
        self,
        batch_size: int = 5,
        max_servers: int = 200
    ) -> Dict[str, Any]:
        """
        Force re-curation of ALL servers by clearing cache first.

        Use this when the curation prompt has been significantly updated
        and you need to refresh all curation data.

        Args:
            batch_size: Number of servers to process per LLM batch
            max_servers: Maximum servers to curate in one run

        Returns:
            Curation statistics
        """
        self._init_llm_curation()

        # Clear the existing cache
        old_count = len(self._curated_cache)
        self._curated_cache = {}
        logger.info(f"Cleared curation cache ({old_count} entries)")

        # Ensure servers are synced first
        if not self._servers:
            await self.sync()

        # Get all servers EXCEPT:
        # - BIGMCP: already curated in bigmcp_source.json
        # - CUSTOM: admin-defined metadata is authoritative
        # OFFICIAL/NPM/GITHUB are external sources that need curation
        all_servers = [
            s for s in self._servers.values()
            if s.source not in (ServerSource.BIGMCP, ServerSource.CUSTOM)
        ]

        if not all_servers:
            return {
                "status": "no_servers",
                "message": "No external servers to curate (BIGMCP pre-curated, CUSTOM admin-defined)"
            }

        # Limit to max_servers
        to_curate = all_servers[:max_servers]
        curated_count = 0
        errors = []

        logger.info(f"Starting FULL LLM curation for {len(to_curate)} servers (cache cleared)")

        # Process in batches
        for i in range(0, len(to_curate), batch_size):
            batch = to_curate[i:i + batch_size]

            tasks = [self._curate_server_with_llm(s) for s in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for server, result in zip(batch, results):
                if isinstance(result, Exception):
                    errors.append(f"{server.id}: {str(result)}")
                else:
                    # Store in cache
                    cache_key = result.get("package_key", self._get_dedup_key(server))
                    self._curated_cache[cache_key] = result
                    curated_count += 1

                    # Update server with curated data
                    self._apply_curation_to_server(server, result)

            logger.info(f"Curated batch {i//batch_size + 1}/{(len(to_curate) + batch_size - 1)//batch_size}")

            # Rate limiting
            if i + batch_size < len(to_curate):
                await asyncio.sleep(2)

        # Save updated cache
        self._save_curated_cache()

        # Run deduplication
        dedup_result = self.deduplicate_by_service()

        return {
            "status": "completed",
            "cache_cleared": old_count,
            "total_curated": len(self._curated_cache),
            "new_curated": curated_count,
            "remaining": len(all_servers) - len(to_curate),
            "errors": errors,
            "deduplication": dedup_result
        }

    def _apply_curation_to_server(self, server: MarketplaceServer, curation: Dict[str, Any]):
        """Apply curation data to a server object."""
        # Category and tags (from LLM or static)
        if curation.get("category"):
            server.category = curation["category"]

        if curation.get("tags"):
            server.tags = list(set(server.tags + curation["tags"]))

        if curation.get("quality_score"):
            server.popularity = int((server.popularity + curation["quality_score"]) / 2)

        # Tools preview (from static analysis - FACTUAL)
        # Apply if server doesn't have tools_preview, even for curated servers
        if curation.get("tools_preview") and not server.tools_preview:
            server.tools_preview = curation["tools_preview"]

        # Requires local access - NEVER overwrite curated source (already curated)
        if "requires_local_access" in curation and not server.is_curated:
            server.requires_local_access = curation["requires_local_access"]

        # Credentials handling
        if curation.get("credentials") is not None:
            if server.is_curated:
                # For curated servers: ENRICH metadata only (descriptions, docs)
                # Never overwrite names, types, or required status
                curation_creds_map = {c.get("name"): c for c in curation["credentials"]}
                for cred in server.credentials:
                    if cred.name in curation_creds_map:
                        curation_cred = curation_creds_map[cred.name]
                        # Only enrich if source data is missing
                        if not cred.description and curation_cred.get("description"):
                            cred.description = curation_cred["description"]
                        if not cred.documentation_url and curation_cred.get("documentation_url"):
                            cred.documentation_url = curation_cred["documentation_url"]
                        if not cred.example and curation_cred.get("example"):
                            cred.example = curation_cred["example"]
            else:
                # Replace all credentials with LLM-filtered list (only for non-curated sources)
                server.credentials = []
                for cred_data in curation["credentials"]:
                    cred_name = cred_data.get("name", "")
                    if cred_name:
                        server.credentials.append(CredentialSpec(
                            name=cred_name,
                            description=cred_data.get("description", ""),
                            required=cred_data.get("required", True),
                            type=cred_data.get("type", "secret")
                        ))

        # Tool descriptions enrichment (LLM-generated for missing descriptions ONLY)
        if curation.get("tool_descriptions"):
            # Build map of tool name -> description
            llm_desc_map = {}
            for td in curation["tool_descriptions"]:
                if isinstance(td, dict) and td.get("name") and td.get("description"):
                    llm_desc_map[td["name"]] = td["description"]

            if llm_desc_map and server.tools:
                # Enrich existing tools with missing descriptions
                for tool in server.tools:
                    tool_name = tool.get("name", "")
                    current_desc = tool.get("description", "")
                    # Only apply if description is missing or empty
                    if tool_name in llm_desc_map and not current_desc.strip():
                        tool["description"] = llm_desc_map[tool_name]
                        logger.debug(f"Enriched tool '{tool_name}' description for {server.name}")

    async def get_curation_status(self) -> Dict[str, Any]:
        """Get curation status and statistics."""
        self._init_llm_curation()
        curated = self._load_curated_cache()

        # Count servers needing curation
        needs_curation = 0
        needs_icon_refresh = 0
        if self._servers:
            needs_curation = len(self._identify_new_servers(self._servers))

        # Count servers with invalid/unvalidated icons
        for key, curation in curated.items():
            if not curation.get("icon_validated", False):
                needs_icon_refresh += 1

        return {
            "total_servers": len(self._servers) if self._servers else 0,
            "curated_servers": len(curated),
            "pending_curation": needs_curation,
            "needs_icon_refresh": needs_icon_refresh,
            "llm_configured": bool(self.llm_api_key) if hasattr(self, 'llm_api_key') else False,
            "cache_path": str(self.curated_cache_path) if hasattr(self, 'curated_cache_path') else None
        }

    def get_server_icon(self, marketplace_server_id: str) -> Optional[Dict[str, str]]:
        """
        Get icon URLs for a marketplace server from curated cache.

        Used to attach service icons to MCP tools for Claude Desktop display.

        Args:
            marketplace_server_id: The marketplace server ID (e.g., "github", "grist-mcp")

        Returns:
            Dict with icon URLs: {"primary": ..., "secondary": ..., "fallback": ...}
            or None if not found
        """
        self._load_curated_cache()

        if not self._curated_cache:
            return None

        # Search by service_id first (primary identifier), then by server_id
        marketplace_id_lower = marketplace_server_id.lower()

        for key, curation in self._curated_cache.items():
            # Match by service_id (e.g., "github")
            service_id = curation.get("service_id", "").lower()
            if service_id == marketplace_id_lower:
                return curation.get("icon_urls")

            # Match by server_id (e.g., "mcp-server-github")
            server_id = curation.get("server_id", "").lower()
            if server_id == marketplace_id_lower:
                return curation.get("icon_urls")

            # Partial match for server names containing the ID
            if marketplace_id_lower in server_id or marketplace_id_lower in service_id:
                return curation.get("icon_urls")

        return None

    async def refresh_invalid_icons(self, max_servers: int = 100) -> Dict[str, Any]:
        """
        Re-curate ONLY servers with invalid/unvalidated icons.

        Does NOT modify other curation data - only updates icon fields.
        Uses LLM to get new icon_search_terms for servers without validated icons.

        Args:
            max_servers: Maximum servers to process in one run

        Returns:
            Statistics about refreshed icons
        """
        self._init_llm_curation()
        self._load_curated_cache()

        # Ensure servers are synced
        if not self._servers:
            await self.sync()

        # Find servers with invalid icons
        servers_needing_icons = []
        for key, curation in self._curated_cache.items():
            if curation.get("is_duplicate"):
                continue
            if not curation.get("icon_validated", False):
                # Find the matching server
                server_id = curation.get("server_id")
                if server_id and server_id in self._servers:
                    servers_needing_icons.append((key, self._servers[server_id]))

        if not servers_needing_icons:
            return {
                "status": "up_to_date",
                "message": "All icons are already validated",
                "total_checked": len(self._curated_cache)
            }

        # Limit processing
        to_process = servers_needing_icons[:max_servers]
        refreshed = 0
        failed = []

        logger.info(f"Refreshing icons for {len(to_process)} servers")

        for cache_key, server in to_process:
            try:
                # Get new icon search terms from LLM
                result = await self._curate_server_with_llm(server)

                if result.get("icon_validated"):
                    # Update only icon-related fields in existing cache entry
                    existing = self._curated_cache[cache_key]
                    existing["icon_search_terms"] = result.get("icon_search_terms", [])
                    existing["icon_hint"] = result.get("icon_hint")
                    existing["icon_url"] = result.get("icon_url")
                    existing["icon_urls"] = result.get("icon_urls")
                    existing["icon_validated"] = True
                    existing["icon_source"] = result.get("icon_source")
                    existing["icon_refreshed_at"] = datetime.utcnow().isoformat()
                    refreshed += 1
                    logger.info(f"Icon validated for {server.name}: {result.get('icon_hint')}")
                else:
                    failed.append(f"{server.name}: No valid icon found")

            except Exception as e:
                failed.append(f"{server.name}: {str(e)}")

            # Rate limiting
            await asyncio.sleep(1)

        # Save updated cache
        self._save_curated_cache()

        return {
            "status": "completed",
            "total_needing_refresh": len(servers_needing_icons),
            "processed": len(to_process),
            "refreshed": refreshed,
            "failed": len(failed),
            "failed_details": failed[:10],  # Limit details
            "remaining": len(servers_needing_icons) - len(to_process)
        }

    async def revalidate_existing_icons(self, max_servers: int = 200) -> Dict[str, Any]:
        """
        Re-validate existing icon_search_terms without calling LLM.

        For servers that have icon_search_terms but not icon_validated,
        just re-test the terms against CDNs without re-curating.

        This is much faster than refresh_invalid_icons because it doesn't
        call the LLM - it just re-tests existing search terms.

        Args:
            max_servers: Maximum servers to process

        Returns:
            Statistics about revalidation
        """
        self._init_llm_curation()
        self._load_curated_cache()

        # Find servers with search terms but not validated
        to_revalidate = []
        for key, curation in self._curated_cache.items():
            if curation.get("is_duplicate"):
                continue
            if not curation.get("icon_validated", False):
                search_terms = curation.get("icon_search_terms", [])
                if search_terms:
                    to_revalidate.append((key, curation, search_terms))

        if not to_revalidate:
            return {
                "status": "nothing_to_revalidate",
                "message": "No servers with unvalidated icon_search_terms found"
            }

        # Limit processing
        to_process = to_revalidate[:max_servers]
        validated = 0
        still_invalid = 0

        logger.info(f"Re-validating icons for {len(to_process)} servers (no LLM calls)")

        for cache_key, curation, search_terms in to_process:
            service_name = curation.get("service_display_name", "")

            # Test existing search terms against CDNs
            icon_result = await IconResolver.resolve_validated(
                search_terms=search_terms,
                service_name=service_name,
                http_client=self.http_client
            )

            if icon_result.get("validated"):
                # Update icon fields
                curation["icon_hint"] = icon_result.get("matched_term")
                curation["icon_url"] = icon_result.get("primary")
                curation["icon_urls"] = {
                    "primary": icon_result.get("primary"),
                    "secondary": icon_result.get("secondary"),
                    "fallback": icon_result.get("fallback")
                }
                curation["icon_validated"] = True
                curation["icon_source"] = icon_result.get("source")
                curation["icon_revalidated_at"] = datetime.utcnow().isoformat()
                validated += 1
                logger.info(f"Icon revalidated: {service_name} -> {icon_result.get('matched_term')}")
            else:
                still_invalid += 1

        # Save updated cache
        self._save_curated_cache()

        return {
            "status": "completed",
            "total_checked": len(to_process),
            "newly_validated": validated,
            "still_invalid": still_invalid,
            "remaining": len(to_revalidate) - len(to_process)
        }


# Singleton instance with thread-safe initialization
import threading
_marketplace_service: Optional[MarketplaceSyncService] = None
_singleton_lock = threading.Lock()  # Threading lock for proper sync


def get_marketplace_service() -> MarketplaceSyncService:
    """
    Get or create singleton marketplace service (thread-safe).

    Uses threading.Lock with double-checked locking pattern.
    """
    global _marketplace_service

    # Quick check without lock
    if _marketplace_service is not None:
        return _marketplace_service

    with _singleton_lock:
        # Double-check after acquiring lock
        if _marketplace_service is None:
            _marketplace_service = MarketplaceSyncService()
            logger.info("✅ Created singleton MarketplaceSyncService instance")
        return _marketplace_service
