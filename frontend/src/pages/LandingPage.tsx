/**
 * Landing Page
 *
 * Marketing page for BigMCP Cloud SaaS.
 * Not shown on self-hosted deployments.
 */

import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowRightIcon, CheckIcon } from '@heroicons/react/24/outline'
import { Button } from '@/components/ui'
import { BigMCPLogo, BigMCPLogoWithText } from '@/components/brand/BigMCPLogo'
import { PhoneMockup } from '@/components/landing/PhoneMockup'
import { usePageMeta } from '@/hooks/usePageMeta'
import { useBranding } from '@/contexts/BrandingContext'
import { useEdition } from '@/hooks/useAuth'
import { SelfHostedLandingPage } from './SelfHostedLanding'

export function LandingPage() {
  const { t } = useTranslation('landing')
  const { branding, isLoading: brandingLoading } = useBranding()
  const { isCloudSaaS, editionLoading } = useEdition()

  // Self-hosted + customized → sober welcome screen instead of the
  // SaaS marketing pitch. Wait for both signals so we don't flash the
  // wrong page on first paint.
  const isLoading = brandingLoading || editionLoading
  const shouldShowSelfHosted = !isLoading && !isCloudSaaS && branding.customized

  // Hook calls must precede any conditional return — usePageMeta is
  // only meaningful for the SaaS variant since SelfHostedLandingPage
  // calls it itself.
  usePageMeta({
    title: shouldShowSelfHosted
      ? branding.instance_name
      : 'BigMCP - Unified MCP Server Gateway',
    description: shouldShowSelfHosted
      ? branding.instance_tagline
      : 'Connect, manage, and orchestrate all your MCP servers in one place. Natural language workflows with AI-powered composition.',
  })

  if (shouldShowSelfHosted) {
    return <SelfHostedLandingPage />
  }

  return (
    <div className="min-h-screen bg-white">
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 bg-white/90 backdrop-blur-lg z-50 border-b border-gray-100">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center hover:opacity-80 transition-opacity">
            <BigMCPLogoWithText size="sm" textSize="md" />
          </Link>

          <div className="hidden md:flex items-center gap-8">
            <a href="#features" className="text-gray-600 hover:text-orange transition-colors font-medium">
              {t('nav.features')}
            </a>
            <a href="#how-it-works" className="text-gray-600 hover:text-orange transition-colors font-medium">
              {t('nav.howItWorks')}
            </a>
            <Link to="/login" className="text-gray-600 hover:text-orange transition-colors font-medium">
              {t('nav.login')}
            </Link>
            <Link to="/signup">
              <Button variant="primary" size="sm" className="rounded-full px-6">
                {t('nav.getStarted')}
              </Button>
            </Link>
          </div>

          {/* Mobile-only: Documentation + Sign up */}
          <div className="flex md:hidden items-center gap-3">
            <Link to="/docs" className="text-sm font-medium text-gray-700 hover:text-orange transition-colors">
              {t('nav.docs', 'Documentation')}
            </Link>
            <Link to="/signup">
              <Button variant="primary" size="sm" className="rounded-full px-4">
                {t('nav.getStarted')}
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center justify-center pt-24 pb-16 px-6 overflow-hidden bg-gradient-to-b from-white to-gray-50">
        {/* Grid background */}
        <div className="absolute inset-0 opacity-30">
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: `
                linear-gradient(rgba(217, 119, 87, 0.05) 1px, transparent 1px),
                linear-gradient(90deg, rgba(217, 119, 87, 0.05) 1px, transparent 1px)
              `,
              backgroundSize: '60px 60px',
            }}
          />
        </div>

        <div className="relative z-10 max-w-4xl mx-auto text-center">
          {/* Logo */}
          <div className="mb-8 flex justify-center">
            <BigMCPLogo size="lg" animate />
          </div>

          {/* Badge */}
          <div className="inline-flex items-center gap-2 bg-orange-100 text-orange-700 px-4 py-1.5 rounded-full text-sm font-semibold mb-6">
            <div className="w-2 h-2 bg-orange rounded-full" />
            {t('hero.badge')}
          </div>

          {/* Headline */}
          <h1 className="text-4xl md:text-5xl lg:text-6xl font-extrabold text-gray-900 mb-6 leading-tight">
            {t('hero.title')} <span className="text-orange">{t('hero.titleHighlight')}</span>
            <br />{t('hero.titleEnd')}
          </h1>

          {/* Subtitle */}
          <p className="text-lg md:text-xl text-gray-600 mb-10 max-w-2xl mx-auto font-serif">
            {t('hero.subtitle')}
          </p>

          {/* CTAs */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a href="#airgap">
              <Button
                variant="primary"
                size="lg"
                className="rounded-full px-8 shadow-orange-lg"
                rightIcon={<ArrowRightIcon className="w-5 h-5" />}
              >
                {t('hero.cta')}
              </Button>
            </a>
            <Link to="/signup">
              <Button variant="outline" size="lg" className="rounded-full px-8">
                {t('hero.ctaSecondary')}
              </Button>
            </Link>
          </div>
          <div className="mt-6">
            <a
              href="https://github.com/BigFatDot/BigMCP"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-sm font-medium text-gray-600 hover:text-orange transition-colors"
            >
              <span>⭐</span>
              {t('hero.ctaTertiary')}
            </a>
          </div>
        </div>
      </section>

      {/* LLM Providers Section */}
      <section className="py-16 px-6 bg-white border-b border-gray-100">
        <div className="max-w-5xl mx-auto text-center">
          <div className="flex items-center justify-center gap-2 text-orange font-semibold text-sm uppercase tracking-wider mb-4">
            <div className="w-2 h-2 bg-orange rounded-full" />
            {t('providers.badge')}
          </div>
          <h2 className="text-2xl md:text-3xl font-extrabold text-gray-900 mb-4">
            {t('providers.title')}
          </h2>
          <p className="text-base text-gray-600 mb-10 max-w-3xl mx-auto font-serif">
            {t('providers.subtitle')}
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-3xl mx-auto">
            {(t('providers.items', { returnObjects: true }) as Array<{ name: string; tag: string }>).map((p, i) => (
              <div
                key={i}
                className="bg-gray-50 border border-gray-200 rounded-2xl px-4 py-5 flex flex-col items-center justify-center hover:border-orange transition-colors"
              >
                <span className="text-lg font-bold text-gray-900">{p.name}</span>
                <span className="text-xs uppercase tracking-wider text-orange font-semibold mt-1">{p.tag}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Air-gap Section */}
      <section id="airgap" className="py-24 px-6 bg-gray-900 text-white">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-12">
            <div className="flex items-center justify-center gap-2 text-orange font-semibold text-sm uppercase tracking-wider mb-4">
              <div className="w-2 h-2 bg-orange rounded-full" />
              {t('airgap.badge')}
            </div>
            <h2 className="text-3xl md:text-4xl font-extrabold mb-4">
              {t('airgap.title')}
            </h2>
            <p className="text-lg text-gray-300 max-w-3xl mx-auto font-serif">
              {t('airgap.description')}
            </p>
          </div>
          <div className="bg-gray-950 border border-gray-700 rounded-2xl overflow-hidden max-w-3xl mx-auto shadow-xl">
            <div className="px-4 py-2 bg-gray-800 border-b border-gray-700 text-xs font-mono text-gray-400">
              {t('airgap.snippetTitle')}
            </div>
            <pre className="p-6 text-sm font-mono text-gray-100 overflow-x-auto leading-relaxed"><code>{`LLM_API_URL=http://ollama:11434/v1
LLM_MODEL=llama3.1
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSION=768
AIRGAP_MODE=true`}</code></pre>
          </div>
          <p className="text-center text-sm text-gray-400 mt-6 max-w-2xl mx-auto font-serif">
            {t('airgap.verifyText')}{' '}
            <code className="px-2 py-0.5 bg-gray-800 rounded text-orange text-xs">{t('airgap.verifyCode')}</code>{' '}
            {t('airgap.verifyTail')}
          </p>
        </div>
      </section>

      {/* Mobile Demo Section */}
      <section className="py-24 px-6 bg-white">
        <div className="max-w-7xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-16 items-center">
            {/* Phone mockup */}
            <div className="flex justify-center lg:justify-start">
              <PhoneMockup />
            </div>

            {/* Content */}
            <div>
              <div className="flex items-center gap-2 text-orange font-semibold text-sm uppercase tracking-wider mb-4">
                <div className="w-2 h-2 bg-orange rounded-full" />
                {t('mobileDemo.badge')}
              </div>

              <h2 className="text-3xl md:text-4xl font-extrabold text-gray-900 mb-6">
                {t('mobileDemo.title')}
                <br />
                <span className="text-orange">{t('mobileDemo.titleHighlight')}</span>
              </h2>

              <p className="text-lg text-gray-600 mb-8 font-serif leading-relaxed">
                {t('mobileDemo.description')}
              </p>

              <ul className="space-y-4">
                {(t('mobileDemo.features', { returnObjects: true }) as string[]).map((item: string, i: number) => (
                  <li key={i} className="flex items-start gap-3 text-gray-700">
                    <span className="text-orange font-bold mt-0.5">→</span>
                    <span className="font-medium">{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* Problem/Solution Section */}
      <section className="py-24 px-6 bg-gray-50">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <div className="flex items-center justify-center gap-2 text-orange font-semibold text-sm uppercase tracking-wider mb-4">
              <div className="w-2 h-2 bg-orange rounded-full" />
              {t('challenge.badge')}
            </div>
            <h2 className="text-3xl md:text-4xl font-extrabold text-gray-900 mb-4">
              {t('challenge.title')}
            </h2>
            <p className="text-lg text-gray-600 max-w-2xl mx-auto font-serif">
              {t('challenge.subtitle')}
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-8">
            {/* Problem */}
            <div className="bg-white border-2 border-gray-200 rounded-3xl p-8 transition-all hover:-translate-y-2 hover:shadow-xl">
              <div className="w-14 h-14 bg-gray-800 rounded-full mb-6" />
              <h3 className="text-2xl font-bold text-gray-900 mb-6">{t('challenge.withoutTitle')}</h3>
              <ul className="space-y-4">
                {(t('challenge.withoutItems', { returnObjects: true }) as string[]).map((item: string, i: number) => (
                  <li key={i} className="flex items-start gap-3 text-gray-600">
                    <span className="text-gray-400 text-xl leading-none">×</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Solution */}
            <div className="bg-orange-50 border-2 border-orange rounded-3xl p-8 transition-all hover:-translate-y-2 hover:shadow-orange-lg">
              <div className="w-14 h-14 bg-orange rounded-full mb-6 animate-pulse" />
              <h3 className="text-2xl font-bold text-gray-900 mb-6">{t('challenge.withTitle')}</h3>
              <ul className="space-y-4">
                {(t('challenge.withItems', { returnObjects: true }) as string[]).map((item: string, i: number) => (
                  <li key={i} className="flex items-start gap-3 text-gray-700">
                    <CheckIcon className="w-5 h-5 text-orange flex-shrink-0 mt-0.5" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* How It Works Section */}
      <section id="how-it-works" className="py-24 px-6 bg-white">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <div className="flex items-center justify-center gap-2 text-orange font-semibold text-sm uppercase tracking-wider mb-4">
              <div className="w-2 h-2 bg-orange rounded-full" />
              {t('howItWorks.badge')}
            </div>
            <h2 className="text-3xl md:text-4xl font-extrabold text-gray-900 mb-4">
              {t('howItWorks.title')}
            </h2>
            <p className="text-lg text-gray-600 max-w-2xl mx-auto font-serif">
              {t('howItWorks.subtitle')}
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            {(t('howItWorks.steps', { returnObjects: true }) as Array<{ title: string; description: string }>).map((item, index) => (
              <div key={index} className="text-center">
                <div className="w-20 h-20 bg-orange rounded-full flex items-center justify-center text-white text-3xl font-extrabold mx-auto mb-6 shadow-orange-lg transition-transform hover:scale-110">
                  {index + 1}
                </div>
                <h3 className="text-xl font-bold text-gray-900 mb-3">{item.title}</h3>
                <p className="text-gray-600 font-serif leading-relaxed">{item.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Comparison Section */}
      <section id="comparison" className="py-24 px-6 bg-gray-50">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-12">
            <div className="flex items-center justify-center gap-2 text-orange font-semibold text-sm uppercase tracking-wider mb-4">
              <div className="w-2 h-2 bg-orange rounded-full" />
              How We Compare
            </div>
            <h2 className="text-3xl md:text-4xl font-extrabold text-gray-900 mb-4">
              BigMCP vs the alternatives
            </h2>
            <p className="text-lg text-gray-600 max-w-3xl mx-auto font-serif">
              Honest comparison. BigMCP isn't always the answer — but if you're aggregating
              many MCP servers behind one URL with org-level governance and durable workflows,
              it's purpose-built for that.
            </p>
          </div>

          <div className="overflow-x-auto bg-white rounded-2xl shadow-sm border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left py-4 px-6 font-semibold text-gray-700">Capability</th>
                  <th className="text-center py-4 px-4 font-semibold text-orange">BigMCP</th>
                  <th className="text-center py-4 px-4 font-semibold text-gray-600">n8n</th>
                  <th className="text-center py-4 px-4 font-semibold text-gray-600">Composio</th>
                  <th className="text-center py-4 px-4 font-semibold text-gray-600">LangGraph</th>
                  <th className="text-center py-4 px-4 font-semibold text-gray-600">Roll your own</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                <tr>
                  <td className="py-3 px-6 text-gray-700 font-medium">MCP-native gateway</td>
                  <td className="text-center py-3 px-4 text-orange font-bold">✓</td>
                  <td className="text-center py-3 px-4 text-gray-400">—</td>
                  <td className="text-center py-3 px-4 text-gray-600">partial</td>
                  <td className="text-center py-3 px-4 text-gray-400">—</td>
                  <td className="text-center py-3 px-4 text-gray-400">build</td>
                </tr>
                <tr>
                  <td className="py-3 px-6 text-gray-700 font-medium">Aggregate 180+ servers behind one URL</td>
                  <td className="text-center py-3 px-4 text-orange font-bold">✓</td>
                  <td className="text-center py-3 px-4 text-gray-400">—</td>
                  <td className="text-center py-3 px-4 text-gray-600">~150 tools</td>
                  <td className="text-center py-3 px-4 text-gray-400">—</td>
                  <td className="text-center py-3 px-4 text-gray-400">build</td>
                </tr>
                <tr>
                  <td className="py-3 px-6 text-gray-700 font-medium">Durable suspending workflows (Postgres state)</td>
                  <td className="text-center py-3 px-4 text-orange font-bold">✓ B-1</td>
                  <td className="text-center py-3 px-4 text-gray-600">via webhooks</td>
                  <td className="text-center py-3 px-4 text-gray-400">—</td>
                  <td className="text-center py-3 px-4 text-orange font-bold">✓</td>
                  <td className="text-center py-3 px-4 text-gray-400">build</td>
                </tr>
                <tr>
                  <td className="py-3 px-6 text-gray-700 font-medium">Org-level RBAC (4 roles + scoped API keys)</td>
                  <td className="text-center py-3 px-4 text-orange font-bold">✓</td>
                  <td className="text-center py-3 px-4 text-gray-600">paid only</td>
                  <td className="text-center py-3 px-4 text-gray-600">basic</td>
                  <td className="text-center py-3 px-4 text-gray-400">—</td>
                  <td className="text-center py-3 px-4 text-gray-400">build</td>
                </tr>
                <tr>
                  <td className="py-3 px-6 text-gray-700 font-medium">Audit log with HMAC integrity</td>
                  <td className="text-center py-3 px-4 text-orange font-bold">✓</td>
                  <td className="text-center py-3 px-4 text-gray-600">paid only</td>
                  <td className="text-center py-3 px-4 text-gray-400">—</td>
                  <td className="text-center py-3 px-4 text-gray-400">—</td>
                  <td className="text-center py-3 px-4 text-gray-400">build</td>
                </tr>
                <tr>
                  <td className="py-3 px-6 text-gray-700 font-medium">Self-host fully free (AGPLv3)</td>
                  <td className="text-center py-3 px-4 text-orange font-bold">✓</td>
                  <td className="text-center py-3 px-4 text-orange font-bold">✓</td>
                  <td className="text-center py-3 px-4 text-gray-400">SaaS only</td>
                  <td className="text-center py-3 px-4 text-orange font-bold">✓</td>
                  <td className="text-center py-3 px-4 text-orange font-bold">✓</td>
                </tr>
                <tr>
                  <td className="py-3 px-6 text-gray-700 font-medium">Visual workflow editor</td>
                  <td className="text-center py-3 px-4 text-gray-600">JSON + LLM</td>
                  <td className="text-center py-3 px-4 text-orange font-bold">✓ best-in-class</td>
                  <td className="text-center py-3 px-4 text-gray-400">—</td>
                  <td className="text-center py-3 px-4 text-gray-400">code-only</td>
                  <td className="text-center py-3 px-4 text-gray-400">—</td>
                </tr>
                <tr>
                  <td className="py-3 px-6 text-gray-700 font-medium">Per-org marketplace curation</td>
                  <td className="text-center py-3 px-4 text-orange font-bold">✓</td>
                  <td className="text-center py-3 px-4 text-gray-400">—</td>
                  <td className="text-center py-3 px-4 text-gray-600">single global</td>
                  <td className="text-center py-3 px-4 text-gray-400">—</td>
                  <td className="text-center py-3 px-4 text-gray-400">build</td>
                </tr>
                <tr>
                  <td className="py-3 px-6 text-gray-700 font-medium">Single MCP URL across clients (Claude, Cursor, n8n, …)</td>
                  <td className="text-center py-3 px-4 text-orange font-bold">✓</td>
                  <td className="text-center py-3 px-4 text-gray-400">—</td>
                  <td className="text-center py-3 px-4 text-gray-600">SDK per language</td>
                  <td className="text-center py-3 px-4 text-gray-400">—</td>
                  <td className="text-center py-3 px-4 text-gray-400">build</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="mt-8 grid md:grid-cols-2 gap-6 max-w-4xl mx-auto">
            <div className="p-5 rounded-lg bg-white border border-gray-200">
              <p className="font-semibold text-gray-900 mb-2">When BigMCP is the right answer</p>
              <p className="text-sm text-gray-600 font-serif leading-relaxed">
                You have 5+ MCP servers (internal or third-party), multiple teams,
                and you want one URL with org RBAC + audit + durable workflows.
              </p>
            </div>
            <div className="p-5 rounded-lg bg-white border border-gray-200">
              <p className="font-semibold text-gray-900 mb-2">When it's overkill</p>
              <p className="text-sm text-gray-600 font-serif leading-relaxed">
                Solo dev with 1–2 MCP servers. Native config in Claude Desktop or
                Cursor is simpler. Come back when your team grows or compliance
                lands on your desk.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="py-24 px-6 bg-gray-900 text-white">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <div className="flex items-center justify-center gap-2 text-orange font-semibold text-sm uppercase tracking-wider mb-4">
              <div className="w-2 h-2 bg-orange rounded-full" />
              {t('features.badge')}
            </div>
            <h2 className="text-3xl md:text-4xl font-extrabold mb-4">
              {t('features.title')}
              <br />{t('features.titleEnd')}
            </h2>
            <p className="text-lg text-gray-400 max-w-2xl mx-auto font-serif">
              {t('features.subtitle')}
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            {(t('features.items', { returnObjects: true }) as Array<{ title: string; description: string }>).map((feature, i) => (
              <div
                key={i}
                className="bg-gray-800 border border-gray-700 rounded-2xl p-8 transition-all hover:border-orange hover:-translate-y-2 hover:shadow-2xl group"
              >
                <div className="w-14 h-14 bg-orange rounded-full mb-6 transition-transform group-hover:scale-110" />
                <h3 className="text-xl font-bold mb-3">{feature.title}</h3>
                <p className="text-gray-400 font-serif leading-relaxed">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* For Organizations Section */}
      <section id="orgs" className="py-24 px-6 bg-gray-50">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <div className="flex items-center justify-center gap-2 text-orange font-semibold text-sm uppercase tracking-wider mb-4">
              <div className="w-2 h-2 bg-orange rounded-full" />
              {t('orgs.badge')}
            </div>
            <h2 className="text-3xl md:text-4xl font-extrabold text-gray-900 mb-4">
              {t('orgs.title')}
            </h2>
            <p className="text-lg text-gray-600 max-w-2xl mx-auto font-serif">
              {t('orgs.subtitle')}
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            {(t('orgs.items', { returnObjects: true }) as Array<{ icon: string; title: string; description: string }>).map((item, i) => (
              <div
                key={i}
                className="bg-white border border-gray-200 rounded-2xl p-6 hover:border-orange transition-colors"
              >
                <div className="text-3xl mb-3">{item.icon}</div>
                <h3 className="text-base font-bold text-gray-900 mb-2">{item.title}</h3>
                <p className="text-sm text-gray-600 font-serif leading-relaxed">{item.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Community Section */}
      <section id="community" className="py-20 px-6 bg-gray-900 text-white">
        <div className="max-w-5xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-orange/20 text-orange text-xs font-semibold uppercase tracking-wider mb-4">
            <span className="w-1.5 h-1.5 bg-orange rounded-full animate-pulse" />
            {t('community.badge')}
          </div>
          <h2 className="text-3xl md:text-4xl font-extrabold mb-4">
            {t('community.title')}
          </h2>
          <p className="text-lg text-gray-300 mb-10 font-serif max-w-2xl mx-auto">
            {t('community.subtitle')}
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            {(t('community.links', { returnObjects: true }) as Array<{ icon: string; label: string; url: string }>).map((link, i) => (
              <a
                key={i}
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-4 py-2.5 bg-gray-800 hover:bg-gray-700 border border-gray-700 hover:border-orange rounded-full text-sm font-medium transition-colors"
              >
                <span>{link.icon}</span>
                <span>{link.label}</span>
              </a>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-24 px-6 bg-orange text-white">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl md:text-4xl font-extrabold mb-4">
            {t('finalCta.title')}
          </h2>
          <p className="text-lg text-white/90 mb-10 font-serif">
            {t('finalCta.subtitle')}
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a href="https://github.com/BigFatDot/BigMCP" target="_blank" rel="noopener noreferrer">
              <Button
                variant="secondary"
                size="lg"
                className="rounded-full px-8 bg-white text-orange-700 hover:bg-gray-100"
                rightIcon={<ArrowRightIcon className="w-5 h-5" />}
              >
                {t('finalCta.cta')}
              </Button>
            </a>
            <Link to="/signup">
              <Button
                variant="outline"
                size="lg"
                className="rounded-full px-8 border-white text-white hover:bg-white/10"
              >
                {t('finalCta.ctaSecondary')}
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-900 text-gray-400 py-16 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="grid md:grid-cols-4 gap-12 mb-12">
            {/* Brand */}
            <div className="md:col-span-2">
              <BigMCPLogoWithText size="sm" variant="dark" className="mb-4" />
              <p className="font-serif leading-relaxed mb-4">
                {t('footer.tagline')}
              </p>
              <p className="text-sm text-gray-500">
                {t('footer.madeBy')} <a href="https://bigfatdot.org" className="text-orange hover:text-white">BigFatDot</a>
              </p>
            </div>

            {/* Product */}
            <div>
              <h4 className="text-white font-bold text-sm uppercase tracking-wider mb-4">{t('footer.product')}</h4>
              <ul className="space-y-2">
                <li><a href="#features" className="hover:text-orange transition-colors">{t('footer.links.features')}</a></li>
                <li><a href="#how-it-works" className="hover:text-orange transition-colors">{t('footer.links.howItWorks')}</a></li>
                <li><Link to="/docs" className="hover:text-orange transition-colors">{t('footer.links.documentation')}</Link></li>
              </ul>
            </div>

            {/* Community */}
            <div>
              <h4 className="text-white font-bold text-sm uppercase tracking-wider mb-4">{t('footer.community')}</h4>
              <ul className="space-y-2">
                <li><a href="https://github.com/BigFatDot/BigMCP" target="_blank" rel="noopener noreferrer" className="hover:text-orange transition-colors">{t('footer.links.github')}</a></li>
                <li><a href="https://github.com/BigFatDot/BigMCP/discussions" target="_blank" rel="noopener noreferrer" className="hover:text-orange transition-colors">{t('footer.links.discussions')}</a></li>
                <li><a href="https://github.com/BigFatDot/BigMCP/issues" target="_blank" rel="noopener noreferrer" className="hover:text-orange transition-colors">{t('footer.links.issues')}</a></li>
                <li><a href="https://github.com/BigFatDot/BigMCP/blob/main/LICENSE" target="_blank" rel="noopener noreferrer" className="hover:text-orange transition-colors">{t('footer.links.license')}</a></li>
                <li><a href="https://bigfatdot.org" className="hover:text-orange transition-colors">{t('footer.links.about')}</a></li>
              </ul>
            </div>
          </div>

          <div className="border-t border-gray-800 pt-8 text-center text-sm">
            <p>{t('footer.copyright')}</p>
          </div>
        </div>
      </footer>
    </div>
  )
}

