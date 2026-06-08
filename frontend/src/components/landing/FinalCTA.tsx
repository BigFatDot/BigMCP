/**
 * FinalCTA — full-bleed accent band closing the landing.
 *
 * White-on-orange. Two CTAs (Star on GitHub / Try the demo) plus a small
 * meta line (AGPLv3 · Self-host · BYOL) in mono.
 */

const REPO_URL = 'https://github.com/BigFatDot/BigMCP'
const DEMO_URL = 'https://app.bigmcp.cloud'

/** Right arrow used inside CTAs. */
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

export function FinalCTA() {
  return (
    <section
      className="landing-section"
      id="start"
      style={{
        background: 'linear-gradient(135deg, var(--accent), var(--accent-600))',
        color: '#fff',
      }}
    >
      <div className="container">
        <div className="reveal flex flex-col items-center text-center gap-5 max-w-3xl mx-auto">
          <h2
            className="font-sans font-bold"
            style={{
              fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
              fontSize: 'clamp(32px, 4.8vw, 56px)',
              letterSpacing: '-0.03em',
              lineHeight: 1.05,
              color: '#fff',
            }}
          >
            One URL for every tool your agents need
          </h2>
          <p
            className="font-serif"
            style={{
              fontSize: 'clamp(16px, 1.5vw, 19px)',
              lineHeight: 1.55,
              color: 'rgba(255,255,255,0.9)',
              maxWidth: 620,
            }}
          >
            Free and open source under AGPLv3. No user limits, no license keys. Self-host in
            minutes or try the live demo.
          </p>

          <div className="flex flex-wrap items-center justify-center gap-3" style={{ marginTop: 12 }}>
            <a
              href={REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded-xl font-sans font-semibold transition-all"
              style={{
                background: '#fff',
                color: 'var(--accent-700)',
                padding: '15px 24px',
                fontSize: 15.5,
                boxShadow: '0 12px 32px -12px rgba(0,0,0,0.35)',
              }}
            >
              Star on GitHub
              <Arrow />
            </a>
            <a
              href={DEMO_URL}
              className="inline-flex items-center justify-center gap-2 rounded-xl font-sans font-semibold transition-all"
              style={{
                background: 'transparent',
                color: '#fff',
                padding: '14px 24px',
                fontSize: 15.5,
                border: '1.5px solid rgba(255,255,255,0.5)',
              }}
            >
              Try the demo
            </a>
          </div>

          <div
            className="font-mono"
            style={{
              marginTop: 16,
              fontSize: 12,
              letterSpacing: '0.08em',
              color: 'rgba(255,255,255,0.8)',
            }}
          >
            AGPLv3 &nbsp;·&nbsp; Self-host &nbsp;·&nbsp; BYOL
          </div>
        </div>
      </div>
    </section>
  )
}
