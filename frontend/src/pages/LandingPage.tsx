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

export function LandingPage() {
  const { t } = useTranslation('landing')

  usePageMeta({
    title: 'BigMCP - Unified MCP Server Gateway',
    description: 'Connect, manage, and orchestrate all your MCP servers in one place. Natural language workflows with AI-powered composition.',
  })

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
            <a href="#pricing" className="text-gray-600 hover:text-orange transition-colors font-medium">
              {t('nav.pricing')}
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
            <Link to="/signup">
              <Button
                variant="primary"
                size="lg"
                className="rounded-full px-8 shadow-orange-lg"
                rightIcon={<ArrowRightIcon className="w-5 h-5" />}
              >
                {t('hero.cta')}
              </Button>
            </Link>
            <a href="#how-it-works">
              <Button variant="outline" size="lg" className="rounded-full px-8">
                {t('hero.ctaSecondary')}
              </Button>
            </a>
          </div>
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

      {/* Pricing Section */}
      <section id="pricing" className="py-24 px-6 bg-gray-50">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <div className="flex items-center justify-center gap-2 text-orange font-semibold text-sm uppercase tracking-wider mb-4">
              <div className="w-2 h-2 bg-orange rounded-full" />
              {t('pricing.badge')}
            </div>
            <h2 className="text-3xl md:text-4xl font-extrabold text-gray-900 mb-4">
              {t('pricing.title')}
            </h2>
            <p className="text-lg text-gray-600 max-w-2xl mx-auto font-serif">
              {t('pricing.subtitle')}
            </p>
          </div>

          {/* Cloud vs Self-hosted toggle info */}
          <div className="flex justify-center gap-4 mb-12">
            <span className="inline-flex items-center gap-2 px-4 py-2 bg-blue-100 text-blue-800 rounded-full text-sm font-medium">
              {t('pricing.cloudLabel')}
            </span>
            <span className="inline-flex items-center gap-2 px-4 py-2 bg-purple-100 text-purple-800 rounded-full text-sm font-medium">
              {t('pricing.selfHostedLabel')}
            </span>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 max-w-6xl mx-auto">
            {/* Cloud Individual */}
            <PricingCard
              title={t('pricing.individual.title')}
              subtitle={t('pricing.individual.subtitle')}
              price={t('pricing.individual.price')}
              period={t('pricing.individual.period')}
              features={t('pricing.individual.features', { returnObjects: true }) as string[]}
              ctaText={t('pricing.individual.cta')}
              ctaLink="/signup"
            />

            {/* Cloud Team - Featured */}
            <PricingCard
              title={t('pricing.team.title')}
              subtitle={t('pricing.team.subtitle')}
              price={t('pricing.team.price')}
              period={t('pricing.team.period')}
              featured
              badge={t('pricing.team.badge')}
              features={t('pricing.team.features', { returnObjects: true }) as string[]}
              ctaText={t('pricing.team.cta')}
              ctaLink="/signup"
            />

            {/* Self-hosted Enterprise */}
            <PricingCard
              title={t('pricing.enterprise.title')}
              subtitle={t('pricing.enterprise.subtitle')}
              price={t('pricing.enterprise.price')}
              period={t('pricing.enterprise.period')}
              features={t('pricing.enterprise.features', { returnObjects: true }) as string[]}
              ctaText={t('pricing.enterprise.cta')}
              ctaLink="/app/subscription"
            />

            {/* Self-hosted Community */}
            <PricingCard
              title={t('pricing.community.title')}
              subtitle={t('pricing.community.subtitle')}
              price={t('pricing.community.price')}
              period={t('pricing.community.period')}
              features={t('pricing.community.features', { returnObjects: true }) as string[]}
              ctaText={t('pricing.community.cta')}
              ctaLink="https://github.com/bigfatdot/BigMCP"
            />
          </div>

          {/* Edition explanation */}
          <div className="mt-12 text-center">
            <p className="text-sm text-gray-500 max-w-2xl mx-auto">
              {t('pricing.note')}
            </p>
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
          <Link to="/signup">
            <Button
              variant="secondary"
              size="lg"
              className="rounded-full px-8 bg-white text-orange-700 hover:bg-gray-100"
              rightIcon={<ArrowRightIcon className="w-5 h-5" />}
            >
              {t('finalCta.cta')}
            </Button>
          </Link>
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
                <li><a href="#pricing" className="hover:text-orange transition-colors">{t('footer.links.pricing')}</a></li>
                <li><Link to="/docs" className="hover:text-orange transition-colors">{t('footer.links.documentation')}</Link></li>
              </ul>
            </div>

            {/* Company */}
            <div>
              <h4 className="text-white font-bold text-sm uppercase tracking-wider mb-4">{t('footer.company')}</h4>
              <ul className="space-y-2">
                <li><a href="https://bigfatdot.org" className="hover:text-orange transition-colors">{t('footer.links.about')}</a></li>
                <li><a href="mailto:contact@bigmcp.cloud" className="hover:text-orange transition-colors">{t('footer.links.contact')}</a></li>
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

function PricingCard({
  title,
  subtitle,
  price,
  period,
  features,
  ctaText,
  ctaLink,
  featured = false,
  badge,
  comingSoon = false,
  comingSoonLabel = 'Coming Soon',
}: {
  title: string
  subtitle?: string
  price: string
  period: string
  features: string[]
  ctaText: string
  ctaLink: string
  featured?: boolean
  badge?: string
  comingSoon?: boolean
  comingSoonLabel?: string
}) {
  const isMailtoLink = ctaLink.startsWith('mailto:')

  return (
    <div
      className={`
        bg-white rounded-3xl p-6 text-center transition-all hover:-translate-y-2 relative
        ${featured
          ? 'border-3 border-orange shadow-orange-lg scale-105'
          : comingSoon
          ? 'border-2 border-gray-200 opacity-90'
          : 'border-2 border-gray-200 hover:border-orange hover:shadow-xl'
        }
      `}
    >
      {comingSoon && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-gray-600 text-white text-xs font-bold uppercase rounded-full">
          {comingSoonLabel}
        </div>
      )}
      {badge && !comingSoon && (
        <span className="inline-block bg-orange text-white text-xs font-bold uppercase px-3 py-1 rounded-full mb-4">
          {badge}
        </span>
      )}
      {subtitle && (
        <span className={`inline-block text-xs font-medium uppercase px-2 py-1 rounded mb-2 ${
          subtitle === 'Cloud' ? 'bg-blue-100 text-blue-700' : 'bg-purple-100 text-purple-700'
        }`}>
          {subtitle}
        </span>
      )}
      <h3 className="text-xl font-bold text-gray-900 mb-2">{title}</h3>
      <div className={`text-3xl font-extrabold my-4 ${comingSoon ? 'text-gray-400' : 'text-orange'}`}>
        {price}
        <span className="text-sm font-normal text-gray-600"> {period}</span>
      </div>
      <ul className="text-left space-y-3 mb-8">
        {features.map((feature, i) => (
          <li key={i} className={`flex items-center gap-3 ${comingSoon ? 'text-gray-500' : 'text-gray-700'}`}>
            <div className={`w-4 h-4 rounded-full flex-shrink-0 ${comingSoon ? 'bg-gray-300' : 'bg-orange'}`} />
            <span>{feature}</span>
          </li>
        ))}
      </ul>
      {isMailtoLink ? (
        <a href={ctaLink} className="block">
          <Button
            variant={comingSoon ? 'secondary' : featured ? 'primary' : 'outline'}
            className="w-full rounded-full"
          >
            {ctaText}
          </Button>
        </a>
      ) : (
        <Link to={ctaLink} className="block">
          <Button
            variant={featured ? 'primary' : 'outline'}
            className="w-full rounded-full"
          >
            {ctaText}
          </Button>
        </Link>
      )}
    </div>
  )
}
