/**
 * OnboardingWizard - Multi-step onboarding for new users
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
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

const POPULAR_SERVERS = [
  {
    id: 'notion',
    name: 'Notion',
    description: 'Manage your workspace and documents',
    icon: '📝',
    category: 'Productivity',
  },
  {
    id: 'google-drive',
    name: 'Google Drive',
    description: 'Access files and folders',
    icon: '📁',
    category: 'Storage',
  },
  {
    id: 'github',
    name: 'GitHub',
    description: 'Manage repositories and code',
    icon: '🐙',
    category: 'Development',
  },
  {
    id: 'slack',
    name: 'Slack',
    description: 'Send messages and notifications',
    icon: '💬',
    category: 'Communication',
  },
  {
    id: 'openai',
    name: 'OpenAI',
    description: 'AI-powered text generation',
    icon: '🤖',
    category: 'AI',
  },
  {
    id: 'postgres',
    name: 'PostgreSQL',
    description: 'Query and manage databases',
    icon: '🗄️',
    category: 'Data',
  },
]

export function OnboardingWizard() {
  const navigate = useNavigate()
  const { organizationId } = useOrganization()
  const [step, setStep] = useState<OnboardingStep>('welcome')
  const [selectedServers, setSelectedServers] = useState<string[]>([])
  const [isConnecting, setIsConnecting] = useState(false)
  const [connectionResults, setConnectionResults] = useState<ServerConnectionResult[]>([])
  const [currentConnecting, setCurrentConnecting] = useState<string | null>(null)

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
        const serverInfo = POPULAR_SERVERS.find(s => s.id === serverId)
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
                  Welcome to BigMCP
                </h1>
                <p className="text-xl text-gray-600 font-serif max-w-2xl mx-auto">
                  Your unified gateway to connect, manage, and orchestrate all your
                  MCP servers in one place. Let's get you set up!
                </p>
              </div>

              <div className="grid md:grid-cols-3 gap-6 mt-12">
                <Card padding="lg">
                  <div className="text-4xl mb-4">🔌</div>
                  <h3 className="text-lg font-bold text-gray-900 mb-2">
                    Connect Services
                  </h3>
                  <p className="text-sm text-gray-600 font-serif">
                    Connect to hundreds of MCP servers with a few clicks
                  </p>
                </Card>

                <Card padding="lg">
                  <div className="text-4xl mb-4">🤖</div>
                  <h3 className="text-lg font-bold text-gray-900 mb-2">
                    AI Workflows
                  </h3>
                  <p className="text-sm text-gray-600 font-serif">
                    Create powerful workflows using natural language
                  </p>
                </Card>

                <Card padding="lg">
                  <div className="text-4xl mb-4">🔒</div>
                  <h3 className="text-lg font-bold text-gray-900 mb-2">
                    Secure & Private
                  </h3>
                  <p className="text-sm text-gray-600 font-serif">
                    Your credentials are encrypted and never shared
                  </p>
                </Card>
              </div>

              <div className="flex justify-center gap-4 mt-12">
                <Button variant="secondary" onClick={handleSkip}>
                  Skip for now
                </Button>
                <Button variant="primary" size="lg" onClick={handleContinue}>
                  Get Started
                </Button>
              </div>
            </div>
          )}

          {/* Choose Servers Step */}
          {step === 'choose-servers' && (
            <div className="space-y-8 animate-fade-in">
              <div className="text-center">
                <h2 className="text-4xl font-bold text-gray-900 mb-4">
                  Choose Your Services
                </h2>
                <p className="text-lg text-gray-600 font-serif max-w-2xl mx-auto">
                  Select the services you use. You can always add more later from the
                  marketplace.
                </p>
              </div>

              <div className="grid md:grid-cols-3 gap-4">
                {POPULAR_SERVERS.map((server) => {
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
                  Back
                </Button>
                <div className="flex gap-3">
                  <Button variant="secondary" onClick={handleSkip}>
                    Skip for now
                  </Button>
                  <Button variant="primary" onClick={handleContinue}>
                    {selectedServers.length > 0
                      ? `Continue with ${selectedServers.length} service${
                          selectedServers.length > 1 ? 's' : ''
                        }`
                      : 'Skip this step'}
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
                  {isConnecting ? 'Connecting Your Services...' : 'Connection Results'}
                </h2>
                <p className="text-lg text-gray-600 font-serif max-w-2xl mx-auto">
                  {isConnecting
                    ? 'We are connecting to your selected services. This may take a moment.'
                    : 'Here is the status of your service connections.'}
                </p>
              </div>

              <Card padding="lg">
                <div className="space-y-4">
                  {selectedServers.map((serverId) => {
                    const serverInfo = POPULAR_SERVERS.find(s => s.id === serverId)
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
                                ? 'Connecting...'
                                : result?.success
                                ? 'Connected successfully'
                                : result?.requiresCredentials
                                ? 'Requires credentials setup'
                                : result?.error
                                ? result.error
                                : 'Waiting...'}
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
                      <strong>Note:</strong> Some servers require credentials to be configured.
                      You can set them up from the <strong>My Services</strong> page after completing onboarding.
                    </p>
                  </div>
                )}

                {!isConnecting && (
                  <div className="mt-6 flex justify-center">
                    <Button variant="primary" onClick={handleContinue}>
                      {connectionResults.some(r => r.success)
                        ? 'Continue to Dashboard'
                        : 'Continue Anyway'}
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
                  Back
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
                  {serversNeedCredentials ? 'Almost There!' : 'You\'re All Set!'}
                </h2>
                <p className="text-xl text-gray-600 font-serif max-w-2xl mx-auto">
                  {serversNeedCredentials
                    ? 'Some services need credentials to work. Head to My Services to configure them, then start creating AI-powered workflows.'
                    : someServersConnected
                    ? 'Your services are connected! Start exploring the marketplace to discover more services and create your first AI-powered workflow.'
                    : 'Welcome to BigMCP. Start exploring the marketplace to discover services and create your first AI-powered workflow.'}
                </p>
              </div>

              <Button variant="primary" size="lg" onClick={handleContinue}>
                {serversNeedCredentials ? 'Go to My Services' : 'Go to Marketplace'}
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
