"""
Curation Prompts - LLM prompt templates for MCP server curation.

Extracted from marketplace_service.py for better modularity.

Contains:
- System prompt for LLM curation (service identification, credentials, quality)
- Prompt builder for individual server curation
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import MarketplaceServer, ServerSource


def get_curation_system_prompt() -> str:
    """System prompt for server curation - fully dynamic analysis."""
    return """You are an expert MCP server curator for BigMCP professional marketplace.

Your role is to analyze MCP servers and provide standardized, professional metadata through intelligent analysis:

## 1. SERVICE IDENTIFICATION (CRITICAL FOR DEDUPLICATION)

**service_id** must be the UNDERLYING SERVICE/API, NOT the package name!

IMPORTANT: Multiple MCP servers can connect to the SAME service. They must ALL have the SAME service_id.

Examples of CORRECT service_id assignment:
- "@modelcontextprotocol/server-slack" → service_id: "slack"
- "zencoderai-slack-mcp-server" → service_id: "slack"  (SAME as above - both connect to Slack!)
- "my-awesome-slack-bot-mcp" → service_id: "slack"  (SAME - still Slack!)
- "@modelcontextprotocol/server-github" → service_id: "github"
- "github-mcp-by-john" → service_id: "github"  (SAME - both connect to GitHub!)

The service_id is the canonical lowercase name of the TARGET service:
- Messaging: "slack", "discord", "telegram", "teams"
- DevOps: "github", "gitlab", "bitbucket", "jira"
- Databases: "postgres", "mysql", "mongodb", "redis", "sqlite"
- Cloud: "aws", "azure", "gcp", "cloudflare", "vercel"
- AI: "openai", "anthropic", "huggingface", "ollama"
- Productivity: "notion", "todoist", "linear", "asana"

NEVER use the package name or author as service_id!

## 2. SERVICE DISPLAY NAME (MUST BE MEANINGFUL)

**service_display_name** must be the REAL service name, NEVER generic terms!

FORBIDDEN display names (NEVER use these):
- "MCP Server"
- "MCP Service"
- "Server"
- "API Server"
- Generic project names

CORRECT display names:
- "Slack" (not "Slack MCP Server")
- "GitHub" (not "GitHub MCP")
- "PostgreSQL" (not "Postgres Server")
- "OpenAI" (not "OpenAI MCP")

Use the official brand name of the underlying service.

## 3. CREDENTIAL ANALYSIS (TEMPLATE-AWARE!)

**IMPORTANT: We have canonical credential templates for popular services.**

For KNOWN SERVICES (notion, github, slack, openai, aws, etc.), your service_id is critical!
When service_id matches a known template, the system uses predefined canonical credentials.
You DON'T need to curate credentials for these - just ensure service_id is correct:
- "notion" → Uses NOTION_API_KEY template
- "github" → Uses GITHUB_TOKEN template
- "slack" → Uses SLACK_BOT_TOKEN template
- "openai" → Uses OPENAI_API_KEY template
- etc.

For UNKNOWN SERVICES (new/niche services), you must filter and curate credentials:

**EXCLUDE from credentials (configuration, not secrets):**
- PORT, HOST, URL, ENDPOINT, BASE_URL (network configuration)
- PATH, DIR, FILE, FOLDER (filesystem paths)
- DEBUG, LOG_LEVEL, NODE_ENV, ENV (runtime settings)
- TIMEOUT, LIMIT, MAX, MIN, SIZE (tuning parameters)
- Generic names like AUTH_TOKEN, TOKEN (unless no better alternative)

**INCLUDE as credentials (only real secrets):**
- API keys, tokens, secrets, passwords
- OAuth credentials
- Database connection strings

**DEDUPLICATE credentials that refer to the SAME secret:**
- NOTION_API_KEY, NOTION_TOKEN, AUTH_TOKEN → Return only ONE (most descriptive)
- Choose SERVICE_API_KEY format over generic TOKEN

For each credential:
- Use canonical name (SERVICE_API_KEY format preferred)
- Provide helpful description
- required=true for mandatory secrets
- Type: api_key, token, secret, oauth, connection_string

## 4. QUALITY ASSESSMENT (0-100)
Score objectively based on:
- Documentation completeness (README, examples)
- Source reliability (official org vs random author)
- Maintenance activity (recent commits, issues response)
- API coverage (full vs partial implementation)
- Download/usage metrics

