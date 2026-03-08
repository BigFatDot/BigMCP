/**
 * Verify Email Pending Page
 *
 * Shown after signup in SaaS mode. Instructs user to check their email
 * for the verification link. Includes option to resend the email.
 */

import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { BigMCPLogoWithText } from '../../components/brand/BigMCPLogo'
import { EnvelopeIcon, ArrowPathIcon, CheckCircleIcon } from '@heroicons/react/24/outline'

const API_BASE = '/api/v1'

export function VerifyEmailPendingPage() {
  const { t } = useTranslation('auth')
  const location = useLocation()
  const email = location.state?.email || ''

  const [isResending, setIsResending] = useState(false)
  const [resendSuccess, setResendSuccess] = useState(false)
  const [resendError, setResendError] = useState('')

  const handleResendEmail = async () => {
    if (!email) {
      setResendError(t('verify.noEmailAvailable'))
      return
    }

    setIsResending(true)
    setResendError('')
    setResendSuccess(false)

    try {
      const response = await fetch(`${API_BASE}/auth/resend-verification-public?email=${encodeURIComponent(email)}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        setResendSuccess(true)
      } else {
        const data = await response.json()
        setResendError(data.detail || t('verify.resendFailed'))
      }
    } catch (err) {
      setResendError(t('verify.resendFailedLater'))
    } finally {
      setIsResending(false)
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
            {/* Icon */}
            <div className="mx-auto w-16 h-16 bg-orange-100 rounded-full flex items-center justify-center mb-6">
              <EnvelopeIcon className="w-8 h-8 text-orange" />
            </div>

            {/* Title */}
            <h1 className="text-2xl font-serif font-bold text-gray-900 mb-3">
              {t('verify.titlePending')}
            </h1>

            {/* Description */}
            <p className="text-gray-600 mb-2">
              {t('verify.subtitleSentTo')}
            </p>
            {email && (
              <p className="font-medium text-gray-900 mb-6">
                {email}
              </p>
            )}

            <p className="text-gray-600 mb-8">
              {t('verify.clickToVerify')}
            </p>

            {/* Resend Success */}
            {resendSuccess && (
              <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg flex items-center gap-2">
                <CheckCircleIcon className="w-5 h-5 text-green-600 flex-shrink-0" />
                <p className="text-sm text-green-800">
                  {t('verify.resentFull')}
                </p>
              </div>
            )}

            {/* Resend Error */}
            {resendError && (
              <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-800">{resendError}</p>
              </div>
            )}

            {/* Actions */}
            <div className="space-y-4">
              {/* Resend Button */}
              <button
                onClick={handleResendEmail}
                disabled={isResending || resendSuccess}
                className="w-full flex items-center justify-center gap-2 bg-orange hover:bg-orange-dark text-white font-medium py-3 px-4 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isResending ? (
                  <>
                    <ArrowPathIcon className="w-5 h-5 animate-spin" />
                    {t('verify.resending')}
                  </>
                ) : resendSuccess ? (
                  <>
                    <CheckCircleIcon className="w-5 h-5" />
                    {t('verify.emailSent')}
                  </>
                ) : (
                  <>
                    <ArrowPathIcon className="w-5 h-5" />
                    {t('verify.resend')}
                  </>
                )}
              </button>

              {/* Login Link */}
              <p className="text-sm text-gray-600">
                {t('verify.alreadyVerifiedQuestion')}{' '}
                <Link to="/login" className="text-orange hover:text-orange-dark font-medium">
                  {t('login.button')}
                </Link>
              </p>
            </div>

            {/* Help Text */}
            <div className="mt-8 pt-6 border-t border-gray-200">
              <p className="text-sm text-gray-500">
                {t('verify.helpText')}{' '}
                <a
                  href="mailto:support@bigmcp.cloud"
                  className="text-orange hover:text-orange-dark"
                >
                  {t('verify.contactSupport')}
                </a>
                .
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
