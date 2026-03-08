/**
 * API Reference Documentation Content
 *
 * Complete REST API documentation for BigMCP.
 */

export const apiContent: Record<string, string> = {
  'api-overview': `
# API Overview

BigMCP provides two ways to interact programmatically:

1. **MCP Gateway** - Full MCP protocol over SSE for AI clients
2. **REST API** - HTTP endpoints for tools, compositions, and management

## Base URLs

| Environment | Base URL |
|-------------|----------|
| Cloud | \`https://bigmcp.cloud\` |
| Self-Hosted | \`https://your-domain.com\` |

## Authentication

All API requests require authentication via API key:

\`\`\`bash
Authorization: Bearer mcphub_sk_your_api_key_here
\`\`\`

Get your API key from **Settings** → **API Keys** in BigMCP.

## MCP Gateway vs REST API

| Feature | MCP Gateway | REST API |
|---------|-------------|----------|
| Protocol | SSE + JSON-RPC 2.0 | HTTP REST |
| Endpoint | \`/mcp/sse\` | \`/api/v1/*\` |
| Use Case | AI clients (Claude, etc.) | Automation, integrations |
| Streaming | Yes | No |
| Tool Discovery | Built-in | Separate endpoint |

## Response Format

All REST API responses use JSON:

\`\`\`json
{
  "success": true,
  "data": { ... },
  "error": null
}
\`\`\`

Error responses:

\`\`\`json
{
  "detail": "Error message",
  "error_code": "INVALID_REQUEST"
}
\`\`\`

## HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request |
| 401 | Unauthorized (invalid/missing API key) |
| 403 | Forbidden (insufficient permissions) |
| 404 | Not Found |
| 422 | Validation Error |
| 429 | Rate Limited |
| 500 | Server Error |

## Rate Limits

| Plan | Requests/min | Concurrent |
|------|--------------|------------|
| Personal | 60 | 5 |
| Team | 300 | 20 |
| Enterprise / Self-Hosted | Unlimited | Unlimited |

## Scopes

API keys have scopes that limit access:

| Scope | Allows |
|-------|--------|
| \`tools:read\` | List tools, view metadata |
| \`tools:execute\` | Execute tools and compositions |
| \`credentials:read\` | View credential info |
| \`credentials:write\` | Create/update credentials |
| \`servers:read\` | View server configs |
| \`servers:write\` | Manage servers |
| \`admin\` | Full access |
`,

  'api-marketplace': `
# Marketplace API

Discover and search MCP servers in the marketplace.

## List Servers

\`\`\`http
GET /api/v1/marketplace/servers
\`\`\`

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| \`category\` | string | Filter by category |
| \`search\` | string | Text search |
| \`source\` | string | Filter by source (local, npm, github) |
| \`limit\` | int | Results per page (default: 50) |
| \`offset\` | int | Pagination offset |

### Response

\`\`\`json
{
  "servers": [
    {
      "package_name": "@anthropic/mcp-server-github",
      "name": "GitHub MCP Server",
      "description": "GitHub integration with issues, PRs, and more",
      "version": "1.2.0",
      "category": "development",
      "source": "npm",
      "icon_url": "https://cdn.simpleicons.org/github/white",
      "tools_count": 15,
      "downloads": 5420,
      "stars": 128,
      "verified": true
    }
  ],
  "total": 127,
  "limit": 50,
  "offset": 0
}
\`\`\`

## Get Server Details

\`\`\`http
GET /api/v1/marketplace/servers/{package_name}
\`\`\`

### Response

\`\`\`json
{
  "package_name": "@anthropic/mcp-server-github",
  "name": "GitHub MCP Server",
  "description": "Full GitHub integration...",
  "version": "1.2.0",
  "author": "Anthropic",
  "repository": "https://github.com/anthropics/mcp-server-github",
  "tools": [
    {
      "name": "create_issue",
      "description": "Create a new GitHub issue",
      "parameters": {
        "type": "object",
        "properties": {
          "repo": {"type": "string"},
          "title": {"type": "string"},
          "body": {"type": "string"}
        },
        "required": ["repo", "title"]
      }
    }
  ],
  "required_credentials": [
    {
      "name": "GITHUB_TOKEN",
      "description": "Personal access token",
      "required": true
    }
  ]
}
\`\`\`

## Semantic Search

\`\`\`http
POST /api/v1/marketplace/search
\`\`\`

### Request

\`\`\`json
{
  "query": "create documents in Google Docs",
  "limit": 10
}
\`\`\`

### Response

\`\`\`json
{
  "results": [
    {
      "package_name": "@anthropic/mcp-server-gdocs",
      "name": "Google Docs",
      "relevance_score": 0.92,
      "matched_tools": ["create_document", "update_document"]
    }
  ]
}
\`\`\`

## Get Categories

\`\`\`http
GET /api/v1/marketplace/categories
\`\`\`

### Response

\`\`\`json
{
  "categories": [
    {"id": "development", "name": "Development", "count": 32},
    {"id": "productivity", "name": "Productivity", "count": 28},
    {"id": "data", "name": "Data & Analytics", "count": 21},
    {"id": "communication", "name": "Communication", "count": 15},
    {"id": "ai", "name": "AI & ML", "count": 12},
    {"id": "other", "name": "Other", "count": 19}
  ]
}
\`\`\`
`,

  'api-credentials': `
# Credentials API

Manage credentials for connected MCP servers.

## List User Credentials

\`\`\`http
GET /api/v1/credentials
\`\`\`

### Response

\`\`\`json
{
  "credentials": [
    {
      "id": "cred-123",
      "name": "GitHub Token",
      "credential_type": "api_key",
      "server_id": "github-mcp",
      "created_at": "2024-01-15T10:00:00Z",
      "last_used_at": "2024-01-20T14:30:00Z"
    }
  ]
}
\`\`\`

## Create Credential

\`\`\`http
POST /api/v1/credentials
\`\`\`

### Request

\`\`\`json
{
  "name": "GitHub Token",
  "credential_type": "api_key",
  "server_id": "github-mcp",
  "value": "ghp_xxxxxxxxxxxx",
  "metadata": {
    "scopes": ["repo", "read:org"]
  }
}
\`\`\`

### Response

\`\`\`json
{
  "id": "cred-456",
  "name": "GitHub Token",
  "credential_type": "api_key",
  "server_id": "github-mcp",
  "created_at": "2024-01-21T09:00:00Z"
}
\`\`\`

## Update Credential

\`\`\`http
PATCH /api/v1/credentials/{credential_id}
\`\`\`

### Request

\`\`\`json
{
  "value": "ghp_new_token_value",
  "name": "GitHub Token (Updated)"
}
\`\`\`

## Delete Credential

\`\`\`http
DELETE /api/v1/credentials/{credential_id}
\`\`\`

### Response

\`\`\`json
{
  "success": true,
  "message": "Credential deleted"
}
\`\`\`

## Credential Types

| Type | Description |
|------|-------------|
| \`api_key\` | Simple API key/token |
| \`oauth2\` | OAuth 2.0 credentials |
| \`basic\` | Username/password |
| \`custom\` | Custom credential schema |
`,

  'api-mcp': `
# MCP Gateway API

The MCP Gateway provides full Model Context Protocol access over Server-Sent Events (SSE).

## Connecting to the Gateway

\`\`\`http
GET /mcp/sse
Authorization: Bearer mcphub_sk_your_api_key
\`\`\`

This establishes an SSE connection for JSON-RPC 2.0 communication.

### Connection Response

\`\`\`
HTTP/1.1 200 OK
Content-Type: text/event-stream
X-Session-ID: session_abc123

event: message
data: {"jsonrpc":"2.0","id":0,"result":{"capabilities":{"tools":{}}}}
\`\`\`

## Toolbox Filtering

**Key Feature**: If your API key is linked to a Toolbox, the gateway only exposes tools from that group.

\`\`\`
API Key without Toolbox → Sees ALL your tools
API Key with Toolbox    → Sees ONLY tools in that group
\`\`\`

This creates specialized MCP servers from a single BigMCP instance.

## JSON-RPC Methods

### List Tools

\`\`\`json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list"
}
\`\`\`

Response:

\`\`\`json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "github_create_issue",
        "description": "Create a GitHub issue",
        "inputSchema": {
          "type": "object",
          "properties": {
            "repo": {"type": "string"},
            "title": {"type": "string"},
            "body": {"type": "string"}
          },
          "required": ["repo", "title"]
        }
      },
      {
        "name": "workflow_issue_triage",
        "description": "Triage and categorize issues",
        "inputSchema": {...}
      },
      {
        "name": "orchestrator_search_tools",
        "description": "Search for tools by capability",
        "inputSchema": {...}
      }
    ]
  }
}
\`\`\`

### Call Tool

\`\`\`json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "github_create_issue",
    "arguments": {
      "repo": "myorg/myrepo",
      "title": "Bug: Login fails",
      "body": "Steps to reproduce..."
    }
  }
}
\`\`\`

Response:

\`\`\`json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Created issue #42: Bug: Login fails"
      }
    ]
  }
}
\`\`\`

### List Resources (Compositions)

\`\`\`json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "resources/list"
}
\`\`\`

### Initialize

\`\`\`json
{
  "jsonrpc": "2.0",
  "id": 0,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {
      "name": "my-client",
      "version": "1.0.0"
    }
  }
}
\`\`\`

## Built-in Orchestration Tools

The gateway always includes these tools:

| Tool | Description |
|------|-------------|
| \`orchestrator_search_tools\` | Semantic search for tools |
| \`orchestrator_analyze_intent\` | AI-powered intent analysis |
| \`orchestrator_execute_composition\` | Execute a composition |
| \`orchestrator_create_composition\` | Create new composition |

## Workflow Tools

Production compositions appear as \`workflow_*\` tools:

\`\`\`json
{
  "name": "workflow_daily_report",
  "description": "Generate daily analytics report",
  "inputSchema": {
    "type": "object",
    "properties": {
      "date": {"type": "string", "format": "date"}
    }
  }
}
\`\`\`

## Message Endpoint (Alternative)

For non-SSE clients, send individual messages:

\`\`\`http
POST /mcp/message
Authorization: Bearer mcphub_sk_your_api_key
X-Session-ID: session_abc123
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list"
}
\`\`\`

## Example: Full Session

\`\`\`javascript
// 1. Connect to SSE
const eventSource = new EventSource(
  'https://bigmcp.cloud/mcp/sse',
  { headers: { 'Authorization': 'Bearer mcphub_sk_xxx' }}
);

// 2. Initialize
await sendMessage({
  jsonrpc: '2.0',
  id: 0,
  method: 'initialize',
  params: {
    protocolVersion: '2024-11-05',
    clientInfo: { name: 'my-app', version: '1.0.0' }
  }
});

// 3. List tools (filtered by Toolbox if applicable)
const tools = await sendMessage({
  jsonrpc: '2.0',
  id: 1,
  method: 'tools/list'
});

// 4. Execute a tool
const result = await sendMessage({
  jsonrpc: '2.0',
  id: 2,
  method: 'tools/call',
  params: {
    name: 'github_create_issue',
    arguments: { repo: 'org/repo', title: 'Issue title' }
  }
});
\`\`\`
`,

  'api-tools': `
# Tools API

Execute tools and manage tool bindings via REST API.

## List Available Tools

\`\`\`http
GET /api/v1/tools
\`\`\`

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| \`server_id\` | string | Filter by server |
| \`refresh\` | bool | Force refresh from servers |

### Response

\`\`\`json
{
  "tools": [
    {
      "id": "tool-uuid",
      "name": "create_issue",
      "server_id": "github-mcp",
      "description": "Create a GitHub issue",
      "parameters": {
        "type": "object",
        "properties": {...},
        "required": [...]
      }
    }
  ]
}
\`\`\`

## Execute Tool via Binding

Tool bindings let you pre-configure parameters and execute tools.

### Create Binding

\`\`\`http
POST /api/v1/tool-bindings
\`\`\`

\`\`\`json
{
  "context_id": "context-uuid",
  "tool_id": "tool-uuid",
  "binding_name": "create_bug_report",
  "default_parameters": {
    "repo": "myorg/myrepo",
    "labels": ["bug"]
  },
  "locked_parameters": ["repo"]
}
\`\`\`

### Execute Binding

\`\`\`http
POST /api/v1/tool-bindings/{binding_id}/execute
\`\`\`

\`\`\`json
{
  "parameters": {
    "title": "Login button broken",
    "body": "The login button doesn't respond on mobile"
  }
}
\`\`\`

**Parameter Merging:**
- \`default_parameters\` from binding are used as base
- \`locked_parameters\` cannot be overridden by user
- User \`parameters\` override non-locked defaults

### Response

\`\`\`json
{
  "success": true,
  "result": {
    "issue_number": 42,
    "url": "https://github.com/myorg/myrepo/issues/42"
  },
  "execution_time_ms": 245.3,
  "binding_id": "binding-uuid",
  "binding_name": "create_bug_report",
  "tool_name": "create_issue",
  "server_id": "github-mcp",
  "merged_parameters": {
    "repo": "myorg/myrepo",
    "labels": ["bug"],
    "title": "Login button broken",
    "body": "The login button doesn't respond on mobile"
  }
}
\`\`\`

## Orchestrate (AI-Powered)

Use natural language to find and execute tools:

\`\`\`http
POST /api/v1/orchestrate
\`\`\`

\`\`\`json
{
  "query": "Create an issue about the login bug in the main repo",
  "execute": true,
  "parameters": {
    "title": "Login bug",
    "body": "Details..."
  }
}
\`\`\`

### Response

\`\`\`json
{
  "query": "Create an issue...",
  "analysis": {
    "intent": "create_issue",
    "confidence": 0.95,
    "proposed_composition": {
      "steps": [
        {
          "tool": "github_create_issue",
          "parameters": {...}
        }
      ]
    }
  },
  "execution": {
    "status": "completed",
    "result": {...}
  }
}
\`\`\`

## Toolboxes

### List Toolboxes

\`\`\`http
GET /api/v1/tool-groups
\`\`\`

### Create Toolbox

\`\`\`http
POST /api/v1/tool-groups
\`\`\`

\`\`\`json
{
  "name": "Customer Support Agent",
  "description": "Tools for customer support workflows",
  "visibility": "private"
}
\`\`\`

### Add Tool to Group

\`\`\`http
POST /api/v1/tool-groups/{group_id}/items
\`\`\`

\`\`\`json
{
  "item_type": "tool",
  "tool_id": "tool-uuid",
  "order": 0
}
\`\`\`

### Add Composition to Group

\`\`\`json
{
  "item_type": "composition",
  "composition_id": "composition-uuid",
  "order": 1
}
\`\`\`

## Compositions API

### List Compositions

\`\`\`http
GET /api/v1/compositions
\`\`\`

### Execute Composition

\`\`\`http
POST /api/v1/compositions/{composition_id}/execute
\`\`\`

\`\`\`json
{
  "parameters": {
    "issue_number": 42
  }
}
\`\`\`

### Promote Composition

\`\`\`http
POST /api/v1/compositions/{composition_id}/promote
\`\`\`

\`\`\`json
{
  "target_status": "production"
}
\`\`\`

Lifecycle: \`temporary\` → \`validated\` → \`production\`

Production compositions appear as \`workflow_*\` tools in the MCP Gateway.
`,
}
