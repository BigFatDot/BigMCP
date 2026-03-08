"""
Known Service Credentials - Canonical credentials for popular services.

When a server's service_id matches a known service, use these templates
instead of relying on static analysis or LLM curation. This ensures:
- Users see exactly the right credential(s) for each service
- No duplicates (e.g., Notion shows only NOTION_API_KEY, not 3 variants)
- Accurate descriptions with documentation links

Format: service_id -> list of canonical credentials
"""

from typing import Any, Dict, List


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


# ============================================================================
# Icon Resolution Service - LLM-driven multi-term validation
# ============================================================================


