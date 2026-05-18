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

This page is the single source of truth for BigMCP's security posture.
DSI / security teams should be able to evaluate the platform from this
page alone, and ops teams should know exactly what to harden before
opening up to real users.

## Threat model

What BigMCP **protects against**:

- **Credential exfiltration** — every credential (MCP server API key, OAuth
  refresh token, DB connection string) is encrypted at rest with Fernet
  (AES-128-CBC + HMAC-SHA256). Plaintext only exists in memory during
  tool execution. A leaked database dump alone is not enough to read
  credentials — the attacker also needs \`ENCRYPTION_KEY\` from the env.
- **Privilege escalation across orgs** — every CRUD endpoint that takes
  an object id checks that the object belongs to the caller's org
  before returning it. Cross-org references surface as 404
  ("does not exist") rather than 403 — no info leak.
- **Unscoped API key abuse** — API keys carry a list of scopes
  (\`tools:read\`, \`tools:execute\`, \`credentials:read\`, \`servers:write\`,
  \`admin\`, …). With \`SCOPE_ENFORCE_MODE=enforce\`, missing scopes return
  403 + audit log entry. With \`log_only\` (default during initial
  rollout) the call goes through but is recorded — flip to \`enforce\`
  after a few days of shadow auditing.
- **Audit-log tampering** — every \`audit_log\` row carries an HMAC-SHA256
  signature over the canonical JSON of the action; \`verify_integrity()\`
  returns False if anyone edits a row in-place. The HMAC key is
  derived from \`SECRET_KEY\` so attackers without that key can't forge
  rows either.
- **Token replay after sign-out** — refresh tokens carry a JTI; per-JTI
  revocation in \`oauth_sessions\` lets a user kill a stolen token
  without nuking every active device (\`/auth/connected-apps\`).
- **CSRF on cookie-bearing endpoints** — every state-changing request
  requires a \`Bearer\` token or API key in the \`Authorization\` header,
  not a cookie. Browsers don't send \`Authorization\` cross-origin
  automatically, so CSRF doesn't apply.
- **Rate-limit-based abuse** — \`RATE_LIMIT_PER_MINUTE=60\` globally;
  \`/auth/\` is harder-capped at 20/min; \`/api-keys/\` at 30/min.

What BigMCP **does NOT protect against** (call this out to your team):

- **Loss of \`ENCRYPTION_KEY\`** — irrecoverable. Every credential becomes
  permanently unreadable. Back the key up out-of-band (vault, hardware
  token, sealed envelope) before deploying to prod.
- **Compromised LLM provider** — composition execution sends tool
  outputs to your configured \`LLM_API_URL\`. If you don't trust the
  LLM provider with that data, point \`LLM_API_URL\` at a self-hosted
  endpoint (Ollama, vLLM, Mistral on-prem).
- **MCP server vulnerabilities** — BigMCP doesn't sandbox 3rd-party
  MCP servers. A malicious server you install can read its own env,
  write to its own working dir, and talk to the network. Install only
  from sources you trust (your own, the curated marketplace, or
  carefully audited 3rd parties).

## At rest

| What | Algorithm | Key source |
|------|-----------|------------|
| User credentials (per-user + per-org) | Fernet (AES-128-CBC + HMAC-SHA256) | \`ENCRYPTION_KEY\` env, single instance-wide key |
| Passwords | bcrypt (cost 12) | Per-row salt |
| API keys | bcrypt (the secret is shown once at creation, only the hash is stored) | Per-row salt |
| Audit log integrity | HMAC-SHA256 over canonical JSON | Derived from \`SECRET_KEY\` |
| JWT signing | HS256 | \`SECRET_KEY\` env |

## In transit

- Frontend → backend: TLS terminated at nginx (or your reverse proxy).
  The default docker-compose ships a self-signed cert; for production,
  use Caddy / Traefik or certbot to mount a real one.
- Backend → MCP servers: TLS where the server supports it. The
  \`HttpMCPWrapper\` doesn't downgrade.
- Backend → LLM / embeddings provider: HTTPS to your configured
  \`LLM_API_URL\`. Cleartext only if you point it at an HTTP endpoint
  (don't).
- MCP gateway endpoint (\`/mcp/sse\`, \`/mcp/message\`): TLS via nginx.
  Per-session auth via \`Authorization: Bearer <api_key>\`.

## Access control

Four layers, evaluated left-to-right:

1. **Authentication** — JWT (login + refresh) or API key (\`bigmcp_sk_*\`).
2. **Edition gating** — billing routes only loaded under
   \`EDITION=cloud_saas\`; MFA optional on community.
3. **Organization membership** — every authenticated request resolves
   the caller's active org (\`Mcp-Session-Id\` for MCP, \`org_id\` claim
   on JWT, \`organization_id\` on API key). Every object query joins
   on this org.
4. **RBAC role** — four tiers: \`Owner > Admin > Member > Viewer\`.
   Admin actions (invite, key rotation, audit access, org default
   pool) require Admin+; instance-wide actions (SSO, branding,
   scope policy, users) require \`user.preferences.instance_admin
   = true\`. The instance admin is a **super-role**: orthogonal to
   the org hierarchy, it implicitly elevates the caller to Owner
   on every org via an override path. Override usage is logged as
   \`iam.cross_org_instance_override\` and denials as
   \`iam.authorization_denied\`.

   All org-scoped endpoints go through the same
   \`app/api/rbac.py::require_role\` factory (aliases:
   \`require_viewer\`, \`require_member\`, \`require_admin\`,
   \`require_owner\`). The factory returns a typed \`AuthContext\`
   (user + org_id + role_level + is_instance_override) so endpoints
   don't re-fetch the membership.

   Cross-org leaks are blocked by \`assert_resource_in_org\`: when
   a resource is loaded by ID, the helper checks that its
   \`organization_id\` matches the JWT context and raises **404**
   on mismatch (not 403, to prevent ID enumeration).

## Audit

Every action that changes state writes a row to \`audit_log\`:

\`\`\`
action          | actor_id | organization_id | resource_type | resource_id | details | signature
auth.login      | <uuid>   | <uuid>          | user          | <uuid>      | {...}   | <hmac>
key.created     | <uuid>   | <uuid>          | api_key       | <uuid>      | {...}   | <hmac>
composition.X   | <uuid>   | <uuid>          | composition   | <uuid>      | {...}   | <hmac>
security.apikey_scope_denied | <uuid> | <uuid> | api_key | <uuid> | {scope_required, scopes_granted} | <hmac>
\`\`\`

Visible to instance admins at \`/api/v1/admin/audit-logs\` with filters
on action prefix, actor, org, date range. PII fields are masked
before output (\`pii_sanitizer.py\`).

## Compliance posture (honest)

- **SOC 2 / ISO 27001**: BigMCP is not certified. Self-hosting puts
  the compliance perimeter on YOUR infrastructure, not ours — which
  is usually what regulated orgs want.
- **GDPR**: self-hosted = data residency is your choice. SaaS demo
  (bigmcp.cloud) runs on a single VPS in EU; treat it as a
  preview environment, not a system of record.
- **AGPLv3**: deploying internally is fine; if you fork and host a
  modified version for third parties, you must publish your changes.
  No CLA required to contribute.

## Responsible disclosure

Found a vulnerability? Email **security@bigmcp.cloud** with reproduction
steps and PoC. We'll acknowledge within 48h and aim for a fix or
mitigation within 14 days for high-severity, 30 days for others.

Do NOT open a public GitHub issue for security bugs — use the email
above.

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
