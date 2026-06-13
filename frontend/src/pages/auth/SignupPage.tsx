/**
 * Signup Page
 *
 * Handles user registration for BigMCP.
 * Cloud users access the free demo platform. Self-hosted users register to get started.
 */

import { useState, FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../hooks/useAuth'
import { InstanceLogoWithText } from '../../components/brand/InstanceLogo'
import { useBranding } from '../../contexts/BrandingContext'
import { usePageMeta } from '../../hooks/usePageMeta'
import { PasswordStrengthMeter } from '../../components/auth'

export function SignupPage() {
  const { t } = useTranslation('auth')
  const { t: tCommon } = useTranslation('common')
  const navigate = useNavigate()
  const { signup, deploymentConfig } = useAuth()
  const { branding } = useBranding()

  usePageMeta({
    title: tCommon('meta.signup.title'),
    description: tCommon('meta.signup.description'),
  })

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [acceptedTerms, setAcceptedTerms] = useState(false)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')

    // Validation
    if (password !== confirmPassword) {
      setError(t('signup.errors.passwordMismatch'))
      return
    }

    if (password.length < 8) {
      setError(t('signup.errors.weakPassword'))
      return
    }

    if (!acceptedTerms) {
      setError(t('signup.termsRequired'))
      return
    }

    setIsLoading(true)

    try {
      await signup(email, password, fullName)

      // Redirect to onboarding or app
      if (deploymentConfig.is_cloud) {
        navigate('/onboarding')
      } else {
        navigate('/app/my-servers')
      }
    } catch (err: any) {
      // SaaS mode: Redirect to verification pending page
      if (err.requiresVerification) {
        navigate('/verify-email-pending', {
          state: { email: err.email || email },
          replace: true
        })
        return
      }
      setError(err instanceof Error ? err.message : 'Signup failed. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link to="/" className="flex items-center">
              <InstanceLogoWithText size="sm" textSize="md" />
            </Link>

            <Link
              to="/login"
              className="text-sm text-gray-600 hover:text-gray-900 transition-colors"
            >
              {t('signup.hasAccount')} <span className="text-orange font-medium">{t('signup.loginLink')}</span>
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
                {deploymentConfig.is_cloud
                  ? t('signup.titleCloud', { brand: branding.instance_name })
                  : t('signup.titleSelfHosted', { brand: branding.instance_name })}
              </h1>
              <p className="text-gray-600">
                {deploymentConfig.is_cloud
                  ? t('signup.subtitleCloud')
                  : t('signup.subtitleSelfHosted')}
              </p>
            </div>

            {/* Error Message */}
            {error && (
              <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-800">{error}</p>
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Full Name */}
              <div>
                <label htmlFor="fullName" className="block text-sm font-medium text-gray-700 mb-2">
                  {t('signup.fullName')}
                </label>
                <input
                  id="fullName"
                  type="text"
                  required
                  autoComplete="name"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-transparent transition-shadow"
                  placeholder="John Doe"
                  disabled={isLoading}
                />
              </div>

              {/* Email */}
              <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
                  {t('signup.email')}
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
                <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-2">
                  {t('signup.password')}
                </label>
                <input
                  id="password"
                  type="password"
                  required
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-transparent transition-shadow"
                  placeholder="••••••••"
                  disabled={isLoading}
                />
                <p className="mt-1 text-xs text-gray-500">{t('signup.passwordHint')}</p>
                <PasswordStrengthMeter password={password} />
              </div>

              {/* Confirm Password */}
              <div>
                <label
                  htmlFor="confirmPassword"
                  className="block text-sm font-medium text-gray-700 mb-2"
                >
                  {t('signup.confirmPassword')}
                </label>
                <input
                  id="confirmPassword"
                  type="password"
                  required
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-transparent transition-shadow"
                  placeholder="••••••••"
                  disabled={isLoading}
                />
              </div>

              {/* Terms Acceptance */}
              <div className="flex items-start">
                <input
                  id="terms"
                  type="checkbox"
                  checked={acceptedTerms}
                  onChange={(e) => setAcceptedTerms(e.target.checked)}
                  className="mt-1 h-4 w-4 text-orange focus:ring-orange border-gray-300 rounded"
                  disabled={isLoading}
                />
                <label htmlFor="terms" className="ml-2 text-sm text-gray-600">
                  {t('signup.termsAgree')}{' '}
                  <Link to="/terms" className="text-orange hover:text-orange-dark">
                    {t('signup.termsLink')}
                  </Link>{' '}
                  {t('signup.and')}{' '}
                  <Link to="/privacy" className="text-orange hover:text-orange-dark">
                    {t('signup.privacyLink')}
                  </Link>
                </label>
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={isLoading}
                className="w-full bg-orange hover:bg-orange-dark text-white font-medium py-3 px-4 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading
                  ? t('signup.buttonLoading')
                  : deploymentConfig.is_cloud
                    ? t('signup.buttonCloud')
                    : t('signup.button')}
              </button>
            </form>

            {/* OAuth Divider / buttons removed — they were always
                disabled placeholders ("coming soon"). When real
                per-user OAuth providers ship, gate this section on a
                deploymentConfig flag (e.g. oauth_providers_enabled)
                so we don't show greyed-out CTAs in the meantime. */}
          </div>

          {/* Trial Info for Cloud */}
          {deploymentConfig.is_cloud && (
            <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <h3 className="text-sm font-medium text-blue-900 mb-1">
                {t('signup.trialInfo.title')}
              </h3>
              <ul className="text-sm text-blue-800 space-y-1">
                <li>• {t('signup.trialInfo.feature1')}</li>
                <li>• {t('signup.trialInfo.feature2')}</li>
                <li>• {t('signup.trialInfo.feature3')}</li>
                <li>• {t('signup.trialInfo.feature4')}</li>
              </ul>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
