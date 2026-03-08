/**
 * OAuthFlow - Handle OAuth 2.0 authentication flow
 */

import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { CheckCircleIcon } from '@heroicons/react/24/outline'
import { Button, Spinner, Alert } from '@/components/ui'
import { oauthApi } from '@/services/marketplace'
import type { MCPServer } from '@/types/marketplace'

export interface OAuthFlowProps {
  server: MCPServer
  onSuccess: () => void
  onError: (error: string) => void
  onBack: () => void
}

type OAuthStep = 'init' | 'authorizing' | 'completing' | 'success'

export function OAuthFlow({ server, onSuccess, onError, onBack }: OAuthFlowProps) {
  const [step, setStep] = useState<OAuthStep>('init')

  // Initiate OAuth mutation
  const initOAuthMutation = useMutation({
    mutationFn: () => {
      const redirectUri = `${window.location.origin}/oauth/callback`
      return oauthApi.initiateOAuth(server.id, redirectUri)
    },
    onSuccess: (data) => {
      setStep('authorizing')
      // Open OAuth popup
      const width = 600
      const height = 700
      const left = window.screen.width / 2 - width / 2
      const top = window.screen.height / 2 - height / 2

      const popup = window.open(
        data.authorization_url,
        'oauth_popup',
        `width=${width},height=${height},left=${left},top=${top},popup=yes`
      )

      if (!popup) {
        onError('Failed to open OAuth popup. Please allow popups for this site.')
        setStep('init')
        return
      }

      // Listen for OAuth callback
      const handleMessage = (event: MessageEvent) => {
        if (event.origin !== window.location.origin) return

        if (event.data.type === 'oauth_success') {
          setStep('success')
          window.removeEventListener('message', handleMessage)
          setTimeout(() => {
            onSuccess()
          }, 1500)
        } else if (event.data.type === 'oauth_error') {
          onError(event.data.error || 'OAuth authorization failed')
          setStep('init')
          window.removeEventListener('message', handleMessage)
        }
      }

      window.addEventListener('message', handleMessage)

      // Check if popup was closed
      const checkClosed = setInterval(() => {
        if (popup.closed) {
          clearInterval(checkClosed)
          window.removeEventListener('message', handleMessage)
          if (step !== 'success') {
            setStep('init')
          }
        }
      }, 500)
    },
    onError: (error) => {
      onError(error instanceof Error ? error.message : 'Failed to initiate OAuth')
      setStep('init')
    },
  })

  const handleStartOAuth = () => {
    initOAuthMutation.mutate()
  }

  return (
    <div className="space-y-6">
      {/* Step Indicator */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div
            className={`w-8 h-8 rounded-full flex items-center justify-center font-medium ${
              step === 'init' || step === 'authorizing'
                ? 'bg-orange text-white'
                : 'bg-green-500 text-white'
            }`}
          >
            {step === 'success' ? (
              <CheckCircleIcon className="w-5 h-5" />
            ) : (
              '1'
            )}
          </div>
          <span className="font-medium text-gray-900">Authorize</span>
        </div>
        <div className="h-px flex-1 mx-4 bg-gray-300" />
        <div className="flex items-center gap-2">
          <div
            className={`w-8 h-8 rounded-full flex items-center justify-center font-medium ${
              step === 'completing' || step === 'success'
                ? 'bg-orange text-white'
                : 'bg-gray-300 text-gray-600'
            }`}
          >
            {step === 'success' ? (
              <CheckCircleIcon className="w-5 h-5" />
            ) : (
              '2'
            )}
          </div>
          <span className="font-medium text-gray-900">Complete</span>
        </div>
      </div>

      {/* Content */}
      {step === 'init' && (
        <div className="text-center py-6">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-orange-100 flex items-center justify-center">
            <svg
              className="w-8 h-8 text-orange"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z"
              />
            </svg>
          </div>
          <h3 className="text-xl font-bold text-gray-900 mb-2">
            Connect with OAuth
          </h3>
          <p className="text-gray-600 font-serif mb-6">
            You'll be redirected to {server.name} to authorize access. This is the
            secure way to connect without sharing your password.
          </p>
          {server.documentation_url && (
            <Alert variant="info">
              <a
                href={server.documentation_url}
                target="_blank"
                rel="noopener noreferrer"
                className="underline"
              >
                Learn more about required permissions
              </a>
            </Alert>
          )}
        </div>
      )}

      {step === 'authorizing' && (
        <div className="text-center py-6">
          <Spinner size="lg" className="mx-auto mb-4" />
          <h3 className="text-xl font-bold text-gray-900 mb-2">
            Waiting for Authorization
          </h3>
          <p className="text-gray-600 font-serif">
            Please complete the authorization in the popup window...
          </p>
        </div>
      )}

      {step === 'completing' && (
        <div className="text-center py-6">
          <Spinner size="lg" className="mx-auto mb-4" />
          <h3 className="text-xl font-bold text-gray-900 mb-2">
            Completing Connection
          </h3>
          <p className="text-gray-600 font-serif">
            Saving your credentials securely...
          </p>
        </div>
      )}

      {step === 'success' && (
        <div className="text-center py-6">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-green-100 flex items-center justify-center">
            <CheckCircleIcon className="w-10 h-10 text-green-500" />
          </div>
          <h3 className="text-xl font-bold text-gray-900 mb-2">
            Connection Successful!
          </h3>
          <p className="text-gray-600 font-serif">
            {server.name} has been connected to your workspace.
          </p>
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-between gap-3 pt-4 border-t border-gray-200">
        <Button variant="ghost" onClick={onBack} disabled={step !== 'init'}>
          Back
        </Button>
        {step === 'init' && (
          <Button
            variant="primary"
            onClick={handleStartOAuth}
            isLoading={initOAuthMutation.isPending}
          >
            Continue with OAuth
          </Button>
        )}
      </div>
    </div>
  )
}
