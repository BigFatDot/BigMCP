/**
 * Account Page
 *
 * User account settings including profile, password, and account deletion.
 * Edition-aware sections:
 * - Community: Profile, Password, License, Danger Zone
 * - Enterprise: Profile, Password, License, Instance Admin, Danger Zone
 * - Cloud SaaS: Profile, Password, Danger Zone (no license or admin sections)
 */

import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
  UserCircleIcon,
  KeyIcon,
  TrashIcon,
  ShieldCheckIcon,
  BuildingOfficeIcon,
  CheckCircleIcon,
  ArrowUpIcon,
} from '@heroicons/react/24/outline'
import { Button, Card } from '@/components/ui'
import { MFASetupModal, MFADisableModal } from '@/components/auth'
import { useAuth, useEdition } from '@/hooks/useAuth'
import { useInstanceAdmin } from '@/hooks/useInstanceAdmin'
import { authApi, mfaApi } from '@/services/marketplace'
import type { MFAStatus } from '@/types/auth'

// SaaS platform URL for license purchases
const SAAS_URL = 'https://app.bigmcp.cloud'

// Enterprise plan info
const ENTERPRISE_PLAN = {
  price: 'Free',
  priceNote: 'launch offer • 3 months',
  features: [
    'Unlimited users',
    'SSO / SAML authentication',
    'Full audit logs',
    'Custom branding',
    'Priority support',
    'Perpetual license',
  ],
}

