/**
 * Subscription Page
 *
 * Displays subscription status, usage metrics, billing management,
 * and Enterprise licenses for self-hosted deployments.
 * Integrates with LemonSqueezy for payment processing.
 */

import { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  CreditCardIcon,
  ChartBarIcon,
  ArrowUpIcon,
  CheckCircleIcon,
  KeyIcon,
  ClipboardDocumentIcon,
  BuildingOfficeIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline'
import { Button, Card } from '@/components/ui'
import { cn } from '@/utils/cn'
import { useSubscription, useEdition } from '@/hooks/useAuth'
import { apiClient, licensesApi } from '@/services/marketplace'
import type { License, PublicSectorEligibility, EditionLicenseInfo } from '@/types/auth'

interface UsageMetric {
  name: string
  current: number
  limit: number | null
  unit: string
}

interface UsageResponse {
  connected_servers: number
  tool_executions: number
  compositions: number
  team_members: number
  max_team_members: number
}

const PLANS = [
  {
    id: 'individual',
    name: 'Individual',
    subtitle: 'Cloud',
    price: '4,99€',
    period: '/month',
    features: [
      'Unlimited MCP servers',
      'AI-powered orchestration',
      'Semantic search',
      'Unlimited compositions',
      'Managed LLM included',
    ],
  },
  {
    id: 'team',
    name: 'Team',
    subtitle: 'Cloud',
    price: '4,99€',
    period: '/month + €4.99/user',
    features: [
      'Everything in Individual',
      'Team collaboration',
      'Shared credentials',
      'Role-based access control',
      'Advanced audit logs',
    ],
    popular: true,
  },
]

// Enterprise plan (separate - one-time purchase for self-hosted)
const ENTERPRISE_PLAN = {
  id: 'enterprise',
  name: 'Enterprise',
  subtitle: 'Self-Hosted',
  price: 'Free',
  period: 'launch offer • 3 months',
  features: [
    'Unlimited users',
    'SSO / SAML authentication (Coming Soon)',
    'Full audit logs',
    'Custom branding',
    'Priority support',
    'Dedicated infrastructure',
    'API access',
    'Perpetual license',
  ],
}

// SaaS platform URL for license purchases
const SAAS_URL = 'https://app.bigmcp.cloud'

// ============================================================================
// Edition-Specific Components
// ============================================================================

/**
 * Enterprise Edition: Shows installed license information.
 * Displayed when running self-hosted with a valid LICENSE_KEY JWT.
 * No billing UI needed - license is perpetual.
 */
function EnterpriseLicenseSection({ license }: { license: EditionLicenseInfo }) {
  const { t } = useTranslation('settings')
  return (
    <Card padding="lg" className="mb-6 border-purple-200 bg-gradient-to-br from-purple-50 to-white">
      <div className="flex items-start gap-4">
        <div className="w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center flex-shrink-0">
          <ShieldCheckIcon className="w-6 h-6 text-purple-600" />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-block text-xs font-medium uppercase px-2 py-1 rounded bg-purple-100 text-purple-700">
              {t('account.license.enterprise.badge')}
            </span>
            <span className="inline-block text-xs font-medium px-2 py-1 rounded bg-green-100 text-green-700">
              {t('account.license.enterprise.active')}
            </span>
          </div>
          <h3 className="text-xl font-bold text-gray-900">{license.organization}</h3>
          <p className="text-sm text-gray-600 mt-1">
            {t('subscription.enterprise.perpetualLicense')}
          </p>

          {/* Licensed Features */}
          {license.features && license.features.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-medium text-gray-500 uppercase mb-2">{t('subscription.enterprise.licensedFeatures')}</p>
              <div className="flex flex-wrap gap-2">
                {license.features.map((feature) => (
                  <span
                    key={feature}
                    className="px-2 py-1 bg-purple-50 text-purple-700 rounded text-xs flex items-center gap-1"
                  >
                    <CheckCircleIcon className="w-3 h-3" />
                    {feature.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Benefits Summary */}
          <div className="mt-4 pt-4 border-t border-purple-100">
            <ul className="grid md:grid-cols-2 gap-2">
              {(t('subscription.plans.enterprise.features', { returnObjects: true }) as string[]).slice(0, 6).map((feature, idx) => (
                <li key={idx} className="flex items-center gap-2 text-sm text-gray-600">
                  <CheckCircleIcon className="w-4 h-4 text-purple-500 flex-shrink-0" />
                  {feature}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </Card>
  )
}

/**
 * Community Edition: Shows current features and upgrade path.
 * Displayed when running self-hosted without a license (free tier).
 * Links to SaaS platform for Enterprise license purchase.
 */
function CommunityUpgradeSection() {
  const { t } = useTranslation('settings')
  return (
    <Card padding="lg" className="mb-6 border-gray-200">
      <div className="flex items-start gap-4">
        <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center flex-shrink-0">
          <BuildingOfficeIcon className="w-6 h-6 text-gray-600" />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-block text-xs font-medium uppercase px-2 py-1 rounded bg-gray-100 text-gray-700">
              {t('subscription.community.title')}
            </span>
          </div>
          <h3 className="text-xl font-bold text-gray-900">{t('subscription.community.singleUser')}</h3>
          <p className="text-sm text-gray-600 mt-1">
            {t('subscription.community.subtitle')}
          </p>

          {/* Current Features */}
          <div className="mt-4 p-3 bg-gray-50 rounded-lg">
            <p className="text-xs font-medium text-gray-500 uppercase mb-2">{t('subscription.community.included')}</p>
            <ul className="grid md:grid-cols-2 gap-2">
              <li className="flex items-center gap-2 text-sm text-gray-600">
                <CheckCircleIcon className="w-4 h-4 text-green-500 flex-shrink-0" />
                {t('subscription.community.marketplaceAccess')}
              </li>
              <li className="flex items-center gap-2 text-sm text-gray-600">
                <CheckCircleIcon className="w-4 h-4 text-green-500 flex-shrink-0" />
                {t('subscription.community.mcpServerManagement')}
              </li>
              <li className="flex items-center gap-2 text-sm text-gray-600">
                <CheckCircleIcon className="w-4 h-4 text-green-500 flex-shrink-0" />
                {t('subscription.community.aiOrchestration')}
              </li>
              <li className="flex items-center gap-2 text-sm text-gray-600">
                <CheckCircleIcon className="w-4 h-4 text-green-500 flex-shrink-0" />
                {t('subscription.community.semanticSearch')}
              </li>
            </ul>
          </div>

          {/* Upgrade CTA */}
          <div className="mt-4 p-4 bg-purple-50 rounded-lg border border-purple-200">
            <div className="flex items-start justify-between">
              <div>
                <h4 className="font-semibold text-purple-900">{t('subscription.community.upgradeTitle')}</h4>
                <p className="text-sm text-purple-700 mt-1">
                  {t('subscription.community.upgradeSubtitle')}
                </p>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="text-2xl font-bold text-purple-900">{ENTERPRISE_PLAN.price}</span>
                  <span className="text-sm text-purple-600">{t('subscription.enterprise.oneTime')} • {t('subscription.enterprise.perpetual')}</span>
                </div>
              </div>
              <Button
                variant="primary"
                className="bg-purple-600 hover:bg-purple-700 flex-shrink-0"
                onClick={() => window.open(`${SAAS_URL}/enterprise`, '_blank')}
              >
                <ArrowUpIcon className="w-4 h-4 mr-2" />
                {t('subscription.upgrade')}
              </Button>
            </div>
            <p className="text-xs text-purple-600 mt-3">
              {t('subscription.community.purchaseNote')}
            </p>
          </div>
        </div>
      </div>
    </Card>
  )
}

export function SubscriptionPage() {
  const { t } = useTranslation('settings')
  const { tier, isActive, isInTrial, daysUntilTrialEnd, cancelAtPeriodEnd } = useSubscription()
  const { edition, editionLoading, isCloudSaaS, isEnterprise, isCommunity } = useEdition()
  const [searchParams, setSearchParams] = useSearchParams()
  const [usageMetrics, setUsageMetrics] = useState<UsageMetric[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isCheckoutLoading, setIsCheckoutLoading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Enterprise license state
  const [licenses, setLicenses] = useState<License[]>([])
  const [licensesLoading, setLicensesLoading] = useState(true)
  const [eligibility, setEligibility] = useState<PublicSectorEligibility | null>(null)
  const [copiedLicenseId, setCopiedLicenseId] = useState<string | null>(null)
  const [copiedAdminTokenId, setCopiedAdminTokenId] = useState<string | null>(null)
  const [enterpriseOrgName, setEnterpriseOrgName] = useState('')
  const [showEnterpriseModal, setShowEnterpriseModal] = useState(false)

  // Load usage metrics from backend
  const loadUsage = useCallback(async () => {
    try {
      const response = await apiClient.get<UsageResponse>('/subscriptions/usage')
      if (response.data) {
        setUsageMetrics([
          { name: t('subscription.usage.connectedServers'), current: response.data.connected_servers, limit: null, unit: t('subscription.usage.servers') },
          { name: t('subscription.usage.toolExecutions'), current: response.data.tool_executions, limit: null, unit: t('subscription.usage.executions') },
          { name: t('subscription.usage.compositions'), current: response.data.compositions, limit: null, unit: t('subscription.usage.workflows') },
          { name: t('subscription.usage.teamMembers'), current: response.data.team_members, limit: response.data.max_team_members, unit: t('subscription.usage.users') },
        ])
      }
    } catch (err) {
      console.error('Failed to load usage metrics:', err)
      // Use fallback data
      setUsageMetrics([
        { name: t('subscription.usage.connectedServers'), current: 0, limit: null, unit: t('subscription.usage.servers') },
        { name: t('subscription.usage.toolExecutions'), current: 0, limit: null, unit: t('subscription.usage.executions') },
        { name: t('subscription.usage.compositions'), current: 0, limit: null, unit: t('subscription.usage.workflows') },
        { name: t('subscription.usage.teamMembers'), current: 1, limit: 1, unit: t('subscription.usage.users') },
      ])
    } finally {
      setIsLoading(false)
    }
  }, [])

  // Load Enterprise licenses and eligibility (SaaS only)
  const loadLicenses = useCallback(async () => {
    // Skip API calls in non-SaaS mode (endpoints don't exist)
    if (!isCloudSaaS) {
      setLicensesLoading(false)
      return
    }

    try {
      const [licensesRes, eligibilityRes] = await Promise.all([
        licensesApi.getMyLicenses(),
        licensesApi.checkEligibility(),
      ])
      setLicenses(licensesRes.licenses || [])
      setEligibility(eligibilityRes)
    } catch (err) {
      console.error('Failed to load licenses:', err)
      setLicenses([])
    } finally {
      setLicensesLoading(false)
    }
  }, [isCloudSaaS])

  // Check for success param from checkout redirect
  useEffect(() => {
    if (searchParams.get('success') === 'true') {
      setSuccessMessage(t('subscription.paymentSuccess'))
      setSearchParams({}, { replace: true })
      setTimeout(() => setSuccessMessage(null), 5000)
    } else if (searchParams.get('enterprise_success') === 'true') {
      setSuccessMessage(t('subscription.enterprisePaymentSuccess', 'Enterprise license purchased successfully! Check below for your license key.'))
      setSearchParams({}, { replace: true })
      setTimeout(() => setSuccessMessage(null), 8000)
      // Reload licenses to show the newly created one
      loadLicenses()
    }
  }, [searchParams, setSearchParams, t, loadLicenses])

  useEffect(() => {
    loadUsage()
  }, [loadUsage])

  useEffect(() => {
    // Wait for edition to be determined before loading
    if (!editionLoading) {
      loadLicenses()
    }
  }, [loadLicenses, editionLoading])

  // Copy license key to clipboard
  const handleCopyLicense = async (license: License) => {
    try {
      await navigator.clipboard.writeText(license.license_key)
      setCopiedLicenseId(license.id)
      setTimeout(() => setCopiedLicenseId(null), 2000)
    } catch (err) {
      console.error('Failed to copy license:', err)
    }
  }

  // Copy admin token to clipboard
  const handleCopyAdminToken = async (license: License) => {
    if (!license.admin_token) return
    try {
      await navigator.clipboard.writeText(license.admin_token)
      setCopiedAdminTokenId(license.id)
      setTimeout(() => setCopiedAdminTokenId(null), 2000)
    } catch (err) {
      console.error('Failed to copy admin token:', err)
    }
  }

  // Create Enterprise checkout
  const handleEnterpriseCheckout = async () => {
    if (!enterpriseOrgName.trim()) {
      setError(t('subscription.enterprise.enterOrgName'))
      return
    }

    setIsCheckoutLoading('enterprise')
    setError(null)

    try {
      const response = await licensesApi.createCheckout({
        organization_name: enterpriseOrgName.trim(),
      })

      if (response.checkout_url) {
        window.location.href = response.checkout_url
      }
    } catch (err: any) {
      console.error('Failed to create enterprise checkout:', err)
      setError(err.response?.data?.detail || 'Failed to create checkout session')
    } finally {
      setIsCheckoutLoading(null)
      setShowEnterpriseModal(false)
    }
  }

  const handleUpgrade = async (planId: string) => {
    setIsCheckoutLoading(planId)
    setError(null)

    try {
      const response = await apiClient.post<{ checkout_url: string }>('/subscriptions/checkout', {
        plan: planId
      })

      if (response.data?.checkout_url) {
        // Redirect to LemonSqueezy checkout
        window.location.href = response.data.checkout_url
      }
    } catch (err: any) {
      console.error('Failed to create checkout:', err)
      setError(err.response?.data?.detail || 'Failed to create checkout session')
    } finally {
      setIsCheckoutLoading(null)
    }
  }

  const handleManageBilling = async () => {
    setError(null)

    try {
      const response = await apiClient.get<{ portal_url: string }>('/subscriptions/portal')

      if (response.data?.portal_url) {
        // Open LemonSqueezy customer portal in new tab
        window.open(response.data.portal_url, '_blank')
      }
    } catch (err: any) {
      console.error('Failed to get portal URL:', err)
      // Fallback: open LemonSqueezy orders page
      window.open('https://app.lemonsqueezy.com/my-orders', '_blank')
    }
  }

  return (
    <div className="container py-8">
      {/* Header - Adapts to edition */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-gray-900 mb-2">
          {isCloudSaaS ? t('subscription.title') : t('subscription.titleLicense')}
        </h1>
        <p className="text-lg text-gray-600 font-serif">
          {isCloudSaaS && t('subscription.subtitle')}
          {isEnterprise && t('subscription.subtitleEnterprise')}
          {isCommunity && t('subscription.subtitleCommunity')}
        </p>
      </div>

      {/* Edition Loading State */}
      {editionLoading && (
        <Card padding="lg" className="mb-6">
          <div className="text-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-2 border-gray-300 border-t-orange mx-auto" />
            <p className="text-sm text-gray-500 mt-2">{t('subscription.loading')}</p>
          </div>
        </Card>
      )}

      {/* ENTERPRISE Edition: Show installed license */}
      {!editionLoading && isEnterprise && edition?.license && (
        <EnterpriseLicenseSection license={edition.license} />
      )}

      {/* COMMUNITY Edition: Show upgrade CTA */}
      {!editionLoading && isCommunity && (
        <CommunityUpgradeSection />
      )}

      {/* CLOUD SAAS Edition: Full billing UI */}
      {!editionLoading && isCloudSaaS && (
        <>
          {/* Success Message */}
          {successMessage && (
            <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg text-green-700 flex items-center gap-2">
              <CheckCircleIcon className="w-5 h-5 flex-shrink-0" />
              {successMessage}
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
              {error}
            </div>
          )}

          {/* Current Plan */}
          <Card padding="lg" className="mb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-orange-100 rounded-full flex items-center justify-center">
              <CreditCardIcon className="w-6 h-6 text-orange" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">
                {tier ? t(`subscription.${tier}Plan`) : t('subscription.freeTier')}
              </h2>
              <p className="text-sm text-gray-600">
                {isInTrial
                  ? t('subscription.trialEndsIn', { days: daysUntilTrialEnd })
                  : isActive
                  ? t('subscription.activeSubscription')
                  : t('subscription.noActiveSubscription')}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {cancelAtPeriodEnd && (
              <span className="px-2 py-1 bg-amber-100 text-amber-700 rounded text-xs font-medium">
                {t('subscription.cancelsAtPeriodEnd')}
              </span>
            )}
            {/* Only show Manage Billing if user has an actual subscription */}
            {tier && (
              <Button variant="secondary" onClick={handleManageBilling}>
                {t('subscription.manage')}
              </Button>
            )}
          </div>
        </div>
      </Card>

      {/* Usage Metrics */}
      <Card padding="lg" className="mb-6">
        <div className="flex items-center gap-3 mb-6">
          <ChartBarIcon className="w-6 h-6 text-gray-600" />
          <h2 className="text-lg font-semibold text-gray-900">{t('subscription.usage.title')}</h2>
        </div>

        {isLoading ? (
          <div className="text-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-2 border-gray-300 border-t-orange mx-auto" />
          </div>
        ) : (
          <div className="grid md:grid-cols-2 gap-4">
            {usageMetrics.map((metric) => (
              <div key={metric.name} className="p-4 bg-gray-50 rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-gray-600">{metric.name}</span>
                  {metric.limit != null && metric.limit > 0 && (
                    <span className="text-xs text-gray-500">
                      {metric.current}/{metric.limit} {metric.unit}
                    </span>
                  )}
                </div>
                <p className="text-2xl font-bold text-gray-900">
                  {metric.current.toLocaleString()}
                  {(metric.limit == null || metric.limit === 0) && <span className="text-sm font-normal text-gray-500 ml-1">{metric.unit}</span>}
                </p>
                {metric.limit != null && metric.limit > 0 && (
                  <div className="mt-2 h-2 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-orange rounded-full"
                      style={{ width: `${Math.min((metric.current / metric.limit) * 100, 100)}%` }}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Available Plans */}
      <h2 className="text-lg font-semibold text-gray-900 mb-4">{t('subscription.availablePlans')}</h2>
      <div className="grid md:grid-cols-2 gap-4 pt-2">
        {PLANS.map((plan) => {
          const isCurrentPlan = tier === plan.id
          const planName = t(`subscription.plans.${plan.id}.name`)
          const planSubtitle = t(`subscription.plans.${plan.id}.subtitle`)
          const planPeriod = t(`subscription.plans.${plan.id}.period`)
          const planFeatures = t(`subscription.plans.${plan.id}.features`, { returnObjects: true }) as string[]
          return (
            <Card
              key={plan.id}
              padding="lg"
              className={cn(
                'relative overflow-visible',
                plan.popular && 'border-orange ring-1 ring-orange'
              )}
            >
              {plan.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-orange text-white text-xs font-medium rounded-full whitespace-nowrap z-10">
                  {t('subscription.mostPopular')}
                </div>
              )}

              <div className="mb-4">
                <span className="inline-block text-xs font-medium uppercase px-2 py-1 rounded mb-2 bg-blue-100 text-blue-700">
                  {planSubtitle}
                </span>
                <h3 className="text-xl font-bold text-gray-900">{planName}</h3>
                <div className="mt-2">
                  <span className="text-3xl font-bold text-gray-900">{plan.price}</span>
                  <span className="text-gray-600">{planPeriod}</span>
                </div>
              </div>

              <ul className="space-y-3 mb-6">
                {Array.isArray(planFeatures) && planFeatures.map((feature, idx) => (
                  <li key={idx} className="flex items-center gap-2 text-sm text-gray-600">
                    <CheckCircleIcon className="w-5 h-5 text-green-500 flex-shrink-0" />
                    {feature}
                  </li>
                ))}
              </ul>

              {isCurrentPlan ? (
                <Button variant="secondary" disabled className="w-full">
                  {t('subscription.currentPlanBadge')}
                </Button>
              ) : (
                <Button
                  variant={plan.popular ? 'primary' : 'secondary'}
                  className="w-full"
                  onClick={() => handleUpgrade(plan.id)}
                  disabled={isCheckoutLoading !== null}
                >
                  {isCheckoutLoading === plan.id ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent mr-2" />
                      {t('subscription.creatingCheckout')}
                    </>
                  ) : (
                    <>
                      <ArrowUpIcon className="w-4 h-4 mr-2" />
                      {t('subscription.upgradeTo', { plan: planName })}
                    </>
                  )}
                </Button>
              )}
            </Card>
          )
        })}
      </div>

      {/* Enterprise Licenses Section */}
      <div className="mt-10">
        <div className="flex items-center gap-3 mb-4">
          <KeyIcon className="w-6 h-6 text-purple-600" />
          <h2 className="text-lg font-semibold text-gray-900">{t('subscription.enterprise.title')}</h2>
          {eligibility?.is_eligible && (
            <span className="px-2 py-1 bg-green-100 text-green-700 rounded text-xs font-medium flex items-center gap-1">
              <ShieldCheckIcon className="w-4 h-4" />
              {t('subscription.enterprise.publicSectorEligible')}
            </span>
          )}
        </div>

        {licensesLoading ? (
          <Card padding="lg">
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-6 w-6 border-2 border-gray-300 border-t-purple-600 mx-auto" />
            </div>
          </Card>
        ) : licenses.length > 0 ? (
          <div className="space-y-4">
            {licenses.map((license) => (
              <Card key={license.id} padding="lg" className="border-purple-200">
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-4">
                    <div className="w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center flex-shrink-0">
                      <BuildingOfficeIcon className="w-6 h-6 text-purple-600" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-gray-900">
                        {license.company_name || t('subscription.enterprise.title')}
                      </h3>
                      <p className="text-sm text-gray-600 mt-1">
                        {t('subscription.license.edition')}: <span className="font-medium capitalize">{license.edition}</span>
                        {' • '}
                        {t('subscription.license.status')}: <span className={cn(
                          'font-medium capitalize',
                          license.status === 'active' ? 'text-green-600' : 'text-amber-600'
                        )}>{license.status === 'active' ? t('subscription.status.active') : license.status}</span>
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        {t('subscription.license.issued')}: {new Date(license.issued_at).toLocaleDateString()}
                        {license.expires_at && ` • ${t('subscription.license.expires')}: ${new Date(license.expires_at).toLocaleDateString()}`}
                        {!license.expires_at && ` • ${t('subscription.license.perpetual')}`}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={cn(
                      'px-2 py-1 rounded text-xs font-medium',
                      license.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
                    )}>
                      {license.status === 'active' ? t('subscription.status.active') : license.status}
                    </span>
                  </div>
                </div>

                {/* License Key */}
                <div className="mt-4 p-3 bg-gray-50 rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-gray-500 uppercase">{t('subscription.license.licenseKeyJwt')}</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleCopyLicense(license)}
                      className="text-xs"
                    >
                      {copiedLicenseId === license.id ? (
                        <>
                          <CheckCircleIcon className="w-4 h-4 mr-1 text-green-500" />
                          {t('subscription.license.copied')}
                        </>
                      ) : (
                        <>
                          <ClipboardDocumentIcon className="w-4 h-4 mr-1" />
                          {t('subscription.license.copy')}
                        </>
                      )}
                    </Button>
                  </div>
                  <code className="text-xs text-gray-700 break-all font-mono block">
                    {license.license_key.substring(0, 80)}...
                  </code>
                  <p className="text-xs text-gray-500 mt-2">
                    {t('subscription.license.instruction')} <code className="bg-gray-200 px-1 rounded">LICENSE_KEY=&lt;paste here&gt;</code>
                  </p>
                </div>

                {/* Admin Token - For self-hosted instance admin setup */}
                {license.admin_token && (
                  <div className="mt-3 p-3 bg-purple-50 rounded-lg border border-purple-200">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-purple-600 uppercase">{t('subscription.license.adminToken')}</span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleCopyAdminToken(license)}
                        className="text-xs text-purple-600 hover:text-purple-700"
                      >
                        {copiedAdminTokenId === license.id ? (
                          <>
                            <CheckCircleIcon className="w-4 h-4 mr-1 text-green-500" />
                            {t('subscription.license.copied')}
                          </>
                        ) : (
                          <>
                            <ClipboardDocumentIcon className="w-4 h-4 mr-1" />
                            {t('subscription.license.copy')}
                          </>
                        )}
                      </Button>
                    </div>
                    <code className="text-sm text-purple-700 font-mono block">
                      {license.admin_token}
                    </code>
                    <p className="text-xs text-purple-500 mt-2">
                      {t('subscription.license.adminTokenDescription')}
                    </p>
                  </div>
                )}

                {/* Features */}
                {license.features.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {license.features.map((feature) => (
                      <span
                        key={feature}
                        className="px-2 py-1 bg-purple-50 text-purple-700 rounded text-xs"
                      >
                        {feature.replace(/_/g, ' ')}
                      </span>
                    ))}
                  </div>
                )}
              </Card>
            ))}
          </div>
        ) : (
          /* No licenses - show Enterprise plan card */
          <Card padding="lg" className="border-purple-200 bg-gradient-to-br from-purple-50 to-white">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center flex-shrink-0">
                <BuildingOfficeIcon className="w-6 h-6 text-purple-600" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="inline-block text-xs font-medium uppercase px-2 py-1 rounded bg-purple-100 text-purple-700">
                    {t('subscription.plans.enterprise.subtitle')}
                  </span>
                  {eligibility?.is_eligible && (
                    <span className="inline-block text-xs font-medium px-2 py-1 rounded bg-green-100 text-green-700">
                      {t('subscription.enterprise.free')} - {eligibility.organization_name || eligibility.domain}
                    </span>
                  )}
                </div>
                <h3 className="text-xl font-bold text-gray-900">{t('subscription.plans.enterprise.name')}</h3>
                <div className="mt-2">
                  {eligibility?.is_eligible ? (
                    <span className="text-2xl font-bold text-green-600">
                      {t('subscription.enterprise.free')}
                      <span className="text-sm font-normal text-gray-500 ml-2 line-through">{ENTERPRISE_PLAN.price}</span>
                    </span>
                  ) : (
                    <>
                      <span className="text-2xl font-bold text-gray-900">{ENTERPRISE_PLAN.price}</span>
                      <span className="text-gray-600 ml-1">{t('subscription.plans.enterprise.period')}</span>
                    </>
                  )}
                </div>

                <ul className="mt-4 grid md:grid-cols-2 gap-2">
                  {(t('subscription.plans.enterprise.features', { returnObjects: true }) as string[]).map((feature, idx) => (
                    <li key={idx} className="flex items-center gap-2 text-sm text-gray-600">
                      <CheckCircleIcon className="w-4 h-4 text-purple-500 flex-shrink-0" />
                      {feature}
                    </li>
                  ))}
                </ul>

                <div className="mt-6">
                  <Button
                    variant="primary"
                    className="bg-purple-600 hover:bg-purple-700"
                    onClick={() => setShowEnterpriseModal(true)}
                    disabled={isCheckoutLoading !== null}
                  >
                    {eligibility?.is_eligible ? t('subscription.enterprise.getFreeLicense') : t('subscription.enterprise.purchaseEnterprise')}
                  </Button>
                </div>
              </div>
            </div>
          </Card>
        )}
      </div>

      {/* Enterprise Checkout Modal (SaaS only) */}
      {showEnterpriseModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card padding="lg" className="max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              {eligibility?.is_eligible ? t('subscription.enterprise.modalTitleFree') : t('subscription.enterprise.modalTitlePurchase')}
            </h3>

            {eligibility?.is_eligible && (
              <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg">
                <p className="text-sm text-green-700">
                  <ShieldCheckIcon className="w-4 h-4 inline mr-1" />
                  {t('subscription.enterprise.publicSectorMessage', { name: eligibility.organization_name, domain: eligibility.domain })}
                </p>
              </div>
            )}

            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('subscription.enterprise.organizationName')}
              </label>
              <input
                type="text"
                value={enterpriseOrgName}
                onChange={(e) => setEnterpriseOrgName(e.target.value)}
                placeholder={eligibility?.organization_name || t('subscription.enterprise.organizationPlaceholder')}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
              />
            </div>

            <div className="flex gap-3">
              <Button
                variant="secondary"
                className="flex-1"
                onClick={() => {
                  setShowEnterpriseModal(false)
                  setEnterpriseOrgName('')
                }}
              >
                {t('account.cancel')}
              </Button>
              <Button
                variant="primary"
                className="flex-1 bg-purple-600 hover:bg-purple-700"
                onClick={handleEnterpriseCheckout}
                disabled={isCheckoutLoading === 'enterprise'}
              >
                {isCheckoutLoading === 'enterprise' ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent mr-2" />
                    {t('subscription.enterprise.processing')}
                  </>
                ) : eligibility?.is_eligible ? (
                  t('subscription.enterprise.getFreeLicense')
                ) : (
                  t('subscription.enterprise.continueToCheckout')
                )}
              </Button>
            </div>
          </Card>
        </div>
      )}
        </>
      )}
    </div>
  )
}
