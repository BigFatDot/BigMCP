# Outreach Mail Templates

Three variants for three personas. Each is short on purpose — a cold
mail that runs longer than 8 sentences gets archived.

**Anti-patterns to avoid** :
- Don't open with "I hope this finds you well" — feature flag for AI-generated mail
- Don't pitch "the platform" before naming the specific problem
- Don't send a deck attached — link to it. Attachments trigger filters
- Don't add a CTA larger than "15 min next week ?"

---

## Variant A — DSI / CTO, public sector or regulated org

**Subject** : `BigMCP — MCP gateway open source que vous pouvez déployer chez vous`

**Body** :

> Bonjour {{first_name}},
>
> Je tombe sur {{contextual_hook — e.g. "votre poste à Cerema sur la stratégie data" / "votre article dans Acteurs Publics sur l'IA en collectivité"}}, et je me dis que ce qu'on construit avec BigMCP pourrait vous intéresser.
>
> En une phrase : BigMCP est une **passerelle MCP open-source** (AGPLv3) qui agrège vos outils internes — Grist, GitLab, vos APIs métier, vos serveurs MCP custom — derrière **une seule URL**, avec RBAC, audit immuable et workflows durables qui survivent aux redémarrages. Vos employés branchent leur Claude / Cursor / Mistral Le Chat avec un Bearer token et accèdent uniquement aux outils que leur rôle autorise.
>
> Tout est **self-host** sur votre infra (Docker Compose, 5 min) — vos credentials chiffrés Fernet ne quittent jamais votre serveur. Le compliance perimeter reste chez vous, ce qui simplifie pas mal pour le secteur public.
>
> On est en phase **Early Adopter Program** : 5 premières orgs ont une ligne directe avec moi (le mainteneur), bugs priorisés, feature requests entendues avant la roadmap. Pas de fee, pas de NDA.
>
> 15 minutes la semaine prochaine pour vous montrer en live ? Sinon : [bigmcp.cloud](https://bigmcp.cloud) (démo) + [github.com/bigfatdot/BigMCP](https://github.com/bigfatdot/BigMCP) (code + docs).
>
> Cordialement,
> Nicolas
>
> PS — Si BigMCP n'est pas pour vous mais que vous connaissez quelqu'un que ça toucherait, je vous serais reconnaissant d'un transfert.

**Why this works for the persona** :
- "Open-source que vous pouvez déployer chez vous" = bypasses the SaaS allergy of public sector
- AGPLv3 + self-host + Fernet = three compliance-buzzwords without sounding salesy
- "Compliance perimeter reste chez vous" = exact phrasing a DSI uses internally
- Early Adopter Program = converts the 0-customer reality into a privilege
- 15 min ask = low friction
- PS = optimizes for forward even if persona is wrong

---

## Variant B — Head of Platform / SRE / DevOps lead, mid-size tech company

**Subject** : `Question rapide — vous gérez combien de serveurs MCP en interne ?`

**Body** :

> Hi {{first_name}},
>
> Quick one — saw {{contextual_hook — e.g. "your talk at PlatformCon on internal AI tooling" / "your tweet about juggling Claude configs across the team"}}.
>
> If your team has more than 3-4 internal MCP servers (custom APIs, GitHub, your DB, your DAG runner, whatever) and you're managing per-user creds + per-team access manually, there's an OSS gateway I built that might save you a weekend of duct tape.
>
> **BigMCP** — single URL, scoped API keys per Tool Group, audit log, durable workflows that survive pod restarts. AGPLv3, deploys via Docker Compose, no vendor lock-in.
>
> The differentiator vs n8n / Composio :
> - **MCP-native** — your Claude Desktop / Cursor / Continue.dev connect with one URL, no SDK per language
> - **Durable suspension** — workflows can pause for human approval, a webhook callback, or a future timestamp, then resume exactly where they stopped (Postgres-backed state)
> - **Org-level governance** — RBAC + scoped keys + audit with HMAC integrity
>
> Comparison table + demo at [bigmcp.cloud](https://bigmcp.cloud). Code at [github.com/bigfatdot/BigMCP](https://github.com/bigfatdot/BigMCP).
>
> Early Adopter Program is open — first 5 orgs get direct line to me, prioritised bugs, feature requests heard early. No NDA.
>
> Worth 15 min on a call to see if it fits your stack?
>
> Cheers,
> Nicolas

**Why this works for the persona** :
- "Quick one" + reference to a public moment of theirs = real, not bulk-blast
- "Save you a weekend of duct tape" = SRE empathy
- Tech comparison vs n8n/Composio = they're already evaluating these
- "Durable suspension" + "Postgres-backed state" = engineer-speak that earns credibility
- "No SDK per language" = real pain point if they've integrated SDKs before

---

## Variant C — AI Ops / Platform AI lead, company with multiple LLM-using teams

**Subject** : `MCP gateway pour {{their_company}} — direct line to the maintainer`

**Body** :

> Hi {{first_name}},
>
> Saw {{contextual_hook — e.g. "your post about deploying Claude across 200 internal users" / "your job posting for an AI platform engineer"}}.
>
> If you're deploying Claude / Cursor / Continue.dev across multiple teams and each user is configuring their own MCP servers, you're looking at a credentials sprawl problem before long.
>
> **BigMCP** consolidates that : every employee connects to a single URL, gets only the tools their role allows, every action is audited. The interesting bit for AI ops specifically — compositions that **suspend** for human approval (HITL pattern), wait for an external webhook, or hold for a future timestamp. Workflows that needed Temporal-class infra before are 5 lines of JSON now.
>
> 100% self-host on your infra (Docker Compose), AGPLv3, no SaaS dependency. Compose with your existing LLM provider — bring your own Anthropic key.
>
> Honest framing : I'm running an Early Adopter Program. First 5 orgs that deploy get direct line to me (the mainteneur), prioritised bugs, feature requests heard before they hit roadmap. No fee, no NDA, no commitment.
>
> Worth 15 min for a quick demo? Even if BigMCP isn't a fit, happy to share what we learned building the durable composition engine — might be useful context for your own ops.
>
> [bigmcp.cloud](https://bigmcp.cloud) (demo) · [github.com/bigfatdot/BigMCP](https://github.com/bigfatdot/BigMCP) (code)
>
> Best,
> Nicolas

**Why this works for the persona** :
- AI Ops thinks in "deploying Claude at scale" not "MCP gateway"
- Credentials sprawl + RBAC = the explicit pain
- "Temporal-class infra in 5 lines of JSON" = vocabulary they know
- "Even if not a fit, happy to share..." = generous, opens door

---

## Follow-up cadence

If no reply :

| Day | Action |
|-----|--------|
| D+0 | Send mail |
| D+5 | Light follow-up (1 sentence : "Bumping this in case it got buried — any interest?") |
| D+12 | Final follow-up with a single new piece of info (a specific feature shipped that week, or a use case relevant to them) |
| D+25 | Move to "passive" : add to a quarterly "what's new" newsletter (if you have one) |

Three touches max. If they don't bite after 3, they're not the persona — move on.

---

## Tracking template

Keep a flat CSV or Notion / Airtable table :

| Date sent | Persona | Name | Company | Email | Hook used | Reply (Y/N) | Outcome |
|-----------|---------|------|---------|-------|-----------|-------------|---------|
| 2026-05-17 | A | ... | Cerema | ... | "article Acteurs Publics" | | |

After 20 sends, you can A/B which subject line / hook converts.

---

## How to personalise

The single biggest mistake : sending the same mail to 20 prospects.
The single biggest unlock : **2 minutes of LinkedIn / GitHub / company-site research** before each send, lifted into the `{{contextual_hook}}` slot.

Examples of strong hooks :
- A recent talk / podcast / article they did
- A job posting their company has open (signals what they're hiring around)
- A tweet / LinkedIn post from the last 6 months
- A specific repo they starred or contributed to
- A press article about their company's AI initiative

Examples of weak hooks (don't use) :
- "I saw you on LinkedIn"
- "Your company is doing innovative things in AI"
- Anything generated by an AI assistant without verifying the source
