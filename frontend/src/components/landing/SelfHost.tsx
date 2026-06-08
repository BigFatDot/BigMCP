/**
 * SelfHost — sovereignty section pairing copy with the NetworkBoundary
 * schematic.
 *
 * Two columns: lead copy + a "Configuration guide" CTA pointing at the
 * self-hosting docs on GitHub, and the NetworkBoundary diagram on the
 * right.
 */

import { Eyebrow } from './Eyebrow'
import { NetworkBoundary } from './NetworkBoundary'

const SELFHOST_DOC_URL = 'https://github.com/BigFatDot/BigMCP#self-hosted-deployment'

/** Right arrow used inside the primary CTA. */
function Arrow({ size = 18 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  )
}

export function SelfHost() {
  return (
    <section className="landing-section" id="selfhost">
      <div className="container">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          <div className="reveal">
            <Eyebrow>Sovereign by default</Eyebrow>
            <h2
              className="font-sans font-bold"
              style={{
                fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
                fontSize: 'clamp(28px, 3.6vw, 42px)',
                letterSpacing: '-0.025em',
                lineHeight: 1.08,
                color: 'var(--ink)',
                marginTop: 14,
              }}
            >
              Nothing leaves your network
            </h2>
            <p className="landing-lead" style={{ marginTop: 18 }}>
              Self-host BigMCP with your own LLM. Everything else stays inside your network. Built
              for sensitive data, regulated industries, and sovereign deployments.
            </p>
            <div style={{ marginTop: 28 }}>
              <a
                href={SELFHOST_DOC_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center gap-2 rounded-xl font-sans font-semibold transition-all"
                style={{
                  background: 'var(--accent)',
                  color: '#fff',
                  padding: '14px 22px',
                  fontSize: 15,
                  boxShadow: 'var(--shadow-accent)',
                }}
              >
                Configuration guide
                <Arrow />
              </a>
            </div>
          </div>

          <div className="reveal d2">
            <NetworkBoundary />
          </div>
        </div>
      </div>
    </section>
  )
}
