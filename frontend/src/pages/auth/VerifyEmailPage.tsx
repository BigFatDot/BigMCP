/**
 * Verify Email Page
 *
 * Handles email verification when user clicks the link in their email.
 * On successful verification, stores the returned tokens and redirects
 * to the app (auto-login).
 */

import { useState, useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { BigMCPLogoWithText } from '../../components/brand/BigMCPLogo'
import { CheckCircleIcon, XCircleIcon, ArrowPathIcon } from '@heroicons/react/24/outline'

const API_BASE = '/api/v1'

// Storage keys (must match AuthContext)
const STORAGE_KEYS = {
  ACCESS_TOKEN: 'bigmcp_access_token',
  REFRESH_TOKEN: 'bigmcp_refresh_token',
  USER: 'bigmcp_user',
  SUBSCRIPTION: 'bigmcp_subscription',
  ORGANIZATION: 'bigmcp_organization',
} as const

type VerificationStatus = 'loading' | 'success' | 'error' | 'already_verified' | 'expired'

export function VerifyEmailPage() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')

  const [status, setStatus] = useState<VerificationStatus>('loading')
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    if (!token) {
      setStatus('error')
      setErrorMessage(t('verify.errorInvalidLink'))
      return
    }

    verifyEmail(token)
  }, [token, t])

  const verifyEmail = async (verificationToken: string) => {
    try {
      const response = await fetch(`${API_BASE}/auth/verify-email?token=${encodeURIComponent(verificationToken)}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      const data = await response.json()

      if (response.ok && data.verified) {
        // Clear any stale session data from previous accounts first
        // This is critical when users have multiple accounts in the same browser
        localStorage.removeItem(STORAGE_KEYS.USER)
        localStorage.removeItem(STORAGE_KEYS.SUBSCRIPTION)
        localStorage.removeItem(STORAGE_KEYS.ORGANIZATION)

        // Store tokens for auto-login
        if (data.access_token && data.refresh_token) {
          localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, data.access_token)
          localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, data.refresh_token)

          // Fetch user data to get correct organization
          try {
            const meResponse = await fetch(`${API_BASE}/auth/me`, {
              headers: {
                'Authorization': `Bearer ${data.access_token}`,
                'Content-Type': 'application/json',
              },
            })

            if (meResponse.ok) {
              const meData = await meResponse.json()
              // Store user and organization data
              if (meData.user) {
                localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(meData.user))
              }
              if (meData.organization) {
                localStorage.setItem(STORAGE_KEYS.ORGANIZATION, JSON.stringify(meData.organization))
              }
              if (meData.subscription) {
                localStorage.setItem(STORAGE_KEYS.SUBSCRIPTION, JSON.stringify(meData.subscription))
              }
            }
          } catch (meError) {
            console.error('Failed to fetch user data after verification:', meError)
            // Continue anyway - AuthContext will fetch on app load
          }
        }

        setStatus('success')

        // Redirect to app after a short delay
        setTimeout(() => {
          navigate('/app', { replace: true })
        }, 2000)
      } else {
        // Handle specific error cases
        const errorDetail = data.detail || ''

        if (errorDetail.includes('already been verified')) {
          setStatus('already_verified')
        } else if (errorDetail.includes('expired')) {
          setStatus('expired')
          setErrorMessage(errorDetail)
        } else {
          setStatus('error')
          setErrorMessage(errorDetail || 'Failed to verify email. Please try again.')
        }
      }
    } catch (err) {
      setStatus('error')
      setErrorMessage(t('verify.errorOccurred'))
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link to="/" className="flex items-center">
              <BigMCPLogoWithText size="sm" textSize="md" />
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          {/* Card */}
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8 text-center">
            {/* Loading State */}
            {status === 'loading' && (
              <>
                <div className="mx-auto w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-6">
                  <ArrowPathIcon className="w-8 h-8 text-gray-400 animate-spin" />
                </div>
                <h1 className="text-2xl font-serif font-bold text-gray-900 mb-3">
                  {t('verify.titleVerifying')}
                </h1>
                <p className="text-gray-600">
                  {t('verify.verifying')}
                </p>
              </>
            )}

            {/* Success State */}
            {status === 'success' && (
              <>
                <div className="mx-auto w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mb-6">
                  <CheckCircleIcon className="w-8 h-8 text-green-600" />
                </div>
                <h1 className="text-2xl font-serif font-bold text-gray-900 mb-3">
                  {t('verify.titleVerified')}
                </h1>
                <p className="text-gray-600 mb-6">
                  {t('verify.verified')}
                </p>
                <div className="flex items-center justify-center gap-2 text-orange">
                  <ArrowPathIcon className="w-5 h-5 animate-spin" />
                  <span>{t('verify.redirecting')}</span>
                </div>
              </>
            )}

            {/* Already Verified State */}
            {status === 'already_verified' && (
              <>
                <div className="mx-auto w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mb-6">
                  <CheckCircleIcon className="w-8 h-8 text-blue-600" />
                </div>
                <h1 className="text-2xl font-serif font-bold text-gray-900 mb-3">
                  {t('verify.titleAlreadyVerified')}
                </h1>
                <p className="text-gray-600 mb-6">
                  {t('verify.alreadyVerified')}
                </p>
                <Link
                  to="/login"
                  className="inline-flex items-center justify-center w-full bg-orange hover:bg-orange-dark text-white font-medium py-3 px-4 rounded-lg transition-colors"
                >
                  {t('login.button')}
                </Link>
              </>
            )}

            {/* Expired State */}
            {status === 'expired' && (
              <>
                <div className="mx-auto w-16 h-16 bg-amber-100 rounded-full flex items-center justify-center mb-6">
                  <XCircleIcon className="w-8 h-8 text-amber-600" />
                </div>
                <h1 className="text-2xl font-serif font-bold text-gray-900 mb-3">
                  {t('verify.titleExpired')}
                </h1>
                <p className="text-gray-600 mb-6">
                  {t('verify.expired')}
                </p>
                <Link
                  to="/login"
                  className="inline-flex items-center justify-center w-full bg-orange hover:bg-orange-dark text-white font-medium py-3 px-4 rounded-lg transition-colors"
                >
                  {t('verify.signInToResend')}
                </Link>
              </>
            )}

            {/* Error State */}
            {status === 'error' && (
              <>
                <div className="mx-auto w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mb-6">
                  <XCircleIcon className="w-8 h-8 text-red-600" />
                </div>
                <h1 className="text-2xl font-serif font-bold text-gray-900 mb-3">
                  {t('verify.titleFailed')}
                </h1>
                <p className="text-gray-600 mb-6">
                  {errorMessage || t('verify.errorGeneric')}
                </p>
                <div className="space-y-3">
                  <Link
                    to="/signup"
                    className="inline-flex items-center justify-center w-full bg-orange hover:bg-orange-dark text-white font-medium py-3 px-4 rounded-lg transition-colors"
                  >
                    {t('verify.signUpAgain')}
                  </Link>
                  <Link
                    to="/login"
                    className="inline-flex items-center justify-center w-full border border-gray-300 text-gray-700 font-medium py-3 px-4 rounded-lg hover:bg-gray-50 transition-colors"
                  >
                    {t('login.button')}
                  </Link>
                </div>
              </>
            )}

            {/* Help Text */}
            <div className="mt-8 pt-6 border-t border-gray-200">
              <p className="text-sm text-gray-500">
                {t('verify.havingTrouble')}{' '}
                <a
                  href="mailto:support@bigmcp.cloud"
                  className="text-orange hover:text-orange-dark"
                >
                  {t('verify.contactSupport')}
                </a>
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
