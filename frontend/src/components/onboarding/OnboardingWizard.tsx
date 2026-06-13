/**
 * OnboardingWizard - Multi-step onboarding for new users
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { CheckIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import { Button, Card } from '@/components/ui'
import { cn } from '@/utils/cn'
import { useOrganization } from '@/hooks/useAuth'
import { marketplaceApi } from '@/services/marketplace'

type OnboardingStep = 'welcome' | 'choose-servers' | 'connect-servers' | 'complete'

interface ServerConnectionResult {
  serverId: string
  serverName: string
  success: boolean
  requiresCredentials: boolean
  error?: string
}

interface PopularServerCard {
  id: string
  name: string
  description: string
  icon: string
  category: string
}

// Static curated fallback if the marketplace fetch fails — keeps the wizard
// usable even when the backend is partially down.
const FALLBACK_POPULAR_SERVERS: PopularServerCard[] = [
  { id: 'notion', name: 'Notion', description: 'Manage your workspace and documents', icon: '📝', category: 'Productivity' },
  { id: 'google-drive', name: 'Google Drive', description: 'Access files and folders', icon: '📁', category: 'Storage' },
  { id: 'github', name: 'GitHub', description: 'Manage repositories and code', icon: '🐙', category: 'Development' },
  { id: 'slack', name: 'Slack', description: 'Send messages and notifications', icon: '💬', category: 'Communication' },
  { id: 'openai', name: 'OpenAI', description: 'AI-powered text generation', icon: '🤖', category: 'AI' },
  { id: 'postgres', name: 'PostgreSQL', description: 'Query and manage databases', icon: '🗄️', category: 'Data' },
]

// Map a category id to a display emoji. Anything not listed falls back to 🔌.
const CATEGORY_EMOJI: Record<string, string> = {
  productivity: '📝',
  storage: '📁',
  development: '🐙',
  dev: '🐙',
  communication: '💬',
  ai: '🤖',
  data: '🗄️',
  cloud: '☁️',
  search: '🔍',
  automation: '⚙️',
  security: '🔒',
  media: '🎬',
  documents: '📄',
  finance: '💰',
  payment: '💳',
}

export function OnboardingWizard() {
  const navigate = useNavigate()
  const { t } = useTranslation('common')
  const { organizationId } = useOrganization()
  const [step, setStep] = useState<OnboardingStep>('welcome')
  const [selectedServers, setSelectedServers] = useState<string[]>([])
  const [isConnecting, setIsConnecting] = useState(false)
  const [connectionResults, setConnectionResults] = useState<ServerConnectionResult[]>([])
  const [currentConnecting, setCurrentConnecting] = useState<string | null>(null)

  // Fetch the 6 most popular marketplace servers dynamically. Fall back to
  // the static curated list if the marketplace is unreachable so the wizard
  // remains usable. Pre-installed servers (already in user's pool) are
  // filtered out so we don't suggest something they already have.
  const [popularServers, setPopularServers] = useState<PopularServerCard[]>(
    FALLBACK_POPULAR_SERVERS,
  )
  useEffect(() => {
    let cancelled = false
    marketplaceApi
      .listServers({
        sort_by: 'popularity',
        sort_order: 'desc',
        limit: 6,
      })
      .then((servers) => {
        if (cancelled || !servers || servers.length === 0) return
        setPopularServers(
          servers.map((s) => {
            // The marketplace API returns ``category`` as a string[]
            // (multi-category support). Pick the first one for the card.
            const firstCategory = Array.isArray(s.category)
              ? s.category[0] || ''
              : (s.category as unknown as string) || ''
            return {
              id: s.id,
              name: s.name,
              description: s.description?.slice(0, 80) || 'MCP server',
              icon: CATEGORY_EMOJI[firstCategory.toLowerCase()] || '🔌',
              category: firstCategory || 'Other',
            }
          }),
        )
      })
      .catch(() => {
        // Keep the static fallback — log only, no toast (we're in onboarding)
        console.warn('Could not fetch popular servers; using fallback list')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const handleServerToggle = (serverId: string) => {
    setSelectedServers((prev) =>
      prev.includes(serverId)
        ? prev.filter((id) => id !== serverId)
        : [...prev, serverId]
    )
  }

  // Connect to selected servers when entering 'connect-servers' step
  useEffect(() => {
    if (step !== 'connect-servers' || selectedServers.length === 0 || !organizationId) {
      return
    }

    const connectServers = async () => {
      setIsConnecting(true)
      const results: ServerConnectionResult[] = []

      for (const serverId of selectedServers) {
        setCurrentConnecting(serverId)
        const serverInfo = popularServers.find((s) => s.id === serverId)
        const serverName = serverInfo?.name || serverId

        try {
          // Get server details from marketplace to check if credentials are required
          const serverData = await marketplaceApi.getServer(serverId)

          if (serverData.requires_credentials) {
            // Server requires credentials - mark for manual setup
            results.push({
              serverId,
              serverName,
              success: false,
              requiresCredentials: true,
            })
          } else {
            // Server doesn't require credentials - connect with empty credentials
            await marketplaceApi.connectServer(
              serverId,
              organizationId,
              {},  // Empty credentials
              serverName,
              false // Don't auto-start
            )
            results.push({
              serverId,
              serverName,
              success: true,
              requiresCredentials: false,
            })
          }
        } catch (error) {
          // Server not found in marketplace or connection failed
          results.push({
            serverId,
            serverName,
            success: false,
            requiresCredentials: true,
            error: error instanceof Error ? error.message : 'Connection failed',
          })
        }
      }

      setConnectionResults(results)
      setCurrentConnecting(null)
      setIsConnecting(false)
    }

    connectServers()
  }, [step, selectedServers, organizationId])

  const serversNeedCredentials = connectionResults.some(r => r.requiresCredentials)
  const someServersConnected = connectionResults.some(r => r.success)

  const handleContinue = () => {
    if (step === 'welcome') {
      setStep('choose-servers')
    } else if (step === 'choose-servers') {
      if (selectedServers.length > 0) {
        setStep('connect-servers')
      } else {
        setStep('complete')
      }
    } else if (step === 'connect-servers') {
      setStep('complete')
    } else if (step === 'complete') {
      // Redirect to Tools if some servers need credentials, otherwise to Marketplace
      if (serversNeedCredentials) {
        navigate('/app/tools')
      } else {
        navigate('/app/marketplace')
      }
    }
  }

  const handleSkip = () => {
    navigate('/app/marketplace')
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-orange-50 via-white to-blue-50">
      {/* Progress Bar */}
      <div className="fixed top-0 left-0 right-0 h-1 bg-gray-200 z-50">
        <div
          className="h-full bg-orange transition-all duration-500"
          style={{
            width:
              step === 'welcome'
                ? '25%'
                : step === 'choose-servers'
                ? '50%'
                : step === 'connect-servers'
                ? '75%'
                : '100%',
          }}
        />
      </div>

      <div className="container mx-auto px-4 py-12">
        <div className="max-w-4xl mx-auto">
          {/* Welcome Step */}
          {step === 'welcome' && (
            <div className="text-center space-y-8 animate-fade-in">
              {/* Logo */}
              <div className="w-24 h-24 mx-auto">
                <svg
                  viewBox="0 0 100 100"
                  className="w-full h-full animate-spin-slow"
                >
                  <circle cx="50" cy="50" r="15" fill="#D97757" />
                  {[...Array(12)].map((_, i) => {
                    const angle = (i * 30 * Math.PI) / 180
                    const radius = 35
                    const x = 50 + radius * Math.cos(angle)
                    const y = 50 + radius * Math.sin(angle)
                    return (
                      <circle
                        key={i}
                        cx={x}
                        cy={y}
                        r="3"
                        fill="white"
                        opacity="0.9"
                      />
                    )
                  })}
                </svg>
              </div>

              <div>
                <h1 className="text-5xl font-bold text-gray-900 mb-4">
                  {t('onboarding.welcome.title')}
                </h1>
                <p className="text-xl text-gray-600 font-serif max-w-2xl mx-auto">
                  {t('onboarding.welcome.subtitle')}
                </p>
              </div>

              <div className="grid md:grid-cols-3 gap-6 mt-12">
                <Card padding="lg">
                  <div className="text-4xl mb-4">🔌</div>
                  <h3 className="text-lg font-bold text-gray-900 mb-2">
                    {t('onboarding.welcome.feature1.title')}
                  </h3>
                  <p className="text-sm text-gray-600 font-serif">
                    {t('onboarding.welcome.feature1.body')}
                  </p>
                </Card>

                <Card padding="lg">
                  <div className="text-4xl mb-4">🤖</div>
                  <h3 className="text-lg font-bold text-gray-900 mb-2">
                    {t('onboarding.welcome.feature2.title')}
                  </h3>
                  <p className="text-sm text-gray-600 font-serif">
                    {t('onboarding.welcome.feature2.body')}
                  </p>
                </Card>

                <Card padding="lg">
                  <div className="text-4xl mb-4">🔒</div>
                  <h3 className="text-lg font-bold text-gray-900 mb-2">
                    {t('onboarding.welcome.feature3.title')}
                  </h3>
                  <p className="text-sm text-gray-600 font-serif">
                    {t('onboarding.welcome.feature3.body')}
                  </p>
                </Card>
              </div>

              <div className="flex justify-center gap-4 mt-12">
                <Button variant="secondary" onClick={handleSkip}>
                  {t('onboarding.actions.skip')}
                </Button>
                <Button variant="primary" size="lg" onClick={handleContinue}>
                  {t('onboarding.actions.getStarted')}
                </Button>
              </div>
            </div>
          )}

          {/* Choose Servers Step */}
          {step === 'choose-servers' && (
            <div className="space-y-8 animate-fade-in">
              <div className="text-center">
                <h2 className="text-4xl font-bold text-gray-900 mb-4">
                  {t('onboarding.chooseServers.title')}
                </h2>
                <p className="text-lg text-gray-600 font-serif max-w-2xl mx-auto">
                  {t('onboarding.chooseServers.subtitle')}
                </p>
              </div>

              <div className="grid md:grid-cols-3 gap-4">
                {popularServers.map((server) => {
                  const isSelected = selectedServers.includes(server.id)
                  return (
                    <button
                      key={server.id}
                      onClick={() => handleServerToggle(server.id)}
                      className={cn(
                        'relative p-6 rounded-xl border-2 transition-all text-left',
                        isSelected
                          ? 'border-orange bg-orange-50'
                          : 'border-gray-200 bg-white hover:border-orange-200'
                      )}
                    >
                      {isSelected && (
                        <div className="absolute top-3 right-3 w-6 h-6 bg-orange rounded-full flex items-center justify-center">
                          <CheckIcon className="w-4 h-4 text-white" />
                        </div>
                      )}

                      <div className="text-4xl mb-3">{server.icon}</div>
                      <h3 className="font-bold text-gray-900 mb-1">
                        {server.name}
                      </h3>
                      <p className="text-sm text-gray-600 font-serif mb-2">
                        {server.description}
                      </p>
                      <span className="inline-block px-2 py-1 bg-gray-100 rounded text-xs font-medium text-gray-700">
                        {server.category}
                      </span>
                    </button>
                  )
                })}
              </div>

              <div className="flex justify-between mt-12">
                <Button variant="ghost" onClick={() => setStep('welcome')}>
                  {t('onboarding.actions.back')}
                </Button>
                <div className="flex gap-3">
                  <Button variant="secondary" onClick={handleSkip}>
                    {t('onboarding.actions.skip')}
                  </Button>
                  <Button variant="primary" onClick={handleContinue}>
                    {selectedServers.length > 0
                      ? t('onboarding.actions.continueWith', { count: selectedServers.length })
                      : t('onboarding.actions.skipStep')}
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* Connect Servers Step */}
          {step === 'connect-servers' && (
            <div className="space-y-8 animate-fade-in">
              <div className="text-center">
                <h2 className="text-4xl font-bold text-gray-900 mb-4">
                  {isConnecting
                    ? t('onboarding.connect.titleConnecting')
                    : t('onboarding.connect.titleResults')}
                </h2>
                <p className="text-lg text-gray-600 font-serif max-w-2xl mx-auto">
                  {isConnecting
                    ? t('onboarding.connect.subtitleConnecting')
                    : t('onboarding.connect.subtitleResults')}
                </p>
              </div>

              <Card padding="lg">
                <div className="space-y-4">
                  {selectedServers.map((serverId) => {
                    const serverInfo = popularServers.find((s) => s.id === serverId)
                    const result = connectionResults.find(r => r.serverId === serverId)
                    const isCurrentlyConnecting = currentConnecting === serverId

                    return (
                      <div
                        key={serverId}
                        className={cn(
                          'flex items-center justify-between p-4 rounded-lg border',
                          result?.success
                            ? 'border-green-200 bg-green-50'
                            : result?.requiresCredentials
                            ? 'border-amber-200 bg-amber-50'
                            : isCurrentlyConnecting
                            ? 'border-orange-200 bg-orange-50'
                            : 'border-gray-200 bg-gray-50'
                        )}
                      >
                        <div className="flex items-center gap-3">
                          <span className="text-2xl">{serverInfo?.icon || '🔌'}</span>
                          <div>
                            <h4 className="font-semibold text-gray-900">
                              {serverInfo?.name || serverId}
                            </h4>
                            <p className="text-sm text-gray-600">
                              {isCurrentlyConnecting
                                ? t('onboarding.connect.statusConnecting')
                                : result?.success
                                ? t('onboarding.connect.statusSuccess')
                                : result?.requiresCredentials
                                ? t('onboarding.connect.statusNeedsCreds')
                                : result?.error
                                ? result.error
                                : t('onboarding.connect.statusWaiting')}
                            </p>
                          </div>
                        </div>
                        <div>
                          {isCurrentlyConnecting ? (
                            <div className="w-6 h-6 border-2 border-orange border-t-transparent rounded-full animate-spin" />
                          ) : result?.success ? (
                            <div className="w-6 h-6 bg-green-500 rounded-full flex items-center justify-center">
                              <CheckIcon className="w-4 h-4 text-white" />
                            </div>
                          ) : result?.requiresCredentials ? (
                            <div className="w-6 h-6 bg-amber-500 rounded-full flex items-center justify-center">
                              <ExclamationTriangleIcon className="w-4 h-4 text-white" />
                            </div>
                          ) : null}
                        </div>
                      </div>
                    )
                  })}
                </div>

                {!isConnecting && connectionResults.some(r => r.requiresCredentials) && (
                  <div className="mt-6 p-4 bg-amber-50 border border-amber-200 rounded-lg">
                    <p className="text-sm text-amber-800">
                      <strong>{t('onboarding.connect.noteLabel')}:</strong>{' '}
                      {t('onboarding.connect.noteCredentials', { services: t('menu.services') })}
                    </p>
                  </div>
                )}

                {!isConnecting && (
                  <div className="mt-6 flex justify-center">
                    <Button variant="primary" onClick={handleContinue}>
                      {connectionResults.some(r => r.success)
                        ? t('onboarding.actions.continueDashboard')
                        : t('onboarding.actions.continueAnyway')}
                    </Button>
                  </div>
                )}
              </Card>

              <div className="flex justify-between">
                <Button
                  variant="ghost"
                  onClick={() => setStep('choose-servers')}
                  disabled={isConnecting}
                >
                  {t('onboarding.actions.back')}
                </Button>
              </div>
            </div>
          )}

          {/* Complete Step */}
          {step === 'complete' && (
            <div className="text-center space-y-8 animate-fade-in">
              <div className={cn(
                'w-24 h-24 mx-auto rounded-full flex items-center justify-center',
                serversNeedCredentials ? 'bg-amber-100' : 'bg-green-100'
              )}>
                {serversNeedCredentials ? (
                  <ExclamationTriangleIcon className="w-12 h-12 text-amber-500" />
                ) : (
                  <CheckIcon className="w-12 h-12 text-green-500" />
                )}
              </div>

              <div>
                <h2 className="text-4xl font-bold text-gray-900 mb-4">
                  {serversNeedCredentials
                    ? t('onboarding.complete.titleAlmost')
                    : t('onboarding.complete.titleDone')}
                </h2>
                <p className="text-xl text-gray-600 font-serif max-w-2xl mx-auto">
                  {serversNeedCredentials
                    ? t('onboarding.complete.bodyNeedsCreds', { services: t('menu.services') })
                    : someServersConnected
                    ? t('onboarding.complete.bodyConnected')
                    : t('onboarding.complete.bodyWelcome')}
                </p>
              </div>

              <Button variant="primary" size="lg" onClick={handleContinue}>
                {serversNeedCredentials
                  ? t('onboarding.actions.goToServices', { services: t('menu.services') })
                  : t('onboarding.actions.goToMarketplace')}
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
