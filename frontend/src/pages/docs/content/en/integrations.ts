/**
 * Integrations Documentation Content
 *
 * How to integrate BigMCP with various clients and platforms.
 */

export const integrationsContent: Record<string, string> = {
  'claude-desktop': `
# Claude Desktop Integration

Connect BigMCP to Claude Desktop to access all your tools directly in Claude.

## Overview

With BigMCP + Claude Desktop, you can:
- Access all your connected MCP servers through one endpoint
- Use Toolboxes to create specialized Claude profiles
- Leverage compositions as ready-to-use workflows
- Maintain one source of truth for credentials

## Prerequisites

- [Claude Desktop](https://claude.ai/desktop) installed
- BigMCP account with connected servers
- API key from BigMCP

## Quick Setup

### 1. Create an API Key

1. Log in to BigMCP
2. Go to **Settings** → **API Keys**
3. Click **Create Key**
4. Configure:
   - **Name**: "Claude Desktop"
   - **Scopes**: \`tools:read\`, \`tools:execute\`
   - **Toolbox**: (Optional) Select to limit available tools
5. Copy the generated key (shown only once!)

### 2. Configure Claude Desktop

Locate your Claude config file:

| OS | Path |
|----|------|
| macOS | \`~/Library/Application Support/Claude/claude_desktop_config.json\` |
| Windows | \`%APPDATA%\\Claude\\claude_desktop_config.json\` |
| Linux | \`~/.config/Claude/claude_desktop_config.json\` |

### 3. Add BigMCP Server

Edit the config file:

\`\`\`json
{
  "mcpServers": {
    "bigmcp": {
      "command": "npx",
      "args": [
        "-y",
        "@anthropic/mcp-proxy",
        "--endpoint", "https://bigmcp.cloud/mcp/sse",
        "--api-key", "mcphub_sk_your_key_here"
      ]
    }
  }
}
\`\`\`

### 4. Restart Claude Desktop

Close and reopen Claude Desktop to apply changes.

## Multiple Profiles with Toolboxes

Create different Claude configurations for different use cases:

\`\`\`json
{
  "mcpServers": {
    "work-tools": {
      "command": "npx",
      "args": [
        "-y", "@anthropic/mcp-proxy",
        "--endpoint", "https://bigmcp.cloud/mcp/sse",
        "--api-key", "mcphub_sk_work_key"
      ]
    },
    "personal-tools": {
      "command": "npx",
      "args": [
        "-y", "@anthropic/mcp-proxy",
        "--endpoint", "https://bigmcp.cloud/mcp/sse",
        "--api-key", "mcphub_sk_personal_key"
      ]
    },
    "read-only": {
      "command": "npx",
      "args": [
        "-y", "@anthropic/mcp-proxy",
        "--endpoint", "https://bigmcp.cloud/mcp/sse",
        "--api-key", "mcphub_sk_readonly_key"
      ]
    }
  }
}
\`\`\`

Each key can be linked to a different Toolbox, effectively creating specialized agents.

## Self-Hosted Configuration

For self-hosted BigMCP:

\`\`\`json
{
  "mcpServers": {
    "my-bigmcp": {
      "command": "npx",
      "args": [
        "-y", "@anthropic/mcp-proxy",
        "--endpoint", "https://your-domain.com/mcp/sse",
        "--api-key", "mcphub_sk_your_key"
      ]
    }
  }
}
\`\`\`

## Verification

After restarting Claude Desktop:

1. Start a new conversation
2. Look for the tools icon (🔧) in the input area
3. Click to see available tools
4. Try: "List my available tools"

## What You'll See

Claude will have access to:

- **Your connected tools**: All tools from servers you've connected
- **Orchestration tools**: \`orchestrator_search_tools\`, \`orchestrator_analyze_intent\`, etc.
- **Workflow tools**: Production compositions as \`workflow_*\` tools

If using a Toolbox-restricted key, only tools in that group appear.

## Troubleshooting

### "Connection failed"

- Verify API key is correct (starts with \`mcphub_sk_\`)
- Check internet connection
- Ensure BigMCP servers are connected
- Try accessing \`https://bigmcp.cloud/mcp/sse\` in browser (should show SSE stream)

### "No tools available"

- Check Toolbox permissions on API key
- Verify servers are connected in BigMCP dashboard
- Ensure API key has \`tools:read\` scope
- Try regenerating the API key

### Tools not executing

- Ensure API key has \`tools:execute\` scope
- Check credential validity in BigMCP
- Review tool-specific error messages
- Test the tool directly in BigMCP first

### Configuration not loading

- Verify JSON syntax is valid
- Check file path is correct for your OS
- Ensure no duplicate server names
- Try removing and re-adding the configuration
`,

  'mistral-lechat': `
# Mistral Le Chat Integration

Connect BigMCP to Mistral Le Chat to access all your tools directly in Mistral's AI assistant.

## Overview

Mistral Le Chat supports MCP connections via two methods:
- **OAuth 2.0** - Seamless, secure connection with automatic token management
- **API Key** - Direct connection with Toolbox support for access control

With BigMCP + Mistral Le Chat:
- Access all your connected MCP servers through one endpoint
- Use Toolboxes to control which tools are available
- Leverage compositions as ready-to-use workflows

## Prerequisites

- [Mistral Le Chat](https://chat.mistral.ai) account
- BigMCP account with connected servers
- At least one tool connected

## Method 1: OAuth Connection (Recommended)

OAuth provides seamless authentication without manual key management.

### Setup

1. Go to [chat.mistral.ai](https://chat.mistral.ai)
2. Navigate to **Settings** → **MCP Servers**
3. Click **Add Server**
4. Enter the BigMCP endpoint:
   \`\`\`
   https://bigmcp.cloud
   \`\`\`
5. Click **Connect**
6. You'll be redirected to BigMCP to authorize
7. Sign in and click **Authorize**

Done! Mistral Le Chat now has access to all your BigMCP tools.

### OAuth Benefits
- No API keys to manage
- Automatic token refresh
- Easy revocation from BigMCP settings

## Method 2: API Key Connection

Use API keys when you need Toolbox filtering for access control.

### Setup

1. In BigMCP, go to **Settings** → **API Keys**
2. Create a new key:
   - **Name**: "Mistral Le Chat"
   - **Scopes**: \`tools:read\`, \`tools:execute\`
   - **Toolbox**: Select a group to limit available tools
3. Copy the generated key

4. In Mistral Le Chat:
   - Go to **Settings** → **MCP Servers**
   - Click **Add Server**
   - Enter endpoint: \`https://bigmcp.cloud\`
   - Select **API Key** authentication
   - Paste your BigMCP API key
   - Click **Connect**

### API Key Benefits
- Toolbox filtering for access control
- Create specialized profiles with limited tools
- Multiple keys for different use cases

## Using Tools

Once connected, your tools appear in Mistral's interface:

1. Start a new conversation
2. Look for the **Tools** button in the message input
3. Ask Mistral to use any tool naturally:

\`\`\`
"Create a GitHub issue about the login bug"
"Search my Notion workspace for meeting notes"
"Send a Slack message to #general"
\`\`\`

## Toolboxes for Access Control

Create specialized Mistral profiles with limited tool access:

### Example: Read-Only Profile

1. Create a Toolbox "Read Only" with only \`list_*\`, \`get_*\`, \`read_*\` tools
2. Create an API Key linked to this group
3. Connect Mistral with this key

Mistral can only read data, never modify it.

### Example: Development Profile

1. Create a Toolbox "Dev Tools" with GitHub, GitLab, and Jira tools
2. Create an API Key linked to this group
3. Connect Mistral with this key

Mistral only sees development-related tools.

## Self-Hosted Configuration

For self-hosted BigMCP:

\`\`\`
https://your-domain.com
\`\`\`

Both OAuth and API Key methods work the same way.

## Troubleshooting

### "Authorization Failed"
- Ensure BigMCP is accessible
- Clear browser cookies and retry
- Check your BigMCP account status

### "No Tools Available"
- Verify you have connected servers in BigMCP
- Check server credentials are valid
- If using API Key, verify the Toolbox has tools

### "Tool Execution Failed"
- Check the specific server's credentials
- Verify the tool's required permissions
- Review error details in BigMCP dashboard

## Revoking Access

### OAuth
1. Go to BigMCP **Settings** → **Connected Apps**
2. Find "Mistral Le Chat"
3. Click **Revoke Access**

### API Key
1. Go to BigMCP **Settings** → **API Keys**
2. Find the key used by Mistral
3. Click **Delete**

## Comparison

| Feature | OAuth | API Key |
|---------|-------|---------|
| Setup | One-click | Manual |
| Toolboxes | All tools | Filtered |
| Token management | Automatic | Static |
| Best for | Quick start | Access control |
`,

  n8n: `
# n8n Integration

Use BigMCP tools in n8n automation workflows via REST API.

## Overview

n8n is a powerful workflow automation platform. With BigMCP integration:
- Access all your MCP tools from n8n nodes
- Build complex automations using AI-powered orchestration
- Execute compositions as single API calls
- Connect 100+ services through BigMCP

## Integration Methods

### Method 1: HTTP Request Node (Recommended)

Use n8n's built-in HTTP Request node to call BigMCP API.

#### Execute a Tool Binding

\`\`\`
Method: POST
URL: https://bigmcp.cloud/api/v1/tool-bindings/{binding_id}/execute
Headers:
  Authorization: Bearer mcphub_sk_your_key
  Content-Type: application/json
Body:
{
  "parameters": {
    "title": "{{ $json.title }}",
    "body": "{{ $json.body }}"
  }
}
\`\`\`

#### Execute via Orchestration

\`\`\`
Method: POST
URL: https://bigmcp.cloud/api/v1/orchestrate
Headers:
  Authorization: Bearer mcphub_sk_your_key
  Content-Type: application/json
Body:
{
  "query": "Create a GitHub issue for {{ $json.bug_description }}",
  "execute": true
}
\`\`\`

#### Execute a Composition

\`\`\`
Method: POST
URL: https://bigmcp.cloud/api/v1/compositions/{composition_id}/execute
Headers:
  Authorization: Bearer mcphub_sk_your_key
  Content-Type: application/json
Body:
{
  "parameters": {
    "issue_number": {{ $json.issue_number }}
  }
}
\`\`\`

### Method 2: Custom n8n Node (Coming Soon)

We're developing a dedicated BigMCP node for n8n with:
- Visual tool selection
- Auto-complete for parameters
- Composition browser
- Built-in authentication

## Example Workflows

### Issue Triage Automation

\`\`\`mermaid
flowchart LR
    GH(["<b>GitHub</b><br/>Webhook"])
    AI(["<b>BigMCP</b><br/>Analyze"])
    Label(["<b>BigMCP</b><br/>Add Labels"])
    Slack(["<b>Slack</b><br/>Notify"])

    GH --> AI --> Label --> Slack

    style GH fill:#ffffff,stroke:#d4d4d4,color:#262626
    style AI fill:#D97757,stroke:#c4624a,color:#ffffff
    style Label fill:#D97757,stroke:#c4624a,color:#ffffff
    style Slack fill:#f4e4df,stroke:#c4624a,color:#262626
\`\`\`

1. **Trigger**: GitHub webhook (new issue created)
2. **HTTP Request**: Call BigMCP orchestrate to analyze issue
3. **HTTP Request**: Call BigMCP to add labels based on analysis
4. **HTTP Request**: Call BigMCP to send Slack notification

### Daily Report Generation

\`\`\`mermaid
flowchart LR
    Sched(["<b>Schedule</b><br/>9 AM"])
    BigMCP(["<b>BigMCP</b><br/>Composition"])
    Email(["<b>Email</b><br/>Send"])

    Sched --> BigMCP --> Email

    style Sched fill:#ffffff,stroke:#d4d4d4,color:#262626
    style BigMCP fill:#D97757,stroke:#c4624a,color:#ffffff
    style Email fill:#f4e4df,stroke:#c4624a,color:#262626
\`\`\`

1. **Schedule Trigger**: Daily at 9 AM
2. **HTTP Request**: Execute BigMCP composition for report
3. **Send Email**: Forward report to stakeholders

### Customer Support Pipeline

\`\`\`mermaid
flowchart LR
    ZD(["<b>Zendesk</b><br/>New Ticket"])
    Cat(["<b>BigMCP</b><br/>Categorize"])
    Ctx(["<b>BigMCP</b><br/>Get Context"])
    Notion(["<b>Notion</b><br/>Log"])

    ZD --> Cat --> Ctx --> Notion

    style ZD fill:#ffffff,stroke:#d4d4d4,color:#262626
    style Cat fill:#D97757,stroke:#c4624a,color:#ffffff
    style Ctx fill:#D97757,stroke:#c4624a,color:#ffffff
    style Notion fill:#f4e4df,stroke:#c4624a,color:#262626
\`\`\`

## Authentication Setup

### Create Dedicated API Key

1. Go to BigMCP **Settings** → **API Keys**
2. Create key with:
   - **Name**: "n8n Automation"
   - **Scopes**: \`tools:execute\`
   - **Toolbox**: (Optional) Restrict to specific tools
3. Store key in n8n credentials

### n8n Credentials Configuration

1. In n8n, go to **Settings** → **Credentials**
2. Create new **Header Auth** credential:
   - **Name**: BigMCP API
   - **Header Name**: Authorization
   - **Header Value**: Bearer mcphub_sk_your_key

## Best Practices

1. **Use Toolboxes** - Create a specific group for n8n with only needed tools
2. **Handle Errors** - Add error handling nodes after API calls
3. **Rate Limiting** - Add delays between rapid API calls
4. **Logging** - Log BigMCP responses for debugging
5. **Separate Keys** - Use different API keys for different workflows
6. **Use Compositions** - Complex sequences should be BigMCP compositions, not n8n chains
`,

  'custom-clients': `
# Custom Clients

Build your own applications using the BigMCP MCP Gateway or REST API.

## Two Integration Approaches

| Approach | Use Case | Protocol |
|----------|----------|----------|
| MCP Gateway | AI assistants, real-time tools | SSE + JSON-RPC 2.0 |
| REST API | Automation, scripts, integrations | HTTP REST |

## MCP Gateway Integration

The MCP Gateway exposes your tools via standard MCP protocol:

\`\`\`
Endpoint: https://bigmcp.cloud/mcp/sse
Protocol: Server-Sent Events (SSE)
Messages: JSON-RPC 2.0
Auth: Bearer token (API key)
\`\`\`

### JavaScript/TypeScript Client

Using the official MCP SDK:

\`\`\`typescript
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { SSEClientTransport } from '@modelcontextprotocol/sdk/client/sse.js';

// Initialize client
const client = new Client({
  name: 'my-app',
  version: '1.0.0',
});

// Create SSE transport with auth
const transport = new SSEClientTransport(
  new URL('https://bigmcp.cloud/mcp/sse'),
  {
    requestInit: {
      headers: {
        'Authorization': 'Bearer mcphub_sk_your_key',
      },
    },
  }
);

// Connect
await client.connect(transport);

// Initialize session
await client.initialize();

// List available tools
const { tools } = await client.listTools();
console.log('Available tools:', tools.map(t => t.name));

// Call a tool
const result = await client.callTool({
  name: 'github_create_issue',
  arguments: {
    repo: 'myorg/myrepo',
    title: 'Created via MCP',
    body: 'This issue was created using the MCP protocol'
  },
});
console.log('Result:', result);
\`\`\`

### Python Client

Using the MCP Python SDK:

\`\`\`python
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

async def main():
    # Connect with authentication
    async with sse_client(
        "https://bigmcp.cloud/mcp/sse",
        headers={"Authorization": "Bearer mcphub_sk_your_key"}
    ) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize
            await session.initialize()

            # List tools
            tools = await session.list_tools()
            print(f"Found {len(tools.tools)} tools")

            for tool in tools.tools:
                print(f"  - {tool.name}: {tool.description}")

            # Call a tool
            result = await session.call_tool(
                "github_create_issue",
                {
                    "repo": "myorg/myrepo",
                    "title": "Created via MCP Python",
                    "body": "Issue created using MCP Python SDK"
                }
            )
            print(f"Result: {result}")

asyncio.run(main())
\`\`\`

## REST API Integration

For simpler use cases or non-MCP clients:

### cURL Examples

\`\`\`bash
# List tools
curl https://bigmcp.cloud/api/v1/tools \\
  -H "Authorization: Bearer mcphub_sk_your_key"

# Execute tool binding
curl -X POST https://bigmcp.cloud/api/v1/tool-bindings/{id}/execute \\
  -H "Authorization: Bearer mcphub_sk_your_key" \\
  -H "Content-Type: application/json" \\
  -d '{"parameters": {"title": "Hello World"}}'

# AI-powered orchestration
curl -X POST https://bigmcp.cloud/api/v1/orchestrate \\
  -H "Authorization: Bearer mcphub_sk_your_key" \\
  -H "Content-Type: application/json" \\
  -d '{
    "query": "Create an issue about login bug",
    "execute": true
  }'

# Execute composition
curl -X POST https://bigmcp.cloud/api/v1/compositions/{id}/execute \\
  -H "Authorization: Bearer mcphub_sk_your_key" \\
  -H "Content-Type: application/json" \\
  -d '{"parameters": {"issue_number": 42}}'
\`\`\`

### Python Requests

\`\`\`python
import requests

API_KEY = "mcphub_sk_your_key"
BASE_URL = "https://bigmcp.cloud"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# List tools
response = requests.get(f"{BASE_URL}/api/v1/tools", headers=headers)
tools = response.json()

# Execute binding
response = requests.post(
    f"{BASE_URL}/api/v1/tool-bindings/{binding_id}/execute",
    headers=headers,
    json={"parameters": {"title": "Hello"}}
)
result = response.json()

# Orchestrate
response = requests.post(
    f"{BASE_URL}/api/v1/orchestrate",
    headers=headers,
    json={
        "query": "Send a Slack message to #general",
        "execute": True
    }
)
orchestration = response.json()
\`\`\`

### JavaScript Fetch

\`\`\`javascript
const API_KEY = 'mcphub_sk_your_key';
const BASE_URL = 'https://bigmcp.cloud';

const headers = {
  'Authorization': \`Bearer \${API_KEY}\`,
  'Content-Type': 'application/json'
};

// List tools
const tools = await fetch(\`\${BASE_URL}/api/v1/tools\`, { headers })
  .then(r => r.json());

// Execute binding
const result = await fetch(
  \`\${BASE_URL}/api/v1/tool-bindings/\${bindingId}/execute\`,
  {
    method: 'POST',
    headers,
    body: JSON.stringify({ parameters: { title: 'Hello' } })
  }
).then(r => r.json());

// Orchestrate
const orchestration = await fetch(
  \`\${BASE_URL}/api/v1/orchestrate\`,
  {
    method: 'POST',
    headers,
    body: JSON.stringify({
      query: 'Create a Notion page with meeting notes',
      execute: true
    })
  }
).then(r => r.json());
\`\`\`

## Toolbox Filtering

When your API key is linked to a Toolbox:

- **MCP Gateway**: Only tools in the group are listed and callable
- **REST API**: Tool bindings are validated against the group

This enables building specialized clients with limited capabilities.

## SDKs & Libraries

| Language | MCP SDK | REST Client |
|----------|---------|-------------|
| JavaScript | [@modelcontextprotocol/sdk](https://www.npmjs.com/package/@modelcontextprotocol/sdk) | fetch / axios |
| Python | [mcp](https://pypi.org/project/mcp/) | requests / httpx |
| Go | Planned | net/http |
| Rust | Planned | reqwest |

## Resources

- [MCP Specification](https://spec.modelcontextprotocol.io)
- [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [BigMCP API Reference](/docs/api/api-overview)
`,
}
