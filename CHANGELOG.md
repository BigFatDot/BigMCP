# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.3.0] - 2026-05-15

Phase B-0: durable suspension infrastructure for compositions. Adds three new tables and a status-as-lock executor that lets compositions yield, wait for an external event, and resume cleanly across crashes — all exposed via standard MCP 2025-06-18 primitives (`resources/subscribe`, `notifications/resources/updated`). Existing production compositions stay 100% on the legacy sync path (Pattern A) — zero regression.

### Composition execution engine — durable suspension

- **3 new tables** (`composition_execution`, `execution_step_event`, `pending_notification`) via Alembic migration `add_composition_executions`. Down-revision `add_composition_share_request`. No backfill needed (legacy executor was sync).
- **`ResumableExecutor`** singleton (`app/orchestration/resumable_executor.py`) with status-as-lock + conditional UPDATE-RETURNING for concurrency control (no Postgres advisory locks). Idempotence is author-controlled (`step.idempotent=true` opts a step into safe re-run after a crash); the default-safe policy refuses to re-fire a non-idempotent step that crashed mid-flight, surfacing a clear failure reason instead.
- **Pattern A / Pattern C routing** (`app/orchestration/composition_routing.py`): static analysis of the composition's step types decides between the legacy sync executor (Pattern A — zero regression for every existing production composition) and the new detached `ResumableExecutor` (Pattern C — returns `composition://executions/{id}` immediately for clients to subscribe to). Pattern B (progress-streamed) deferred until measured demand.
- **Sub-composition propagation hook**: parent suspended on a `subcomposition` reason gets resumed automatically when the child reaches a terminal state, with the child's result (or error envelope) injected into the parent's suspended step. Depth capped at 5 — enforced pre-flight in `create_execution()` based on the parent's stored depth (caller-supplied `depth=` is overridden, no bypass).
- **Orphan recovery on lifespan startup** marks any `running` row from a prior crashed boot as `failed("backend_restart_orphan")` with a corresponding audit + timeline event before the queue worker accepts new work.
- **Queue worker** (`app/orchestration/queue_worker.py`) singleton: 5s tick, batch limit 200, per-user concurrency cap of 50 — over-quota requests land in `queued` and get promoted FIFO as slots free up.

### MCP surface

- **`composition://executions/{id}` MCP resource** — readable + subscribable, per-user scoped (cross-user reads return the same response as missing rows; no information leak about row existence). Listed in `resources/list` for the calling user; full state via `resources/read`. New `resources/subscribe` and `resources/unsubscribe` handlers track `(session_id → uri)` in process; the executor's terminal/suspended transitions fire `notifications/resources/updated` with parent-chain walk so subscribed ancestors get pinged on child transitions.
- **`composition_status` meta-tool** added to the dynamic pool surface (alongside `search` / `execute` / `describe_tool`) as a polling fallback for clients that can't subscribe. Returns SUMMARY only (status, current step, suspension reason, error, dates) — full state stays behind `resources/read` and the REST endpoint to keep polls cheap. Per-user-scoped: cross-user execution_id returns `status='not_found'`.
- **Pending notification queue + flush on `initialize`**: when the executor fires a transition and the target SSE session isn't live on this process, we persist the `(session_id, uri)` in `pending_notification`. The next `initialize` that comes in with that `Mcp-Session-Id` (gateway now honours the client-supplied header on initialize instead of always minting a new one) triggers a background flush that replays in `created_at` order, deletes on success, and drops rows older than 7 days.
- **Audit emission isolated to its own DB session** (executor `_emit_audit`): the audit_service rolls back on failure, and a shared session would have its ORM identity map expired, breaking the next `execution.composition.steps` lazy-load and silently killing sub-composition propagation.

### REST + UI