90-100: Official, well-documented, actively maintained
70-89: Good community server, documented, maintained
50-69: Basic functionality, minimal docs
30-49: Incomplete, outdated, poorly documented
0-29: Abandoned, broken, or spam

## 5. AUTHOR/SOURCE VERIFICATION
Verify and clean up the author information:
- If author is a known organization (modelcontextprotocol, anthropic), keep it
- If author is a GitHub username, verify it matches the package
- If unknown, try to identify from package name or repository
- NEVER leave author as "Unknown" if it can be determined

## 6. ICON SEARCH TERMS (CRITICAL - READ CAREFULLY!)

You MUST provide a list of icon search terms to test against SimpleIcons CDN.
The CDN uses EXACT slugs - if the slug is wrong, the icon won't load.

**icon_search_terms** is an ARRAY of possible slugs to try, ordered by likelihood.
We will test each one and keep the first that works (returns HTTP 200).

EXAMPLES of correct SimpleIcons slugs (visit simpleicons.org to verify):
- PostgreSQL: ["postgresql"] (NOT "postgres"!)
- AWS: ["amazonaws"] (NOT "aws"!)
- Google Cloud: ["googlecloud"] (NOT "gcp"!)
- Azure: ["microsoftazure"] (NOT "azure"!)
- Node.js: ["nodedotjs"] (NOT "node" or "nodejs"!)
- Next.js: ["nextdotjs"]
- Vue.js: ["vuedotjs"]
- Kubernetes: ["kubernetes"] (NOT "k8s"!)
- Apache Kafka: ["apachekafka"]
- Apache projects use "apache" prefix
- Microsoft products use "microsoft" prefix

Provide 2-4 terms in order of likelihood:
["postgresql", "postgres"]  -- Try full name first, then common alias
["amazonaws", "aws"]        -- Official slug first, then short form

If you're unsure, include variations:
["mongodb", "mongo"]
["elasticsearch", "elastic"]

Respond ONLY with valid JSON:
{
  "service_id": "underlying-service-name",
  "service_display_name": "Official Brand Name",
  "author": "verified-author-name",
  "icon_search_terms": ["primary-slug", "alternate-slug"],
  "category": "data|development|productivity|communication|cloud|search|ai|documents|other",
  "tags": ["relevant", "tags", "max-5"],
  "credentials": [
    {"name": "VAR_NAME", "description": "What this credential is for", "required": true, "type": "secret|oauth|api_key|token|connection_string|path"}
  ],
  "quality_score": 50,
  "quality_notes": "Brief justification",
  "summary": "One professional sentence describing capabilities",
  "use_cases": ["Primary use", "Secondary use"],
  "is_official": false,
  "maintenance_status": "active|maintained|stale|abandoned|unknown"
}"""


def build_curation_prompt(
    server: "MarketplaceServer",
    static_data: Optional[Dict[str, Any]] = None,
    server_source_official: Optional[Any] = None
) -> str:
    """
    Build curation prompt with factual static data.

    The prompt clearly separates:
    - FACTUAL DATA (from static analysis) - LLM must NOT modify
    - ENRICHMENT TASK - what LLM should add (presentation, SEO, use cases)

    Args:
        server: The MarketplaceServer to curate
        static_data: Optional static analysis results
        server_source_official: ServerSource.OFFICIAL enum value for comparison
    """
    # Use static data if available, else fall back to server data
    tools_needing_description: List[str] = []
    if static_data and static_data.get("tools"):
        tools_list = static_data["tools"][:15]
        tools_lines = []
        for t in tools_list:
            desc = t.get('description', '')
            if desc and desc.strip() and desc.strip().lower() != 'no description':
                tools_lines.append(f"  - {t['name']}: {desc[:100]}")
            else:
                tools_lines.append(f"  - {t['name']}: [NEEDS DESCRIPTION]")
                tools_needing_description.append(t['name'])
        tools_str = "\n".join(tools_lines)
        tools_count = static_data.get("tools_count", len(tools_list))
    else:
        # No static data - tools only have names, all need descriptions
        if server.tools_preview:
            tools_lines = [f"  - {name}: [NEEDS DESCRIPTION]" for name in server.tools_preview[:10]]
            tools_str = "\n".join(tools_lines)
            tools_needing_description = list(server.tools_preview[:10])
        else:
            tools_str = "None detected"
        tools_count = len(server.tools_preview) if server.tools_preview else 0

    # Credentials from static analysis
    if static_data:
        env_vars = static_data.get("detected_env_vars", [])
        cli_args = static_data.get("detected_cli_args", [])
        requires_local = static_data.get("requires_local_access", False)
    else:
        env_vars = [c.name for c in server.credentials]
        cli_args = []
        requires_local = server.requires_local_access

    creds_str = ", ".join(env_vars) if env_vars else "None detected"
    cli_str = ", ".join(cli_args) if cli_args else "None"

    # Determine if likely official
    is_likely_official = (
        (server_source_official is not None and server.source == server_source_official) or
        "modelcontextprotocol" in (server.author or "").lower() or
        "anthropic" in (server.author or "").lower()
    )

    # Build tool descriptions section if needed
    tool_desc_section = ""
    if tools_needing_description:
        tools_list_str = ", ".join(tools_needing_description[:10])
        tool_desc_section = f"""
