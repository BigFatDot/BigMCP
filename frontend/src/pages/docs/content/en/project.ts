/**
 * Project — meta docs (roadmap, release cadence, governance).
 */

export const projectContent: Record<string, string> = {
  roadmap: `
# Roadmap

What's shipped, what's next, what's deliberately not in scope.
Last updated 2026-05-17.

> Want to influence priorities? Open a GitHub issue or join the [Early
> Adopter Program](mailto:contact@bigmcp.cloud?subject=Early%20Adopter%20Program)
> — early adopters get direct line to the maintainer.

## Shipped (v2.0 → v2.4)

### v2.4.0 — Phase B-1 + self-host white-label (May 2026)
- 5 durable composition step types: \`elicit\`, \`wait_until\`,
  \`wait_callback\`, \`subcomposition\`, \`approval\`
- Resumable executor with Postgres-persisted state; survives crashes
  and restarts
- Pending-approvals UI + 4-eyes principle by default
- Composition templates + first-run wizard + instance branding
  (logo, name, color, welcome message)
- Sober landing page for non-SaaS deployments
- Admin metrics page for composition adoption insights

### v2.3.0 — Phase B-0 (April 2026)
- Durable suspension infrastructure (\`composition_execution\` +
  \`execution_step_event\` + \`pending_notification\` tables)
- \`_test_suspend\` debug step type for validating the round-trip
- Status-as-lock pattern, atomic UPDATE-WHERE RETURNING throughout

### v2.2.0 — Security consolidation (April 2026)
- OIDC SSO with 5 vendor presets (Google, Microsoft Entra, Okta,
  Authentik, Keycloak), role mapping, force-SSO with admin-backdoor
- Per-JTI refresh token revocation, \`/auth/connected-apps\` page
- HMAC integrity on audit logs (\`verify_integrity()\`)
- DB pool sizing + per-org cross-tenant guards on tool_bindings
- \`SCOPE_ENFORCE_MODE\` env flag for shadow → enforce rollout

### v2.0 → v2.1 — Foundations (Q1 2026)
- Custom MCP server registration (npm, pip, GitHub, Docker, HTTP, local)
- 180+ server marketplace with semantic search
- 4-tier RBAC (Owner / Admin / Member / Viewer)
- Tool Groups with PRIVATE / ORG / PUBLIC visibility + scoped API keys
- MCP 2025-06-18 protocol (Streamable HTTP + SSE)
- OAuth 2.0 + PKCE for AI clients
- Fernet at-rest encryption for credentials

## Next up (Q3 2026 target)

### Phase B-2 — cron triggers
The \`composition_execution.trigger='cron'\` column already exists; the
scheduler doesn't. Lets a composition fire on a cron expression
instead of (or in addition to) on-demand invocation. Use case:
"daily 9am sync of Grist → Sheets".

### First-time experience hub
Replace the marketplace-browse-first \`/app\` landing with a real hub
showing default pool, recent executions, admin announcements. Empty
states converted from "do work" tone to "let me orient you" tone.

### Frontend test scaffolding
Vitest helpers + Playwright on 5 critical paths (login, marketplace
install, composition create, composition execute, admin branding).
Prereq for the industrialisation track.

### Per-org marketplace SaaS-mode parity
Org-scoped marketplace curation already works in self-host (per the
\`org_marketplace_curation\` table); SaaS-mode is single-list global.

## Considering (no commit yet)

- **Real Web UI workflow editor** (drag-and-drop nodes for
  compositions) — today it's JSON or LLM-proposed
- **Per-user OAuth providers** (Google Sign-In, GitHub Sign-In for
  end-users — not for the IdP-level SSO, which is already shipped)
- **Marketplace mode "closed"** as a single env var (\`MARKETPLACE_DISABLED=true\`)
  instead of per-source toggles
- **MCP server sandboxing** — running 3rd-party MCP servers in
  containerised sandboxes by default
- **Webhook outbound integration** for composition events ("notify Slack
  when an approval comes in", "POST to Datadog on every failed step")
- **Multi-region deployment** for the SaaS demo

## Deliberately NOT in scope

- **Visual workflow editor as the primary creation path.** Composition
  authoring is currently JSON or LLM-proposed; we want to keep
  programmatic-first. A visual editor would come ON TOP of the JSON,
  never replacing it.
- **Custom UI plugins / marketplace.** BigMCP is a gateway, not a
  platform-as-a-service. Adding "install custom UI panels" muddies
  the value proposition.
- **Built-in agent runtime.** BigMCP exposes MCP tools; the agent
  framework (LangGraph, your own loop, etc.) stays on the caller side.
  We don't want to compete with LangGraph / Autogen / Composio's
  trigger.dev — we serve them.
- **WYSIWYG composition debugger as a separate product.** Composition
  Executions detail page + audit log + Prometheus metrics cover the
  observability story.

## Release cadence

We aim for a tagged release every 4–6 weeks. Patch releases
(\`2.4.x\`) ship as needed for bugs. The \`main\` branch on GitHub is
always in a deployable state; we tag from \`main\` rather than from
a release branch.

## How to follow along

- [GitHub releases](https://github.com/bigfatdot/BigMCP/releases)
- [CHANGELOG.md](https://github.com/bigfatdot/BigMCP/blob/main/CHANGELOG.md)
- [Issues](https://github.com/bigfatdot/BigMCP/issues) — bug reports
  & feature requests
- [contact@bigmcp.cloud](mailto:contact@bigmcp.cloud) — general inquiries
- [security@bigmcp.cloud](mailto:security@bigmcp.cloud) — vulnerability disclosure
`,
}
