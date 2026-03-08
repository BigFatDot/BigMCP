# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