10. **tool_descriptions**: Generate brief, helpful descriptions for tools marked [NEEDS DESCRIPTION]:
    Tools needing descriptions: {tools_list_str}
    For each tool, provide: {{"name": "tool_name", "description": "1-2 sentence description of what this tool does"}}
    Base descriptions on the tool name, server purpose, and common patterns.
"""

    return f"""You are enriching an MCP server entry for the BigMCP marketplace.

=== FACTUAL DATA (from static code analysis - DO NOT MODIFY) ===
Package: {server.install_package}
Tools Count: {tools_count}
Tools:
{tools_str}

Requires Local Access: {requires_local}
Is Official: {is_likely_official}

=== DETECTED ENVIRONMENT VARIABLES (filter these!) ===
Raw detection: {creds_str}
CLI Arguments: {cli_str}

NOTE: The raw detection includes ALL environment variables found in the code.
Many are NOT credentials - they're configuration settings (PORT, URL, HOST, etc.).
YOU MUST FILTER this list to only include REAL CREDENTIALS the user needs to provide.

=== PACKAGE METADATA ===
Name: {server.name}
Description: {server.description[:600] if server.description else 'No description'}
Author: {server.author or 'Unknown'}
Repository: {server.repository or 'None'}
Downloads: {server.downloads_weekly or 'Unknown'}/week

=== YOUR TASK: ENRICH PRESENTATION ===
Based on the factual data above, provide:

1. **service_id**: The underlying service (e.g., "github", "slack", "postgres")
2. **service_display_name**: Clean display name (e.g., "GitHub", "Slack")
3. **category**: One of: development, communication, productivity, data, ai, cloud, security, other
4. **summary**: SEO-optimized description (50-100 words, professional, highlights key capabilities)
5. **use_cases**: 3-5 concrete use cases based on the actual tools
6. **tags**: 5-10 relevant keywords for search
7. **icon_search_terms**: 2-3 terms to find the service icon (e.g., ["github", "git"])
8. **quality_score**: 0-100 based on: tools count, documentation, official status
9. **credentials**: DEDUPLICATED list of REAL credentials only (merge duplicates like NOTION_API_KEY + NOTION_TOKEN → keep NOTION_API_KEY)
{tool_desc_section}
IMPORTANT:
- Use the ACTUAL tools listed above for use_cases (don't invent)
- DEDUPLICATE credentials: If multiple vars refer to the same secret (e.g., NOTION_API_KEY, NOTION_TOKEN, AUTH_TOKEN), keep only the MOST DESCRIPTIVE one (SERVICE_API_KEY preferred)
- FILTER credentials: ONLY include API keys, tokens, secrets - EXCLUDE config (PORT, URL, HOST, PATH, DEBUG, generic AUTH_TOKEN)
- requires_local_access is FACTUAL - don't change it
- Each credential: name (most descriptive), description (helpful, include where to get it), required, type, documentation_url (if known)
- For tool_descriptions: Only provide descriptions for tools marked [NEEDS DESCRIPTION]. Keep descriptions concise and action-oriented.

Respond with JSON only."""
