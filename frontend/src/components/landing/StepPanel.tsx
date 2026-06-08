/**
 * Mock catalogue / terminal / settings panels used as the right-hand preview
 * inside `HowItWorks`. Each `panel: PanelKind` value maps to a small static
 * illustration of what the actual product surface looks like at that step.
 *
 * Styling intentionally uses Tailwind + the landing CSS variables
 * (`var(--paper)`, `var(--surface)`, `var(--ink)`, `var(--line)`,
 * `var(--accent)`) rather than introducing a parallel `.mock-*` CSS layer.
 */

export type PanelKind =
  | 'signin'
  | 'pick'
  | 'register'
  | 'discover'
  | 'groups'
  | 'keys'
  | 'connect'

interface StepPanelProps {
  which: PanelKind
}

const MONO = "font-['JetBrains_Mono',ui-monospace,monospace]"

/** Tiny inline check mark, matches the rest of the landing's stroke weight. */
function Check({ size = 12, color = 'currentColor' }: { size?: number; color?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={3}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <polyline points="5 12 10 17 19 7" />
    </svg>
  )
}

/** Outer card frame shared by every "panel" mock. */
function MockFrame({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-2xl p-5 ${className}`}
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--line)',
        boxShadow: '0 1px 2px rgba(20,16,12,.04), 0 12px 32px -18px rgba(20,16,12,.18)',
      }}
    >
      {children}
    </div>
  )
}

function MockTitle({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="text-[13px] font-semibold mb-3"
      style={{ color: 'var(--ink)', letterSpacing: '-.005em' }}
    >
      {children}
    </div>
  )
}

function MockLabel({ children }: { children: React.ReactNode }) {
  return (
    <label
      className={`block ${MONO} text-[10px] uppercase tracking-[.14em] mt-3 mb-1.5`}
      style={{ color: 'var(--ink-3)' }}
    >
      {children}
    </label>
  )
}

function MockInput({ children }: { children: React.ReactNode }) {
  return (
    <div
      className={`${MONO} text-[12.5px] px-3 py-2 rounded-md`}
      style={{
        background: 'var(--paper)',
        border: '1px solid var(--line)',
        color: 'var(--ink)',
      }}
    >
      {children}
    </div>
  )
}

function MockGoButton({ children, block = false }: { children: React.ReactNode; block?: boolean }) {
  return (
    <span
      className={`inline-flex items-center justify-center text-[12.5px] font-semibold px-4 py-2 rounded-md ${
        block ? 'w-full' : ''
      }`}
      style={{
        background: 'var(--accent)',
        color: '#fff',
        letterSpacing: '-.005em',
      }}
    >
      {children}
    </span>
  )
}

/** Top "browser-like" bar used by terminal mocks (`discover`, `connect`). */
function TermBar({ label }: { label: string }) {
  return (
    <div
      className="flex items-center gap-2 px-3 py-2 rounded-t-2xl"
      style={{
        background: 'var(--paper)',
        borderBottom: '1px solid var(--line)',
      }}
    >
      <i className="h-2.5 w-2.5 rounded-full" style={{ background: '#E0625A' }} />
      <i className="h-2.5 w-2.5 rounded-full" style={{ background: '#E5B25E' }} />
      <i className="h-2.5 w-2.5 rounded-full" style={{ background: '#7CB985' }} />
      <span className={`${MONO} text-[11px] ml-2`} style={{ color: 'var(--ink-3)' }}>
        {label}
      </span>
    </div>
  )
}

export function StepPanel({ which }: StepPanelProps) {
  if (which === 'signin') {
    return (
      <MockFrame>
        <MockTitle>Sign in to AcmeMCP</MockTitle>
        <button
          type="button"
          className="w-full text-[13px] font-semibold px-4 py-2.5 rounded-md"
          style={{
            background: 'var(--ink)',
            color: '#fff',
            letterSpacing: '-.005em',
          }}
        >
          Continue with your SSO
        </button>
        <div className="flex items-center gap-3 my-4" aria-hidden>
          <span className="flex-1 h-px" style={{ background: 'var(--line)' }} />
          <span className={`${MONO} text-[10px] uppercase tracking-[.18em]`} style={{ color: 'var(--ink-3)' }}>
            or
          </span>
          <span className="flex-1 h-px" style={{ background: 'var(--line)' }} />
        </div>
        <MockLabel>Work email</MockLabel>
        <MockInput>you@acme.com</MockInput>
        <div className="mt-4">
          <MockGoButton block>Sign in</MockGoButton>
        </div>
      </MockFrame>
    )
  }

  if (which === 'pick') {
    const rows: Array<[string, string, boolean]> = [
      ['GitHub', 'create_pr', true],
      ['Linear', 'create_issue', true],
      ['Notion', 'search_pages', true],
      ['Slack', 'post_message', false],
      ['Postgres', 'run_query', true],
    ]
    return (
      <MockFrame>
        <MockTitle>Your catalogue</MockTitle>
        <ul className="flex flex-col gap-1.5">
          {rows.map(([s, t, on], i) => (
            <li
              key={i}
              className="flex items-center gap-3 px-3 py-2 rounded-md"
              style={{
                background: on ? 'var(--accent-50)' : 'var(--paper)',
                border: `1px solid ${on ? 'var(--accent-200)' : 'var(--line)'}`,
              }}
            >
              <span
                className="inline-flex items-center justify-center h-4 w-4 rounded-[4px] flex-none"
                style={{
                  background: on ? 'var(--accent)' : 'transparent',
                  border: `1.5px solid ${on ? 'var(--accent)' : 'var(--line-2)'}`,
                }}
              >
                {on ? <Check size={10} color="#fff" /> : null}
              </span>
              <span className="text-[12.5px]" style={{ color: 'var(--ink)' }}>
                <strong>{s}</strong>{' '}
                <span className={`${MONO} text-[11.5px]`} style={{ color: 'var(--ink-3)' }}>
                  {t}
                </span>
              </span>
            </li>
          ))}
        </ul>
        <p className="text-[11.5px] mt-3" style={{ color: 'var(--ink-3)' }}>
          You only see tools your admin assigned to your team.
        </p>
      </MockFrame>
    )
  }

  if (which === 'register') {
    const pills = ['npm', 'pip', 'GitHub', 'Docker', 'HTTP', 'binary']
    return (
      <MockFrame>
        <MockTitle>Add server to your registry</MockTitle>
        <div className="flex flex-wrap gap-1.5">
          {pills.map((s, i) => {
            const active = i === 2
            return (
              <span
                key={s}
                className={`${MONO} text-[11px] px-2 py-1 rounded-full`}
                style={{
                  background: active ? 'var(--accent)' : 'var(--paper)',
                  color: active ? '#fff' : 'var(--ink-2)',
                  border: `1px solid ${active ? 'var(--accent)' : 'var(--line)'}`,
                }}
              >
                {s}
              </span>
            )
          })}
        </div>
        <MockLabel>Repository</MockLabel>
        <MockInput>github.com/acme/internal-mcp</MockInput>
        <div className="mt-4">
          <MockGoButton>Register & discover</MockGoButton>
        </div>
      </MockFrame>
    )
  }

  if (which === 'discover') {
    return (
      <MockFrame className="!p-0 overflow-hidden">
        <TermBar label="tools/list" />
        <pre
          className={`${MONO} text-[12px] leading-[1.55] p-4 m-0 whitespace-pre`}
          style={{ color: 'var(--ink)', background: 'var(--surface)' }}
        >{`→ indexing acme/internal-mcp
✓ deploy_service        ✓ rollback
✓ query_metrics         ✓ tail_logs
✓ create_incident       ✓ ack_alert
✓ run_migration         ✓ scale_replicas
14 tools indexed · embeddings ready`}</pre>
      </MockFrame>
    )
  }

  if (which === 'groups') {
    const groups: Array<{ name: string; vis: string; color: string; tools: string[] }> = [
      {
        name: 'Dev Team',
        vis: 'ORG',
        color: '#5E6AD2',
        tools: ['deploy_service', 'tail_logs', 'query_metrics', 'run_migration'],
      },
      {
        name: 'Finance',
        vis: 'PRIVATE',
        color: '#2C8C6B',
        tools: ['grist_query', 'db_read', 'export_csv'],
      },
    ]
    return (
      <MockFrame>
        <MockTitle>Tool Groups</MockTitle>
        <div className="flex flex-col gap-3">
          {groups.map((g) => (
            <div
              key={g.name}
              className="rounded-lg p-3"
              style={{ background: 'var(--paper)', border: '1px solid var(--line)' }}
            >
              <div className="flex items-center gap-2 mb-2">
                <span
                  className="h-2.5 w-2.5 rounded-full flex-none"
                  style={{ background: g.color }}
                />
                <span className="text-[12.5px] font-semibold" style={{ color: 'var(--ink)' }}>
                  {g.name}
                </span>
                <span
                  className={`${MONO} text-[9.5px] ml-auto px-1.5 py-0.5 rounded uppercase tracking-[.14em]`}
                  style={{
                    background: 'var(--surface)',
                    color: 'var(--ink-3)',
                    border: '1px solid var(--line)',
                  }}
                >
                  {g.vis}
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {g.tools.map((x) => (
                  <span
                    key={x}
                    className={`${MONO} text-[11px] px-1.5 py-0.5 rounded`}
                    style={{
                      background: 'var(--surface)',
                      color: 'var(--ink-2)',
                      border: '1px solid var(--line)',
                    }}
                  >
                    {x}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </MockFrame>
    )
  }

  if (which === 'keys') {
    const onScopes = ['tools:read', 'tools:execute', 'servers:read']
    const offScopes = ['credentials:write', 'admin']
    return (
      <MockFrame>
        <MockTitle>API Keys</MockTitle>
        <div
          className="flex items-center justify-between px-3 py-2.5 rounded-md"
          style={{ background: 'var(--paper)', border: '1px solid var(--line)' }}
        >
          <span className="text-[12.5px] font-semibold" style={{ color: 'var(--ink)' }}>
            Dev Team · prod
          </span>
          <span className={`${MONO} text-[11.5px]`} style={{ color: 'var(--ink-2)' }}>
            bigmcp_sk_•••• 4f2a
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5 mt-3">
          {onScopes.map((s) => (
            <span
              key={s}
              className={`${MONO} text-[10.5px] px-1.5 py-1 rounded`}
              style={{
                background: 'var(--accent-50)',
                color: 'var(--accent-700)',
                border: '1px solid var(--accent-200)',
              }}
            >
              {s}
            </span>
          ))}
          {offScopes.map((s) => (
            <span
              key={s}
              className={`${MONO} text-[10.5px] px-1.5 py-1 rounded`}
              style={{
                background: 'var(--paper)',
                color: 'var(--ink-3)',
                border: '1px solid var(--line)',
              }}
            >
              {s}
            </span>
          ))}
        </div>
      </MockFrame>
    )
  }

  // connect
  return (
    <MockFrame className="!p-0 overflow-hidden">
      <TermBar label="claude_desktop_config.json" />
      <pre
        className={`${MONO} text-[12px] leading-[1.55] p-4 m-0 whitespace-pre`}
        style={{ color: 'var(--ink)', background: 'var(--surface)' }}
      >{`{
  "mcpServers": {
    "bigmcp": {
      "url": "https://acme.bigmcp.cloud/mcp/sse",
      "headers": {
        "Authorization": "Bearer bigmcp_sk_••••"
      }
    }
  }
}`}</pre>
    </MockFrame>
  )
}
