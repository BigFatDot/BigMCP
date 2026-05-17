# Prospect shortlist worksheet

Goal : **5 first-touch mails** sent this week, tracked, follow-up scheduled.

## Step 1 — Define the ICP (Ideal Customer Profile)

Fill in once. Re-read before each prospect entry to stay disciplined.

| Dimension | Constraint |
|-----------|------------|
| **Org size** | 20–500 employees (small enough to decide fast, big enough to have an actual MCP problem) |
| **Tech maturity** | At least 1 internal API or DB; familiar with Docker / docker-compose |
| **AI tool adoption** | At least one team using Claude / Cursor / Continue.dev / similar |
| **Pain trigger** | Multiple teams asking for similar MCP integrations OR a credentials sprawl complaint OR a compliance ask for audit logs |
| **Decision authority** | Persona has budget + technical credibility (not just a champion) |
| **Geography** | EU first (data residency aligned with self-host pitch) |
| **NOT a fit** | Solo devs, 1-2 MCP servers, no internal infra team, hard SaaS-only mandate |

## Step 2 — Where to find them

Don't cold-scrape LinkedIn. Mine ONE high-signal source per session :

- ✅ **Speakers at recent events** : PlatformCon, KubeCon EU, DevoxxFR, Hack la Commune, Anthropic Builder Day, etc.
- ✅ **Authors of relevant blog posts / Substack / LinkedIn posts** in the last 90 days about MCP, internal AI tooling, AI platform
- ✅ **Company AI job postings** (Head of AI Platform, MLOps, AI Infrastructure) — signals they're investing
- ✅ **Open-source contributors** to MCP-adjacent projects (mcp-go, FastMCP, server-* repos)
- ✅ **Public sector tech leads** with a published track record (Etalab, Cerema, Onepoint, Insee, France Travail, ANSSI...)
- ✅ **Mid-size tech companies you've personally encountered** (your network, a vendor you bought from, a startup you advised)

Anti-pattern : LinkedIn Sales Navigator "everyone with title X". 0% conversion.

## Step 3 — Fill in this table

Pick 5. Quality > quantity. Each row gets a real personalised hook.

| # | Name | Org | Title | Persona variant (A/B/C) | Hook (real, ≤ 1 sentence) | Email | Sent date | Reply ? |
|---|------|-----|-------|--------------------------|----------------------------|-------|-----------|---------|
| 1 |      |     |       |                          |                            |       |           |         |
| 2 |      |     |       |                          |                            |       |           |         |
| 3 |      |     |       |                          |                            |       |           |         |
| 4 |      |     |       |                          |                            |       |           |         |
| 5 |      |     |       |                          |                            |       |           |         |

> **Hook examples that work** :
> - "your DevoxxFR talk on internal Claude deployments"
> - "your team's job posting for an MLOps engineer with MCP experience"
> - "your GitHub PR adding scope claims to mcp-go"
> - "your LinkedIn post from May 2 about credentials sprawl"
>
> **Hook examples that DON'T work** :
> - "your impressive work at {{Company}}"
> - "I saw your profile on LinkedIn"
> - "I noticed {{Company}} is innovative in AI"

## Step 4 — Send

For each prospect :

1. Open `MAIL_TEMPLATES.md`, pick the variant matching column "Persona"
2. Replace `{{first_name}}`, `{{contextual_hook}}` — DO NOT skip the hook
3. Send via your normal mail client (not a "campaign tool" — those land in spam folders for cold outreach)
4. Log the send in the table above

> Send ALL 5 in one sitting, not spread across days. Why : you'll be in the same headspace = consistent tone. Spread across days = drift in copy = harder to A/B.

## Step 5 — Follow up

Mark D+5 and D+12 in your calendar for each mail.

Follow-up template (D+5) :
```
Hi {{first_name}},

Bumping this in case it got buried. Worth 15 min to see if BigMCP is a fit for {{company}} ?

If not now, no worries — happy to circle back in 6 months when context changes.

Cheers,
Nicolas
```

Final follow-up (D+12) — only if you have NEW info :
```
Hi {{first_name}},

Last bump from me. Just shipped {{specific feature relevant to them}} — thought you'd want to know given {{the hook from your first mail}}.

If MCP gateway isn't on your radar this quarter, no problem — I'll close the thread on my side.

Best,
Nicolas
```

## Step 6 — Debrief after the first 5

After 25 days (D+12 of the 5th send), do a 30-min self-review :

- Reply rate ? (Target : 1-2 out of 5 = healthy for cold)
- Which subject line / hook converted best ?
- Which persona variant got the most engagement ?
- What objection came up that the mail didn't address ?

Refine the templates accordingly. Then send the NEXT 5.

## Common questions to anticipate

**"What does it cost?"**
→ It's free. AGPLv3. The Early Adopter Program is also free. (The honest version : eventually we may offer paid support tier for non-early-adopters, but you're early, so it's all free for you.)

**"Can we evaluate without deploying?"**
→ Yes — bigmcp.cloud has a live demo, full features, persistent account. 15-min screen-share also works.

**"What about GDPR / data residency?"**
→ Self-host = your data, your servers, your residency. The encryption keys + JWT secret live in your env. We don't ingest anything from your deploy.

**"Why should we trust a project with no logos?"**
→ Fair. That's why the Early Adopter Program exists — direct line to the maintainer, prioritised everything, no fee. You're not betting on a roadmap, you're getting a personal commitment.

**"What if you stop maintaining it?"**
→ AGPLv3 open source. Fork it, dump the DB, you have a runnable system forever. No proprietary format.

---

## Tracking dashboard (lightweight)

If you want a dashboard, the minimum :

```
Outreach send log
=================
2026-MM-DD  | A | Marie X      | Cerema    | "article Acteurs Publics" | sent | -
2026-MM-DD  | B | David Y      | Doctolib  | "PlatformCon talk"        | sent | replied D+2
2026-MM-DD  | B | Sandra Z     | Algolia   | "GitHub mcp-go PR"        | sent | -
2026-MM-DD  | C | Karim A      | Mistral   | "tweet about MCP scale"   | sent | -
2026-MM-DD  | A | Lisa B       | Etalab    | "DINUM newsletter"        | sent | -

Replies received : 1 / 5 (20%)
Demos booked    : 1 / 5 (20%)
Deploys started : 0 / 5 (0%)
```

That's all. Excel / Google Sheet / Notion table — pick what's already in your stack.

---

## Final note

The single highest-leverage activity in this whole process is **2 minutes of research per prospect** before sending. Skip that and you're spam. Do it consistently and your reply rate doubles.

Three rules :
1. **One specific hook per mail** (not generic)
2. **One specific ask** ("15 min" not "let me know")
3. **Three touches max** then move on

Good luck.
