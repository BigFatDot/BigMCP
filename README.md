<p align="center">
  <a href="https://bigmcp.cloud">
    <img src="assets/logos/bigmcp-logo.svg" alt="BigMCP Logo" width="280"/>
  </a>
</p>

<h3 align="center">Unified MCP Gateway & AI-Powered Orchestration Platform</h3>

<p align="center">
  Transform your MCP tools into a unified, secure, cloud-accessible platform.
</p>

<p align="center">
  <a href="CHANGELOG.md">
    <img src="https://img.shields.io/badge/version-1.2.0-blue.svg" alt="Version"/>
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-ELv2-blue.svg" alt="License"/>
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
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-features">Features</a> •
  <a href="#-editions--pricing">Editions</a> •
  <a href="https://bigmcp.cloud/docs">API Docs</a> •
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

---

## Table of Contents

- [What is BigMCP?](#-what-is-bigmcp)
- [Quick Start](#-quick-start)
- [Editions & Pricing](#-editions--pricing)
- [Features](#-features)
- [Architecture](#-architecture)
- [Self-Hosted Deployment](#-self-hosted-deployment)
- [Documentation](#-documentation)
- [Technology Stack](#-technology-stack)
- [Roadmap](#-roadmap)
- [Contributing](#-contributing)
- [License](#-license)
- [Support](#-support)

---

## 🎯 What is BigMCP?

BigMCP is a **production-ready platform** that centralizes all your MCP (Model Context Protocol) servers into a single, secure, authenticated gateway. Access your tools from anywhere with enterprise-grade security and intelligent orchestration.

### The Problem

| Without BigMCP | With BigMCP |
|----------------|-------------|
| Install 10+ MCP servers on each device | **One connection** - Access all tools |
| Configure credentials separately | **Centralized credentials** - User → Org → Server |
| No mobile access | **Cloud-based** - Desktop, mobile, web |
| No access control | **Enterprise RBAC** - Owner, Admin, Member, Viewer |
| Manual workflow creation | **AI orchestration** - Auto-generate workflows |

---

## 🚀 Quick Start

### Option 1: Cloud SaaS (Fastest)

```json
// Claude Desktop config
{
  "mcpServers": {
    "bigmcp": {
      "url": "https://api.bigmcp.cloud/mcp/sse",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

Get your API key at [app.bigmcp.cloud](https://app.bigmcp.cloud)

### Option 2: Self-Hosted (Docker)

```bash
# Clone & start
git clone https://github.com/bigfatdot/bigmcp.git
cd bigmcp
cp .env.example .env
docker compose up -d

# Run migrations & create admin
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.cli.create_admin

# Access at http://localhost:3000
```

> **Community Edition**: Free for personal use (1 user). See [Editions](#-editions--pricing) for multi-user options.

---

## 💎 Editions & Pricing

BigMCP follows an **Open Core** model with three editions:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    BigMCP Cloud (bigmcp.cloud)                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Marketplace API - Centralized (180+ MCP servers)            │    │
│  └─────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  SaaS Platform (app.bigmcp.cloud) - Fully managed            │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                               │
                     Marketplace API access
                               │
          ┌────────────────────┴────────────────────┐
          ▼                                         ▼
┌──────────────────────┐              ┌──────────────────────┐
│   Community Edition  │              │  Enterprise Edition  │
│     (Self-Hosted)    │              │    (Self-Hosted)     │
├──────────────────────┤              ├──────────────────────┤
│ ✓ Complete platform  │              │ ✓ Complete platform  │
│ ✓ 1 user             │              │ ✓ Unlimited users    │
│ ✓ Free (ELv2)        │              │ ✓ RBAC + SSO/SAML    │
│ ✓ Your infrastructure│              │ ✓ Air-gapped support │
└──────────────────────┘              └──────────────────────┘
```

### Pricing Comparison

| Edition | Price | Users | Best For |
|---------|-------|-------|----------|
| **Cloud SaaS Individual** | €4.99/month | 1 | Getting started fast |
| **Cloud SaaS Team** | €4.99/month + €4.99/user/month | 2-20 | Teams needing managed hosting |
| **Community (Self-Hosted)** | **Free** | 1 | Personal use, evaluation |
| **Enterprise (Self-Hosted)** | One-time license | Unlimited | Organizations, on-premise |

> **Public Sector**: Enterprise licenses are **free** for government and public entities worldwide.

**[Start Free →](https://app.bigmcp.cloud)** | **[Enterprise Contact →](mailto:enterprise@bigmcp.cloud)**

---

## ✨ Features

### Authentication & Security
- **OAuth 2.0 + PKCE** (RFC 7636) for third-party apps
- **JWT tokens** with configurable expiration
- **API Keys** for programmatic access (bcrypt hashed)
- **MFA / TOTP** two-factor authentication
- **Credentials encrypted at rest** (Fernet)
- **Multi-tenant isolation** at database level

### Multi-Tenant Architecture
- **Organization-based isolation** with RBAC
- **Hierarchical credentials**: User → Organization → Server
- **4-tier roles**: Owner, Admin, Member, Viewer
- **Service Account Mode** for sensitive credentials

### Dynamic Marketplace
- **180+ MCP servers** from npm, GitHub, Glama.ai, Smithery.ai
- **Semantic search** with vector embeddings
- **One-click installation** with credential detection
- **Background sync** with caching

### AI Orchestration
- **Intent analysis** - Natural language → workflow
- **Auto-workflow generation** - "Sync Grist to Sheets daily"
- **Composition store** with lifecycle (temporary → production)
- **Data mappings** with wildcards (`[*]`) and templates

### Universal Access
- **Desktop**: Claude Desktop, Continue.dev, Cline
- **Mobile**: Claude Mobile (via cloud server)
- **Web**: REST API v1, React dashboard
- **MCP Protocol 2024-11-05** compliant

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      CLIENT INTERFACES                           │
├─────────────────┬─────────────────┬─────────────────────────────┤
│  MCP Protocol   │   REST API v1   │    OAuth 2.0 Clients        │
│  (SSE/JSON-RPC) │     (JSON)      │  (Claude Desktop, etc.)     │
└────────┬────────┴────────┬────────┴──────────────┬──────────────┘
         │                 │                       │
         └─────────────────┼───────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   GATEWAY LAYER (FastAPI)                        │
│  Authentication • Authorization • Rate Limiting • Routing        │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  ORCHESTRATION LAYER                             │
│  Semantic Search • Intent Analysis • Workflow Composition        │
│  Credential Resolution • Permission Checks                       │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                 REGISTRY & MARKETPLACE                           │
│  Tool Catalog • User Server Pools • Health Monitoring            │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MCP SERVERS                                   │
│  grist-mcp │ github-mcp │ notion-mcp │ [marketplace servers]     │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DATABASE LAYER                                │
│  PostgreSQL 15+ • Redis • Qdrant                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🐳 Self-Hosted Deployment

### Requirements

- Docker & Docker Compose
- PostgreSQL 15+ (included in compose)
- 2GB RAM minimum

### Quick Deploy

```bash
# 1. Clone
git clone https://github.com/bigfatdot/bigmcp.git
cd bigmcp

# 2. Configure
cp .env.example .env
# Edit .env with your secrets (JWT_SECRET, ENCRYPTION_KEY)

# 3. Start
docker compose up -d

# 4. Initialize
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.cli.create_admin
```

### Environment Variables

```bash
# Required
DATABASE_URL=postgresql://user:pass@localhost:5432/bigmcp
JWT_SECRET=your-secret-key-min-32-chars
ENCRYPTION_KEY=your-fernet-key

# Optional - LLM for AI orchestration
LLM_API_URL=https://api.mistral.ai/v1
LLM_API_KEY=your-api-key
LLM_MODEL=mistral-small-latest
```

### Production Deployment

For production, ensure you:

1. **Generate secure secrets:**
   ```bash
   # JWT Secret (min 32 chars)
   python -c "import secrets; print(secrets.token_urlsafe(32))"

   # Encryption Key (Fernet)
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. **Configure SSL/TLS** via reverse proxy (Nginx included in compose)

3. **Set up backups** for PostgreSQL

4. **Set up monitoring** - Prometheus endpoint at `/metrics`

5. **Register for Marketplace API** at [bigmcp.cloud](https://bigmcp.cloud) (free for self-hosted)

### Connecting Claude Desktop

```json
// Claude Desktop config
// macOS: ~/Library/Application Support/Claude/claude_desktop_config.json
// Windows: %APPDATA%/Claude/claude_desktop_config.json
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

## 📚 Documentation

| Resource | Description |
|----------|-------------|
| [API Reference](https://bigmcp.cloud/docs) | Swagger/OpenAPI (also at `/docs` on your instance) |
| [Changelog](CHANGELOG.md) | Version history |
| [Contributing](CONTRIBUTING.md) | How to contribute |
| [Licensing](LICENSING.md) | License details |

---

## 🛠 Technology Stack

| Layer | Technologies |
|-------|--------------|
| **Backend** | FastAPI, Python 3.11+, SQLAlchemy 2.0, Alembic |
| **Database** | PostgreSQL 15+, Redis, Qdrant |
| **Security** | JWT, bcrypt, Fernet encryption, OAuth 2.0, MFA/TOTP |
| **Frontend** | React 18, TypeScript, Tailwind CSS, Vite |
| **Infrastructure** | Docker, Uvicorn, Nginx |
| **Monitoring** | Prometheus metrics endpoint (`/metrics`) |
| **Protocols** | MCP 2024-11-05, SSE, JSON-RPC 2.0 |

---

## 🗺 Roadmap

### Completed ✅
- [x] Authentication & Authorization (JWT, OAuth 2.0, PKCE)
- [x] Multi-tenant RBAC
- [x] MCP Gateway (Protocol 2024-11-05)
- [x] Dynamic Marketplace
- [x] AI-powered Orchestration
- [x] REST API v1
- [x] Web UI (React + TypeScript)
- [x] CI/CD Pipeline

### In Progress 🚧
- [ ] Visual Workflow Builder (drag & drop)
- [ ] Social OAuth (Google, GitHub buttons)
- [ ] Template Gallery

### Planned 📋
- [ ] Mobile apps (iOS/Android)
- [ ] Advanced analytics
- [ ] Custom branding (white-label)
- [ ] Kubernetes deployment

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
# Development setup
cd mcp-registry
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

# Run tests
pytest tests/ -v

# Start dev server
uvicorn app.main:app --reload --port 8001
```

---

## 📄 License

This project is licensed under the **Elastic License 2.0 (ELv2)**.

| Edition | License | Commercial Use |
|---------|---------|----------------|
| Community | ELv2 | ✅ Personal/internal use |
| Cloud SaaS | Commercial | ✅ Subscription service |
| Enterprise | Commercial | ✅ Unlimited users |

See [LICENSING.md](LICENSING.md) for full details.

---

## 💬 Support

| Channel | Description |
|---------|-------------|
| [Documentation](https://bigmcp.cloud/docs) | Guides and API reference |
| [API Reference](https://bigmcp.cloud/docs) | Swagger documentation |
| [GitHub Issues](https://github.com/bigfatdot/bigmcp/issues) | Bug reports & features |
| [Email](mailto:support@bigmcp.cloud) | General support |
| [Enterprise](mailto:enterprise@bigmcp.cloud) | Enterprise inquiries |

---

<p align="center">
  <b>BigMCP</b> - Unified MCP Gateway & AI-Powered Orchestrator
  <br/>
  <sub>Made with care for the MCP community by <a href="https://bigfatdot.org">BigFatDot</a></sub>
</p>
