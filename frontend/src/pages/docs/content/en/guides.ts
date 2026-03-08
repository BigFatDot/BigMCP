/**
 * Guides Documentation Content
 *
 * Practical how-to guides for BigMCP features.
 */

export const guidesContent: Record<string, string> = {
  marketplace: `
# Discover Servers

The BigMCP Marketplace is your gateway to discovering and connecting MCP servers.

## Browsing Servers

The marketplace aggregates MCP servers from multiple sources:

- **Official Registry** - Curated, verified servers
- **NPM Registry** - Community packages with \`@mcp/\` prefix
- **GitHub** - Open source MCP server repositories

### Categories

Servers are organized by category:

- **Data & Analytics** - Database connectors, BI tools
- **Development** - Git, CI/CD, code analysis
- **Productivity** - Documents, calendars, notes
- **Communication** - Email, chat, notifications
- **AI & ML** - Model APIs, embeddings, inference
- **Other** - Miscellaneous tools

### Search

Use the search bar to find servers by:
- Name or description
- Capabilities (tools, resources)
- Keywords and tags

## Connecting a Server

### 1. Select a Server

Click on a server card to view its details:
- Available tools and their descriptions
- Required credentials
- Configuration options

### 2. Configure Credentials

Most servers require credentials to function:

1. Click **Connect** on the server card
2. Fill in required credentials (API keys, tokens, etc.)
3. Optionally set a custom connection name
4. Click **Connect Server**

### 3. Verify Connection

Once connected, the server will:
- Appear in your **Services** page
- Show connection status (Active, API Only, Standby, or Disabled)
- List all available tools
`,

  'tool-groups': `
# Toolboxes

Toolboxes are one of BigMCP's most powerful features. They let you create **specialized MCP servers** by bundling specific tools together.

## What are Toolboxes?

A Toolbox is a curated collection of tools that can be exposed as a **dedicated MCP server** via an API key. This enables:

- **Specialized Agents** - Create focused agents with only relevant tools
- **Access Control** - Limit what tools an integration can use
- **Security** - Expose read-only tools to some clients, full access to others
- **Organization** - Group related tools for specific use cases

## How Toolboxes Work

\`\`\`mermaid
flowchart TB
    subgraph account [" "]
        SERVERS(["<b>Your Account</b><br/>━━━━━━━━━━━━━<br/>GitHub · Notion · Slack · PostgreSQL<br/>45 Total Tools"])
    end

    subgraph groups [" "]
        direction LR
        G1(["<b>Dev Assistant</b><br/>12 tools"])
        G2(["<b>Read-Only</b><br/>20 tools"])
        G3(["<b>Data Agent</b><br/>8 tools"])
    end

    subgraph keys [" "]
        direction LR
        K1(["<b>Claude Dev</b><br/>→ 12 tools"])
        K2(["<b>Public Bot</b><br/>→ 20 tools"])
        K3(["<b>Analytics</b><br/>→ 8 tools"])
    end

    SERVERS --> G1 & G2 & G3
    G1 --> K1
    G2 --> K2
    G3 --> K3

    style account fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style groups fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style keys fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style SERVERS fill:#D97757,stroke:#c4624a,color:#ffffff
    style G1 fill:#f4e4df,stroke:#c4624a,color:#262626
    style G2 fill:#f4e4df,stroke:#c4624a,color:#262626
    style G3 fill:#f4e4df,stroke:#c4624a,color:#262626
    style K1 fill:#ffffff,stroke:#d4d4d4,color:#262626
    style K2 fill:#ffffff,stroke:#d4d4d4,color:#262626
    style K3 fill:#ffffff,stroke:#d4d4d4,color:#262626
\`\`\`

When you create an API key linked to a Toolbox, that key **only sees and can execute** the tools in that group.

## Creating a Toolbox

### 1. Navigate to Toolboxes

Go to **Services** → **Toolboxes** tab → **Create Group**

### 2. Configure the Group

- **Name**: Descriptive name (e.g., "Customer Support Agent")
- **Description**: What this group is for
- **Visibility**:
  - Private (only you)
  - Organization (team members)
  - Public (discoverable)

### 3. Add Tools

Select tools to include from your connected servers:

1. Browse available tools by server
2. Check the tools you want to include
3. Optionally reorder for display priority
4. Click **Save Group**

### 4. Add Compositions (Optional)

You can also add saved compositions (workflows) to a Toolbox. These appear as \`workflow_*\` tools when accessed via MCP.

## Linking a Toolbox to an API Key

This is the key step that creates a specialized MCP server:

1. Go to **API Keys** page
2. Click **Create API Key**
3. Select your Toolbox from the dropdown
4. Set appropriate scopes (\`tools:read\`, \`tools:execute\`)
5. Copy the generated key

Now, any MCP client using this key will only see and access the tools in that group.

## Use Cases

### Read-Only Analytics Agent

Create a group with only \`list_*\`, \`get_*\`, \`read_*\`, and \`query_*\` tools. Link it to an API key for a reporting bot that can read but never modify data.

### Customer Support Agent

Bundle tools for:
- Reading customer data
- Viewing order history
- Creating support tickets
- Sending notifications

Exclude tools for refunds, account deletion, or admin actions.

### Development Assistant

Include:
- GitHub: create_issue, list_prs, read_file
- Notion: search_docs, read_page
- Slack: send_message (to dev channel only)

### Automation Pipeline

Create a minimal group for a specific automation:
- One database query tool
- One notification tool
- One logging tool

This limits blast radius if the automation is compromised.

## Best Practices

1. **Principle of Least Privilege** - Only include tools actually needed
2. **Descriptive Names** - Make the purpose clear from the name
3. **Document Usage** - Use the description field to explain intended use
4. **Regular Review** - Periodically check if tools are still needed
5. **Separate Environments** - Use different groups for dev/staging/prod

## Accessing Toolboxes via MCP

Once you have an API key linked to a Toolbox, configure your MCP client:

\`\`\`json
{
  "mcpServers": {
    "my-specialized-agent": {
      "command": "npx",
      "args": [
        "-y", "@anthropic/mcp-proxy",
        "--endpoint", "https://bigmcp.cloud/mcp/sse",
        "--api-key", "mcphub_sk_your_key_here"
      ]
    }
  }
}
\`\`\`

The client will only see tools from the linked Toolbox.
`,

  'api-keys': `
# API Keys

API keys provide secure, scoped access to BigMCP's capabilities for external integrations.

## Overview

API keys enable:
- **MCP Gateway Access** - Connect Claude Desktop, Cursor, or custom clients
- **REST API Access** - Execute tools and compositions programmatically
- **Toolbox Filtering** - Expose only specific tools per key
- **Audit Trail** - Track usage per key

## Key Format

BigMCP API keys follow this format:

\`\`\`
mcphub_sk_<random_characters>
\`\`\`

Example: \`mcphub_sk_abc123def456ghi789jkl012mno345\`

## Creating an API Key

### 1. Navigate to API Keys

Go to **Settings** → **API Keys** → **Create Key**

### 2. Configure the Key

| Field | Description |
|-------|-------------|
| **Name** | Descriptive name (e.g., "Claude Desktop - Work") |
| **Description** | Optional notes about usage |
| **Scopes** | Permissions granted (see below) |
| **Toolbox** | Optional - restrict to specific tools |
| **Expiration** | Optional expiry date |

### 3. Select Scopes

Available scopes:

| Scope | Permission |
|-------|------------|
| \`tools:read\` | List and view tool metadata |
| \`tools:execute\` | Execute tools |
| \`credentials:read\` | View credential metadata |
| \`credentials:write\` | Create/update credentials |
| \`servers:read\` | View server configurations |
| \`servers:write\` | Manage servers |
| \`admin\` | Full administrative access |

**Recommended for MCP clients:** \`tools:read\` + \`tools:execute\`

### 4. Link to Toolbox (Optional but Recommended)

Select a Toolbox to restrict which tools this key can access:

- **No Toolbox**: Key accesses ALL your tools
- **With Toolbox**: Key only accesses tools in that group

This is the mechanism for creating specialized agents.

### 5. Save and Copy

**Important**: The full key is only shown once. Copy it immediately and store securely.

## Using API Keys

### MCP Gateway (SSE)

For MCP clients like Claude Desktop:

\`\`\`bash
# Connect to the MCP gateway
GET https://bigmcp.cloud/mcp/sse
Authorization: Bearer mcphub_sk_your_key_here
\`\`\`

### REST API

For HTTP API calls:

\`\`\`bash
# List available tools
curl https://bigmcp.cloud/api/v1/tools \\
  -H "Authorization: Bearer mcphub_sk_your_key_here"

# Execute a tool binding
curl -X POST https://bigmcp.cloud/api/v1/tool-bindings/{id}/execute \\
  -H "Authorization: Bearer mcphub_sk_your_key_here" \\
  -H "Content-Type: application/json" \\
  -d '{"parameters": {"title": "Hello"}}'
\`\`\`

## Managing Keys

### View All Keys

The API Keys page shows:
- Key name and prefix (first 8 chars)
- Associated Toolbox (if any)
- Scopes granted
- Created date
- Last used date

### Revoke a Key

1. Find the key in the list
2. Click **Revoke**
3. Confirm the action

Revoked keys immediately stop working. This cannot be undone.

### Rotate a Key

For security, periodically rotate keys:

1. Create a new key with same configuration
2. Update your integrations to use the new key
3. Verify everything works
4. Revoke the old key

## Security Best Practices

1. **Enable 2FA** - Protect your account with [two-factor authentication](/docs/concepts/security)
2. **One Key Per Integration** - Don't share keys between different uses
3. **Use Toolboxes** - Limit access to only needed tools
4. **Minimal Scopes** - Only grant required permissions
5. **Set Expiration** - For temporary integrations, set an expiry
6. **Monitor Usage** - Check "last used" to detect unauthorized use
7. **Rotate Regularly** - Change keys periodically
8. **Never Commit Keys** - Keep keys out of source code

## API Key + Toolbox = Specialized Server

The combination of an API key with a Toolbox is powerful:

\`\`\`
API Key: "Support Bot Key"
├── Toolbox: "Customer Support"
│   ├── get_customer_info
│   ├── list_orders
│   ├── create_ticket
│   └── send_notification
└── Exposed via: https://bigmcp.cloud/mcp/sse

Any client using this key sees ONLY these 4 tools,
as if it were a dedicated MCP server just for support.
\`\`\`

This enables:
- Different Claude Desktop profiles with different capabilities
- Multiple AI agents with specialized access
- Secure automation with minimal permissions
`,

  credentials: `
# Manage Services

The **Services** page is your central dashboard for managing all connected MCP servers and their tools.

## Overview

From the Services page, you can:
- View all your connected servers
- Control server visibility for Claude
- Start, stop, and restart servers
- Remove servers you no longer need
- See available tools from each server

## Services Page Layout

The Services page has two main views:

### Servers Tab
Shows all your connected MCP servers with:
- Connection status (Active, API Only, Standby, Disabled, Error)
- Number of tools available
- Visibility toggle for Claude
- Server controls

### Toolboxes Tab
Manage collections of tools for API key access. See [Toolboxes guide](/docs/guides/tool-groups) for details.

## Server Status

Each server displays one of these statuses:

| Status | Meaning |
|--------|---------|
| **Active** | Running and visible to Claude |
| **API Only** | Running but hidden from Claude (API/Toolboxes only) |
| **Standby** | Stopped but will be visible when started |
| **Disabled** | Stopped and hidden |
| **Error** | Server encountered an issue |

## Visibility Toggle

The visibility toggle controls whether a server's tools are available to Claude:

- **Visible (On)** - Claude can see and use all tools from this server
- **Hidden (Off)** - Tools are hidden from Claude but still available via API keys and Toolboxes

> **Tip:** Hide servers you only need for automations or specific API integrations.

## Server Controls

For each connected server, you can:

| Action | Description |
|--------|-------------|
| **Start** | Start a stopped server |
| **Stop** | Stop a running server |
| **Restart** | Restart the server (useful after credential updates) |
| **Delete** | Remove the server and its credentials |

## Viewing Tools

Click the expand arrow on any server to see:
- List of all available tools
- Tool descriptions
- Creation date and last used timestamp

## Updating Credentials

To update credentials for a server:
1. Delete the current server connection
2. Reconnect the server from the Marketplace
3. Enter the new credentials

> **Note:** Direct credential editing will be available in a future update.

## Team Services

With a **Team plan**, you'll see an additional "Team Servers" tab with servers shared by your organization administrator. See [Team Services guide](/docs/guides/team-services) for details.

## Troubleshooting

### Server Shows "Error" Status
- Check that your credentials are still valid
- Try restarting the server
- If persistent, delete and reconnect with fresh credentials

### Tools Not Appearing
- Ensure the server is running (green status)
- Wait a few seconds for tool discovery
- Check if the server actually exposes tools

### Server Won't Start
- Verify your credentials are correct
- Check if the external service is available
- Review server logs for specific errors
`,

  compositions: `
# Build Compositions

Compositions (also called Workflows) let you chain multiple tools together into reusable, automated sequences.

## What are Compositions?

A composition is a saved sequence of tool calls that:
- Execute in order with data flowing between steps
- Can be triggered via API or MCP
- Support parameter templates and mappings
- Track execution history and metrics

## Composition Lifecycle

\`\`\`mermaid
flowchart LR
    T(["<b>Temporary</b><br/>Auto-created"])
    V(["<b>Validated</b><br/>Tested & approved"])
    P(["<b>Production</b><br/>workflow_* tools"])

    T --> V --> P

    style T fill:#f4e4df,stroke:#c4624a,color:#262626
    style V fill:#f4e4df,stroke:#c4624a,color:#262626
    style P fill:#D97757,stroke:#c4624a,color:#ffffff
\`\`\`

1. **Temporary**: Auto-created from orchestration, experimental
2. **Validated**: Tested and approved for regular use
3. **Production**: Stable, exposed as \`workflow_*\` tools in the MCP Gateway

## Tool Naming Convention

When you call \`list_tools\`, tools are returned with **prefixed names** for uniqueness:

\`\`\`
Format: ServerName__original_tool_name

Examples:
- Hostinger__list_organizations
- Grist__list_workspaces
- Notion__search_pages
- GitHub__create_issue
\`\`\`

**Always use these prefixed names in your compositions.**

## Creating Compositions

### Via Natural Language (Recommended)

1. Open BigMCP chat or connect via MCP
2. Describe what you want to accomplish
3. BigMCP analyzes intent and suggests tools
4. Execute the sequence
5. If successful, save as a composition

### Via API

\`\`\`bash
POST /api/v1/compositions
{
  "name": "Issue Triage",
  "description": "Analyze and route new issues",
  "steps": [
    {
      "id": "1",
      "tool": "GitHub__get_issue",
      "parameters": {"issue_number": "\${input.issue_number}"}
    },
    {
      "id": "2",
      "tool": "AI__analyze_text",
      "parameters": {"text": "\${step_1.body}"}
    },
    {
      "id": "3",
      "tool": "Slack__send_message",
      "parameters": {
        "channel": "#dev-alerts",
        "text": "Issue #\${input.issue_number}: \${step_2.summary}"
      }
    }
  ],
  "input_schema": {
    "type": "object",
    "properties": {
      "issue_number": {"type": "integer", "description": "GitHub issue number"}
    },
    "required": ["issue_number"]
  }
}
\`\`\`

## Data Mappings - Reference Syntax

Compositions support data flow between steps using \`\${...}\` template syntax:

| Syntax | Description | Example |
|--------|-------------|---------|
| \`\${input.param}\` | Input parameter | \`\${input.workspace_id}\` |
| \`\${step_X.field}\` | Field from step X result | \`\${step_1.id}\` |
| \`\${step_X.path.to.value}\` | Nested field | \`\${step_1.data.items[0].name}\` |

### Wildcard Extraction \`[*]\`

Extract **all values** from an array:

\`\`\`json
{
  "id": "2",
  "tool": "Grist__get_records",
  "parameters": {
    "doc_ids": "\${step_1.documents[*].id}"
  }
}
\`\`\`

Result: \`["doc1", "doc2", "doc3"]\` (flattened list)

**Nested wildcards** for complex structures:
\`\`\`
\${step_1.workspaces[*].docs[*].id}
\`\`\`
Extracts all doc IDs from all workspaces (auto-flattened).

### Template/Map Pattern

For complex transformations with parent context:

\`\`\`json
{
  "id": "3",
  "tool": "Notion__create_pages",
  "parameters": {
    "pages": {
      "_template": "\${step_1.workspaces[*].docs[*]}",
      "_map": {
        "doc_id": "\${_item.id}",
        "doc_title": "\${_item.title}",
        "workspace_id": "\${_parent.id}",
        "synced_at": "\${_now}"
      }
    }
  }
}
\`\`\`

**Variables available in \`_map\`:**

| Variable | Description |
|----------|-------------|
| \`\${_item}\` | Current iteration item |
| \`\${_parent}\` | Parent object (one level up) |
| \`\${_root}\` | Original step result |
| \`\${_index}\` | Iteration index (0, 1, 2...) |
| \`\${_now}\` | ISO timestamp |

## Complete Example

\`\`\`json
{
  "name": "Sync Grist to Notion",
  "description": "Synchronize Grist tables to Notion pages",
  "steps": [
    {
      "id": "1",
      "tool": "Grist__list_workspaces",
      "parameters": {}
    },
    {
      "id": "2",
      "tool": "Grist__list_docs",
      "parameters": {
        "workspace_id": "\${step_1.workspaces[0].id}"
      }
    },
    {
      "id": "3",
      "tool": "Notion__create_pages",
      "parameters": {
        "pages": {
          "_template": "\${step_2.docs[*]}",
          "_map": {
            "title": "\${_item.name}",
            "source_id": "\${_item.id}",
            "workspace": "\${step_1.workspaces[0].name}",
            "imported_at": "\${_now}"
          }
        }
      }
    }
  ],
  "input_schema": {
    "type": "object",
    "properties": {},
    "required": []
  }
}
\`\`\`

## Executing Compositions

### Via MCP Gateway

Production compositions appear as tools prefixed with \`workflow_\`:

\`\`\`json
{
  "method": "tools/call",
  "params": {
    "name": "workflow_issue_triage",
    "arguments": {
      "issue_number": 123
    }
  }
}
\`\`\`

### Via REST API

\`\`\`bash
POST /api/v1/compositions/{composition_id}/execute
{
  "parameters": {
    "issue_number": 123
  }
}
\`\`\`

### Via Orchestrate Endpoint

\`\`\`bash
POST /api/v1/orchestrate
{
  "query": "Triage issue #123",
  "execute": true
}
\`\`\`

BigMCP will match your intent to existing compositions.

## Promoting Compositions

To move a composition to production:

\`\`\`bash
POST /api/v1/compositions/{id}/promote
{
  "target_status": "production"
}
\`\`\`

Or use the UI: Compositions page → Select composition → Promote

## Adding to Toolboxes

Production compositions can be added to Toolboxes:

1. Go to Toolboxes
2. Edit your group
3. Switch to "Compositions" tab
4. Select compositions to include
5. Save

The composition then appears as a tool when accessing that group via API key.

## Monitoring

View composition execution history:

- **Executions**: Success/failure count
- **Duration**: Average execution time
- **Errors**: Recent failures with details
- **Usage**: Which integrations use this composition

## Best Practices

1. **Test Thoroughly** - Run compositions multiple times before promoting
2. **Handle Errors** - Consider what happens if a step fails
3. **Descriptive Names** - Make the purpose clear
4. **Document Parameters** - Explain expected inputs
5. **Version Control** - Keep notes on changes
6. **Monitor Production** - Watch for failures after promoting
`,

  'team-services': `
# Team Services

Team Services allow organization administrators to configure **shared MCP servers** that are automatically available to all team members.

## Overview

With a **Team plan**, administrators can:
- Connect MCP servers at the organization level
- Share credentials securely across all team members
- Ensure consistent tool availability for the entire team
- Manage access from a central dashboard

## How Team Services Work

\`\`\`
Organization Administrator
        │
        ▼
┌─────────────────────────────────────┐
│         Team Services               │
│  ┌─────────┐ ┌─────────┐ ┌───────┐  │
│  │ GitHub  │ │  Slack  │ │ Jira  │  │
│  │ (org)   │ │  (org)  │ │ (org) │  │
│  └─────────┘ └─────────┘ └───────┘  │
└─────────────────────────────────────┘
        │
        ▼ (automatically shared)
┌─────────────────────────────────────┐
│           Team Members              │
│  👤 Alice  👤 Bob  👤 Charlie       │
│  (sees team + personal services)    │
└─────────────────────────────────────┘
\`\`\`

Team members see **both**:
- **Team Services**: Managed by the administrator
- **Personal Services**: Their own connected servers

## Setting Up Team Services (Admin)

### 1. Access Admin Panel

1. Log in as an organization administrator
2. Go to **Settings** → **Organization**
3. Select the **Team Services** tab

### 2. Connect a Team Server

1. Click **Add Team Service**
2. Browse the marketplace or search for a server
3. Enter the organization-level credentials
4. Click **Save**

The server is now available to all team members.

### 3. Configure Visibility

For each team service, you can set:

| Setting | Description |
|---------|-------------|
| **Visible** | Tools appear in members' Services page |
| **Hidden** | Available for compositions but not shown |
| **Disabled** | Temporarily turned off for the team |

## Member Experience

Team members see team services in their **Services** page with a "Team" badge. They can:

- **Use** all visible team services
- **Create compositions** using team services
- **Hide** team services from their personal view

Members **cannot**:
- Modify team service credentials
- Disconnect team services
- Change team service settings

## Credential Management

### Organization Credentials

Team service credentials are stored at the organization level:
- Encrypted with **AES-128** (Fernet)
- Accessible only to admins for editing
- Injected automatically for team members

### Best Practices

1. **Use service accounts** - Create dedicated accounts for team services
2. **Rotate regularly** - Update credentials every 90 days
3. **Document access** - Note which credentials have admin-level access
4. **Audit usage** - Review which members are using team services

## Use Cases

### Development Team

Connect shared development tools:
- **GitHub** with organization repo access
- **Jira** for project tracking
- **Confluence** for documentation
- **SonarQube** for code quality

### Customer Success Team

Shared customer-facing tools:
- **Zendesk** for support tickets
- **Salesforce** for customer data
- **Intercom** for chat history

### Data Team

Shared data infrastructure:
- **PostgreSQL** production database (read-only)
- **Metabase** for dashboards
- **dbt** for transformations

## Differences: Personal vs Team Services

| Aspect | Personal Services | Team Services |
|--------|-------------------|---------------|
| **Managed by** | Individual user | Organization admin |
| **Credentials** | User's own | Organization-level |
| **Visibility** | Only the user | All team members |
| **Billing** | Included in user plan | Included in Team plan |
| **Modifications** | User controls | Admin controls |

## Plan Requirements

| Feature | Personal | Team | Enterprise |
|---------|----------|------|------------|
| Personal Services | ✅ | ✅ | ✅ |
| Team Services | ❌ | ✅ | ✅ |
| Custom Marketplace | ❌ | ❌ | ✅ |

> **Note:** Team Services require a **Team** or **Enterprise** plan. [Upgrade your plan](/pricing) to enable this feature.
`,
}
