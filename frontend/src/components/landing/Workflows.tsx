/**
 * Workflows — dark band positioned right under Features.
 *
 * Two-column band: copy on the left (eyebrow / title / lead / inline note)
 * and a vertical list of five suspending step types on the right. Sits on
 * the same dark canvas as Features, but with no top padding to chain
 * visually.
 */

import { Eyebrow } from './Eyebrow'

interface Step {
  n: string
  d: string
}

const WF: Step[] = [
  { n: 'elicit', d: 'Pause mid-flight for human input' },
  { n: 'wait_until', d: 'Clock-driven resume at a future time' },
  { n: 'wait_callback', d: 'HMAC-protected webhook resume' },
  { n: 'subcomposition', d: 'Call another composition, suspend until it ends' },
  { n: 'approval', d: 'Cross-user gate, four-eyes by default' },
]

export function Workflows() {
  return (
    <section
      className="landing-section dark"
      style={{
        background: 'var(--dark-bg)',
        color: 'var(--dark-ink)',
        paddingTop: 0,
      }}
    >
      <div className="container">
        <div
          className="grid grid-cols-1 lg:grid-cols-2 gap-10 lg:gap-16 items-start"
          style={{
            background: 'var(--dark-surface)',
            border: '1px solid var(--dark-line)',
            borderRadius: 22,
            padding: 'clamp(28px, 4vw, 56px)',
          }}
        >
          <div className="reveal">
            <Eyebrow>Durable workflows · Phase B-1</Eyebrow>
            <h2
              className="font-sans font-bold"
              style={{
                fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
                fontSize: 'clamp(28px, 3.6vw, 42px)',
                letterSpacing: '-0.025em',
                lineHeight: 1.08,
                color: '#fff',
                marginTop: 14,
              }}
            >
              Compositions that survive crashes &amp; restarts
            </h2>
            <p
              className="font-serif"
              style={{
                marginTop: 18,
                maxWidth: 460,
                fontSize: 16,
                lineHeight: 1.6,
                color: 'var(--dark-ink-2)',
              }}
            >
              A resumable executor persists every step in Postgres. Promote a validated composition
              and it becomes a first-class MCP tool. Five suspending step types pause and resume
              cleanly:
            </p>
            <p
              className="font-serif"
              style={{
                marginTop: 18,
                fontSize: 14,
                lineHeight: 1.6,
                color: 'var(--dark-ink-2)',
                opacity: 0.85,
              }}
            >
              Plus non-suspending steps{' '}
              <code
                className="font-mono"
                style={{
                  fontSize: 13,
                  padding: '2px 6px',
                  borderRadius: 4,
                  background: 'var(--dark-surface-2)',
                  color: 'var(--dark-ink)',
                }}
              >
                transform
              </code>{' '}
              (LLM JSON extraction) and{' '}
              <code
                className="font-mono"
                style={{
                  fontSize: 13,
                  padding: '2px 6px',
                  borderRadius: 4,
                  background: 'var(--dark-surface-2)',
                  color: 'var(--dark-ink)',
                }}
              >
                foreach
              </code>{' '}
              (fan-out over a list) — shipped in 2.5.
            </p>
          </div>

          <div className="reveal d2 flex flex-col gap-3">
            {WF.map((w, i) => (
              <div
                key={w.n}
                className="flex items-center gap-4"
                style={{
                  background: 'var(--dark-surface-2)',
                  border: '1px solid var(--dark-line)',
                  borderRadius: 14,
                  padding: '16px 18px',
                }}
              >
                <span
                  className="font-mono flex-none"
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: 'var(--accent)',
                    letterSpacing: '0.04em',
                    minWidth: 28,
                  }}
                >
                  {String(i + 1).padStart(2, '0')}
                </span>
                <code
                  className="font-mono"
                  style={{
                    fontSize: 14,
                    fontWeight: 600,
                    color: '#fff',
                    minWidth: 130,
                  }}
                >
                  {w.n}
                </code>
                <span
                  className="font-serif"
                  style={{
                    fontSize: 14,
                    lineHeight: 1.5,
                    color: 'var(--dark-ink-2)',
                  }}
                >
                  {w.d}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
