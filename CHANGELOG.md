# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0] - 2026-05-03

### MCP Surface Redesign — `search` + `execute` (BREAKING)

- **Two-tool surface**: OAuth clients (Claude Desktop, Cursor, Cline, …) now see only **`search`** and **`execute`** instead of the previous 8 `orchestrator_*` meta-tools. Drastically reduces context bloat and aligns with the natural agent loop.
- **Dynamic per-user pool**: `search(query, mode=append|replace, limit=10)` loads tools from the user's full catalog into an active session pool. The pool is materialized via the existing `Tool.is_visible_to_oauth_clients` flag — no new infra, all notifications/cache hooks reused.
- **`execute(goal | tool_name | composition_id [, params])`** with 4-level shortcut routing:
  - L0 explicit (composition_id or tool_name+params) → 0 LLM calls
  - L1 single-entry pool → 0–1 LLM call (param extraction only)
  - L2 clear textual top-1 winner → 1 LLM call
  - L3 ambiguous / multi-step → full IntentAnalyzer + CompositionExecutor
- **Compositions are first-class tools**: production compositions are indexed by `search` and routable through `execute`. Promotion to production now **requires a complete `input_schema`** declaring every `${parameters.X}` referenced in steps (HTTP 422 on mismatch).
- **Audit trail**: every `execute` call writes a fire-and-forget row to the new `execution_log` table (goal, mode, shortcut_level, duration_ms, status, errors). Useful for tuning the L2 thresholds and tracking LLM cost.

### Migration & Rollback

- **Migration `dynamic_pool_default_empty`**: resets every `tools.is_visible_to_oauth_clients` to `false` so users start with an **empty pool**. Users must call `search("…")` once at session start to populate it. Adds a partial index `ix_tools_org_visible_partial` to keep `tools/list` fast.
- **Migration `add_execution_log`**: creates the audit table.
- **Backward-compat shim**: legacy `orchestrator_*` tool names still dispatch correctly (only hidden from `tools/list`). Users who can't update their integrations can re-expose them with `LEGACY_ORCHESTRATOR_TOOLS_VISIBLE=true`.
- **Hard rollback**: set `LEGACY_POOL_BEHAVIOR=true` to revert `tools/list` to the legacy surface (orchestrator_* visible, search/execute hidden) without redeploy.

### Internals

- New module `mcp-registry/app/routers/mcp_gateway/pool/` with `definitions.py`, `pool_loader.py`, `search_handler.py`, `execute_handler.py`.
- Unified `PoolEntry` shape over Tool + Composition for scoring and orchestration.
- Search uses textual scoring (V1); semantic boost via Qdrant embeddings comes in V2.

---

## [2.0.0] - 2026-04-14

### Open Source Pivot
- **License**: Changed from Elastic License v2 (ELv2) to **AGPLv3** — BigMCP is now fully open source
- **No more user limits**: Community edition now supports unlimited users and organizations
- **All features unlocked**: RBAC, OAuth 2.0, Team Credentials, Tool Groups, Compositions — all available in every edition
- **Self-hosted first**: BigMCP is designed to be deployed on your own infrastructure
- **bigmcp.cloud**: Now a free demo/trial platform (no paid subscriptions)

### Improvements
- **Instance Admin**: First registered user is auto-promoted to admin; additional admins via token validation
- **Organization defaults**: Raised limits — 100 MCP servers, 100 contexts, 500 tool bindings, 50 API keys per org
- **Frontend**: Removed all "Upgrade to Enterprise" paywalls for self-hosted users
- **Feature gates**: All subscription-based restrictions bypassed in self-hosted mode
- **MCP 2025-03-26**: OAuth JWT tokens now accepted for MCP SSE connections (Claude Desktop compatibility)

### Migration Notes
- Existing Community Edition users: restart to get unlimited users (no migration needed)
- Existing organizations: run `alembic upgrade head` to update resource limits
- The first user on a fresh instance becomes instance admin automatically

---

## [1.2.0] - 2026-04-13

### MCP Gateway
- **OAuth JWT for SSE**: MCP SSE connections now accept both API Keys and OAuth JWT tokens (MCP 2025-03-26 compliance)
- **Improved tool change notifications**: SSE sessions are closed and re-initialized when tools change, ensuring Claude Desktop picks up changes