- **REST endpoints** at `/api/v1/compositions/executions`:
  - `GET /` — paginated list with `?status=`, `?include_terminal=`, `?limit=`, `?offset=`. Default filter: non-terminal statuses.
  - `GET /{id}` — full detail with state + recent timeline events.
  - `POST /{id}/cancel` — cooperative cancel (202 Accepted, lands at the next step boundary).
  - `POST /{id}/resume` — JWT-only B-0 (B-3 will branch on the Authorization scheme to also accept HMAC webhook tokens). Returns 409 when the row is no longer suspended.
  - `GET /api/v1/compositions/{id}/executions` — admin governance view, all executions of one composition for the org (Admin/Owner only).
- **Web UI** under `/app/compositions/executions`:
  - List page with status chips, include-terminal toggle, per-row cancel button, polls every 5s while ≥1 row is non-terminal.
  - Detail page with status header, parent-execution link for sub-compositions, "Provide test response" form for `_test_suspend` rows (POSTs `/resume`), result/error blocks, full step-event timeline, collapsible raw state.
  - "View executions" link in the existing `CompositionsPage` header so the route is discoverable.

### Schema cleanup

- **`CompositionStep` Pydantic schema** now uses canonical runtime field names (`step_id` / `parameters`) instead of the legacy doc-only `id` / `params` aliases that never matched what the executor reads from the JSONB column. New flags added with safe defaults: `optional`, `idempotent`, `cancellable`, `retry_strategy`, `timeout_seconds`. `extra='forbid'` so authors get a 422 at promotion time instead of a silent runtime mismatch later.
- **`server_bindings`** marked deprecated on `CompositionCreate` and `CompositionUpdate` (field stays on the model — no migration). The executor no longer reads it; tool routing resolves through the user's server pool. Frontend stops sending the empty `{}`. May be repurposed in B-1+ if a real `${binding.X}` use case emerges.

### Quality

- **196 tests passing across 9 new B-0 test files**, zero regression on existing 100+ tests. The 14 must-pass tests from the design doc are all covered; `test_must_pass_b0.py::test_must_pass_tests_exist` freezes the coverage map and fails loud if any test is renamed without updating the map.

### Misc

- **Fixed pre-existing `execution_log` retention bug**: the daily prune loop was failing with `invalid input for query argument $1: 30 (expected str, got int)` under asyncpg because the `(:days || ' days')::interval` pattern needed the bind to be a string. Switched to `make_interval(days => :days)` which takes the int directly.

### Audit log events added

`composition.execution_created`, `composition.execution_started`, `composition.execution_completed`, `composition.execution_failed`, `composition.execution_cancelled`, `composition.execution_expired`, `composition.execution_suspended`, `composition.execution_resumed`.

### Design doc

Full design: `mcp-registry/docs/composition_executions_b0.md` (~1000 lines, two review rounds integrated). Roadmap for B-1+ step types (`elicit`, `wait_callback`, `wait_until`, `approval`, `subcomposition`) follows the same shape — add the type to `SUSPENDING_STEP_TYPES`, add a dispatch branch in `_execute_step`.

---

## [2.2.0] - 2026-05-09

Iterative hardening of the v2.1.0 surface, a new Services workspace, MCP 2025-06-18 alignment, remote streamable-HTTP MCP servers, and a session-store rewrite that makes sessions survive backend restarts.

### MCP protocol — 2025-06-18 alignment

- **`MCP_PROTOCOL_VERSION` bumped to `2025-06-18`** in `initialize` (was 2025-03-26).
- **`tools/list` items declare `title` + `outputSchema`** (the `search` and `execute` envelopes), and `tools/call` returns `structuredContent` next to the legacy text body so clients can parse the response without regex.
- **`initialize.result.instructions`** describes the search → tools/list → execute flow so clients understand the gateway's two-tool model from the first message.
- **Prompts (`tool_discovery`, `compose_workflow`, `getting_started`, `tool_usage`) rewritten** to reference `search`/`execute` instead of the legacy `orchestrator_*` set.
- **Spec-compliant tool-list invalidation**: `notify_org_tools_changed` now pushes a standard `notifications/tools/list_changed` envelope into every matching SSE session's outbound queue instead of severing the SSE connection. The legacy hard-kill behaviour stays available behind `MCP_KILL_SESSION_ON_TOOLS_CHANGED=true` as an emergency fallback.

