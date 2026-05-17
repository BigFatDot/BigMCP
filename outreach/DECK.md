# BigMCP — 5-slide pitch deck

**Audience** : DSI, CTO, head of platform, AI ops lead
**Time** : 5 minutes (1 min / slide)
**Format** : markdown — render via Slidev / Marp / reveal.js, or screen-share as-is in a Google Doc / Notion

> Convert with one of these :
> - `npx slidev outreach/DECK.md --remote` (best for live demo)
> - `marp outreach/DECK.md --pdf` (sober PDF)
> - Copy-paste into Google Slides one slide at a time

---

## Slide 1 — The problem

# Your team uses 5+ MCP servers. Each one is its own snowflake.

- Every employee configures Claude / Cursor / Continue.dev separately
- Each MCP server holds its own credentials, with its own rotation cycle
- Zero visibility into who used what, when
- "I want Bob to access GitHub but NOT prod DB" → impossible without forking each server
- Workflows that span 3 tools = manual orchestration, no audit, no recovery on crash

> *Speaker notes : pause here. Let them nod. The problem must land before the solution.*

---

## Slide 2 — What BigMCP is

# One URL. Every MCP server. Org-level governance.

```
┌─────────────────┐
│  Claude Desktop │──┐
│  Cursor         │──┤
│  Continue.dev   │──┤      ONE URL          ┌──────────────┐
│  Mistral LeChat │──┼─►  bigmcp.acme.fr ──► │   BigMCP     │──► [any MCP server]
│  n8n            │──┤   (Bearer token)      │   gateway    │──► [your custom APIs]
│  custom client  │──┘                       └──────────────┘──► [180+ marketplace]
└─────────────────┘
                                                    │
                                                    ▼
                                            ┌──────────────┐
                                            │  Postgres    │
                                            │  • Audit log │
                                            │  • Org RBAC  │
                                            │  • Workflow  │
                                            │    state     │
                                            └──────────────┘
```

- **Self-host** on your infra (Docker Compose, 5 min)
- **AGPLv3** — no vendor lock-in, no per-seat pricing, no upsell
- **MCP 2025-06-18** native (Streamable HTTP + SSE)

> *Speaker notes : the value prop is the diagram. If they get it, the rest is detail.*

---

## Slide 3 — Why it's different

# Three things you don't get with n8n / Composio / DIY

### 1. Durable workflows that survive crashes

Compositions can suspend mid-flight for :
- `elicit` — ask the user a question
- `wait_until` — pause until a future timestamp
- `wait_callback` — wait for an external webhook (HMAC-protected URL)
- `subcomposition` — call another composition; parent suspends until child terminates
- `approval` — cross-user gate, four-eyes principle by default

State persists in Postgres. Pod restarts ? Composition resumes exactly where it stopped.

### 2. Org-level governance baked in

- 4-tier RBAC (Owner / Admin / Member / Viewer)
- Scoped API keys per Tool Group (`tools:read`, `tools:execute`, `credentials:read`, …)
- Audit log with HMAC-SHA256 integrity (`verify_integrity()` detects tampering)
- OIDC SSO with 5 vendor presets + role mapping + force-SSO toggle

### 3. White-label your instance in 5 min

- Instance name, logo, color, welcome message
- First-run wizard for the instance admin
- Becomes "Acme MCP" everywhere — navbar, page title, emails, landing page

> *Speaker notes : pick the one that hits hardest for THIS prospect. For an AI ops lead, lead with #1. For a DSI, lead with #2.*

---

## Slide 4 — Proof

# Security model + production posture

| What | Algorithm |
|------|-----------|
| Credentials at rest | Fernet (AES-128-CBC + HMAC-SHA256) |
| Passwords | bcrypt cost 12 |
| API key hashes | bcrypt |
| Audit integrity | HMAC-SHA256 over canonical JSON |
| JWT signing | HS256 |

### Threat model

- **Protects against** : credential exfil (db dump useless without `ENCRYPTION_KEY`), cross-org leak (404 not 403), unscoped API key abuse, audit tampering, token replay
- **Does NOT** : substitute for `ENCRYPTION_KEY` backup, sandbox 3rd-party MCP servers, replace your LLM provider's compliance

