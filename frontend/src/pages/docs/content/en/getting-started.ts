/**
 * Getting Started Documentation Content
 */

export const gettingStartedContent: Record<string, string> = {
  introduction: `
# Introduction

BigMCP is a **centralized MCP management platform** that connects your AI assistants (Claude, Mistral Le Chat, etc.) and automation tools (n8n, Make) to a unified ecosystem of services and tools.

## How It Works

\`\`\`mermaid
flowchart TB
    subgraph top [" "]
        direction LR
        CLAUDE(["<b>Claude</b><br/>Desktop & Mobile"])
        MISTRAL(["<b>Mistral</b><br/>Le Chat"])
        N8N(["<b>n8n</b><br/>Automation"])
    end

    GATEWAY(["<b>BigMCP</b><br/>━━━━━━━━━━━━━<br/>Unified MCP Gateway<br/>OAuth 2.0 · API Keys"])

    subgraph bottom [" "]
        direction LR
        S1(["GitHub"])
        S2(["Slack"])
        S3(["Drive"])
        S4(["100+ more..."])
    end

    CLAUDE & MISTRAL & N8N --> GATEWAY
    GATEWAY --> S1 & S2 & S3 & S4

    style top fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style bottom fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style CLAUDE fill:#ffffff,stroke:#d4d4d4,color:#262626
    style MISTRAL fill:#ffffff,stroke:#d4d4d4,color:#262626
    style N8N fill:#ffffff,stroke:#d4d4d4,color:#262626
    style GATEWAY fill:#D97757,stroke:#c4624a,color:#ffffff
    style S1 fill:#f4e4df,stroke:#c4624a,color:#262626
    style S2 fill:#f4e4df,stroke:#c4624a,color:#262626
    style S3 fill:#f4e4df,stroke:#c4624a,color:#262626
    style S4 fill:#f4e4df,stroke:#c4624a,color:#262626
\`\`\`

**BigMCP acts as a central hub**: your AI assistants and automation tools connect to BigMCP, which then manages connections to all your services (GitHub, Slack, databases, etc.).

## What is MCP?

The [Model Context Protocol (MCP)](https://modelcontextprotocol.io) is an open standard that allows AI assistants to securely access external tools and data sources:

- **Tools** - Functions executable by AI (read files, query databases, send messages)
- **Resources** - Accessible data (documents, APIs, knowledge bases)
- **Prompts** - Pre-defined templates for common tasks

## Why BigMCP?

| Problem | BigMCP Solution |
|---------|-----------------|
| Complex configuration | One-click OAuth connection, no config files |
| Credential management | AES-128 encrypted vault (Fernet), secure sharing |
| Access control | Toolboxes to restrict by context |
| Multi-client support | Single account for Claude, Mistral, n8n... |
| Enterprise Shadow AI | Audit trail, centralized credentials, governance |

## Connection Methods

### OAuth 2.0 + PKCE (Recommended)
The simplest method for compatible AI assistants:
- **No file configuration** - Connect directly from Claude or Mistral
- **Secure** - Standard authentication with revocable tokens
- **Seamless experience** - Login once, immediate access to all your tools

### API Key
For advanced use cases:
- **Automation** - Scripts, CI/CD, n8n workflows
- **Toolbox restriction** - Limit access to a subset of tools
- **Long-lived** - Non-expiring tokens for permanent integrations

### REST API
For programmatic integrations:
- **n8n, Make, Zapier** - Use your BigMCP tools in workflows
- **Custom applications** - Build your own integrations
- **Batch processing** - Execute tools in bulk

## Toolboxes: Control and Context

Toolboxes are at the heart of BigMCP, serving two purposes:

### 1. Access Control
Restrict which tools are accessible by API Key:
- Create a "Production" group with only validated tools
- Generate an API Key linked to this group
- The API Key can only access tools from that group

### 2. Context for AI Agents
Organize your tools by use case:
- **"Dev Tools"**: GitHub, GitLab, Jira, CI/CD
- **"Communication"**: Slack, Email, Discord
- **"Data Analysis"**: PostgreSQL, BigQuery, Sheets

Your AI agents only see tools relevant to their context.

## Use Cases

### Personal
- Connect Claude Desktop to all your services from a single interface
- Manage your API keys and credentials in one place
- Create tool compositions to automate complex tasks

### Team
- Share secure credentials between members (Team Services)
- Define roles and permissions (RBAC)
- Standardize tool configurations across your organization

### Enterprise
- **Shadow AI Governance**: Centralize AI access to sensitive data
- **Audit trail**: Track every tool usage
- **Custom Marketplace**: Add your own private MCP servers
- **Centralized credentials**: No more secrets in individual configs

## Next Steps

Ready to get started? Continue to the [Quick Start](/docs/getting-started/quickstart) to set up your account in 5 minutes.
`,

  quickstart: `
# Quick Start

Get up and running with BigMCP in 5 minutes.

## Step 1: Create an Account

1. Visit [bigmcp.cloud](https://bigmcp.cloud)
2. Click **Start Free Trial**
3. Enter your email and create a password
4. Verify your email address (check your inbox)

> **Note:** All new accounts include a 15-day free trial with full access to all features.

## Step 2: Explore the Marketplace

Once logged in, you'll land on the **Marketplace**. Here you can:

- Browse servers by category
- Search for specific tools
- View server details and required credentials

## Step 3: Connect Your First Server

Let's connect the **Fetch** server as an example (no credentials required):

1. Find "Fetch" in the marketplace
2. Click **Connect**
3. Click **Save** (no credentials needed for this server)

The Fetch server provides a single tool to retrieve web content - perfect for testing!

> **Tip:** For servers requiring credentials (like GitHub), you'll need to provide an API key or token.

## Step 4: View Your Services

Navigate to **Services** to see:

- Your connected servers
- Available tools from each server
- Connection status (green = connected)

## Step 5: Connect an AI Client

BigMCP works with any MCP-compatible client. The simplest way to get started:

1. Open your AI client (Claude Desktop, Mistral Le Chat, Cursor, etc.)
2. Go to the MCP settings / connectors section
3. Add a new MCP server with your instance URL:

\`\`\`
https://bigmcp.cloud
\`\`\`

4. Sign in with your **BigMCP credentials** (email and password)
5. Your tools appear automatically in the client

> For clients that don't support URL-based connection, see the [Integrations](/docs/integrations/claude-desktop) section for manual configuration via API key.

## What's Next?

- [Connect more servers](/docs/getting-started/first-server) from the marketplace
- [Learn about tools](/docs/concepts/tools) and how they work
- [Create tool groups](/docs/guides/tool-groups) to organize your setup
`,

  'first-server': `
# Connect Your First Server

This guide walks you through connecting an MCP server to BigMCP.

## Prerequisites

- A BigMCP account ([sign up here](/signup))
- Credentials for the server you want to connect (API keys, tokens, etc.)

## Finding Servers

### Browse by Category

The marketplace organizes servers into categories:

- **Data & Databases** - PostgreSQL, MongoDB, Airtable
- **Documents & Files** - Filesystem, Google Drive, Dropbox
- **Communication** - Slack, Discord, Email
- **Development** - GitHub, GitLab, Jira
- **Search & Knowledge** - Brave Search, Wikipedia
- **AI & ML** - OpenAI, Hugging Face

### Search

Use the search bar to find specific servers by name or functionality.

## Connecting a Server

### Step 1: Select the Server

Click on any server card to view its details:

- Description and capabilities
- Required credentials
- Available tools
- Source and verification status

### Step 2: Enter Credentials

Each server requires different credentials. Common types:

| Type | Example |
|------|---------|
| API Key | \`sk-abc123...\` |
| OAuth | Connect with Google/GitHub |
| Token | Personal access token |
| Path | Directory path on your system |

### Step 3: Save and Verify

Click **Save Credentials** to:

1. Encrypt and store your credentials
2. Verify the connection works
3. Fetch available tools

> **Security:** All credentials are encrypted using AES-128 (Fernet) before storage.

## Managing Connections

### View Status

In the **Services** page, each server shows:

- 🟢 Connected - Server is active and working
- 🔴 Disconnected - Connection issue (check credentials)
- ⚪ Inactive - Server manually disabled

### Update Credentials

1. Click the server in **Services**
2. Click the edit icon
3. Update credentials
4. Save changes

### Remove a Server

1. Click the server in **Services**
2. Click the trash icon
3. Confirm deletion

> **Note:** Removing a server deletes its credentials but doesn't affect the server itself.

## Troubleshooting

### "Connection Failed"

- Verify your credentials are correct
- Check if the external service is up
- Try disconnecting and reconnecting

### "Invalid Credentials"

- Regenerate your API key from the provider
- Check for expiration dates
- Ensure you have the required permissions

## Next Steps

- Learn about [MCP Servers](/docs/concepts/servers)
- Organize servers with [Toolboxes](/docs/guides/tool-groups)
- Set up [API Keys](/docs/guides/api-keys) for external access
`,
}
