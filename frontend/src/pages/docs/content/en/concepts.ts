/**
 * Core Concepts Documentation Content
 */

export const conceptsContent: Record<string, string> = {
  'mcp-overview': `
# MCP Protocol

The **Model Context Protocol (MCP)** is an open standard developed by Anthropic that enables AI assistants to securely connect to external tools and data sources.

## How MCP Works

\`\`\`mermaid
sequenceDiagram
    participant C as Claude (Client)
    participant S as MCP Server

    C->>S: Connect via SSE
    S-->>C: Advertise capabilities
    C->>S: tools/list
    S-->>C: Available tools
    C->>S: tools/call (execute)
    S-->>C: Tool result

    Note over C,S: JSON-RPC 2.0 over Server-Sent Events
\`\`\`

1. **Client** (Claude) connects to an MCP server
2. **Server** advertises available tools and resources
3. **Client** requests tool execution when needed
4. **Server** executes and returns results

## Protocol Components

### Tools
Functions that the AI can execute. Each tool has:
- A unique name
- Input schema (JSON Schema)
- Description for the AI

### Resources
Data the AI can read and reference:
- Files and documents
- Database records
- API responses

### Prompts
Pre-defined templates:
- System prompts
- User message templates
- Multi-turn conversation starters

## BigMCP's Role

BigMCP acts as a **gateway** between Claude and your MCP servers:

\`\`\`mermaid
flowchart LR
    CLAUDE(["<b>Claude</b>"])

    subgraph gateway [" "]
        direction TB
        GW(["<b>BigMCP Gateway</b>"])
        subgraph features [" "]
            direction LR
            F1(["Credentials"])
            F2(["Access Control"])
            F3(["Monitoring"])
        end
    end

    subgraph servers [" "]
        direction TB
        S1(["GitHub"])
        S2(["Slack"])
        S3(["Database"])
    end

    CLAUDE --> GW
    GW --> S1 & S2 & S3

    style gateway fill:none,stroke:#c4624a,stroke-width:2px
    style features fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style servers fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style CLAUDE fill:#ffffff,stroke:#d4d4d4,color:#262626
    style GW fill:#D97757,stroke:#c4624a,color:#ffffff
    style F1 fill:#f4e4df,stroke:#c4624a,color:#262626
    style F2 fill:#f4e4df,stroke:#c4624a,color:#262626
    style F3 fill:#f4e4df,stroke:#c4624a,color:#262626
    style S1 fill:#f4e4df,stroke:#c4624a,color:#262626
    style S2 fill:#f4e4df,stroke:#c4624a,color:#262626
    style S3 fill:#f4e4df,stroke:#c4624a,color:#262626
\`\`\`

## Learn More

- [Official MCP Documentation](https://modelcontextprotocol.io)
- [MCP Specification](https://spec.modelcontextprotocol.io)
- [MCP GitHub Repository](https://github.com/modelcontextprotocol)
`,

  servers: `
# MCP Servers

MCP servers are programs that expose **tools** and **resources** to AI assistants via the Model Context Protocol.

## What is an MCP Server?

An MCP server is a process that:
1. Listens for connections from MCP clients (like Claude)
2. Advertises its capabilities (tools, resources, prompts)
3. Executes tool requests and returns results

## Server Types

### Official Servers
Maintained by the MCP team:
- \`@modelcontextprotocol/server-filesystem\` - File operations
- \`@modelcontextprotocol/server-github\` - GitHub API
- \`@modelcontextprotocol/server-slack\` - Slack integration

### Community Servers
Created by the community:
- Database connectors (PostgreSQL, MongoDB)
- Third-party APIs (Notion, Airtable)
- Specialized tools (web scraping, image processing)

## Server Lifecycle

### Installation
\`\`\`bash
# npm servers
npx @modelcontextprotocol/server-filesystem

# Python servers
uvx mcp-server-sqlite

# Docker servers
docker run bigmcp/server-custom
\`\`\`

### Connection
BigMCP handles server lifecycle:
1. Starts the server process
2. Establishes MCP connection
3. Monitors health status
4. Restarts on failure

### Credentials
Many servers require credentials:
- API keys for external services
- OAuth tokens for user data
- Paths for local resources

## In BigMCP

### Marketplace
Browse 100+ curated servers with:
- Descriptions and capabilities
- Required credentials
- Verification status
- Popularity scores

### Connection Status
- 🟢 **Connected** - Server running and healthy
- 🔴 **Disconnected** - Connection failed
- ⚪ **Inactive** - Manually disabled

### Managing Servers
From the **Services** page:
- View connected servers and their tools
- Toggle visibility (show/hide from Claude)
- Start, stop, and restart servers
- Remove servers
`,

  tools: `
# Tools

Tools are the primary way MCP servers provide functionality to AI assistants.

## What is a Tool?

A tool is a function that:
- Has a unique **name** within its server
- Accepts structured **input** (JSON Schema)
- Returns structured **output**
- Includes a **description** for the AI

## Tool Example

\`\`\`json
{
  "name": "read_file",
  "description": "Read the contents of a file at the specified path",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Path to the file to read"
      }
    },
    "required": ["path"]
  }
}
\`\`\`

## Tool Visibility

In BigMCP, you can control which tools are available:

### Show/Hide Tools
- Toggle visibility per tool
- Hidden tools won't appear in Claude's context
- Useful for reducing noise

### Toolboxes
Bundle related tools together:
- "Development" group with GitHub + Jira
- "Research" group with Search + Wikipedia
- Assign groups to API keys

## Tool Execution

When Claude uses a tool:

1. Claude generates a tool call request
2. BigMCP validates the request
3. BigMCP forwards to the MCP server
4. Server executes and returns result
5. BigMCP sends result to Claude

## Best Practices

### For OAuth Users (Claude, Mistral)

OAuth connections expose **all visible services** to the AI assistant. To optimize your experience:

1. **Use Compositions** - Create custom tools by chaining multiple services together. This lets you expose a single, purpose-built tool instead of many raw tools.

2. **Hide services, show compositions** - Set services to "Hidden" in the Services page. The AI will only see your curated Compositions which can still use hidden services behind the scenes.

3. **Keep it focused** - Fewer tools = better AI performance. Only enable what you actually need.

### For API Key Users

API Keys offer more control through Toolboxes:

1. **Create Toolboxes** - Bundle related tools for specific use cases
2. **Restrict by API Key** - Each key can be limited to specific groups
3. **Separate concerns** - Different keys for different workflows
`,

  security: `
# Security Model

BigMCP implements a comprehensive security model to protect your credentials and data.

## Credential Types

| Type | Example | Use Case |
|------|---------|----------|
| API Key | \`sk-abc123...\` | Most APIs |
| OAuth Token | Access + Refresh | User data |
| Basic Auth | Username/Password | Legacy systems |
| Path | \`/home/user/docs\` | Local files |
| Connection String | \`postgres://...\` | Databases |

## Security Model

### Encryption
All credentials are encrypted:
- AES-128 encryption at rest (Fernet)
- TLS 1.3 in transit
- Per-user encryption keys

### Access Control
- Credentials are user-scoped
- Team credentials require Team plan
- No credential sharing by default

### Audit Trail
- All access is logged
- Credential usage tracked
- Alerts for suspicious activity

## Managing Credentials

### Adding Credentials
1. Connect a server from marketplace
2. Enter required values
3. Credentials are encrypted and stored

### Updating Credentials
To update credentials for a server:
1. Delete the current connection
2. Reconnect from the Marketplace
3. Enter the new credentials

### Rotating Credentials
Best practice is to rotate regularly:
1. Generate new credentials at provider
2. Reconnect the server in BigMCP with new credentials
3. Verify connection works
4. Revoke old credentials at provider

## Team Credentials

With a Team plan:
- Share credentials across organization
- Set per-credential permissions
- Central credential management

> **Note:** Team credentials are only available on Team and Enterprise plans.

## Two-Factor Authentication (2FA)

Protect your account with an extra layer of security using TOTP-based two-factor authentication.

### How to Enable 2FA

1. Go to **Settings → Account**
2. Find the **Two-Factor Authentication** section
3. Click **Enable 2FA**
4. Scan the QR code with your authenticator app (Google Authenticator, Authy, 1Password, etc.)
5. Save the **backup codes** securely
6. Enter a verification code to confirm

### Backup Codes

When you enable 2FA, you receive 10 backup codes:
- Each code can only be used **once**
- Store them in a secure location (password manager, safe)
- Use a backup code if you lose access to your authenticator app

### Logging In with 2FA

1. Enter your email and password
2. When prompted, enter the 6-digit code from your app
3. Or use a backup code if needed

### Disabling 2FA

To disable 2FA, go to **Settings → Account** and click **Disable 2FA**. You'll need to enter a valid code to confirm.

> **Security tip:** Keep 2FA enabled for maximum account protection. If you lose your device, use a backup code to regain access.
`,
}
