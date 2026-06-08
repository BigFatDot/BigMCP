/**
 * Nav — sticky top navigation for the landing.
 *
 * Transparent at the top of the page; once the user scrolls past 24px,
 * gains a blurred paper background and a hairline bottom border. Links
 * use anchor hrefs (no react-router), and the primary "Get started"
 * CTA points at /signup.
 */

import { useEffect, useState } from 'react'
import { BigMCPLogoWithText } from '@/components/brand/BigMCPLogo'

const SIGNUP_URL = '/signup'

const NAV_LINKS: { label: string; href: string }[] = [
  { label: 'Why', href: '#why' },
  { label: 'How', href: '#how' },
  { label: 'Features', href: '#features' },
  { label: 'Compare', href: '#compare' },
]

export function Nav() {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <nav
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 50,
        background: scrolled ? 'rgba(250, 248, 245, 0.82)' : 'transparent',
        borderBottom: scrolled ? '1px solid var(--line)' : '1px solid transparent',
        backdropFilter: scrolled ? 'saturate(180%) blur(16px)' : 'none',
        WebkitBackdropFilter: scrolled ? 'saturate(180%) blur(16px)' : 'none',
        transition: 'background .2s ease, border-color .2s ease',
      }}
    >
      <div
        className="container flex items-center justify-between"
        style={{ height: 64 }}
      >
        <a
          href="/"
          aria-label="BigMCP home"
          style={{ textDecoration: 'none', display: 'inline-flex' }}
        >
          <BigMCPLogoWithText size="sm" accentVar />
        </a>

        <div className="flex items-center gap-1 sm:gap-2">
          <div className="hidden md:flex items-center gap-1">
            {NAV_LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className="font-sans"
                style={{
                  fontSize: 14,
                  fontWeight: 500,
                  color: 'var(--ink-2)',
                  textDecoration: 'none',
                  padding: '8px 14px',
                  borderRadius: 8,
                  transition: 'color .15s ease, background .15s ease',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = 'var(--ink)'
                  e.currentTarget.style.background = 'var(--paper)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = 'var(--ink-2)'
                  e.currentTarget.style.background = 'transparent'
                }}
              >
                {l.label}
              </a>
            ))}
            <a
              href="/docs"
              className="font-sans"
              style={{
                fontSize: 14,
                fontWeight: 500,
                color: 'var(--ink-2)',
                textDecoration: 'none',
                padding: '8px 14px',
                borderRadius: 8,
              }}
            >
              Docs
            </a>
          </div>

          <a
            href={SIGNUP_URL}
            className="inline-flex items-center justify-center gap-1.5 rounded-lg font-sans font-semibold transition-all"
            style={{
              background: 'var(--accent)',
              color: '#fff',
              padding: '10px 18px',
              fontSize: 13.5,
              boxShadow: '0 6px 16px -8px rgba(var(--accent-rgb), 0.6)',
              textDecoration: 'none',
            }}
          >
            Get started
          </a>
        </div>
      </div>
    </nav>
  )
}