### Sessions persisted in Redis (no more stale clients on redeploy)

- **`MCPSessionStore`** replaces the module-level `mcp_sessions` dict. Metadata (user_id, org_id, api_key_id, …) lives in Redis through the existing `CacheBackend` (TTL aligned with `SESSION_TIMEOUT_SECONDS`); the per-process `asyncio.Queue` is recreated on demand. Sessions survive backend restarts.
- **Reconnect via `Mcp-Session-Id` header**: the SSE GET endpoint now resumes an existing session if its metadata is still in Redis — clients don't need to re-issue `initialize` after a redeploy.
- **TTL refresh** every keepalive interval keeps long-lived SSE streams warm without flooding Redis.

### OAuth visibility fix (CRITICAL)

- **`Tool.is_visible_to_oauth_clients` is now actually enforced.** The previous filter only honoured `MCPServer.is_visible_to_oauth_clients`, which let the entire catalog (~221 tools) leak to OAuth clients regardless of pool state. Filter now intersects on `(server_uuid, tool_name)` keys against the pool. Without this fix, the dynamic pool from v2.1.0 was effectively a no-op for OAuth clients on the read path.

### Web UI — Services workspace

- **Three-column drag-and-drop UX** (catalog / active pool / toolboxes) built on `@dnd-kit/{core,sortable,utilities}`, with optimistic updates via TanStack Query for instant feedback.
- **Drop a tool on `+ New toolbox`** to create one in place; auto-suffix on duplicate names with a sticky error banner.
- **Edit toolboxes** (rename, recolor, prune items, delete) and **revoke services from chips** (deletes the user credential).
- **AssistantModal becomes a toolbox-by-intent builder** — the LLM proposes a coherent toolbox from a natural-language goal, then the user accepts / regenerates / refines.
- **Mobile tab switcher** for the same workspace at small widths.
- **Full EN/FR translations** for the new UX.

### Pool API surface

- New endpoints to drive the workspace from the web UI:
  - `POST /api/v1/pool/unload` — remove tools from the active pool.
  - `POST /api/v1/pool/suggest` — LLM-assisted tool suggestion for a free-text goal.
  - `POST /api/v1/tool-groups/{id}/load-into-pool` — load an entire toolbox into the active pool in one call.
- All endpoints write to `audit_logs` (POOL_LOAD / POOL_UNLOAD / POOL_TOOLBOX_LOAD).

### Remote streamable-HTTP MCP servers

- **New `remote` install type**: connect to upstream MCP servers exposing a public HTTP endpoint without installing a local process. URL resolved from the marketplace manifest, credentials mapped onto standard auth headers (Bearer, X-API-Key, …) following the same convention as STDIO env injection.
- Schema: new `mcp_servers.url` column, `command` and `install_package` made nullable. Migration `add_remote_install_type` (heals the v2.1.0 chain that referenced this revision).
- Coverage: `tests/test_http_auth_headers.py` validates the credential → header mapping.

### Hardening (post-2.1.0 review backlog)

- Two passes of review hardening on the v2.1.0 batch (defensive org-scoping on bulk updates, error envelope normalisation, rate-limit entries for the LLM-backed propose endpoints).
- `i18n(workspace)`: clarified the wording around server kill-switch vs dynamic pool — they were getting confused in the UI.

### Internals

- New module `mcp-registry/app/services/mcp_session_store.py`.
- 7-test suite for the session store (`test_mcp_session_store.py`).
- Stress-tested live: 50 concurrent OAuth `tools/list` consistent, pool flips propagate after cache invalidation, no cross-org leak, 200 sessions × 20 messages without loss, Redis reattach across simulated process restarts.

---

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
