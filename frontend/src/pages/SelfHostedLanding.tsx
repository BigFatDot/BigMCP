/**
 * Self-Hosted Landing Page
 *
 * The "this is YOUR instance" home screen. Rendered at `/` when:
 *   1. edition is not cloud_saas (i.e. self-hosted), AND
 *   2. branding.customized is true (admin has set at least one
 *      branding field), AND
 *   3. user is not authenticated yet (authed users land on /app).
 *
 * Sober, no marketing fluff. Logo + name + tagline + optional
 * markdown welcome message + two CTAs: Sign in (primary) and
 * Documentation (secondary). Footer carries the legal entity and
 * support email if provided. A small "Powered by BigMCP" line keeps
 * AGPLv3 attribution intact.
 */

import { Link } from 'react-router-dom'
import { ArrowRightIcon } from '@heroicons/react/24/outline'
import { Button } from '@/components/ui'
import { useBranding } from '@/contexts/BrandingContext'
import { InstanceLogo } from '@/components/brand/InstanceLogo'
import { usePageMeta } from '@/hooks/usePageMeta'


/** Very small markdown renderer: paragraphs + line breaks + inline
 *  links `[label](url)`. Intentionally minimal — we don't want to
 *  pull a full markdown lib for a 4KB welcome blurb. */
function renderMiniMarkdown(src: string): React.ReactNode {
  const paragraphs = src.split(/\n{2,}/)
  const linkRegex = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g
  return paragraphs.map((para, i) => {
    const lines = para.split('\n')
    return (
      <p key={i} className="text-gray-700 leading-relaxed mb-4 last:mb-0">
        {lines.map((line, j) => {
          const parts: React.ReactNode[] = []
          let lastIndex = 0
          let match: RegExpExecArray | null
          linkRegex.lastIndex = 0
          while ((match = linkRegex.exec(line)) !== null) {
            if (match.index > lastIndex) {
              parts.push(line.slice(lastIndex, match.index))
            }
            parts.push(
              <a
                key={`${j}-${match.index}`}
                href={match[2]}
                className="text-[color:var(--brand-primary,#D97757)] underline hover:opacity-80"
                rel="noreferrer"
              >
                {match[1]}
              </a>
            )
            lastIndex = match.index + match[0].length
          }
          if (lastIndex < line.length) {
            parts.push(line.slice(lastIndex))
          }
          return (
            <span key={j}>
              {parts}
              {j < lines.length - 1 && <br />}
            </span>
          )
        })}
      </p>
    )
  })
}


export function SelfHostedLandingPage() {
  const { branding } = useBranding()

  usePageMeta({
    title: branding.instance_name,
    description: branding.instance_tagline,
  })

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Slim top bar */}
      <nav className="bg-white border-b border-gray-200">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <InstanceLogo size="sm" />
            <span className="text-lg font-bold text-gray-900">
              {branding.instance_name}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <Link
              to="/docs"
              className="text-sm font-medium text-gray-700 hover:text-[color:var(--brand-primary,#D97757)] transition-colors"
            >
              Documentation
            </Link>
            <Link to="/login">
              <Button variant="primary" size="sm" className="rounded-md">
                Sign in
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <main className="flex-1 flex items-center justify-center px-6 py-16">
        <div className="max-w-2xl w-full text-center">
          <div className="flex justify-center mb-6">
            <InstanceLogo size="xl" />
          </div>
          <h1 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">
            {branding.instance_name}
          </h1>
          <p className="text-lg text-gray-600 font-serif mb-8">
            {branding.instance_tagline}
          </p>

          {branding.welcome_message && (
            <div className="text-left bg-white rounded-lg border border-gray-200 p-6 mb-8 max-w-xl mx-auto">
              {renderMiniMarkdown(branding.welcome_message)}
            </div>
          )}

          <div className="flex items-center justify-center gap-3">
            <Link to="/login">
              <Button variant="primary" size="lg" className="rounded-md">
                Sign in
                <ArrowRightIcon className="w-4 h-4" />
              </Button>
            </Link>
            <Link to="/docs">
              <Button variant="secondary" size="lg" className="rounded-md">
                Documentation
              </Button>
            </Link>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 bg-white">
        <div className="container mx-auto px-4 py-6 text-center text-xs text-gray-500 space-y-1">
          {(branding.legal_entity || branding.support_email) && (
            <div className="space-x-2">
              {branding.legal_entity && (
                <span>© {new Date().getFullYear()} {branding.legal_entity}</span>
              )}
              {branding.legal_entity && branding.support_email && <span>·</span>}
              {branding.support_email && (
                <a
                  href={`mailto:${branding.support_email}`}
                  className="hover:text-gray-700 underline"
                >
                  {branding.support_email}
                </a>
              )}
            </div>
          )}
          <div className="italic opacity-60">
            Powered by{' '}
            <a
              href="https://github.com/bigfatdot/bigmcp"
              target="_blank"
              rel="noreferrer"
              className="hover:opacity-100"
            >
              BigMCP
            </a>
          </div>
        </div>
      </footer>
    </div>
  )
}
