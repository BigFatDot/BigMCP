/**
 * Backup Codes Display Component
 *
 * Displays backup codes in a grid with copy functionality.
 */

import { useState } from 'react'
import { ClipboardDocumentIcon, CheckIcon } from '@heroicons/react/24/outline'
import { cn } from '@/utils/cn'

interface BackupCodesDisplayProps {
  codes: string[]
  className?: string
}

/**
 * Displays MFA backup codes in a 2-column grid with copy-all button.
 */
export function BackupCodesDisplay({ codes, className }: BackupCodesDisplayProps) {
  const [copied, setCopied] = useState(false)

  const handleCopyAll = async () => {
    const text = codes.join('\n')
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy backup codes:', err)
    }
  }

  return (
    <div className={cn('space-y-4', className)}>
      {/* Instructions */}
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
        <p className="text-sm text-amber-800">
          <strong>Important:</strong> Save these backup codes in a secure location.
          Each code can only be used once to access your account if you lose your authenticator device.
        </p>
      </div>

      {/* Codes Grid */}
      <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
        <div className="grid grid-cols-2 gap-2">
          {codes.map((code, index) => (
            <div
              key={index}
              className="font-mono text-sm bg-white px-3 py-2 rounded border border-gray-200 text-center"
            >
              {code}
            </div>
          ))}
        </div>
      </div>

      {/* Copy Button */}
      <button
        type="button"
        onClick={handleCopyAll}
        className={cn(
          'w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg',
          'text-sm font-medium transition-all duration-200',
          copied
            ? 'bg-green-100 text-green-700 border border-green-300'
            : 'bg-gray-100 text-gray-700 hover:bg-gray-200 border border-gray-300'
        )}
      >
        {copied ? (
          <>
            <CheckIcon className="w-4 h-4" />
            <span>Copied!</span>
          </>
        ) : (
          <>
            <ClipboardDocumentIcon className="w-4 h-4" />
            <span>Copy All Codes</span>
          </>
        )}
      </button>
    </div>
  )
}