export function AccountPage() {
  const { t } = useTranslation('settings')
  const { user, logout, refreshUser } = useAuth()
  const { edition, editionLoading, isCloudSaaS, isEnterprise, isCommunity, licenseOrg, licenseFeatures } = useEdition()
  const {
    isInstanceAdmin,
    isLoading: adminLoading,
    error: adminError,
    requiresToken,
    tokenHint,
    validateToken,
  } = useInstanceAdmin()

  const [isEditing, setIsEditing] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [name, setName] = useState(user?.name || '')
  const [email] = useState(user?.email || '')  // Email is read-only
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Sync name state with user context when user changes
  useEffect(() => {
    if (user?.name !== undefined) {
      setName(user.name || '')
    }
  }, [user?.name])

  // Auto-clear success message after 3 seconds
  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => setSuccess(null), 3000)
      return () => clearTimeout(timer)
    }
  }, [success])

  // Password change modal state
  const [showPasswordModal, setShowPasswordModal] = useState(false)
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isChangingPassword, setIsChangingPassword] = useState(false)

  // Admin token state (Enterprise only)
  const [adminToken, setAdminToken] = useState('')
  const [isValidatingToken, setIsValidatingToken] = useState(false)

  // MFA state
  const [mfaStatus, setMfaStatus] = useState<MFAStatus | null>(null)
  const [mfaLoading, setMfaLoading] = useState(true)
  const [showMFASetup, setShowMFASetup] = useState(false)
  const [showMFADisable, setShowMFADisable] = useState(false)

  // Fetch MFA status on mount
  useEffect(() => {
    const fetchMFAStatus = async () => {
      try {
        const status = await mfaApi.getStatus()
        setMfaStatus(status)
      } catch (err) {
        console.error('Failed to fetch MFA status:', err)
      } finally {
        setMfaLoading(false)
      }
    }
    fetchMFAStatus()
  }, [])

  const handleMFASetupSuccess = async () => {
    // Refresh MFA status after enabling
    try {
      const status = await mfaApi.getStatus()
      setMfaStatus(status)
      setSuccess(t('account.mfa.enabledSuccess'))
    } catch (err) {
      console.error('Failed to refresh MFA status:', err)
    }
  }

  const handleMFADisableSuccess = async () => {
    // Refresh MFA status after disabling
    try {
      const status = await mfaApi.getStatus()
      setMfaStatus(status)
      setSuccess(t('account.mfa.disabledSuccess'))
    } catch (err) {
      console.error('Failed to refresh MFA status:', err)
    }
  }

  const handleSaveProfile = async () => {
    setIsSaving(true)
    setError(null)
    setSuccess(null)
    try {
      await authApi.updateProfile({ name })
      await refreshUser()  // Refresh user data in context
      setSuccess(t('account.profile.updated'))
      setIsEditing(false)
    } catch (err: any) {
      console.error('Failed to update profile:', err)
      setError(err.response?.data?.detail || 'Failed to update profile')
    } finally {
      setIsSaving(false)
    }
  }

  const handleChangePassword = async () => {
    if (newPassword !== confirmPassword) {
      setError(t('account.password.mismatch'))
      return
    }
    if (newPassword.length < 8) {
      setError(t('account.password.tooShort'))
      return
    }

    setIsChangingPassword(true)
    setError(null)
    try {
      await authApi.changePassword({
        old_password: oldPassword,
        new_password: newPassword,
      })
      setSuccess(t('account.password.changed'))
      setShowPasswordModal(false)
      setOldPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err: any) {
      console.error('Failed to change password:', err)
      setError(err.response?.data?.detail || 'Failed to change password')
    } finally {
      setIsChangingPassword(false)
    }
  }

  const handleDeleteAccount = async () => {
    if (!confirm(t('account.danger.confirmPrompt'))) {
      return
    }
    // Double confirmation for destructive action
    const confirmText = prompt(t('account.danger.typeDelete'))
    if (confirmText !== 'DELETE') {
      return
    }

    try {
      await authApi.deleteAccount()
      logout()  // Clear session and redirect to login
    } catch (err: any) {
      console.error('Failed to delete account:', err)
      setError(err.response?.data?.detail || 'Failed to delete account')
    }
  }

  // Admin token validation (Enterprise only)
  const handleValidateAdminToken = async () => {
    if (!adminToken.trim()) {
      setError('Please enter an admin token')
      return
    }

    setIsValidatingToken(true)
    setError(null)

    try {
      const success = await validateToken(adminToken)
      if (success) {
        setSuccess(t('account.instanceAdmin.validated'))
        setAdminToken('')
      }
    } catch (err: any) {
      // Error is handled by the hook
    } finally {
      setIsValidatingToken(false)
    }
  }

  return (
    <div className="container py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-gray-900 mb-2">{t('account.title')}</h1>
        <p className="text-lg text-gray-600 font-serif">
          {t('account.subtitle')}
        </p>
      </div>

      {/* Profile Section */}
      <Card padding="lg" className="mb-6">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 bg-orange-100 rounded-full flex items-center justify-center">
            <UserCircleIcon className="w-6 h-6 text-orange" />
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-semibold text-gray-900">{t('account.profile.title')}</h2>
            <p className="text-sm text-gray-600">{t('account.profile.subtitle')}</p>
          </div>
          {isEditing ? (
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => setIsEditing(false)} disabled={isSaving}>
                {t('account.cancel')}
              </Button>
              <Button variant="primary" onClick={handleSaveProfile} disabled={isSaving}>
                {isSaving ? t('account.saving') : t('account.save')}
              </Button>
            </div>
          ) : (
            <Button variant="secondary" onClick={() => setIsEditing(true)}>
              {t('account.profile.edit')}
            </Button>
          )}
        </div>

        {isEditing && (
          <div className="mt-4 pt-4 border-t border-gray-100 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('account.profile.name')}
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('account.profile.email')}
              </label>
              <p className="text-gray-900">{user?.email || t('account.profile.notSet')}</p>
              <p className="text-xs text-gray-500 mt-1">{t('account.profile.emailCannotChange')}</p>
            </div>
          </div>
        )}
      </Card>

      {/* Password Section */}
      <Card padding="lg" className="mb-6">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
            <KeyIcon className="w-6 h-6 text-blue-600" />
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-semibold text-gray-900">{t('account.password.title')}</h2>
            <p className="text-sm text-gray-600">{t('account.password.subtitle')}</p>
          </div>
          <Button variant="secondary" onClick={() => setShowPasswordModal(true)}>
            {t('account.password.change')}
          </Button>
        </div>
      </Card>

      {/* Two-Factor Authentication Section */}
      <Card padding="lg" className="mb-6">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 bg-indigo-100 rounded-full flex items-center justify-center">
            <ShieldCheckIcon className="w-6 h-6 text-indigo-600" />
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-semibold text-gray-900">
              {t('account.mfa.title')}
            </h2>
            <p className="text-sm text-gray-600">
              {mfaStatus?.enabled
                ? t('account.mfa.enabledSubtitle')
                : t('account.mfa.subtitle')}
            </p>
          </div>
          {mfaLoading ? (
            <div className="animate-spin rounded-full h-5 w-5 border-2 border-gray-300 border-t-indigo-600" />
          ) : mfaStatus?.enabled ? (
            <Button
              variant="secondary"
              onClick={() => setShowMFADisable(true)}
              className="text-red-600 border-red-200 hover:bg-red-50"
            >
              {t('account.mfa.disableButton')}
            </Button>
          ) : (
            <Button
              variant="primary"
              onClick={() => setShowMFASetup(true)}
              className="bg-indigo-600 hover:bg-indigo-700"
            >
              {t('account.mfa.enable')}
            </Button>
          )}
        </div>

        {/* Status info when enabled */}
        {mfaStatus?.enabled && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <div className="flex items-center gap-2 text-sm text-green-700">
              <CheckCircleIcon className="w-4 h-4" />
              {t('account.mfa.activeStatus')}
            </div>
            {mfaStatus.backup_codes_remaining !== null && (
              <p className="text-xs text-gray-500 mt-1">
                {t('account.mfa.backupCodesRemaining', {
                  count: mfaStatus.backup_codes_remaining
                })}
              </p>
            )}
          </div>
        )}
      </Card>

      {/* Instance Admin Section - Enterprise Only (First) */}
      {!editionLoading && isEnterprise && (
        <Card padding="lg" className="mb-6 border-indigo-200">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 bg-indigo-100 rounded-full flex items-center justify-center flex-shrink-0">
              <ShieldCheckIcon className="w-6 h-6 text-indigo-600" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <h2 className="text-lg font-semibold text-gray-900">{t('account.instanceAdmin.title')}</h2>
                {isInstanceAdmin && (
                  <span className="inline-block text-xs font-medium px-2 py-1 rounded bg-green-100 text-green-700">
                    {t('account.instanceAdmin.active')}
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-600">
                {t('account.instanceAdmin.subtitle')}
              </p>

              {adminLoading ? (
                <div className="mt-4">
                  <div className="animate-spin rounded-full h-5 w-5 border-2 border-gray-300 border-t-indigo-600" />
                </div>
              ) : isInstanceAdmin ? (
                <div className="mt-4 p-3 bg-green-50 rounded-lg border border-green-200">
                  <p className="text-sm text-green-700">
                    <CheckCircleIcon className="w-4 h-4 inline mr-1" />
                    {t('account.instanceAdmin.hasPrivileges')}
                  </p>
                </div>
              ) : requiresToken ? (
                <form
                  className="mt-4 space-y-3"
                  onSubmit={(e) => {
                    e.preventDefault()
                    handleValidateAdminToken()
                  }}
                >
                  <p className="text-sm text-gray-600">
                    {t('account.instanceAdmin.enterToken')}
                  </p>
                  {tokenHint && (
                    <p className="text-xs text-gray-500">
                      {t('account.instanceAdmin.hint')} {tokenHint}
                    </p>
                  )}
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={adminToken}
                      onChange={(e) => setAdminToken(e.target.value)}
                      placeholder={t('account.instanceAdmin.placeholder')}
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                      autoComplete="off"
                    />
                    <Button
                      type="submit"
                      variant="primary"
                      className="bg-indigo-600 hover:bg-indigo-700"
                      disabled={isValidatingToken || !adminToken.trim()}
                    >
                      {isValidatingToken ? t('account.instanceAdmin.validating') : t('account.instanceAdmin.validate')}
                    </Button>
                  </div>
                  {adminError && (
                    <p className="text-sm text-red-600">{adminError}</p>
                  )}
                </form>
              ) : (
                <div className="mt-4 p-3 bg-amber-50 rounded-lg border border-amber-200">
                  <p className="text-sm text-amber-700">
                    {t('account.instanceAdmin.notConfigured')}
                  </p>
                </div>
              )}
            </div>
          </div>
        </Card>
      )}

      {/* License Section - Enterprise Edition (Second) */}
      {!editionLoading && isEnterprise && (
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
              <h3 className="text-xl font-bold text-gray-900">{licenseOrg || 'Enterprise'}</h3>
              <p className="text-sm text-gray-600 mt-1">
                {t('account.license.enterprise.selfHosted')}
              </p>

              {/* Licensed Features */}
              {licenseFeatures && licenseFeatures.length > 0 && (
                <div className="mt-4">
                  <p className="text-xs font-medium text-gray-500 uppercase mb-2">{t('account.license.enterprise.features')}</p>
                  <div className="flex flex-wrap gap-2">
                    {licenseFeatures.map((feature) => (
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
            </div>
          </div>
        </Card>
      )}

      {/* License Section - Community Edition */}
      {!editionLoading && isCommunity && (
        <Card padding="lg" className="mb-6 border-gray-200">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center flex-shrink-0">
              <BuildingOfficeIcon className="w-6 h-6 text-gray-600" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="inline-block text-xs font-medium uppercase px-2 py-1 rounded bg-gray-100 text-gray-700">
                  {t('account.license.community.badge')}
                </span>
              </div>
              <h3 className="text-xl font-bold text-gray-900">{t('account.license.community.title')}</h3>
              <p className="text-sm text-gray-600 mt-1">
                {t('account.license.community.subtitle')}
              </p>

              {/* Current Features */}
              <div className="mt-4 p-3 bg-gray-50 rounded-lg">
                <p className="text-xs font-medium text-gray-500 uppercase mb-2">{t('account.license.community.included')}</p>
                <ul className="grid md:grid-cols-2 gap-2">
                  <li className="flex items-center gap-2 text-sm text-gray-600">
                    <CheckCircleIcon className="w-4 h-4 text-green-500 flex-shrink-0" />
                    {t('account.license.community.marketplaceAccess')}
                  </li>
                  <li className="flex items-center gap-2 text-sm text-gray-600">
                    <CheckCircleIcon className="w-4 h-4 text-green-500 flex-shrink-0" />
                    {t('account.license.community.mcpServerManagement')}
                  </li>
                  <li className="flex items-center gap-2 text-sm text-gray-600">
                    <CheckCircleIcon className="w-4 h-4 text-green-500 flex-shrink-0" />
                    {t('account.license.community.aiOrchestration')}
                  </li>
                  <li className="flex items-center gap-2 text-sm text-gray-600">
                    <CheckCircleIcon className="w-4 h-4 text-green-500 flex-shrink-0" />
                    {t('account.license.community.instanceAdmin')}
                  </li>
                </ul>
              </div>

              {/* Upgrade CTA */}
              <div className="mt-4 p-4 bg-purple-50 rounded-lg border border-purple-200">
                <div className="flex items-start justify-between">
                  <div>
                    <h4 className="font-semibold text-purple-900">{t('account.license.community.upgradeTitle')}</h4>
                    <p className="text-sm text-purple-700 mt-1">
                      {t('account.license.community.upgradeSubtitle')}
                    </p>
                    <div className="mt-2 flex items-baseline gap-2">
                      <span className="text-2xl font-bold text-purple-900">{ENTERPRISE_PLAN.price}</span>
                      <span className="text-sm text-purple-600">{t('account.license.community.oneTime')}</span>
                    </div>
                  </div>
                  <Button
                    variant="primary"
                    className="bg-purple-600 hover:bg-purple-700 flex-shrink-0"
                    onClick={() => window.open(`${SAAS_URL}/enterprise`, '_blank')}
                  >
                    <ArrowUpIcon className="w-4 h-4 mr-2" />
                    {t('account.license.community.upgrade')}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Danger Zone */}
      <Card padding="lg" className="border-red-200">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center">
            <TrashIcon className="w-6 h-6 text-red-600" />
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-semibold text-red-900">{t('account.danger.title')}</h2>
            <p className="text-sm text-red-600">
              {t('account.danger.subtitle')}
            </p>
          </div>
          <Button
            variant="secondary"
            onClick={handleDeleteAccount}
            className="text-red-600 border-red-200 hover:bg-red-50"
          >
            {t('account.danger.deleteAccount')}
          </Button>
        </div>
      </Card>

      {/* Error/Success Messages */}
      {error && (
        <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          {error}
        </div>
      )}
      {success && (
        <div className="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg text-green-700">
          {success}
        </div>
      )}

      {/* Password Change Modal */}
      {showPasswordModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full mx-4">
            <div className="p-6 border-b border-gray-200">
              <h2 className="text-xl font-bold text-gray-900">{t('account.password.modalTitle')}</h2>
              <p className="text-sm text-gray-600 mt-1">
                {t('account.password.modalSubtitle')}
              </p>
            </div>

            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t('account.password.current')}
                </label>
                <input
                  type="password"
                  value={oldPassword}
                  onChange={(e) => setOldPassword(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange"
                  placeholder={t('account.password.currentPlaceholder')}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t('account.password.new')}
                </label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange"
                  placeholder={t('account.password.newPlaceholder')}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t('account.password.confirm')}
                </label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange"
                  placeholder={t('account.password.confirmPlaceholder')}
                />
              </div>
            </div>

            <div className="p-6 border-t border-gray-200 flex justify-end gap-3">
              <Button
                variant="secondary"
                onClick={() => {
                  setShowPasswordModal(false)
                  setOldPassword('')
                  setNewPassword('')
                  setConfirmPassword('')
                  setError(null)
                }}
                disabled={isChangingPassword}
              >
                {t('account.cancel')}
              </Button>
              <Button
                variant="primary"
                onClick={handleChangePassword}
                disabled={isChangingPassword || !oldPassword || !newPassword || !confirmPassword}
              >
                {isChangingPassword ? t('account.password.changing') : t('account.password.updateButton')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* MFA Setup Modal */}
      <MFASetupModal
        isOpen={showMFASetup}
        onClose={() => setShowMFASetup(false)}
        onSuccess={handleMFASetupSuccess}
      />

      {/* MFA Disable Modal */}
      <MFADisableModal
        isOpen={showMFADisable}
        onClose={() => setShowMFADisable(false)}
        onSuccess={handleMFADisableSuccess}
      />
    </div>
  )
}
