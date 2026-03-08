/**
 * Signup Page
 *
 * Handles user registration for BigMCP.
 * Cloud users get a 15-day trial. Self-hosted users register to get API keys.
 */

import { useState, FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../hooks/useAuth'
import { BigMCPLogoWithText } from '../../components/brand/BigMCPLogo'

export function SignupPage() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const { signup, deploymentConfig } = useAuth()

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
              <BigMCPLogoWithText size="sm" textSize="md" />
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
                {deploymentConfig.is_cloud ? t('signup.titleCloud') : t('signup.titleSelfHosted')}
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

            {/* OAuth Divider */}
            <div className="mt-8">
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-300" />
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="px-2 bg-white text-gray-500">{t('login.orContinueWith')}</span>
                </div>
              </div>

              {/* OAuth Buttons (coming soon) */}
              <div className="mt-6 grid grid-cols-2 gap-3">
                <button
                  type="button"
                  disabled
                  className="flex items-center justify-center px-4 py-2 border border-gray-300 rounded-lg bg-white text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24">
                    <path
                      fill="currentColor"
                      d="M12.545,10.239v3.821h5.445c-0.712,2.315-2.647,3.972-5.445,3.972c-3.332,0-6.033-2.701-6.033-6.032s2.701-6.032,6.033-6.032c1.498,0,2.866,0.549,3.921,1.453l2.814-2.814C17.503,2.988,15.139,2,12.545,2C7.021,2,2.543,6.477,2.543,12s4.478,10,10.002,10c8.396,0,10.249-7.85,9.426-11.748L12.545,10.239z"
                    />
                  </svg>
                  Google
                </button>
                <button
                  type="button"
                  disabled
                  className="flex items-center justify-center px-4 py-2 border border-gray-300 rounded-lg bg-white text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24">
                    <path
                      fill="currentColor"
                      d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"
                    />
                  </svg>
                  GitHub
                </button>
              </div>
            </div>
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
