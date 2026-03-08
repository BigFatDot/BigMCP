/**
 * TOTP Input Component
 *
 * 6-digit input for TOTP codes with auto-focus, paste support,
 * and backup code fallback.
 */

import { useRef, useEffect, useState, KeyboardEvent, ClipboardEvent } from 'react'
import { cn } from '@/utils/cn'

interface TOTPInputProps {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  autoFocus?: boolean
  error?: string
  className?: string
}

/**
 * TOTP code input with 6 individual digit boxes.
 * Supports paste, auto-advance, and backspace navigation.
 */
export function TOTPInput({
  value,
  onChange,
  disabled = false,
  autoFocus = false,
  error,
  className,
}: TOTPInputProps) {
  const inputRefs = useRef<(HTMLInputElement | null)[]>([])
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null)

  // Split value into individual digits
  const digits = value.padEnd(6, '').slice(0, 6).split('')

  // Auto-focus first input on mount
  useEffect(() => {
    if (autoFocus && inputRefs.current[0]) {
      inputRefs.current[0].focus()
    }
  }, [autoFocus])

  // Handle single digit input
  const handleInput = (index: number, inputValue: string) => {
    // Only accept digits
    const digit = inputValue.replace(/\D/g, '').slice(-1)

    if (digit) {
      const newDigits = [...digits]
      newDigits[index] = digit
      onChange(newDigits.join(''))

      // Auto-advance to next input
      if (index < 5 && inputRefs.current[index + 1]) {
        inputRefs.current[index + 1]?.focus()
      }
    }
  }

  // Handle paste event (e.g., from authenticator app)
  const handlePaste = (e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault()
    const pastedData = e.clipboardData.getData('text')
    const digits = pastedData.replace(/\D/g, '').slice(0, 6)

    if (digits) {
      onChange(digits)
      // Focus the input after the last pasted digit
      const nextIndex = Math.min(digits.length, 5)
      inputRefs.current[nextIndex]?.focus()
    }
  }

  // Handle keyboard navigation
  const handleKeyDown = (index: number, e: KeyboardEvent<HTMLInputElement>) => {
    switch (e.key) {
      case 'Backspace':
        if (!digits[index] && index > 0) {
          // Move to previous input if current is empty
          inputRefs.current[index - 1]?.focus()
          const newDigits = [...digits]
          newDigits[index - 1] = ''
          onChange(newDigits.join(''))
        } else {
          // Clear current input
          const newDigits = [...digits]
          newDigits[index] = ''
          onChange(newDigits.join(''))
        }
        e.preventDefault()
        break
      case 'ArrowLeft':
        if (index > 0) {
          inputRefs.current[index - 1]?.focus()
        }
        e.preventDefault()
        break
      case 'ArrowRight':
        if (index < 5) {
          inputRefs.current[index + 1]?.focus()
        }
        e.preventDefault()
        break
    }
  }

  return (
    <div className={cn('flex flex-col items-center', className)}>
      <div className="flex gap-2 sm:gap-3">
        {[0, 1, 2, 3, 4, 5].map((index) => (
          <input
            key={index}
            ref={(el) => (inputRefs.current[index] = el)}
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            maxLength={1}
            value={digits[index] || ''}
            disabled={disabled}
            onFocus={() => setFocusedIndex(index)}
            onBlur={() => setFocusedIndex(null)}
            onChange={(e) => handleInput(index, e.target.value)}
            onKeyDown={(e) => handleKeyDown(index, e)}
            onPaste={handlePaste}
            className={cn(
              'w-10 h-12 sm:w-12 sm:h-14 text-center text-xl font-mono font-bold',
              'border-2 rounded-lg transition-all',
              'focus:outline-none focus:ring-2 focus:ring-offset-1',
              'disabled:bg-gray-100 disabled:cursor-not-allowed',
              error
                ? 'border-red-300 focus:ring-red-500 focus:border-red-500'
                : focusedIndex === index
                  ? 'border-indigo-500 ring-2 ring-indigo-200'
                  : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'
            )}
            aria-label={`Digit ${index + 1}`}
          />
        ))}
      </div>

      {error && (
        <p className="mt-2 text-sm text-red-600">{error}</p>
      )}
    </div>
  )
}
