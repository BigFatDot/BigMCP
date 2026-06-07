<p align="center">
  <a href="https://github.com/bigfatdot/bigmcp">
    <img src="assets/logos/bigmcp-logo.svg" alt="BigMCP Logo" width="280"/>
  </a>
</p>

<h3 align="center">Open Source MCP Gateway for Organizations</h3>

<p align="center">
  Register, govern, and expose your MCP services to your teams — with full control over who sees what.
</p>

<p align="center">
  <a href="CHANGELOG.md">
    <img src="https://img.shields.io/badge/version-2.4.0-blue.svg" alt="Version"/>
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-AGPLv3-blue.svg" alt="License"/>
  </a>
  <a href="https://bigmcp.cloud/docs">
    <img src="https://img.shields.io/badge/docs-swagger-green.svg" alt="API Docs"/>
  </a>
  <img src="https://img.shields.io/badge/docker-ready-blue.svg" alt="Docker"/>
  <a href="https://lobehub.com/mcp/bigfatdot-bigmcp">
    <img src="https://lobehub.com/badge/mcp/bigfatdot-bigmcp" alt="LobeHub MCP"/>
  </a>
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> &bull;
  <a href="#-why-bigmcp">Why BigMCP</a> &bull;
  <a href="#-features">Features</a> &bull;
  <a href="https://bigmcp.cloud/docs">API Docs</a> &bull;
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

---

## Quick Start

```bash
git clone https://github.com/bigfatdot/bigmcp.git
cd bigmcp
cp .env.example .env
# Edit .env with your secrets (SECRET_KEY, ENCRYPTION_KEY)
docker compose up -d
docker compose exec backend alembic upgrade head
```

Open **http://localhost** — the first user to register becomes instance admin (Community / Enterprise edition).

