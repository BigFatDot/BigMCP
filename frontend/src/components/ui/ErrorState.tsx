/**
 * ErrorState - Display error states with retry option
 */

import { ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import { Button } from './Button'
import { cn } from '@/utils/cn'

export interface ErrorStateProps {
  title?: string
  message: string
  onRetry?: () => void
  className?: string
}

/**
 * ErrorState component for displaying error states with optional retry.
 *
 * @example
 * <ErrorState
 *   title="Failed to load data"
 *   message="Could not fetch servers from the marketplace"
 *   onRetry={() => refetch()}
 * />
 */
export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div className={cn('text-center py-12', className)}>
      {/* Error Icon */}
      <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-red-100 flex items-center justify-center">
        <ExclamationTriangleIcon className="w-8 h-8 text-red-600" />
      </div>

      {/* Title */}
      <h3 className="text-xl font-bold text-gray-900 mb-2">{title}</h3>

      {/* Message */}
      <p className="text-gray-600 font-serif mb-6 max-w-md mx-auto">{message}</p>

      {/* Retry Button */}
      {onRetry && (
        <Button variant="primary" onClick={onRetry}>
          Try Again
        </Button>
      )}
    </div>
  )
}
