/**
 * Problem — "Without BigMCP" vs "With BigMCP" comparison.
 *
 * Two-card grid: the "off" card lists the pain points of running a
 * scattered MCP setup; the accent card lists how BigMCP collapses it
 * into one governed gateway.
 */

import { Eyebrow } from './Eyebrow'

const WITHOUT = [
  'Install & update MCP servers on every device',
  'Configure credentials separately, everywhere',
  'No access control over who runs which tool',
  'Zero visibility into who used what, when',
  'Re-do the whole setup for each new teammate',
]

const WITH = [
  'One governed endpoint for every connected tool',
  'Credentials encrypted at rest (Fernet) — User › Org › Server',
  'RBAC across 4 roles, scoped per Tool Group',
  'Immutable, HMAC-signed audit logs',
  'Self-hosted: your infrastructure, your rules',
]

/** Thin × icon used to mark "without" bullets. */
function Cross({ size = 14 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  )
}

/** Tick icon used to mark "with" bullets. */
function Check({ size = 14, color }: { size?: number; color?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color ?? 'currentColor'}
      strokeWidth="2.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M20 6 9 17l-5-5" />
    </svg>
  )
}

export function Problem() {
  return (
    <section className="landing-section" id="why">
      <div className="container">
        <div className="reveal max-w-3xl mx-auto text-center flex flex-col items-center gap-4">
          <Eyebrow center>The MCP sprawl problem</Eyebrow>
          <h2
            className="landing-display"
            style={{
              fontSize: 'clamp(32px, 4.6vw, 52px)',
              lineHeight: 1.05,
            }}
          >
            Every server, every device, every credential
          </h2>
          <p className="landing-lead">
            As soon as a team adopts more than a couple of MCP servers, configuration sprawl and
            access risk explode. BigMCP collapses it into one governed gateway you run yourself.
          </p>
        </div>

        <div
          className="grid grid-cols-1 md:grid-cols-2 gap-6 lg:gap-8"
          style={{ marginTop: 56 }}
        >
          {/* Without card */}
          <div
            className="reveal d1"
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--line)',
              borderRadius: 20,
              padding: 32,
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <div className="flex items-center gap-3" style={{ marginBottom: 20 }}>
              <span
                className="flex items-center justify-center rounded-full"
                style={{
                  width: 36,
                  height: 36,
                  background: 'var(--line)',
                  color: 'var(--ink-2)',
                }}
              >
                <Cross size={16} />
              </span>
              <h3
                className="font-sans font-bold"
                style={{
                  fontSize: 22,
                  color: 'var(--ink)',
                  letterSpacing: '-0.01em',
                }}
              >
                Without BigMCP
              </h3>
            </div>
            <ul className="flex flex-col gap-3">
              {WITHOUT.map((x, i) => (
                <li
                  key={i}
                  className="flex items-start gap-3 font-serif"
                  style={{ fontSize: 15, color: 'var(--ink-3)', lineHeight: 1.55 }}
                >
                  <span
                    className="flex items-center justify-center flex-none"
                    style={{
                      width: 20,
                      height: 20,
                      borderRadius: '50%',
                      background: 'var(--line)',
                      color: 'var(--ink-3)',
                      marginTop: 2,
                    }}
                  >
                    <Cross size={11} />
                  </span>
                  <span>{x}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* With BigMCP — accent card */}
          <div
            className="reveal d2"
            style={{
              background: 'linear-gradient(180deg, var(--accent-50), var(--surface) 70%)',
              border: '1px solid var(--accent-200)',
              borderRadius: 20,
              padding: 32,
              boxShadow: 'var(--shadow-md)',
            }}
          >
            <div className="flex items-center gap-3" style={{ marginBottom: 20 }}>
              <span
                className="flex items-center justify-center rounded-full"
                style={{
                  width: 36,
                  height: 36,
                  background: 'var(--accent)',
                  color: '#fff',
                  boxShadow: '0 6px 16px -6px rgba(217,119,87,.55)',
                }}
              >
                <Check size={18} color="#fff" />
              </span>
              <h3
                className="font-sans font-bold"
                style={{
                  fontSize: 22,
                  color: 'var(--ink)',
                  letterSpacing: '-0.01em',
                }}
              >
                With BigMCP
              </h3>
            </div>
            <ul className="flex flex-col gap-3">
              {WITH.map((x, i) => (
                <li
                  key={i}
                  className="flex items-start gap-3 font-serif"
                  style={{ fontSize: 15, color: 'var(--ink)', lineHeight: 1.55 }}
                >
                  <span
                    className="flex items-center justify-center flex-none"
                    style={{
                      width: 20,
                      height: 20,
                      borderRadius: '50%',
                      background: 'var(--accent-100)',
                      color: 'var(--accent-700)',
                      marginTop: 2,
                    }}
                  >
                    <Check size={12} />
                  </span>
                  <span>{x}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  )
}