> Want to try it first? [bigmcp.cloud](https://app.bigmcp.cloud) is a free demo platform.

### Connect Claude Desktop

```json
{
  "mcpServers": {
    "bigmcp": {
      "url": "https://your-domain.com/mcp/sse",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

---

## Why BigMCP

BigMCP is the **control plane for all your MCP servers** — the 180+ from the marketplace AND your own custom servers.

| Without BigMCP | With BigMCP |
|----------------|-------------|
| Install MCP servers on each device | **One endpoint** — access all tools |
| Configure credentials separately | **Centralized credentials** — User + Org + Server |
| No access control | **RBAC** — Owner, Admin, Member, Viewer |
| No visibility into usage | **Audit logs** — who used what, when |
| Manual setup per team | **Tool Groups + API Keys** — selective service exposure |

### For Organizations

The core use case: **register your internal MCP servers, create Tool Groups per team, generate scoped API Keys, and let each team member connect their AI client with a single URL.**

1. **Register your servers** — npm, pip, Docker, HTTP, or local binary
2. **Auto-discover tools** — BigMCP calls `tools/list` and indexes everything
3. **Create Tool Groups** — "Dev Team" gets GitHub + CI/CD, "Finance" gets Grist + DB queries
4. **Generate API Keys** — scoped per Tool Group, with granular permissions
5. **Connect** — each user pastes one URL in Claude/Cursor and sees only their tools

---

## Features

### Custom MCP Server Management
- Register servers from **any source**: npm, pip, GitHub, Docker, HTTP URL, local binary
- **Auto-discovery** via `tools/list` — tools are indexed automatically
- **Closed mode**: instance admin can disable each marketplace source individually via `/api/v1/admin/sources/{source_id}` so a hardened deploy can run with custom servers only
- **Team vs Personal** servers with granular visibility

### Selective Service Exposure
- **Tool Groups** — curated sets of tools with PRIVATE / ORGANIZATION / PUBLIC visibility
- **Scoped API Keys** — 7 granular scopes (tools:read, tools:execute, credentials:read/write, servers:read/write, admin)
- **Per-Tool Group API Keys** — each key only exposes the tools you choose
- **Usage tracking** — per tool, per server, per key

### Authentication & Security
- **OAuth 2.0 + PKCE** (RFC 7636) with Dynamic Client Registration
- **JWT tokens** with configurable expiration
- **API Keys** for programmatic access (bcrypt hashed, `bigmcp_sk_*` format)
- **MFA / TOTP** two-factor authentication
- **Credentials encrypted at rest** (Fernet)
- **Immutable audit logs** with HMAC-SHA256 signatures

### Multi-Tenant Architecture
- **Organization-based isolation** with RBAC
- **4-tier roles**: Owner, Admin, Member, Viewer
- **Hierarchical credentials**: User > Organization > Server
- **Unlimited users and organizations**

### Dynamic Marketplace
- **180+ MCP servers** from npm, GitHub, Glama.ai, Smithery.ai
- **Semantic search** with vector embeddings
- **One-click installation** with credential detection
- Marketplace can be fully disabled for closed environments

### AI Orchestration & Durable Workflows
- **Intent analysis** — Natural language to workflow
- **Composition lifecycle** — temporary → validated → production; promoted compositions become first-class MCP tools
- **5 suspending step types** that survive crashes & restarts (Phase B-1):
  - `elicit` — pause for human input mid-flight
  - `wait_until` — clock-driven resume at a future timestamp
  - `wait_callback` — HMAC-protected webhook resume (external systems POST back)
  - `subcomposition` — call another composition; parent suspends until child terminates
  - `approval` — cross-user gate with four-eyes default, role + user_id approver list
- **Resumable executor** persists every step in Postgres; clients subscribe to `composition://executions/{id}` for live updates

### MCP Protocol Compliance
- **MCP 2025-06-18** — Streamable HTTP + SSE
- **OAuth 2.0** authorization for MCP clients
- Works with **Claude Desktop, Cursor, Continue.dev, Cline**, and any MCP-compatible client

---

## Architecture

```
+-----------------------------------------------------------------+
|                      CLIENT INTERFACES                           |
+------------------+-----------------+-----------------------------+
|  MCP Protocol    |   REST API v1   |    OAuth 2.0 Clients        |
|  (SSE/JSON-RPC)  |     (JSON)      |  (Claude Desktop, etc.)     |
+--------+---------+--------+--------+--------------+--------------+
         |                  |                       |
         +------------------+-----------------------+
                            v
+-----------------------------------------------------------------+
|                   GATEWAY LAYER (FastAPI)                         |
|  Authentication - Authorization - Rate Limiting - Routing        |
+-----------------------------------------------------------------+
                            |
                            v
+-----------------------------------------------------------------+
|                  ORCHESTRATION LAYER                              |
|  Semantic Search - Intent Analysis - Workflow Composition         |
|  Credential Resolution - Permission Checks                       |
+-----------------------------------------------------------------+
                            |
                            v
+-----------------------------------------------------------------+
|                 REGISTRY & MARKETPLACE                            |
|  Tool Catalog - User Server Pools - Health Monitoring             |
+-----------------------------------------------------------------+
                            |
                            v
+-----------------------------------------------------------------+
|                    MCP SERVERS                                    |
|  your-custom-api | github-mcp | notion-mcp | [marketplace]       |
+-----------------------------------------------------------------+
                            |
                            v
+-----------------------------------------------------------------+
|                    DATABASE LAYER                                 |
|  PostgreSQL 16 - Redis 7 - Qdrant                                |
+-----------------------------------------------------------------+
```

---

## Self-Hosted Deployment

### Requirements

- Docker & Docker Compose
- 2GB RAM minimum
- PostgreSQL 16 (included in compose)

### Production Deploy

```bash
# 1. Clone
git clone https://github.com/bigfatdot/bigmcp.git
cd bigmcp

# 2. Configure
cp .env.example .env
# Generate secrets:
python3 -c "import secrets; print(secrets.token_urlsafe(32))"       # SECRET_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # ENCRYPTION_KEY

# 3. Start
docker compose up -d

# 4. Initialize database
docker compose exec backend alembic upgrade head

# 5. Access at http://localhost (nginx serves the frontend on port 80)
```

### Environment Variables

```bash
# Required
SECRET_KEY=your-secret-key-min-32-chars
ENCRYPTION_KEY=your-fernet-key
DATABASE_URL=postgresql+asyncpg://mcphub:mcphub@postgres:5432/mcphub

# Optional — LLM provider (Bring Your Own LLM)
# Any OpenAI-compatible /chat/completions endpoint. Tested: Mistral, OpenAI,
# Ollama, vLLM. Anthropic NOT supported here (non-OpenAI-compatible API).
LLM_API_URL=https://api.mistral.ai/v1
LLM_API_KEY=your-api-key
LLM_MODEL=mistral-small-latest
EMBEDDING_MODEL=mistral-embed
EMBEDDING_DIMENSION=1536       # 1024 for mistral-embed, 768 for nomic-embed
RERANK_ENABLED=false           # Mistral-only feature; leave off for portability

# Optional — Air-gap mode (no outbound HTTP except your LLM)
AIRGAP_MODE=false              # true disables marketplace sync + icon CDN + LemonSqueezy

# Optional — SMTP for email invitations
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your-email
SMTP_PASSWORD=your-password
```

#### Run fully offline with a local LLM

```bash
# Example: BigMCP + Ollama, zero outbound traffic
LLM_API_URL=http://ollama:11434/v1
LLM_MODEL=llama3.1
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSION=768
AIRGAP_MODE=true
```

### Monitoring

- `GET /health` — Liveness probe
- `GET /ready` — Readiness probe (DB + registry + cache)
- `GET /metrics` — Prometheus endpoint

---

## Technology Stack

| Layer | Technologies |
|-------|--------------|
| **Backend** | FastAPI, Python 3.11+, SQLAlchemy 2.0, Alembic |
| **Database** | PostgreSQL 16, Redis 7, Qdrant |
| **Security** | JWT, bcrypt, Fernet encryption, OAuth 2.0 + PKCE, MFA/TOTP |
| **Frontend** | React 18, TypeScript, Tailwind CSS, Vite |
| **Infrastructure** | Docker Compose, Uvicorn, Nginx |
| **Monitoring** | Prometheus metrics |
| **Protocols** | MCP 2025-06-18, SSE, JSON-RPC 2.0 |

---

## Documentation

| Resource | Description |
|----------|-------------|
| [API Reference](https://bigmcp.cloud/docs) | Swagger/OpenAPI (also at `/docs` on your instance) |
| [Changelog](CHANGELOG.md) | Version history |
| [Contributing](CONTRIBUTING.md) | How to contribute |
| [Licensing](LICENSING.md) | AGPLv3 license details |
| [Self-Hosting](https://bigmcp.cloud/docs/self-hosting/self-host-overview) | Full self-hosting guide (Docker, SSL, backup, scaling) |
| [Security](https://bigmcp.cloud/docs/concepts/security) | Threat model, encryption, RBAC, audit, responsible disclosure |

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
# Development setup
cd mcp-registry
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Run tests
pytest tests/ -v

# Start dev server
uvicorn app.main:app --reload --port 8001
```

---

## License

BigMCP is licensed under the **GNU Affero General Public License v3.0** (AGPLv3).

All features are included. No user limits. No license keys.

See [LICENSING.md](LICENSING.md) for details.

---

## Support

| Channel | Description |
|---------|-------------|
| [GitHub Issues](https://github.com/bigfatdot/bigmcp/issues) | Bug reports & feature requests |
| [Documentation](https://bigmcp.cloud/docs) | Guides and API reference |
| [Email](mailto:contact@bigmcp.cloud) | General inquiries |

---

<p align="center">
  <b>BigMCP</b> — Open Source MCP Gateway for Organizations
  <br/>
  <sub>Made with care for the MCP community by <a href="https://bigfatdot.org">BigFatDot</a></sub>
</p>
