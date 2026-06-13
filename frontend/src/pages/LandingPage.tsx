/**
 * Landing Page — v2 redesign (Claude Design port)
 *
 * Marketing page for BigMCP Cloud SaaS. Sections live as standalone
 * components under `@/components/landing`. This page just wires them
 * together, owns the accent state (so the Branding section can recolor
 * the entire page live), and hooks up the scroll-reveal observer.
 *
 * Self-hosted deployments with custom branding still get the sober
 * SelfHostedLanding instead of the SaaS marketing pitch — that branch
 * is preserved as-is.
 */

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Nav,
  Hero,
  StatStrip,
  Problem,
  HowItWorks,
  Marketplace,
  Features,
  Workflows,
  Governance,
  Comparison,
  Branding,
  SelfHost,
  FinalCTA,
  Footer,
} from '@/components/landing'
import { usePageMeta } from '@/hooks/usePageMeta'
import { useBranding } from '@/contexts/BrandingContext'
import { useEdition } from '@/hooks/useAuth'
import { SelfHostedLandingPage } from './SelfHostedLanding'

// ── accent helpers ──────────────────────────────────────────────────────────
// Derive the full accent ramp from a single hex so picking a colour in the
// "Make it yours" section actually repaints the rest of the page.

function hexToRgb(h: string): [number, number, number] {
  let s = h.replace('#', '')
  if (s.length === 3) s = s.split('').map((c) => c + c).join('')
  return [
    parseInt(s.slice(0, 2), 16),
    parseInt(s.slice(2, 4), 16),
    parseInt(s.slice(4, 6), 16),
  ]
}

function mix(
  a: [number, number, number],
  b: [number, number, number],
  t: number,
): string {
  const m = (x: number, y: number) => Math.round(x + (y - x) * t)
  return `rgb(${m(a[0], b[0])}, ${m(a[1], b[1])}, ${m(a[2], b[2])})`
}

function applyAccent(hex: string): void {
  const rgb = hexToRgb(hex)
  const white: [number, number, number] = [255, 255, 255]
  const black: [number, number, number] = [0, 0, 0]
  const s = document.documentElement.style
  s.setProperty('--accent', hex)
  s.setProperty('--accent-rgb', rgb.join(', '))
  s.setProperty('--accent-600', mix(rgb, black, 0.14))
  s.setProperty('--accent-700', mix(rgb, black, 0.34))
  s.setProperty('--accent-200', mix(rgb, white, 0.62))
  s.setProperty('--accent-100', mix(rgb, white, 0.82))
  s.setProperty('--accent-50', mix(rgb, white, 0.92))
}

// ── scroll-reveal observer ─────────────────────────────────────────────────
// Add `.reveal` to any element that should fade in on scroll; this hook
// flips `.in` on the first time it enters the viewport, then forgets about
// it (the unobserve keeps the observer cheap on long pages).

function useScrollReveal(): void {
  useEffect(() => {
    const els = document.querySelectorAll<HTMLElement>('.reveal:not(.in)')
    if (!els.length) return
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add('in')
            io.unobserve(e.target)
          }
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -8% 0px' },
    )
    els.forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [])
}

// ── page ────────────────────────────────────────────────────────────────────

export function LandingPage() {
  const { t } = useTranslation('common')
  const { branding, isLoading: brandingLoading } = useBranding()
  const { isCloudSaaS, editionLoading } = useEdition()

  // Self-hosted + customized → sober welcome screen instead of the
  // SaaS marketing pitch. Wait for both signals so we don't flash the
  // wrong page on first paint.
  const isLoading = brandingLoading || editionLoading
  const shouldShowSelfHosted = !isLoading && !isCloudSaaS && branding.customized

  usePageMeta({
    title: shouldShowSelfHosted
      ? branding.instance_name
      : t('meta.landing.title'),
    description: shouldShowSelfHosted
      ? branding.instance_tagline
      : t('meta.landing.description'),
  })

  // Accent state — passed to Branding, repainted globally via applyAccent.
  // Hooks must precede any conditional return.
  const [accent, setAccent] = useState<string>('#D97757')
  useEffect(() => {
    applyAccent(accent)
  }, [accent])
  useScrollReveal()

  // Canonical: keep <link rel="canonical"> aligned with the URL Lighthouse /
  // search crawlers actually see. Without this, /welcome (SaaS landing route)
  // gets a canonical pointing to the root domain, which Lighthouse flags as
  // "Points to the domain's root URL instead of an equivalent page of content".
  useEffect(() => {
    const href = `${window.location.origin}${window.location.pathname}`
    let link = document.querySelector<HTMLLinkElement>('link[rel="canonical"]')
    const previous = link?.getAttribute('href') ?? null
    if (!link) {
      link = document.createElement('link')
      link.setAttribute('rel', 'canonical')
      document.head.appendChild(link)
    }
    link.setAttribute('href', href)
    return () => {
      if (link && previous !== null) link.setAttribute('href', previous)
    }
  }, [])

  if (shouldShowSelfHosted) {
    return <SelfHostedLandingPage />
  }

  return (
    <div className="min-h-screen" style={{ background: 'var(--paper)' }}>
      <Nav />
      <main>
        <Hero />
        <StatStrip />
        <Problem />
        <HowItWorks />
        <Marketplace />
        <Features />
        <Workflows />
        <Governance />
        <Comparison />
        <Branding accent={accent} onAccent={setAccent} />
        <SelfHost />
        <FinalCTA />
      </main>
      <Footer />
    </div>
  )
}
