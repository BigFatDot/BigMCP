/**
 * Three illustrative use-case cards rendered under the marketplace marquee.
 * Kept as a standalone component for reuse and to keep `Marketplace.tsx`
 * focused on the marquee layout.
 */

interface UseCase {
  tag: string
  t: string
  d: string
}

const USE_CASES: UseCase[] = [
  {
    tag: 'Starter pack',
    t: 'Connect public servers in one click',
    d: 'Add Gmail, Linear, Notion or Slack straight from the curated starter pack — credentials auto-detected.',
  },
  {
    tag: 'Custom',
    t: 'Build custom tools on your stack',
    d: "Wire BigMCP to Grist, Airtable, a Notion database or your internal API. Ship custom MCP tools for your team's widgets — tasks, projects, dashboards.",
  },
  {
    tag: 'Sovereign',
    t: 'Run fully sovereign',
    d: 'Your private registry only, a local LLM (Ollama, vLLM), and air-gap mode on. Nothing leaves your network.',
  },
]

export function UseCases() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
      {USE_CASES.map((u, i) => (
        <article
          key={u.tag}
          className={`reveal d${i + 1} rounded-2xl p-6 flex flex-col gap-3 transition-shadow hover:shadow-md`}
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--line)',
          }}
        >
          <span
            className="self-start font-['JetBrains_Mono',ui-monospace,monospace] text-[10.5px] uppercase tracking-[.16em] px-2 py-1 rounded-full"
            style={{
              background: 'var(--accent-50)',
              color: 'var(--accent-700)',
              border: '1px solid var(--accent-200)',
            }}
          >
            {u.tag}
          </span>
          <h3
            className="font-semibold tracking-[-.01em]"
            style={{
              fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
              fontSize: '20px',
              lineHeight: 1.2,
              color: 'var(--ink)',
            }}
          >
            {u.t}
          </h3>
          <p
            className="text-[14.5px] leading-[1.55]"
            style={{
              color: 'var(--ink-2)',
              fontFamily: "'Source Serif 4', Georgia, serif",
            }}
          >
            {u.d}
          </p>
        </article>
      ))}
    </div>
  )
}
