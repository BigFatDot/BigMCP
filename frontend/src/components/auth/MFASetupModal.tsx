/**
 * MFA Setup Modal Component
 *
 * Multi-step modal for setting up Two-Factor Authentication:
 * 1. Display QR code for authenticator app
 * 2. Show backup codes with copy option
 * 3. Verify TOTP code to activate MFA
 */

import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { QRCodeSVG } from 'qrcode.react'
import {
  ShieldCheckIcon,
  DevicePhoneMobileIcon,
  KeyIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { TOTPInput } from './TOTPInput'
import { BackupCodesDisplay } from './BackupCodesDisplay'
import { mfaApi } from '@/services/marketplace'

interface MFASetupModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
}

type SetupStep = 'loading' | 'qrcode' | 'backup' | 'verify' | 'success'

/**
 * MFA Setup Modal with multi-step flow:
 * 1. QR Code scanning
 * 2. Backup codes display
 * 3. TOTP verification
 * 4. Success confirmation
 */
export function MFASetupModal({ isOpen, onClose, onSuccess }: MFASetupModalProps) {
  const { t } = useTranslation('settings')
  const [step, setStep] = useState<SetupStep>('loading')
  const [provisioningUri, setProvisioningUri] = useState('')
  const [backupCodes, setBackupCodes] = useState<string[]>([])
  const [totpCode, setTotpCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isVerifying, setIsVerifying] = useState(false)

  // Initialize MFA setup when modal opens
  useEffect(() => {
    if (isOpen) {
      initializeSetup()
    } else {
      // Reset state when modal closes
      setStep('loading')
      setProvisioningUri('')
      setBackupCodes([])
      setTotpCode('')
      setError(null)
    }
  }, [isOpen])

  const initializeSetup = async () => {
    setStep('loading')
    setError(null)
    try {
      const response = await mfaApi.setup()
      setProvisioningUri(response.provisioning_uri)
      setBackupCodes(response.backup_codes)
      setStep('qrcode')
    } catch (err: any) {
      console.error('Failed to initialize MFA setup:', err)
      setError(err.response?.data?.detail || 'Failed to initialize MFA setup')
      setStep('qrcode') // Show error in QR step
    }
  }

  const handleVerify = async () => {
    if (totpCode.length !== 6) {
      setError(t('account.mfa.setup.invalidCode'))
      return
    }

    setIsVerifying(true)
    setError(null)

    try {
      await mfaApi.verify(totpCode)
      setStep('success')
      // Delay before closing to show success message
      setTimeout(() => {
        onSuccess()
        onClose()
      }, 2000)
    } catch (err: any) {
      console.error('Failed to verify TOTP code:', err)
      setError(err.response?.data?.detail || t('account.mfa.setup.verifyFailed'))
      setTotpCode('')
    } finally {
      setIsVerifying(false)
    }
  }

  const renderContent = () => {
    switch (step) {
      case 'loading':
        return (
          <div className="flex flex-col items-center py-8">
            <div className="animate-spin rounded-full h-12 w-12 border-2 border-gray-300 border-t-indigo-600 mb-4" />
            <p className="text-gray-600">{t('account.mfa.setup.initializing')}</p>
          </div>
        )

      case 'qrcode':
        return (
          <div className="space-y-6">
            {/* Step indicator */}
            <div className="flex items-center justify-center gap-2 text-sm text-gray-500">
              <span className="w-6 h-6 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-medium">1</span>
              <span className="text-indigo-600 font-medium">{t('account.mfa.setup.step1')}</span>
              <span className="w-8 h-0.5 bg-gray-200" />
              <span className="w-6 h-6 rounded-full bg-gray-200 text-gray-500 flex items-center justify-center text-xs">2</span>
              <span className="w-8 h-0.5 bg-gray-200" />
              <span className="w-6 h-6 rounded-full bg-gray-200 text-gray-500 flex items-center justify-center text-xs">3</span>
            </div>

            {/* Instructions */}
            <div className="flex items-start gap-3 p-4 bg-blue-50 rounded-lg">
              <DevicePhoneMobileIcon className="w-6 h-6 text-blue-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm text-blue-900 font-medium">{t('account.mfa.setup.scanTitle')}</p>
                <p className="text-sm text-blue-700 mt-1">{t('account.mfa.setup.step1Desc')}</p>
              </div>
            </div>

            {/* QR Code */}
            {provisioningUri ? (
              <div className="flex justify-center p-6 bg-white border border-gray-200 rounded-lg">
                <QRCodeSVG value={provisioningUri} size={200} />
              </div>
            ) : error ? (
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-700">{error}</p>
              </div>
            ) : null}

            {/* Actions */}
            <div className="flex gap-3">
              <Button variant="secondary" onClick={onClose} className="flex-1">
                {t('account.cancel')}
              </Button>
              <Button
                variant="primary"
                onClick={() => setStep('backup')}
                className="flex-1 bg-indigo-600 hover:bg-indigo-700"
                disabled={!provisioningUri}
              >
                {t('account.mfa.setup.next')}
              </Button>
            </div>
          </div>
        )

      case 'backup':
        return (
          <div className="space-y-6">
            {/* Step indicator */}
            <div className="flex items-center justify-center gap-2 text-sm text-gray-500">
              <span className="w-6 h-6 rounded-full bg-green-500 text-white flex items-center justify-center text-xs">
                <CheckCircleIcon className="w-4 h-4" />
              </span>
              <span className="w-8 h-0.5 bg-green-500" />
              <span className="w-6 h-6 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-medium">2</span>
              <span className="text-indigo-600 font-medium">{t('account.mfa.setup.step2')}</span>
              <span className="w-8 h-0.5 bg-gray-200" />
              <span className="w-6 h-6 rounded-full bg-gray-200 text-gray-500 flex items-center justify-center text-xs">3</span>
            </div>

            {/* Instructions */}
            <div className="flex items-start gap-3 p-4 bg-amber-50 rounded-lg">
              <KeyIcon className="w-6 h-6 text-amber-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm text-amber-900 font-medium">{t('account.mfa.setup.backupTitle')}</p>
                <p className="text-sm text-amber-700 mt-1">{t('account.mfa.setup.step2Desc')}</p>
              </div>
            </div>

            {/* Backup Codes */}
            <BackupCodesDisplay codes={backupCodes} />

            {/* Actions */}
            <div className="flex gap-3">
              <Button variant="secondary" onClick={() => setStep('qrcode')} className="flex-1">
                {t('account.mfa.setup.back')}
              </Button>
              <Button
                variant="primary"
                onClick={() => setStep('verify')}
                className="flex-1 bg-indigo-600 hover:bg-indigo-700"
              >
                {t('account.mfa.setup.next')}
              </Button>
            </div>
          </div>
        )

      case 'verify':
        return (
          <div className="space-y-6">
            {/* Step indicator */}
            <div className="flex items-center justify-center gap-2 text-sm text-gray-500">
              <span className="w-6 h-6 rounded-full bg-green-500 text-white flex items-center justify-center text-xs">
                <CheckCircleIcon className="w-4 h-4" />
              </span>
              <span className="w-8 h-0.5 bg-green-500" />
              <span className="w-6 h-6 rounded-full bg-green-500 text-white flex items-center justify-center text-xs">
                <CheckCircleIcon className="w-4 h-4" />
              </span>
              <span className="w-8 h-0.5 bg-green-500" />
              <span className="w-6 h-6 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-medium">3</span>
              <span className="text-indigo-600 font-medium">{t('account.mfa.setup.step3')}</span>
            </div>

            {/* Instructions */}
            <div className="flex items-start gap-3 p-4 bg-indigo-50 rounded-lg">
              <ShieldCheckIcon className="w-6 h-6 text-indigo-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm text-indigo-900 font-medium">{t('account.mfa.setup.verifyTitle')}</p>
                <p className="text-sm text-indigo-700 mt-1">{t('account.mfa.setup.step3Desc')}</p>
              </div>
            </div>

            {/* TOTP Input */}
            <div className="py-4">
              <TOTPInput
                value={totpCode}
                onChange={setTotpCode}
                autoFocus
                error={error || undefined}
              />
            </div>

            {/* Actions */}
            <div className="flex gap-3">
              <Button variant="secondary" onClick={() => setStep('backup')} className="flex-1">
                {t('account.mfa.setup.back')}
              </Button>
              <Button
                variant="primary"
                onClick={handleVerify}
                className="flex-1 bg-indigo-600 hover:bg-indigo-700"
                disabled={totpCode.length !== 6 || isVerifying}
                isLoading={isVerifying}
              >
                {t('account.mfa.setup.activate')}
              </Button>
            </div>
          </div>
        )

      case 'success':
        return (
          <div className="flex flex-col items-center py-8 text-center">
            <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mb-4">
              <CheckCircleIcon className="w-8 h-8 text-green-600" />
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              {t('account.mfa.setup.successTitle')}
            </h3>
            <p className="text-gray-600">
              {t('account.mfa.setup.successDesc')}
            </p>
          </div>
        )

      default:
        return null
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={step === 'success' ? () => {} : onClose}
      title={t('account.mfa.setup.title')}
      size="md"
      showClose={step !== 'success'}
    >
      {renderContent()}
    </Modal>
  )
}
