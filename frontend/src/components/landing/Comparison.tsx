/**
 * Comparison — capability matrix.
 *
 * Eight rows across four axes (BigMCP / Anthropic Cloud / Closed SaaS / DIY).
 * Cells are colour-coded by content: the BigMCP column always reads as
 * "winning", explicit checks read positive, em-dashes read negative, and
 * everything else is treated as neutral context.
 */

import { Eyebrow } from './Eyebrow'

const COLS = ['BigMCP', 'Anthropic Cloud', 'Closed SaaS', 'DIY'] as const

type Row = [string, [string, string, string, string]]

const ROWS: Row[] = [
  ['Self-host (AGPLv3)', ['✓', '—', 'SaaS only', '✓']],
  ['Choose your own LLM (BYOL)', ['✓', 'Claude only', 'vendor lock-in', '✓']],
  ['Air-gap support', ['✓', '—', '—', 'depends']],
  ['Data residency control', ['full', 'vendor', 'vendor', 'full']],
  ['Custom MCP servers', ['unlimited', 'vendor catalogue', 'vendor', 'unlimited']],
  ['Built-in RBAC + audit', ['✓', 'partial', 'paid tier', 'build']],
  ['Durable workflows', ['✓ B-1', '—', 'paid tier', 'build']],
  ['No vendor lock-in', ['✓ AGPLv3', 'proprietary', 'proprietary', 'your code']],
]

type Tone = 'win' | 'yes' | 'no' | 'mid'

function tone(value: string, isFirstCol: boolean): Tone {
  if (isFirstCol) return 'win'
  if (value.startsWith('✓')) return 'yes'
  if (value === '—') return 'no'
  return 'mid'
}

function cellStyle(t: Tone): React.CSSProperties {
  switch (t) {
    case 'win':
      return {
        background: 'var(--accent-50)',
        color: 'var(--accent-700)',
        fontWeight: 600,
      }
    case 'yes':
      return { color: 'var(--ink)', fontWeight: 600 }
    case 'no':
      return { color: 'var(--ink-3)' }
    case 'mid':
    default:
      return { color: 'var(--ink-2)' }
  }
}

export function Comparison() {
  return (
    <section className="landing-section" id="compare" style={{ background: 'var(--paper)' }}>
      <div className="container">
        <div className="reveal flex flex-col items-center text-center gap-4 max-w-3xl mx-auto">
          <Eyebrow center>How we compare</Eyebrow>
          <h2
            className="font-sans font-bold"
            style={{
              fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
              fontSize: 'clamp(28px, 3.6vw, 42px)',
              letterSpacing: '-0.025em',
              lineHeight: 1.08,
              color: 'var(--ink)',
            }}
          >
            Compared, on the axes that matter to a sovereign deployment
          </h2>
          <p className="landing-lead">
            We don&apos;t claim to be the only answer. Where BigMCP is built to win is autonomy —
            you choose the LLM, you hold the data, and you run the infrastructure. No proprietary
            lock-in, no per-seat gate.
          </p>
        </div>

        <div
          className="reveal d1"
          style={{
            marginTop: 48,
            background: 'var(--surface)',
            border: '1px solid var(--line)',
            borderRadius: 18,
            overflow: 'hidden',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <div style={{ overflowX: 'auto' }}>
            <table
              style={{
                width: '100%',
                borderCollapse: 'collapse',
                minWidth: 720,
                fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
                fontSize: 14.5,
              }}
            >
              <thead>
                <tr>
                  <th
                    style={{
                      textAlign: 'left',
                      padding: '18px 22px',
                      fontWeight: 600,
                      fontSize: 12.5,
                      letterSpacing: '0.06em',
                      textTransform: 'uppercase',
                      color: 'var(--ink-3)',
                      background: 'var(--paper)',
                      borderBottom: '1px solid var(--line)',
                    }}
                  >
                    Capability
                  </th>
                  {COLS.map((c, i) => {
                    const us = i === 0
                    return (
                      <th
                        key={c}
                        style={{
                          textAlign: 'left',
                          padding: '18px 18px',
                          fontWeight: 700,
                          fontSize: 13.5,
                          color: us ? 'var(--accent-700)' : 'var(--ink-2)',
                          background: us ? 'var(--accent-50)' : 'var(--paper)',
                          borderBottom: `1px solid ${us ? 'var(--accent-200)' : 'var(--line)'}`,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {c}
                      </th>
                    )
                  })}
                </tr>
              </thead>
              <tbody>
                {ROWS.map((row, ri) => (
                  <tr key={row[0]}>
                    <td
                      style={{
                        padding: '16px 22px',
                        fontWeight: 600,
                        color: 'var(--ink)',
                        borderTop: ri === 0 ? 'none' : '1px solid var(--line)',
                        background: 'var(--surface)',
                      }}
                    >
                      {row[0]}
                    </td>
                    {row[1].map((v, ci) => {
                      const t = tone(v, ci === 0)
                      return (
                        <td
                          key={ci}
                          style={{
                            padding: '16px 18px',
                            borderTop: ri === 0 ? 'none' : '1px solid var(--line)',
                            whiteSpace: 'nowrap',
                            ...cellStyle(t),
                          }}
                        >
                          {v}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  )
}
