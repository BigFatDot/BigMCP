/**
 * Features — dark-section 6-card grid.
 *
 * Inline SVG icons via `FIcon` (six glyph keys). Each card stands on a dark
 * elevated surface; staggered `.reveal` delays cycle 1/2/3 across the grid.
 */

import { Eyebrow } from './Eyebrow'

type IconName = 'server' | 'shield' | 'lock' | 'building' | 'grid' | 'flow'

interface Feature {
  t: string
  d: string
  i: IconName
}

const FEATURES: Feature[] = [
  {
    t: 'Custom server management',
    d: 'Register from any source — npm, pip, GitHub, Docker, HTTP, local binary. Auto-discovery via tools/list. Team vs personal visibility.',
    i: 'server',
  },
  {
    t: 'Selective exposure',
    d: 'Tool Groups with PRIVATE / ORG / PUBLIC visibility, plus scoped API keys exposing only the tools you choose.',
    i: 'shield',
  },
  {
    t: 'Auth & security',
    d: 'OAuth 2.0 + PKCE, JWT, MFA/TOTP, API keys (bcrypt), credentials encrypted at rest with Fernet.',
    i: 'lock',
  },
  {
    t: 'Multi-tenant by design',
    d: 'Organization isolation with 4-tier RBAC and hierarchical credentials. Unlimited users and orgs.',
    i: 'building',
  },
  {
    t: 'Custom MCP registry',
    d: 'Declare your private MCP servers and keep them entirely inside your network. Air-gap compatible, full sovereignty.',
    i: 'grid',
  },
  {
    t: 'AI orchestration',
    d: 'Natural language to workflow, a composition lifecycle, and durable steps that survive crashes and restarts.',
    i: 'flow',
  },
]

/** Stroke-based glyph for each feature card. 24×24, currentColor. */
function FIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, JSX.Element> = {
    server: (
      <>
        <rect x="3" y="4" width="18" height="7" rx="2" />
        <rect x="3" y="13" width="18" height="7" rx="2" />
        <path d="M7 7.5h.01M7 16.5h.01" />
      </>
    ),
    shield: (
      <>
        <path d="M12 3l7 3v5c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6z" />
        <path d="M9.5 12l1.8 1.8L15 10" />
      </>
    ),
    lock: (
      <>
        <rect x="4" y="10" width="16" height="10" rx="2" />
        <path d="M8 10V7a4 4 0 0 1 8 0v3" />
      </>
    ),
    building: (
      <>
        <rect x="4" y="3" width="16" height="18" rx="2" />
        <path d="M8 7h.01M12 7h.01M16 7h.01M8 11h.01M12 11h.01M16 11h.01M10 21v-4h4v4" />
      </>
    ),
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" />
        <rect x="14" y="14" width="7" height="7" rx="1.5" />
      </>
    ),
    flow: (
      <>
        <circle cx="6" cy="6" r="2.5" />
        <circle cx="18" cy="12" r="2.5" />
        <circle cx="6" cy="18" r="2.5" />
        <path d="M8.2 7.2L15.8 11M8.2 16.8L15.8 13" />
      </>
    ),
  }
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  )
}

export function Features() {
  return (
    <section
      className="landing-section dark"
      id="features"
      style={{ background: 'var(--dark-bg)', color: 'var(--dark-ink)' }}
    >
      <div className="container">
        <div className="reveal flex flex-col items-center text-center gap-4 max-w-3xl mx-auto">
          <Eyebrow center>Platform</Eyebrow>
          <h2
            className="font-sans font-bold"
            style={{
              fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
              fontSize: 'clamp(32px, 4.6vw, 52px)',
              letterSpacing: '-0.025em',
              lineHeight: 1.05,
              color: '#fff',
            }}
          >
            Everything a team needs to run MCP in production
          </h2>
        </div>

        <div
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 lg:gap-6"
          style={{ marginTop: 64 }}
        >
          {FEATURES.map((f, i) => (
            <div
              key={f.t}
              className={`reveal d${(i % 3) + 1}`}
              style={{
                background: 'var(--dark-surface)',
                border: '1px solid var(--dark-line)',
                borderRadius: 18,
                padding: 28,
              }}
            >
              <span
                className="inline-flex items-center justify-center rounded-xl"
                style={{
                  width: 44,
                  height: 44,
                  background: 'rgba(var(--accent-rgb), 0.14)',
                  color: 'var(--accent)',
                  marginBottom: 18,
                }}
              >
                <FIcon name={f.i} />
              </span>
              <h3
                className="font-sans font-bold"
                style={{
                  fontSize: 19,
                  letterSpacing: '-0.01em',
                  color: '#fff',
                  marginBottom: 10,
                }}
              >
                {f.t}
              </h3>
              <p
                className="font-serif"
                style={{
                  fontSize: 14.5,
                  lineHeight: 1.55,
                  color: 'var(--dark-ink-2)',
                }}
              >
                {f.d}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
