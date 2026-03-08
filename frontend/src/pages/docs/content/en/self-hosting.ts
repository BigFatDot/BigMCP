/**
 * Self-Hosting Documentation Content
 */

export const selfHostingContent: Record<string, string> = {
  'self-host-overview': `
# Self-Hosting Overview

BigMCP can be self-hosted for full control over your data and infrastructure.

## Editions

### Community Edition (Free)
- Full platform features
- 1 user
- Choose your LLM provider
- Open source (Elastic License 2.0)

### Enterprise Edition
- Unlimited users and teams
- Full admin control
- Priority support
- Perpetual license

## Requirements

### Minimum Hardware
- 2 CPU cores
- 4 GB RAM
- 20 GB storage

### Recommended
- 4 CPU cores
- 8 GB RAM
- 50 GB SSD

### Software
- Docker 20.10+
- Docker Compose 2.0+
- Linux (Ubuntu 20.04+ recommended)

## Architecture

\`\`\`mermaid
flowchart TB
    subgraph internet [" "]
        Users(["<b>Users</b>"])
    end

    subgraph docker [" "]
        Nginx(["<b>Nginx</b><br/>Reverse Proxy"])

        subgraph apps [" "]
            direction LR
            Frontend(["<b>Frontend</b><br/>React SPA"])
            Backend(["<b>Backend</b><br/>FastAPI + MCP"])
        end

        subgraph data [" "]
            direction LR
            Postgres(["<b>PostgreSQL</b><br/>Data"])
            Qdrant(["<b>Qdrant</b><br/>Vectors"])
        end

        LLM(["<b>LLM API</b><br/>OpenAI / Anthropic"])
    end

    Users --> Nginx
    Nginx --> Frontend & Backend
    Backend --> Postgres & Qdrant & LLM

    style internet fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style docker fill:none,stroke:#c4624a,stroke-width:2px
    style apps fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style data fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style Users fill:#ffffff,stroke:#d4d4d4,color:#262626
    style Nginx fill:#D97757,stroke:#c4624a,color:#ffffff
    style Frontend fill:#f4e4df,stroke:#c4624a,color:#262626
    style Backend fill:#f4e4df,stroke:#c4624a,color:#262626
    style Postgres fill:#f4e4df,stroke:#c4624a,color:#262626
    style Qdrant fill:#f4e4df,stroke:#c4624a,color:#262626
    style LLM fill:#ffffff,stroke:#d4d4d4,color:#262626
\`\`\`

## Quick Start

\`\`\`bash
# Clone the repository
git clone https://github.com/bigfatdot/bigmcp.git
cd bigmcp

# Copy environment template
cp .env.example .env

# Edit configuration
nano .env

# Start services
docker compose up -d
\`\`\`

Visit \`http://localhost:3000\` to access BigMCP.
`,

  'docker-setup': `
# Docker Setup

Deploy BigMCP using Docker Compose.

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- Domain name (for HTTPS)
- 4GB+ RAM

## Installation

### 1. Clone Repository

\`\`\`bash
git clone https://github.com/bigfatdot/bigmcp.git
cd bigmcp
\`\`\`

### 2. Configure Environment

\`\`\`bash
cp .env.example .env
\`\`\`

Edit \`.env\` with your settings:

\`\`\`bash
# Required
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret
ENCRYPTION_KEY=your-encryption-key
POSTGRES_PASSWORD=secure-password

# LLM Configuration (choose one)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Or use Anthropic
# LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=...

# Or use local Ollama
# LLM_PROVIDER=ollama
# OLLAMA_URL=http://localhost:11434
\`\`\`

### 3. Start Services

\`\`\`bash
docker compose -f docker-compose.prod.yml up -d
\`\`\`

### 4. Verify Installation

\`\`\`bash
# Check services
docker compose ps

# View logs
docker compose logs -f
\`\`\`

## SSL/HTTPS Setup

### With Let's Encrypt

The included nginx configuration supports automatic SSL:

\`\`\`bash
# Edit nginx config
nano nginx/conf.d/bigmcp.conf

# Update domain
server_name your-domain.com;

# Run certbot
docker compose run --rm certbot certonly \\
  --webroot -w /var/www/certbot \\
  -d your-domain.com
\`\`\`

## Updating

\`\`\`bash
# Pull latest changes
git pull

# Rebuild and restart
docker compose -f docker-compose.prod.yml up -d --build
\`\`\`

## Troubleshooting

### Services not starting
\`\`\`bash
docker compose logs backend
docker compose logs postgres
\`\`\`

### Database issues
\`\`\`bash
# Reset database (warning: deletes data)
docker compose down -v
docker compose up -d
\`\`\`
`,

  configuration: `
# Configuration

Environment variables and settings for self-hosted BigMCP.

## Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| SECRET_KEY | App secret key | Random 32+ chars |
| JWT_SECRET_KEY | JWT signing key | Random 32+ chars |
| ENCRYPTION_KEY | Credential encryption | 32-char key |
| POSTGRES_PASSWORD | Database password | Secure password |

## LLM Configuration

### OpenAI
\`\`\`bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o
EMBEDDING_MODEL=text-embedding-3-small
\`\`\`

### Anthropic
\`\`\`bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-3-5-sonnet-20241022
\`\`\`

### Mistral
\`\`\`bash
LLM_PROVIDER=mistral
MISTRAL_API_KEY=...
LLM_MODEL=mistral-small-latest
EMBEDDING_MODEL=mistral-embed
\`\`\`

### Local (Ollama)
\`\`\`bash
LLM_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434
LLM_MODEL=llama2
EMBEDDING_MODEL=nomic-embed-text
\`\`\`

## Database Configuration

\`\`\`bash
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/bigmcp
\`\`\`

## Feature Flags

\`\`\`bash
# Enable/disable features
ENABLE_MARKETPLACE=true
ENABLE_SEMANTIC_SEARCH=true
ENABLE_ORGANIZATIONS=true
ENABLE_OAUTH=false
\`\`\`

## Security Settings

\`\`\`bash
# CORS
CORS_ORIGINS=https://your-domain.com

# Rate limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60

# Session
SESSION_EXPIRY_HOURS=24
\`\`\`
`,

  'llm-providers': `
# LLM Providers

Configure your AI backend for self-hosted BigMCP.

## Supported Providers

| Provider | Models | Embedding Support |
|----------|--------|-------------------|
| OpenAI | GPT-4o, GPT-4, GPT-3.5 | Yes |
| Anthropic | Claude 3.5, Claude 3 | No* |
| Mistral | Mistral Small/Large | Yes |
| Ollama | Any local model | Depends |

*Anthropic doesn't provide embedding API; use a secondary provider.

## OpenAI Setup

\`\`\`bash
LLM_PROVIDER=openai
LLM_API_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o
EMBEDDING_MODEL=text-embedding-3-small
\`\`\`

### Azure OpenAI

\`\`\`bash
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_KEY=...
AZURE_OPENAI_DEPLOYMENT=gpt-4o
\`\`\`

## Anthropic Setup

\`\`\`bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-3-5-sonnet-20241022

# For embeddings, use a secondary provider
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
\`\`\`

## Local Models (Ollama)

### Install Ollama

\`\`\`bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama2
ollama pull nomic-embed-text
\`\`\`

### Configure BigMCP

\`\`\`bash
LLM_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434
LLM_MODEL=llama2
EMBEDDING_MODEL=nomic-embed-text
\`\`\`

## Choosing a Provider

| Use Case | Recommended |
|----------|-------------|
| Best quality | OpenAI GPT-4o or Claude 3.5 |
| Cost-effective | Mistral Small |
| Privacy-first | Ollama + local models |
| Enterprise | Azure OpenAI |

## Performance Tips

1. **Use smaller models** for simple tasks
2. **Enable caching** to reduce API calls
3. **Batch embeddings** when possible
4. **Monitor usage** to control costs
`,

  'custom-servers': `
# Custom MCP Servers

Add your own private or internal MCP servers to your self-hosted BigMCP instance.

## Overview

Enterprise Edition allows you to register custom MCP servers that:
- Connect to internal APIs and databases
- Use private packages from your registry
- Run Docker containers with proprietary tools
- Execute local scripts and binaries

This enables full control over which tools your organization's AI assistants can access.

## Installation Types

BigMCP supports multiple installation methods for custom servers:

| Type | Use Case | Example |
|------|----------|---------|
| **NPM** | Node.js packages | \`@company/mcp-server\` |
| **PIP** | Python packages | \`internal-mcp-server\` |
| **GitHub** | Git repositories | \`https://github.com/org/repo\` |
| **Docker** | Container images | \`registry.company.com/mcp:v1\` |
| **Local** | Scripts & binaries | \`/opt/mcp/server.py\` |

## Adding a Custom Server

### Via API

\`\`\`bash
curl -X POST https://your-bigmcp.com/api/v1/servers \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "server_id": "internal-crm",
    "name": "Internal CRM",
    "install_type": "pip",
    "install_package": "internal-crm-mcp",
    "command": "python",
    "args": ["-m", "crm_mcp_server"],
    "env": {
      "CRM_API_KEY": "\${CRM_API_KEY}",
      "CRM_API_URL": "https://crm.internal.company.com/api"
    },
    "auto_start": true
  }'
\`\`\`

### Configuration Options

| Field | Required | Description |
|-------|----------|-------------|
| \`server_id\` | Yes | Unique identifier (lowercase, hyphens) |
| \`name\` | Yes | Display name |
| \`install_type\` | Yes | \`npm\`, \`pip\`, \`github\`, \`docker\`, \`local\` |
| \`install_package\` | Yes | Package name, repo URL, or path |
| \`command\` | Yes | Executable command |
| \`args\` | No | Command arguments array |
| \`env\` | No | Environment variables |
| \`version\` | No | Package version constraint |
| \`auto_start\` | No | Start immediately after install |

## Installation Types in Detail

### NPM Package

For Node.js MCP servers published to npm (public or private registry).

\`\`\`json
{
  "server_id": "internal-docs",
  "name": "Internal Documentation",
  "install_type": "npm",
  "install_package": "@company/mcp-server-docs",
  "command": "npx",
  "args": ["-y", "@company/mcp-server-docs"],
  "env": {
    "DOCS_API_KEY": "\${DOCS_API_KEY}"
  }
}
\`\`\`

For private npm registry:
\`\`\`bash
# Set npm registry before starting BigMCP
npm config set @company:registry https://npm.company.com
\`\`\`

### Python Package

For Python MCP servers from PyPI or private index.

\`\`\`json
{
  "server_id": "data-warehouse",
  "name": "Data Warehouse",
  "install_type": "pip",
  "install_package": "company-data-mcp",
  "command": "python",
  "args": ["-m", "data_mcp_server"],
  "env": {
    "DW_CONNECTION_STRING": "\${DW_CONNECTION_STRING}"
  }
}
\`\`\`

For private PyPI:
\`\`\`bash
# Configure pip to use private index
pip config set global.extra-index-url https://pypi.company.com/simple
\`\`\`

### GitHub Repository

For servers hosted in Git repositories.

\`\`\`json
{
  "server_id": "custom-analytics",
  "name": "Custom Analytics",
  "install_type": "github",
  "install_package": "https://github.com/company/mcp-analytics.git",
  "version": "v1.2.0",
  "command": "python",
  "args": ["-m", "analytics_server"]
}
\`\`\`

Private repositories require SSH key or token:
\`\`\`bash
# Via SSH (recommended)
install_package: "git@github.com:company/private-mcp.git"

# Via HTTPS with token
install_package: "https://TOKEN@github.com/company/private-mcp.git"
\`\`\`

### Docker Container

For containerized MCP servers.

\`\`\`json
{
  "server_id": "legacy-erp",
  "name": "Legacy ERP Integration",
  "install_type": "docker",
  "install_package": "registry.company.com/mcp-erp:v2.1",
  "command": "docker",
  "args": ["run", "-i", "--rm", "registry.company.com/mcp-erp:v2.1"],
  "env": {
    "ERP_HOST": "\${ERP_HOST}",
    "ERP_API_KEY": "\${ERP_API_KEY}"
  }
}
\`\`\`

Docker registry authentication:
\`\`\`bash
docker login registry.company.com
\`\`\`

### Local Script

For local scripts or binaries.

\`\`\`json
{
  "server_id": "local-tools",
  "name": "Local Dev Tools",
  "install_type": "local",
  "install_package": "/opt/mcp/dev-tools",
  "command": "/opt/mcp/dev-tools/server.py",
  "args": ["--port", "stdio"]
}
\`\`\`

## Credential Management

### Environment Variable Substitution

Use \`\${VAR_NAME}\` syntax for credential injection:

\`\`\`json
{
  "env": {
    "API_KEY": "\${MY_API_KEY}",
    "DB_URL": "\${DATABASE_CONNECTION_STRING}"
  }
}
\`\`\`

### Credential Resolution Order

When a server starts, credentials are resolved hierarchically:

1. **User credentials** - Per-user secrets (highest priority)
2. **Organization credentials** - Shared team secrets
3. **Server defaults** - Values in \`env\` field

### Adding User Credentials

Users can connect your custom server via the marketplace or add credentials via the Services page:

1. Go to **Services**
2. Click on your custom server
3. Configure required credentials
4. Click **Save**

## Server Lifecycle

### Starting a Server

\`\`\`bash
curl -X POST https://your-bigmcp.com/api/v1/servers/{server_id}/start \\
  -H "Authorization: Bearer YOUR_API_KEY"
\`\`\`

### Stopping a Server

\`\`\`bash
curl -X POST https://your-bigmcp.com/api/v1/servers/{server_id}/stop \\
  -H "Authorization: Bearer YOUR_API_KEY"
\`\`\`

### Tool Discovery

When a server starts, BigMCP automatically:
1. Sends MCP \`tools/list\` request
2. Stores discovered tools in database
3. Makes tools available via MCP gateway

## Example: Internal API Server

Complete example for an internal API integration:

### 1. Create the MCP Server Package

\`\`\`python
# internal_api_mcp/server.py
from mcp.server import Server
from mcp.types import Tool

server = Server("internal-api")

@server.tool()
async def get_customer(customer_id: str) -> dict:
    """Get customer details from internal CRM."""
    # Your implementation
    pass

@server.tool()
async def create_ticket(title: str, description: str) -> dict:
    """Create a support ticket."""
    # Your implementation
    pass

if __name__ == "__main__":
    server.run()
\`\`\`

### 2. Publish to Private Registry

\`\`\`bash
# Build and publish to private PyPI
python -m build
twine upload --repository company dist/*
\`\`\`

### 3. Register in BigMCP

\`\`\`bash
curl -X POST https://your-bigmcp.com/api/v1/servers \\
  -H "Authorization: Bearer ADMIN_API_KEY" \\
  -d '{
    "server_id": "internal-api",
    "name": "Internal API",
    "install_type": "pip",
    "install_package": "internal-api-mcp",
    "command": "python",
    "args": ["-m", "internal_api_mcp.server"],
    "env": {
      "INTERNAL_API_KEY": "\${INTERNAL_API_KEY}",
      "INTERNAL_API_URL": "https://api.internal.company.com"
    },
    "auto_start": true
  }'
\`\`\`

### 4. Configure User Credentials

Each user adds their \`INTERNAL_API_KEY\` in the Services page.

### 5. Use in Claude

\`\`\`
"Get customer details for ID 12345"
"Create a support ticket about the login issue"
\`\`\`

## Limits and Quotas

| Resource | Community | Enterprise |
|----------|-----------|------------|
| Custom servers | 1 | Unlimited |
| Active servers | 3 | Unlimited |
| Credentials per server | 5 | Unlimited |

## Troubleshooting

### Server won't start

\`\`\`bash
# Check server logs
docker compose logs -f backend

# Common issues:
# - Package not found: verify install_package and registry access
# - Command not found: ensure command is in PATH
# - Permission denied: check file permissions for local scripts
\`\`\`

### Tools not appearing

1. Verify server status is "running"
2. Check that server implements MCP \`tools/list\` correctly
3. Review backend logs for discovery errors

### Credential errors

1. Verify credential names match exactly (case-sensitive)
2. Check that user has added required credentials
3. Ensure credentials have correct format (no trailing spaces)

## Security Best Practices

1. **Use secrets management** - Store sensitive values in vault, inject at runtime
2. **Minimal permissions** - Only grant required access to internal systems
3. **Audit logging** - Monitor which users access which tools
4. **Version pinning** - Pin package versions to prevent supply chain attacks
5. **Network isolation** - Run containers in isolated networks when possible
`,
  scaling: `
# Scaling & Performance

Optimize your self-hosted BigMCP instance for production workloads.

## How BigMCP Uses Resources

Each MCP server runs as a **separate OS process** (Node.js or Python subprocess). When a user connects via an AI client, BigMCP starts the servers they need on demand.

| Component | Memory Usage |
|-----------|-------------|
| Backend (base process) | ~200 MB fixed |
| Each MCP server (Node.js) | ~27 MB additional |
| PostgreSQL | 45-256 MB (configurable) |
| Redis (cache + rate limiting) | 3-50 MB |
| Frontend + Nginx | ~15 MB |

### Capacity Formula

\`\`\`
Max subprocesses = (Backend memory limit - 200 MB) / 27 MB

Max concurrent users = Max subprocesses / avg servers per user
\`\`\`

**Example:** With a 4 GB backend limit and users averaging 3 servers each:
- Max subprocesses = (4096 - 200) / 27 = ~144
- Max concurrent users = 144 / 3 = **~48 users**

## Resource Isolation

BigMCP provides complete multi-tenant isolation:

1. **Process isolation** — Each user gets their own MCP server processes. A crash in one user's server cannot affect another user.
2. **Credential isolation** — Credentials are resolved per-user at server startup. No user can access another's secrets.
3. **Rate limit isolation** — Each user has independent rate limit counters. One user's activity cannot exhaust another's quota.

## Configuration Variables

All scaling parameters are configured via environment variables in your \`docker-compose.yml\`:

### Server Pool

| Variable | Default | Description |
|----------|---------|-------------|
| \`POOL_MAX_SERVERS_PER_USER\` | 5 | Maximum simultaneous MCP servers per user |
| \`POOL_MAX_TOTAL_SERVERS\` | 50 | Maximum MCP servers globally across all users |
| \`POOL_CLEANUP_TIMEOUT_MINUTES\` | 5 | Minutes of inactivity before a server is stopped |
| \`POOL_CLEANUP_INTERVAL_SECONDS\` | 30 | How often the cleanup task checks for idle servers |

### Rate Limiting

| Route Pattern | Requests/min | Reason |
|---------------|-------------|--------|
| \`/api/v1/api-keys/\` | 30 | Sensitive — key creation/revocation |
| \`/api/v1/credentials/\` | 50 | Sensitive — secret access |
| \`/api/v1/auth/\` | 100 | Login/register — legitimate bursts |
| \`/api/v1/marketplace/\` | 100 | Public — marketplace browsing |
| All other routes | 200 | Default (configurable via \`RATE_LIMIT_DEFAULT\`) |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| Pool size | 5 | Persistent database connections |
| Max overflow | 10 | Additional connections under load (total max: 15) |
| Pool recycle | 300s | Connection renewal interval |

## Tuning Profiles

### Small Deployment (< 10 users)

Works with default settings. Minimum requirements:

- 2 CPU cores, 4 GB RAM
- Backend memory limit: 1 GB

\`\`\`yaml
environment:
  - POOL_MAX_SERVERS_PER_USER=5
  - POOL_MAX_TOTAL_SERVERS=50
  - POOL_CLEANUP_TIMEOUT_MINUTES=5
  - RATE_LIMIT_DEFAULT=200
\`\`\`

### Medium Deployment (10-50 users)

Requires: 4+ CPU cores, 16 GB RAM

\`\`\`yaml
# Backend service
deploy:
  resources:
    limits:
      memory: 8G
    reservations:
      memory: 2G

environment:
  - POOL_MAX_SERVERS_PER_USER=10
  - POOL_MAX_TOTAL_SERVERS=150
  - POOL_CLEANUP_TIMEOUT_MINUTES=3
  - RATE_LIMIT_DEFAULT=150

# PostgreSQL service
deploy:
  resources:
    limits:
      memory: 512M
command:
  - postgres
  - -c
  - shared_buffers=128MB
  - -c
  - effective_cache_size=256MB
  - -c
  - work_mem=8MB
\`\`\`

### Large Deployment (50-200 users)

Requires: 8+ CPU cores, 32 GB RAM

\`\`\`yaml
# Backend service
deploy:
  resources:
    limits:
      memory: 20G
    reservations:
      memory: 4G

environment:
  - POOL_MAX_SERVERS_PER_USER=8
  - POOL_MAX_TOTAL_SERVERS=300
  - POOL_CLEANUP_TIMEOUT_MINUTES=2
  - RATE_LIMIT_DEFAULT=100

# PostgreSQL service
deploy:
  resources:
    limits:
      memory: 1G
command:
  - postgres
  - -c
  - shared_buffers=256MB
  - -c
  - effective_cache_size=512MB
  - -c
  - work_mem=16MB
  - -c
  - max_connections=200
\`\`\`

## Production Checklist

### Memory

- Set backend memory limit to at least 4 GB
- Set PostgreSQL memory limit to at least 256 MB
- Add swap space as a safety net (2 GB recommended)
- Verify \`POOL_MAX_TOTAL_SERVERS\` fits within your memory budget

### Database

- Enable TCP keepalives (prevents stale connections in Docker)
- Set \`idle_in_transaction_session_timeout\` to prevent connection leaks
- Increase \`shared_buffers\` proportionally to available memory

### Swap (Safety Net)

Adding swap prevents the OS from killing processes during temporary memory spikes:

\`\`\`bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
sysctl vm.swappiness=10
echo 'vm.swappiness=10' >> /etc/sysctl.conf
\`\`\`

Setting \`swappiness=10\` ensures swap is only used as a last resort.

## Monitoring

### Pool Stats Endpoint

\`GET /api/v1/admin/pool-stats\` returns real-time resource usage:

\`\`\`json
{
  "pool": {
    "total_users": 12,
    "total_servers": 35,
    "max_servers_per_user": 10,
    "max_total_servers": 150,
    "cleanup_timeout_minutes": 5,
    "servers_per_user": {"user1": 4, "user2": 3}
  },
  "cache": {
    "backend": "redis",
    "keys_count": 42,
    "hit_rate": "87.3%"
  },
  "redis_connected": true,
  "active_sse_sessions": 5
}
\`\`\`

### Key Metrics to Watch

| Metric | Warning Threshold | Action |
|--------|-------------------|--------|
| Total servers / max | > 80% | Increase \`POOL_MAX_TOTAL_SERVERS\` or backend memory |
| PostgreSQL memory | > 70% of limit | Increase PostgreSQL memory limit |
| Backend memory | > 85% of limit | Increase backend memory limit |
| Cache hit rate | < 50% | Check Redis connectivity, TTL settings |

### Docker Resource Monitoring

\`\`\`bash
# Live resource usage
docker stats

# Backend process details
docker top your-gateway-container -o pid,rss,args

# PostgreSQL active connections
docker exec your-postgres-container psql -U user -d bigmcp \
  -c "SELECT count(*) FROM pg_stat_activity;"
\`\`\`

## Cache Architecture

BigMCP uses a distributed cache with automatic fallback:

- **Redis** (production) — Shared across restarts, required for multi-instance
- **In-Memory** (fallback) — Automatic if Redis is unavailable, per-instance only

The cache stores tool lists per user, enabling instant responses (< 5 ms) when an AI client connects. Without cache, the first connection requires starting MCP servers which can take 30-60 seconds.

### Cache Invalidation

Tool caches are automatically invalidated when:
- Server visibility is changed from the admin panel
- A server is added or removed
- User credentials are updated

Connected AI clients are notified in real-time to refresh their tool list.

### Redis Configuration

Redis is included in the Docker Compose setup with sensible defaults:

\`\`\`yaml
redis:
  image: redis:7-alpine
  command: redis-server --maxmemory 128mb --maxmemory-policy allkeys-lru
\`\`\`

If Redis becomes unavailable, the system automatically falls back to in-memory caching with no user-visible errors.

## LRU Eviction

When resource limits are reached, BigMCP automatically evicts the least recently used servers:

1. **Per-user limit** — If a user reaches \`POOL_MAX_SERVERS_PER_USER\`, their oldest idle server is stopped before starting a new one.
2. **Global limit** — If the total reaches \`POOL_MAX_TOTAL_SERVERS\`, the globally oldest idle server is stopped (may affect any user).

This ensures the system remains stable under load while prioritizing active workloads.
`,
  monitoring: `
# Monitoring

Keep your BigMCP instance healthy and performant with built-in monitoring capabilities.

## Why Monitor?

Monitoring helps you:

- **Detect issues early** - Spot problems before users notice
- **Plan capacity** - Know when to scale up resources
- **Track usage** - Understand how your team uses BigMCP
- **Troubleshoot faster** - Find the root cause of issues quickly

## How It Works

\`\`\`mermaid
flowchart LR
    subgraph bigmcp [" "]
        APP(["<b>BigMCP</b><br/>/metrics endpoint"])
    end

    subgraph monitoring [" "]
        PROM(["<b>Prometheus</b><br/>Collects metrics"])
        GRAF(["<b>Grafana</b><br/>Visualizes data"])
    end

    subgraph you [" "]
        DASH(["<b>You</b><br/>View dashboards"])
    end

    APP -->|"every 15s"| PROM
    PROM --> GRAF
    GRAF --> DASH

    style bigmcp fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style monitoring fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style you fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style APP fill:#D97757,stroke:#c4624a,color:#ffffff
    style PROM fill:#f4e4df,stroke:#c4624a,color:#262626
    style GRAF fill:#f4e4df,stroke:#c4624a,color:#262626
    style DASH fill:#ffffff,stroke:#d4d4d4,color:#262626
\`\`\`

BigMCP exposes a \`/metrics\` endpoint that Prometheus scrapes periodically. You then visualize the data in Grafana dashboards.

## Quick Start

### Step 1: Verify Metrics Are Working

Run this command to check that metrics are available:

\`\`\`bash
curl http://localhost:8001/metrics
\`\`\`

You should see output like:
\`\`\`
# HELP bigmcp_pool_servers_total Number of active MCP servers
# TYPE bigmcp_pool_servers_total gauge
bigmcp_pool_servers_total 5
...
\`\`\`

> **Tip:** If you see metrics output, BigMCP monitoring is ready to use!

### Step 2: Connect Prometheus

Add BigMCP to your Prometheus configuration:

\`\`\`yaml
# prometheus.yml
scrape_configs:
  - job_name: 'bigmcp'
    static_configs:
      - targets: ['localhost:8001']
    scrape_interval: 15s
\`\`\`

### Step 3: View in Grafana

Once Prometheus is collecting data, you can:
1. Open Grafana (typically at \`http://localhost:3001\`)
2. Add Prometheus as a data source
3. Create dashboards or import our recommended panels

## What Can You Monitor?

### Key Metrics at a Glance

| What to Watch | Metric | Why It Matters |
|---------------|--------|----------------|
| Active servers | \`bigmcp_pool_servers_total\` | Shows current load |
| Active users | \`bigmcp_pool_users_total\` | Track concurrent usage |
| Request rate | \`bigmcp_http_requests_total\` | Understand traffic patterns |
| Response time | \`bigmcp_http_request_duration_seconds\` | Detect slowdowns |
| Cache efficiency | \`bigmcp_cache_hits_total\` | Optimize performance |

### Recommended Dashboard Panels

Build a dashboard with these essential views:

1. **Active Users & Servers** - Are you approaching capacity?
2. **Request Rate** - Traffic over time
3. **Error Rate** - Percentage of failed requests
4. **Response Time** - P50, P95, P99 latency
5. **Cache Hit Rate** - Is caching working effectively?

## Setting Up Alerts

Get notified when something needs attention. Here's a simple alert for high error rates:

\`\`\`yaml
# In your Prometheus alerting rules
groups:
  - name: bigmcp-alerts
    rules:
      - alert: HighErrorRate
        expr: |
          sum(rate(bigmcp_http_requests_total{status=~"5.."}[5m]))
          / sum(rate(bigmcp_http_requests_total[5m])) > 0.05
        for: 5m
        annotations:
          summary: "BigMCP error rate is above 5%"
\`\`\`

> **Note:** This alert triggers when more than 5% of requests fail over a 5-minute period.

## Adding Prometheus & Grafana

Don't have monitoring infrastructure yet? Add it to your Docker Compose:

\`\`\`yaml
services:
  prometheus:
    image: prom/prometheus:v2.47.0
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:10.1.0
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
\`\`\`

Access Grafana at \`http://localhost:3001\` (login: admin / admin).

## Security Considerations

The \`/metrics\` endpoint is open by default for Prometheus compatibility. In production, protect it by:

1. **Network isolation** - Only expose to your internal monitoring network
2. **Reverse proxy auth** - Add authentication via Nginx
3. **Firewall rules** - Block external access to port 8001

## Troubleshooting

### No metrics data in Grafana?

1. Verify BigMCP is running: \`docker ps | grep backend\`
2. Check Prometheus can reach BigMCP: \`curl http://localhost:8001/metrics\`
3. Verify Prometheus config points to correct host

### Metrics look stale?

Check Prometheus targets at \`http://localhost:9090/targets\` - BigMCP should show as "UP".

## Next Steps

- Set up [Backup & Restore](/docs/self-hosting/backup) to protect your data
- Review [Scaling & Performance](/docs/self-hosting/scaling) for capacity planning
`,
  backup: `
# Backup & Restore

Protect your BigMCP data with regular backups. This guide shows you how to create backups and restore them when needed.

## Why Backup?

Backups are your safety net. They protect you against:

- **Hardware failures** - Servers can fail unexpectedly
- **Human errors** - Accidental deletions happen
- **Data corruption** - Software bugs or power outages
- **Security incidents** - Quick recovery if compromised

> **Good news:** BigMCP makes backups simple with provided scripts. Set it up once, and your data is protected automatically.

## How It Works

\`\`\`mermaid
flowchart LR
    subgraph bigmcp [" "]
        DB(["<b>PostgreSQL</b><br/>Your data"])
        ENV(["<b>.env file</b><br/>Your config"])
    end

    subgraph backup [" "]
        SCRIPT(["<b>Backup Script</b><br/>Automated daily"])
    end

    subgraph storage [" "]
        REMOTE(["<b>Remote Storage</b><br/>Safe & encrypted"])
    end

    DB -->|"pg_dump"| SCRIPT
    ENV -->|"copy"| SCRIPT
    SCRIPT -->|"encrypted"| REMOTE

    style bigmcp fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style backup fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style storage fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style DB fill:#D97757,stroke:#c4624a,color:#ffffff
    style ENV fill:#f4e4df,stroke:#c4624a,color:#262626
    style SCRIPT fill:#f4e4df,stroke:#c4624a,color:#262626
    style REMOTE fill:#ffffff,stroke:#d4d4d4,color:#262626
\`\`\`

## What Gets Backed Up

| Component | Priority | Why |
|-----------|----------|-----|
| **PostgreSQL Database** | Critical | All your users, credentials, and settings |
| **\`.env\` file** | Critical | Your encryption keys and configuration |
| Qdrant vectors | Optional | Can be regenerated from data |
| Application logs | Optional | Only for debugging |

> **Important:** Always backup both the database AND the \`.env\` file. Without the encryption keys in \`.env\`, encrypted credentials cannot be recovered.

## Creating Your First Backup

### Step 1: Run the Backup Script

We provide a ready-to-use backup script:

\`\`\`bash
./scripts/ops/backup.sh
\`\`\`

This creates a compressed backup file like \`bigmcp_20260218_120000.sql.gz\` in the \`./backups/\` folder.

### Step 2: Move to Safe Storage

Never keep backups only on the same server! Copy to remote storage:

\`\`\`bash
scp ./backups/bigmcp_*.sql.gz user@backup-server:/backups/
\`\`\`

### Step 3: Clean Up Local Copy

For security, remove the local backup after copying:

\`\`\`bash
rm ./backups/bigmcp_*.sql.gz
\`\`\`

> **Tip:** Want to backup to a custom folder? Just add the path: \`./scripts/ops/backup.sh /my/backup/folder\`

## Restoring from Backup

### When to Restore

- Server hardware failed and you set up a new one
- Database got corrupted
- Someone accidentally deleted important data
- You want to migrate to a different server

### Step 1: Get Your Backup File

Copy the backup from your remote storage:

\`\`\`bash
scp user@backup-server:/backups/bigmcp_20260218.sql.gz ./
\`\`\`

### Step 2: Run the Restore Script

\`\`\`bash
./scripts/ops/restore.sh ./bigmcp_20260218.sql.gz
\`\`\`

The script will ask for confirmation before proceeding (it will overwrite your current database).

### Step 3: Verify Everything Works

\`\`\`bash
curl http://localhost:8001/health
\`\`\`

You should see a healthy response. Try logging into BigMCP to confirm your data is restored.

## Setting Up Automatic Backups

Don't rely on manual backups! Schedule them automatically with cron.

### Choose Your Schedule

| Team Size | Recommended Frequency | Keep Backups For |
|-----------|----------------------|------------------|
| Small team (<50 users) | Daily | 7 days |
| Medium team (50-500) | Every 12 hours | 14 days |
| Large team (500+) | Every 6 hours | 30 days |

### Add to Crontab

Edit your crontab with \`crontab -e\` and add:

\`\`\`bash
# Backup every day at 3 AM
0 3 * * * cd /opt/bigmcp && ./scripts/ops/backup.sh >> /var/log/bigmcp-backup.log 2>&1

# Clean up old backups every Sunday (keep 7 days)
0 4 * * 0 find /opt/bigmcp/backups -name "*.sql.gz" -mtime +7 -delete
\`\`\`

> **Pro tip:** After setting up, wait for the first automatic backup to run, then check \`/var/log/bigmcp-backup.log\` to make sure it worked.

## Security Best Practices

### Do This ✓

- **Store backups remotely** - Different server or cloud storage
- **Encrypt before uploading** - Use GPG encryption
- **Test restore regularly** - At least once a month
- **Document your process** - So anyone on the team can do it

### Avoid This ✗

- Keeping backups only on the production server
- Storing unencrypted backups in cloud storage
- Sharing backups via email or chat
- Forgetting to backup the \`.env\` file

### Encrypting Your Backups

Before uploading to cloud storage, encrypt your backup:

\`\`\`bash
# Encrypt the backup
gpg --encrypt --recipient your-gpg-key backup.sql.gz

# To restore, first decrypt
gpg --decrypt backup.sql.gz.gpg > backup.sql.gz
\`\`\`

## Disaster Recovery Scenarios

### "My server completely died"

1. Set up a new server with Docker
2. Clone the BigMCP repository
3. Restore your \`.env\` file from secure backup
4. Start the services: \`docker-compose up -d\`
5. Wait for PostgreSQL to start
6. Restore the database: \`./scripts/ops/restore.sh backup.sql.gz\`
7. Verify: \`curl http://localhost:8001/health\`

### "The database is corrupted"

1. Stop the backend: \`docker stop bigmcp-backend\`
2. Find your most recent good backup
3. Restore: \`./scripts/ops/restore.sh backup.sql.gz\`
4. Restart: \`docker start bigmcp-backend\`

### "Someone deleted important data"

Same as database corruption - restore from the most recent backup before the deletion.

## Troubleshooting

### Backup script says "container not running"

Check if PostgreSQL is running:

\`\`\`bash
docker ps | grep postgres
\`\`\`

If not, start it:

\`\`\`bash
docker-compose up -d postgres
\`\`\`

### Restore fails with "permission denied"

Verify the database user exists:

\`\`\`bash
docker exec bigmcp-postgres psql -U bigmcp -c "\\du"
\`\`\`

### Backup file is very large

Check the actual size:

\`\`\`bash
gunzip -l backup.sql.gz
\`\`\`

For very large databases (>10GB), consider incremental backup strategies.

## Next Steps

- Set up [Monitoring](/docs/self-hosting/monitoring) to catch issues before they become disasters
- Review [Scaling & Performance](/docs/self-hosting/scaling) for capacity planning
`,
}
