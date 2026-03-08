/**
 * MFA Disable Modal Component
 *
 * Modal to disable Two-Factor Authentication.
 * Requires current TOTP code for security.
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { TOTPInput } from './TOTPInput'
import { mfaApi } from '@/services/marketplace'

interface MFADisableModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
}

/**
 * MFA Disable Modal with TOTP verification.
 */
export function MFADisableModal({ isOpen, onClose, onSuccess }: MFADisableModalProps) {
  const { t } = useTranslation('settings')
  const [totpCode, setTotpCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isDisabling, setIsDisabling] = useState(false)

  const handleClose = () => {
    setTotpCode('')
    setError(null)
    onClose()
  }

  const handleDisable = async () => {
    if (totpCode.length !== 6) {
      setError(t('account.mfa.disable.invalidCode'))
      return
    }

    setIsDisabling(true)
    setError(null)

    try {
      await mfaApi.disable(totpCode)
      onSuccess()
      handleClose()
    } catch (err: any) {
      console.error('Failed to disable MFA:', err)
      setError(err.response?.data?.detail || t('account.mfa.disable.failed'))
      setTotpCode('')
    } finally {
      setIsDisabling(false)
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={t('account.mfa.disable.title')}
      size="sm"
    >
      <div className="space-y-6">
        {/* Warning */}
        <div className="flex items-start gap-3 p-4 bg-red-50 rounded-lg border border-red-200">
          <ExclamationTriangleIcon className="w-6 h-6 text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm text-red-900 font-medium">{t('account.mfa.disable.warningTitle')}</p>
            <p className="text-sm text-red-700 mt-1">{t('account.mfa.disable.warning')}</p>
          </div>
        </div>

        {/* Instructions */}
        <p className="text-sm text-gray-600">{t('account.mfa.disable.enterCode')}</p>

        {/* TOTP Input */}
        <TOTPInput
          value={totpCode}
          onChange={setTotpCode}
          autoFocus
          error={error || undefined}
        />

        {/* Actions */}
        <div className="flex gap-3">
          <Button variant="secondary" onClick={handleClose} className="flex-1">
            {t('account.cancel')}
          </Button>
          <Button
            variant="danger"
            onClick={handleDisable}
            className="flex-1"
            disabled={totpCode.length !== 6 || isDisabling}
            isLoading={isDisabling}
          >
            {t('account.mfa.disable.confirm')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