---

## [1.1.0] - 2026-02-21

### Core Platform
- **Unified MCP Gateway**: Single HTTP/SSE endpoint aggregating multiple MCP servers with intelligent tool routing and semantic discovery
- **Multi-Tenant Architecture**: Complete organization-based data isolation with Role-Based Access Control (Owner, Admin, Member, Viewer)
- **Authentication**: Dual JWT + API Key authentication, OAuth 2.0 Dynamic Client Registration, token blacklist, automatic session refresh

### Server Management
- **Marketplace**: Curated catalog of 180+ MCP servers from multiple sources (npm, GitHub, BigMCP curated) with one-click installation
- **Server Pool**: Per-user MCP server lifecycle management (STDIO/SSE wrappers) with automatic cleanup and auto-recovery on failure
- **Credential Management**: Hierarchical user/organization credentials with Fernet encryption at rest, automatic masking, and key rotation
- **Local Registry**: Self-hosted server registration and management for custom MCP servers

### Orchestration
- **Composition Engine**: Multi-step tool orchestration with template variables, wildcard extraction, map operations, and conditional logic
- **Vector Search**: Semantic tool discovery using embedding-based similarity (Mistral/OpenAI embeddings, Qdrant vector store)
- **SSE Notifications**: Real-time `tools/list_changed` events for connected clients

### Team & Organization
- **Team Management**: Email-based invitation system, organization switching, shared server visibility controls
- **Tool Groups**: Scoped API key access with configurable tool group bindings for fine-grained authorization
- **Instance Admin**: Token-based admin access for marketplace curation and registry management

### Editions & Licensing
- **Edition System**: Community (free, single user), Enterprise (self-hosted, license-based, unlimited users), Cloud SaaS
- **Subscription Integration**: Payment processing with Individual and Team tiers, trial management
- **License Validation**: ES256-signed JWT license keys with feature entitlements and admin token

### Frontend
- **React Application**: React 18 + TypeScript + Tailwind CSS + Vite with full i18n support (English and French)
- **Dashboard**: Server management, tool exploration, group creation, visibility controls
- **Settings**: Account, API keys, team management, preferences, subscription management
- **SEO & PWA**: Meta tags, Open Graph, sitemap generation, service worker, installable app manifest
- **Legal Pages**: Privacy Policy and Terms of Service with i18n support

### Security
- **MFA/TOTP**: Two-factor authentication with QR code enrollment, backup codes, and TOTP verification
- Token blacklist for secure JWT revocation
- Immutable audit logs with PII sanitization
- Rate limiting on authentication and API endpoints
- Security headers middleware (CSP, HSTS, X-Frame-Options)
- Non-root Docker containers with hardened configuration
- Comprehensive security test coverage

### Infrastructure
- **Database**: PostgreSQL with Alembic-managed migrations (18 versions), async SQLAlchemy with connection pooling
- **Caching**: Redis multi-layer cache for server metadata, tool listings, marketplace data, and rate limiting
- **Monitoring**: Prometheus metrics endpoint, health/readiness probes
- **Docker Deployment**: Multi-service Compose with PostgreSQL, Redis, Qdrant, Nginx (TLS), Certbot auto-renewal

### Development History

BigMCP was developed from November 2025 to February 2026 through the following phases:

1. **Foundation** (Nov 2025): Backend architecture, database models, Alembic migrations, multi-tenant data layer
2. **Authentication & API** (Nov-Dec 2025): JWT/API Key auth, OAuth 2.0 DCR, RBAC, token management
3. **Frontend & UX** (Dec 2025): React application, dashboard, marketplace browser, settings pages
4. **Marketplace & Orchestration** (Dec 2025-Jan 2026): Server catalog, composition engine, vector search, tool groups
5. **Editions & Subscriptions** (Jan 2026): Multi-edition licensing, payment integration, feature gating
6. **Team Features** (Jan 2026): Invitations, organization switching, shared credentials, visibility controls
7. **Internationalization** (Jan 2026): Full i18n system with English and French translations
8. **Security Hardening** (Feb 2026): MFA/TOTP, key rotation, rate limiting, security middleware, testing
9. **Production Readiness** (Feb 2026): SEO, PWA, monitoring, log cleanup, branding coherence, documentation
