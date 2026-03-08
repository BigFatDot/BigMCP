/**
 * Accept Invitation Page
 *
 * Handles team invitation acceptance flow:
 * - Shows invitation details
 * - For logged-in users: Accept directly
 * - For new users: Register + accept in one step
 * - For existing users not logged in: Redirect to login
 */

import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../contexts/AuthContext'

// API base URL
const API_BASE = '/api/v1'

interface InvitationInfo {
  organization_name: string
  organization_slug: string
  inviter_name: string | null
  inviter_email: string
  role: string
  email: string
  expires_at: string
  is_expired: boolean
}

export function AcceptInvitationPage() {
  const { t } = useTranslation('auth')
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const { isAuthenticated, user, refreshUser } = useAuth()

  const [invitationInfo, setInvitationInfo] = useState<InvitationInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [accepting, setAccepting] = useState(false)

  // Registration form state (for new users)
  const [showRegisterForm, setShowRegisterForm] = useState(false)
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [registerError, setRegisterError] = useState<string | null>(null)

  // Fetch invitation info on mount
  useEffect(() => {
    if (!token) {
      setError(t('invitation.invalidLink'))
      setLoading(false)
      return
    }

    fetchInvitationInfo()
  }, [token, t])

  const fetchInvitationInfo = async () => {
    try {
      const response = await fetch(`${API_BASE}/organizations/invitations/${token}/info`)

      if (!response.ok) {
        if (response.status === 404) {
          setError(t('invitation.invalid'))
        } else {
          setError(t('invitation.failedToLoad'))
        }
        return
      }

      const data = await response.json()
      setInvitationInfo(data)

      if (data.is_expired) {
        setError(t('invitation.expired'))
      }
    } catch (err: any) {
      setError(t('invitation.failedToLoad'))
    } finally {
      setLoading(false)
    }
  }

  // Accept invitation (for logged-in users)
  const handleAccept = async () => {
    if (!token) return

    setAccepting(true)
    setError(null)

    try {
      const accessToken = localStorage.getItem('bigmcp_access_token')
      const response = await fetch(`${API_BASE}/organizations/invitations/${token}/accept`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Failed to accept invitation')
      }

      await refreshUser()
      navigate('/app/organization', { replace: true })
    } catch (err: any) {
      setError(err.message || 'Failed to accept invitation')
      setAccepting(false)
    }
  }

  // Register + accept (for new users)
  const handleRegisterAndAccept = async (e: React.FormEvent) => {
    e.preventDefault()

    if (password !== confirmPassword) {
      setRegisterError(t('invitation.passwordMismatch'))
      return
    }

    if (password.length < 8) {
      setRegisterError(t('invitation.passwordTooShort'))
      return
    }

    setAccepting(true)
    setRegisterError(null)

    try {
      const response = await fetch(`${API_BASE}/organizations/invitations/${token}/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: name || undefined,
          password,
        }),
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Failed to create account')
      }

      const data = await response.json()

      // Store tokens (use same keys as AuthContext)
      localStorage.setItem('bigmcp_access_token', data.access_token)
      localStorage.setItem('bigmcp_refresh_token', data.refresh_token)

      // Refresh user context and redirect
      await refreshUser()
      navigate('/app/organization', { replace: true })
    } catch (err: any) {
      setRegisterError(err.message || 'Failed to create account')
      setAccepting(false)
    }
  }

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-2 border-gray-300 border-t-orange-500 mx-auto mb-4" />
          <p className="text-gray-600">{t('invitation.loading')}</p>
        </div>
      </div>
    )
  }

  // Error state
  if (error && !invitationInfo) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="max-w-md w-full bg-white rounded-xl shadow-lg p-8 text-center">
          <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
          <h1 className="text-xl font-semibold text-gray-900 mb-2">{t('invitation.titleInvalid')}</h1>
          <p className="text-gray-600 mb-6">{error}</p>
          <Link
            to="/login"
            className="inline-block bg-orange-500 text-white px-6 py-2 rounded-lg font-medium hover:bg-orange-600 transition-colors"
          >
            {t('invitation.goToLogin')}
          </Link>
        </div>
      </div>
    )
  }

  // Registration form for new users
  if (showRegisterForm && invitationInfo) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4 py-12">
        <div className="max-w-md w-full">
          <div className="bg-white rounded-xl shadow-lg overflow-hidden">
            {/* Header */}
            <div className="bg-orange-500 px-6 py-8 text-center">
              <h1 className="text-2xl font-bold text-white">BigMCP</h1>
            </div>

            {/* Content */}
            <div className="p-6">
              <h2 className="text-xl font-semibold text-gray-900 mb-2">{t('signup.title')}</h2>
              <p className="text-gray-600 mb-6">
                {t('invitation.joinAs')} <strong>{invitationInfo.organization_name}</strong> {t('invitation.asRole', { role: invitationInfo.role })}
              </p>

              <form onSubmit={handleRegisterAndAccept} className="space-y-4">
                {/* Email (readonly) */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{t('invitation.email')}</label>
                  <input
                    type="email"
                    value={invitationInfo.email}
                    disabled
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-100 text-gray-600"
                  />
                </div>

                {/* Name */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    {t('invitation.name')} <span className="text-gray-400">{t('invitation.nameOptional')}</span>
                  </label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder={t('invitation.name')}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-transparent"
                  />
                </div>

                {/* Password */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{t('invitation.password')}</label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={t('invitation.passwordHint')}
                    required
                    minLength={8}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-transparent"
                  />
                </div>

                {/* Confirm Password */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{t('invitation.confirmPassword')}</label>
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder={t('invitation.confirmPasswordHint')}
                    required
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-transparent"
                  />
                </div>

                {registerError && (
                  <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-lg text-sm">
                    {registerError}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={accepting}
                  className="w-full bg-orange-500 text-white py-3 rounded-lg font-medium hover:bg-orange-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {accepting ? t('invitation.creatingAccount') : t('invitation.createAccount')}
                </button>
              </form>

              <p className="text-center text-sm text-gray-500 mt-4">
                {t('invitation.alreadyHaveAccountQuestion')}{' '}
                <Link to={`/login?redirect=/invitations/${token}/accept`} className="text-orange-500 hover:underline">
                  {t('invitation.logIn')}
                </Link>
              </p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Main invitation view
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4 py-12">
      <div className="max-w-md w-full">
        <div className="bg-white rounded-xl shadow-lg overflow-hidden">
          {/* Header */}
          <div className="bg-orange-500 px-6 py-8 text-center">
            <h1 className="text-2xl font-bold text-white">BigMCP</h1>
          </div>

          {/* Content */}
          <div className="p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-2">{t('invitation.title')}</h2>

            {invitationInfo && (
              <>
                <p className="text-gray-600 mb-6">
                  {t('invitation.invitedBy', { inviter: invitationInfo.inviter_name || invitationInfo.inviter_email })}{' '}
                  <strong className="text-gray-900">{invitationInfo.organization_name}</strong>{' '}
                  {t('invitation.asRole', { role: invitationInfo.role })}
                </p>

                {error && (
                  <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-lg text-sm mb-4">
                    {error}
                  </div>
                )}

                {isAuthenticated ? (
                  // Logged in - show accept button
                  <>
                    <p className="text-sm text-gray-500 mb-4">
                      {t('invitation.loggedInAs')} <strong>{user?.email}</strong>
                    </p>

                    {user?.email?.toLowerCase() === invitationInfo.email.toLowerCase() ? (
                      <button
                        onClick={handleAccept}
                        disabled={accepting}
                        className="w-full bg-orange-500 text-white py-3 rounded-lg font-medium hover:bg-orange-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {accepting ? t('invitation.accepting') : t('invitation.accept')}
                      </button>
                    ) : (
                      <div className="bg-amber-50 border border-amber-200 text-amber-700 px-4 py-3 rounded-lg text-sm">
                        {t('invitation.wrongEmail')} <strong>{invitationInfo.email}</strong>{t('invitation.wrongEmailSuffix')}
                      </div>
                    )}
                  </>
                ) : (
                  // Not logged in - show options
                  <div className="space-y-3">
                    <button
                      onClick={() => setShowRegisterForm(true)}
                      className="w-full bg-orange-500 text-white py-3 rounded-lg font-medium hover:bg-orange-600 transition-colors"
                    >
                      {t('invitation.createAccount')}
                    </button>

                    <Link
                      to={`/login?redirect=/invitations/${token}/accept`}
                      className="block w-full text-center border border-gray-300 text-gray-700 py-3 rounded-lg font-medium hover:bg-gray-50 transition-colors"
                    >
                      {t('invitation.alreadyHaveAccount')}
                    </Link>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Footer */}
          <div className="px-6 py-4 bg-gray-50 text-center">
            <p className="text-xs text-gray-500">
              {t('invitation.expiresOn')}{' '}
              {invitationInfo && new Date(invitationInfo.expires_at).toLocaleDateString()}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
