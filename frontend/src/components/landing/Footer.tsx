/**
 * Footer — dark four-column footer.
 *
 * Brand column: BigMCP wordmark + tagline + "Made with care" credit.
 * Three link columns (Product / Platform / Community) and a bottom row
 * with copyright + an MCP protocol fingerprint in mono.
 */

import { BigMCPLogoWithText } from '@/components/brand/BigMCPLogo'

interface FooterColumn {
  h: string
  links: { label: string; href: string }[]
}

const REPO_URL = 'https://github.com/BigFatDot/BigMCP'

const COLUMNS: FooterColumn[] = [
  {
    h: 'Product',
    links: [
      { label: 'Features', href: '#features' },
      { label: 'How it works', href: '#how' },
      { label: 'Marketplace', href: '#marketplace' },
      { label: 'Documentation', href: '/docs' },
    ],
  },
  {
    h: 'Platform',
    links: [
      { label: 'Self-hosting', href: '#selfhost' },
      { label: 'Security', href: '#governance' },
      { label: 'Compositions', href: '#compositions' },
      { label: 'API reference', href: '/docs' },
    ],
  },
  {
    h: 'Community',
    links: [
      { label: 'GitHub', href: REPO_URL },
      { label: 'Discussions', href: `${REPO_URL}/discussions` },
      { label: 'Issues', href: `${REPO_URL}/issues` },
      { label: 'License (AGPLv3)', href: `${REPO_URL}/blob/main/LICENSE` },
    ],
  },
]

export function Footer() {
  return (
    <footer
      style={{
        background: 'var(--dark-bg)',
        color: 'var(--dark-ink)',
        paddingTop: 80,
        paddingBottom: 32,
        borderTop: '1px solid var(--dark-line)',
      }}
    >
      <div className="container">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-10 lg:gap-12">
          {/* Brand column */}
          <div className="lg:col-span-1">
            <BigMCPLogoWithText variant="dark" />
            <p
              className="font-serif"
              style={{
                marginTop: 16,
                maxWidth: 320,
                fontSize: 14,
                lineHeight: 1.55,
                color: 'var(--dark-ink-2)',
              }}
            >
              Open-source MCP gateway for organizations. Register, govern, and expose your MCP
              services to your teams — with full control over who sees what.
            </p>
            <p
              style={{
                marginTop: 18,
                fontSize: 13.5,
                color: 'var(--ink-3)',
                fontFamily: "'Source Serif 4', Georgia, serif",
              }}
            >
              Made with care by{' '}
              <a
                href={REPO_URL}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  color: 'var(--accent)',
                  textDecoration: 'none',
                  fontWeight: 600,
                }}
              >
                BigFatDot
              </a>
            </p>
          </div>

          {COLUMNS.map((c) => (
            <div key={c.h}>
              <h4
                className="font-sans font-bold"
                style={{
                  fontSize: 13,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  color: '#fff',
                  marginBottom: 18,
                }}
              >
                {c.h}
              </h4>
              <ul className="flex flex-col gap-2.5">
                {c.links.map((l) => {
                  const external = l.href.startsWith('http')
                  return (
                    <li key={l.label}>
                      <a
                        href={l.href}
                        {...(external
                          ? { target: '_blank', rel: 'noopener noreferrer' }
                          : {})}
                        className="font-sans"
                        style={{
                          fontSize: 14,
                          color: 'var(--dark-ink-2)',
                          textDecoration: 'none',
                          transition: 'color .15s ease',
                        }}
                        onMouseEnter={(e) =>
                          (e.currentTarget.style.color = 'var(--accent)')
                        }
                        onMouseLeave={(e) =>
                          (e.currentTarget.style.color = 'var(--dark-ink-2)')
                        }
                      >
                        {l.label}
                      </a>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </div>

        <div
          className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
          style={{
            marginTop: 56,
            paddingTop: 24,
            borderTop: '1px solid var(--dark-line)',
            color: 'var(--ink-3)',
            fontSize: 12.5,
          }}
        >
          <span className="font-sans">© 2026 BigMCP · AGPLv3</span>
          <span
            className="font-mono"
            style={{
              letterSpacing: '0.04em',
              color: 'var(--dark-ink-2)',
            }}
          >
            MCP 2025-06-18 · Streamable HTTP + SSE
          </span>
        </div>
      </div>
    </footer>
  )
}
