/**
 * Hero — landing page header section.
 *
 * Two-column layout: copy on the left (badge / display title / lead /
 * primary + outline CTAs / meta line) and the OrbitalGateway visual on the
 * right. Uses `.reveal` classes so a global IntersectionObserver can fade
 * each block in on scroll.
 */

import { OrbitalGateway } from './OrbitalGateway'

const REPO_URL = 'https://github.com/BigFatDot/BigMCP'
const SIGNUP_URL = '/signup'

/** Filled-currentColor star icon used inside the "Star on GitHub" CTA. */
function Star({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.8 6.1 20.5l1.2-6.5L2.5 9.4l6.6-.9z" />
    </svg>
  )
}

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

export function Hero() {
  return (
    <header className="landing-section relative overflow-hidden" id="top">
      {/* faint grid backdrop */}
      <div
        aria-hidden="true"
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage:
            'linear-gradient(rgba(217,119,87,.05) 1px, transparent 1px), linear-gradient(90deg, rgba(217,119,87,.05) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
          maskImage:
            'radial-gradient(ellipse at 50% 30%, #000 30%, transparent 75%)',
          WebkitMaskImage:
            'radial-gradient(ellipse at 50% 30%, #000 30%, transparent 75%)',
        }}
      />

      <div className="container relative">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          {/* Copy column */}
          <div>
            <div className="reveal in">
              <span
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full font-mono text-xs font-semibold"
                style={{
                  background: 'var(--accent-50)',
                  border: '1px solid var(--accent-200)',
                  color: 'var(--accent-700)',
                  letterSpacing: '.04em',
                }}
              >
                <span
                  className="animate-pulse-soft"
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: '50%',
                    background: 'var(--accent)',
                    boxShadow: '0 0 0 4px rgba(217,119,87,.18)',
                  }}
                />
                Open-source · Self-hosted · Sovereign
              </span>
            </div>

            <h1 className="landing-display reveal in d1" style={{ marginTop: 28 }}>
              All your MCP servers.
              <br />
              <span style={{ color: 'var(--accent)' }}>One</span> endpoint.
            </h1>

            <p className="landing-lead reveal in d2" style={{ maxWidth: 528, marginTop: 22 }}>
              Self-host an autonomous MCP gateway. Bring your own LLM, run fully offline (with a
              local LLM), and keep every byte on your infrastructure. AGPLv3.
            </p>

            <div
              className="reveal in d3"
              style={{ marginTop: 32, display: 'flex', flexWrap: 'wrap', gap: 12 }}
            >
              <a
                href={SIGNUP_URL}
                className="inline-flex items-center justify-center gap-2 rounded-xl font-sans font-semibold transition-all"
                style={{
                  background: 'var(--accent)',
                  color: '#fff',
                  padding: '14px 22px',
                  fontSize: 15,
                  boxShadow: 'var(--shadow-accent)',
                }}
              >
                Try BigMCP
                <Arrow />
              </a>
              <a
                href={REPO_URL}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex items-center justify-center gap-2 rounded-xl font-sans font-semibold transition-all"
                style={{
                  background: 'transparent',
                  color: 'var(--ink)',
                  padding: '13px 22px',
                  fontSize: 15,
                  border: '1.5px solid var(--line-2)',
                }}
              >
                <Star />
                Star on GitHub
              </a>
            </div>

            <div
              className="reveal in d4 font-mono"
              style={{
                marginTop: 28,
                display: 'inline-flex',
                alignItems: 'center',
                gap: 10,
                fontSize: 12,
                color: 'var(--ink-3)',
                letterSpacing: '.04em',
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: 'var(--accent)',
                  display: 'inline-block',
                }}
              />
              AGPLv3 &nbsp;·&nbsp; Bring your own LLM &nbsp;·&nbsp; Run fully offline (with a local LLM)
            </div>
          </div>

          {/* Visual column */}
          <div className="reveal in d2 flex items-center justify-center">
            <OrbitalGateway />
          </div>
        </div>
      </div>
    </header>
  )
}
