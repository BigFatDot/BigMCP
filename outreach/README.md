# Outreach kit

Materials for the Early Adopter Program outreach campaign. Designed to
ship a small batch of personalised cold mails to qualified prospects,
track replies, follow up disciplined.

## Files

| File | Purpose |
|------|---------|
| [MAIL_TEMPLATES.md](MAIL_TEMPLATES.md) | 3 mail variants (DSI, head of platform, AI ops lead) + cadence + anti-patterns |
| [DECK.md](DECK.md) | 5-slide pitch in markdown (renderable via Slidev / Marp / copy-paste into Google Slides) + speaker notes |
| [PROSPECT_WORKSHEET.md](PROSPECT_WORKSHEET.md) | ICP definition + sourcing strategy + 5-row send table + follow-up templates |

## Workflow

1. Read `PROSPECT_WORKSHEET.md` once — internalise the ICP.
2. Spend 30-60 min sourcing 5 real prospects with real hooks.
3. Open `MAIL_TEMPLATES.md`, pick the matching persona variant per prospect.
4. Send all 5 in one sitting. Log in your tracker.
5. Calendar D+5 and D+12 follow-ups.
6. After 25 days, debrief : reply rate, what converted, what to refine.
7. Send the next 5.

The pitch deck (`DECK.md`) is for the FOLLOW-UP call once a prospect
replies and books 15 min. Don't attach it to the cold mail — link to
`bigmcp.cloud` and `github.com/bigfatdot/BigMCP` instead.

## Renderable deck

```bash
# Slidev (interactive, best for live demo)
npx slidev outreach/DECK.md --remote

# Marp (sober PDF)
marp outreach/DECK.md --pdf

# Or just open in any markdown viewer
```

## What this kit is NOT

- A SaaS marketing campaign — this is **direct outreach** to 5 named
  humans you've researched, not a "drip campaign" to 500 unqualified
  emails.
- A pitch deck for fundraising — the deck is sized for a 15-min
  evaluator call, not a 45-min VC meeting.
- A substitute for product — if BigMCP isn't actually ready for these
  prospects, no copy will save the conversation. The Day 1 + Day 2-3
  audit work (see `.ui-tour/prospect-audit.md`) was to make sure
  product IS ready before sending.

## When you're past the first 5 deploys

The Early Adopter Program by definition runs out after 5 deploys. After
that, the framing shifts :

- Mail templates → less "we're seeking adopters", more "here's the case
  study from Acme Corp"
- Deck slide 5 → replace "Early Adopter Program" with concrete pricing /
  support tier
- Worksheet → ICP narrows based on which of the 5 first deploys actually
  generated value

Keep this kit updated as the project matures. Don't ossify the cold mail
when you've evolved to warm referrals.