### How to evaluate

- [bigmcp.cloud](https://bigmcp.cloud) — live demo, sign up in 30 sec
- [github.com/bigfatdot/BigMCP](https://github.com/bigfatdot/BigMCP) — code, CHANGELOG, roadmap
- [bigmcp.cloud/docs/concepts/security](https://bigmcp.cloud/docs/concepts/security) — full threat model, compliance posture
- [bigmcp.cloud/docs/project/roadmap](https://bigmcp.cloud/docs/project/roadmap) — what's shipped, what's next

> *Speaker notes : skip the table if the prospect is non-technical. Jump to the 4 links.*

---

## Slide 5 — How to engage

# Early Adopter Program — first 5 orgs

Looking for **5 organizations** who'll deploy BigMCP internally and tell us what's missing.

If you join :
- ✅ Direct line to the maintainer (me) — Slack / email, daily availability
- ✅ Prioritised bug fixes (your blockers jump the queue)
- ✅ Feature requests heard before roadmap closes
- ✅ Free deployment support if you want it

What we ask in return :
- 🤝 Honest feedback after deploying
- 🤝 Permission to (anonymised) testimonial later — purely optional

### No fee. No NDA. No commitment.

### Next step

Reply to this mail with :
- Team size
- MCP servers you'd connect (rough list)
- Deployment constraints (on-prem / cloud / hybrid)

I'll come back within 24h with a deploy guide tailored to your context — or, if you prefer, a 15 min screen-share to demo first.

📧 contact@bigmcp.cloud
🌐 [bigmcp.cloud](https://bigmcp.cloud)

> *Speaker notes : end on a CONCRETE next step. "Reply with 3 facts about your stack" is much stickier than "let me know if you're interested".*

---

# Speaker prep notes (for you, not for the deck)

## Anticipated questions

**Q: What's the lock-in story ?**
A: AGPLv3 + Postgres + standard MCP protocol. You can fork the repo, dump the DB, and migrate to any other MCP-compatible system. The only lock-in is the compositions you author — but they're plain JSON, so even those move.

**Q: Why AGPL and not MIT/Apache ?**
A: Self-hosting internally = no copyleft trigger. Only if you fork and host a modified version for THIRD parties do you need to publish your changes. For 99% of enterprise deployers, AGPLv3 is functionally MIT.

**Q: SOC 2 ? ISO 27001 ?**
A: BigMCP is not certified. Self-hosting puts the compliance perimeter on YOUR infra. We're working on a SOC 2 Type I scope for the SaaS demo but it's not a near-term commitment.

**Q: How does this differ from Composio ?**
A: Composio is SaaS-first, MCP-second, with a per-tool pricing model. BigMCP is MCP-first, self-host-first, free. We don't compete on tool count (Composio has more); we compete on governance + durability.

**Q: How does this differ from LangGraph ?**
A: LangGraph is an in-process orchestrator for an agent loop you write yourself. BigMCP is an MCP gateway that exposes durable compositions AS MCP tools — your agents (LangGraph or otherwise) call them as primitives. The two stack.

**Q: What if the project dies ?**
A: Fork the repo, dump the DB, you have a runnable system forever. Compositions are JSON, credentials are Fernet-encrypted (you have the key), MCP servers are standard. No proprietary format anywhere.

**Q: Why should I trust a 0-customer project ?**
A: You shouldn't fully trust any 0-customer project. That's why we ship a real Early Adopter Program with direct maintainer access — you're not betting on a roadmap, you're getting a personal commitment from me to make it work for you.

## What to NOT say

- ❌ "We have plans to add..." → only ship-or-shut-up about what exists today
- ❌ "Soon" / "Q4" → roadmap promises burn credibility
- ❌ "Disruptive" / "Game-changing" / "Synergies" → bullshit detector firing
- ❌ "Compared to OpenAI's plugin store..." → wrong analogue, different problem
- ❌ Pitching the SaaS as primary → self-host is the primary path, SaaS is demo

## What to say if they push back hard

- *"Honest take : if you have 2 MCP servers and 5 users, BigMCP is overkill. Native config in Claude Desktop is simpler. Come back when your team grows or when compliance asks you for an audit log."*

This humility wins more deals than the pitch.
