/**
 * Login Page
 *
 * Handles user authentication for BigMCP Cloud SaaS.
 * Self-hosted users register on cloud but use API keys locally.
 */

import { useState, FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../hooks/useAuth'
import { BigMCPLogoWithText } from '../../components/brand/BigMCPLogo'
import { TOTPInput } from '../../components/auth'
import { EnvelopeIcon, ArrowPathIcon, ShieldCheckIcon } from '@heroicons/react/24/outline'
import { mfaApi } from '../../services/marketplace'

const API_BASE = '/api/v1'

export function LoginPage() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { login, deploymentConfig } = useAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  // Email verification state
  const [showVerificationNeeded, setShowVerificationNeeded] = useState(false)
  const [verificationEmail, setVerificationEmail] = useState('')
  const [isResending, setIsResending] = useState(false)
  const [resendSuccess, setResendSuccess] = useState(false)

  // MFA state
  const [mfaRequired, setMfaRequired] = useState(false)
  const [mfaToken, setMfaToken] = useState('')
  const [mfaCode, setMfaCode] = useState('')
  const [isMfaVerifying, setIsMfaVerifying] = useState(false)

  const redirectTo = searchParams.get('redirect') || '/app/tools'

  const handleResendVerification = async () => {
    setIsResending(true)
    try {
      const response = await fetch(`${API_BASE}/auth/resend-verification-public?email=${encodeURIComponent(verificationEmail)}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })
      if (response.ok) {
        setResendSuccess(true)
      }
    } catch (err) {
      // Silently fail - we show success anyway to prevent enumeration
      setResendSuccess(true)
    } finally {
      setIsResending(false)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setShowVerificationNeeded(false)
    setResendSuccess(false)
    setMfaRequired(false)
    setIsLoading(true)

    try {
      const result = await login(email, password)
      // Check if MFA is required
      if (result?.mfa_required) {
        setMfaToken(result.mfa_token)
        setMfaRequired(true)
        setIsLoading(false)
        return
      }
      navigate(redirectTo)
    } catch (err: any) {
      // Handle email not verified error
      if (err.emailNotVerified) {
        setShowVerificationNeeded(true)
        setVerificationEmail(err.email || email)
        setError(err.message)
      } else {
        setError(err instanceof Error ? err.message : 'Login failed. Please try again.')
      }
    } finally {
      setIsLoading(false)
    }
  }

  const handleMFASubmit = async () => {
    if (mfaCode.length !== 6 && mfaCode.length !== 8) {
      setError(t('login.mfa.invalidCode'))
      return
    }

    setError('')
    setIsMfaVerifying(true)

    try {
      const tokens = await mfaApi.loginWithMFA(mfaToken, mfaCode)
      // Store tokens and complete login
      localStorage.setItem('bigmcp_access_token', tokens.access_token)
      localStorage.setItem('bigmcp_refresh_token', tokens.refresh_token)
      // Refresh auth state
      window.location.href = redirectTo
    } catch (err: any) {
      console.error('MFA verification failed:', err)
      setError(err.response?.data?.detail || t('login.mfa.verifyFailed'))
      setMfaCode('')
    } finally {
      setIsMfaVerifying(false)
    }
  }

  const handleBackToLogin = () => {
    setMfaRequired(false)
    setMfaToken('')
    setMfaCode('')
    setError('')
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

            <Link
              to="/signup"
              className="text-sm text-gray-600 hover:text-gray-900 transition-colors"
            >
              {t('login.noAccount')} <span className="text-orange font-medium">{t('login.signupLink')}</span>
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          {/* Card */}
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
            {/* Title */}
            <div className="text-center mb-8">
              <h1 className="text-3xl font-serif font-bold text-gray-900 mb-2">
                {t('login.title')}
              </h1>
              <p className="text-gray-600">
                {deploymentConfig.is_cloud
                  ? t('login.subtitle')
                  : t('login.subtitleSelfHosted')}
              </p>
            </div>

            {/* Error Message */}
            {error && !showVerificationNeeded && (
              <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-800">{error}</p>
              </div>
            )}

            {/* Email Verification Needed */}
            {showVerificationNeeded && (
              <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-lg">
                <div className="flex items-start gap-3">
                  <EnvelopeIcon className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div className="flex-1">
                    <p className="text-sm font-medium text-amber-900 mb-2">
                      {t('verify.verificationRequired')}
                    </p>
                    <p className="text-sm text-amber-800 mb-3">
                      {t('verify.checkInbox')} <strong>{verificationEmail}</strong>
                    </p>
                    {resendSuccess ? (
                      <p className="text-sm text-green-700">
                        {t('verify.resentCheck')}
                      </p>
                    ) : (
                      <button
                        type="button"
                        onClick={handleResendVerification}
                        disabled={isResending}
                        className="inline-flex items-center gap-1.5 text-sm font-medium text-amber-700 hover:text-amber-900 disabled:opacity-50"
                      >
                        {isResending ? (
                          <>
                            <ArrowPathIcon className="w-4 h-4 animate-spin" />
                            {t('verify.resending')}
                          </>
                        ) : (
                          <>
                            <ArrowPathIcon className="w-4 h-4" />
                            {t('verify.resend')}
                          </>
                        )}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* MFA Verification Form */}
            {mfaRequired ? (
              <div className="space-y-6">
                {/* MFA Header */}
                <div className="flex items-center gap-3 p-4 bg-indigo-50 border border-indigo-200 rounded-lg">
                  <ShieldCheckIcon className="w-6 h-6 text-indigo-600 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-indigo-900">
                      {t('login.mfa.title')}
                    </p>
                    <p className="text-sm text-indigo-700">
                      {t('login.mfa.enterCode')}
                    </p>
                  </div>
                </div>

                {/* TOTP Input */}
                <div className="py-4">
                  <TOTPInput
                    value={mfaCode}
                    onChange={setMfaCode}
                    autoFocus
                    error={error || undefined}
                  />
                </div>

                {/* MFA Submit */}
                <button
                  type="button"
                  onClick={handleMFASubmit}
                  disabled={mfaCode.length < 6 || isMfaVerifying}
                  className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-3 px-4 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isMfaVerifying ? t('login.mfa.verifying') : t('login.mfa.verify')}
                </button>

                {/* Back to Login */}
                <button
                  type="button"
                  onClick={handleBackToLogin}
                  className="w-full text-sm text-gray-600 hover:text-gray-900 transition-colors"
                >
                  {t('login.mfa.backToLogin')}
                </button>

                {/* Backup Code Hint */}
                <p className="text-xs text-center text-gray-500">
                  {t('login.mfa.useBackupCode')}
                </p>
              </div>
            ) : (
              /* Regular Login Form */
              <form onSubmit={handleSubmit} className="space-y-6">
                {/* Email */}
                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
                    {t('login.email')}
                  </label>
                  <input
                    id="email"
                    type="email"
                    required
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-transparent transition-shadow"
                    placeholder="you@example.com"
                    disabled={isLoading}
                  />
                </div>

                {/* Password */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                      {t('login.password')}
                    </label>
                  </div>
                  <input
                    id="password"
                    type="password"
                    required
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-transparent transition-shadow"
                    placeholder="••••••••"
                    disabled={isLoading}
                  />
                </div>

                {/* Submit Button */}
                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full bg-orange hover:bg-orange-dark text-white font-medium py-3 px-4 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isLoading ? t('login.buttonLoading') : t('login.button')}
                </button>
              </form>
            )}

          </div>

          {/* Footer */}
          <p className="mt-8 text-center text-sm text-gray-600">
            {t('login.termsNotice')}{' '}
            <Link to="/terms" className="text-orange hover:text-orange-dark">
              {t('login.termsLink')}
            </Link>{' '}
            {t('login.and')}{' '}
            <Link to="/privacy" className="text-orange hover:text-orange-dark">
              {t('login.privacyLink')}
            </Link>
            .
          </p>
        </div>
      </main>
    </div>
  )
}
