import { HTMLAttributes, forwardRef } from 'react'
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
  XCircleIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { cn } from '@/utils/cn'

export interface AlertProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'success' | 'error' | 'warning' | 'info'
  title?: string
  onClose?: () => void
}

/**
 * Alert component for displaying important messages.
 *
 * @example
 * <Alert variant="success" title="Success!">
 *   Your changes have been saved.
 * </Alert>
 */
export const Alert = forwardRef<HTMLDivElement, AlertProps>(
  (
    {
      className,
      variant = 'info',
      title,
      onClose,
      children,
      ...props
    },
    ref
  ) => {
    const variants = {
      success: {
        container: 'bg-green-50 border-green-200 text-green-800',
        icon: CheckCircleIcon,
        iconColor: 'text-green-400',
      },
      error: {
        container: 'bg-red-50 border-red-200 text-red-800',
        icon: XCircleIcon,
        iconColor: 'text-red-400',
      },
      warning: {
        container: 'bg-amber-50 border-amber-200 text-amber-800',
        icon: ExclamationTriangleIcon,
        iconColor: 'text-amber-400',
      },
      info: {
        container: 'bg-blue-50 border-blue-200 text-blue-800',
        icon: InformationCircleIcon,
        iconColor: 'text-blue-400',
      },
    }

    const config = variants[variant]
    const Icon = config.icon

    return (
      <div
        ref={ref}
        className={cn(
          'rounded-lg border p-4',
          config.container,
          className
        )}
        role="alert"
        {...props}
      >
        <div className="flex">
          <div className="flex-shrink-0">
            <Icon className={cn('h-5 w-5', config.iconColor)} aria-hidden="true" />
          </div>
          <div className="ml-3 flex-1">
            {title && (
              <h3 className="text-sm font-medium mb-1">{title}</h3>
            )}
            <div className="text-sm font-serif">{children}</div>
          </div>
          {onClose && (
            <div className="ml-auto pl-3">
              <button
                type="button"
                onClick={onClose}
                className={cn(
                  'inline-flex rounded-md p-1.5 focus:outline-none focus:ring-2 focus:ring-offset-2',
                  variant === 'success' && 'hover:bg-green-100 focus:ring-green-600',
                  variant === 'error' && 'hover:bg-red-100 focus:ring-red-600',
                  variant === 'warning' && 'hover:bg-amber-100 focus:ring-amber-600',
                  variant === 'info' && 'hover:bg-blue-100 focus:ring-blue-600'
                )}
              >
                <span className="sr-only">Dismiss</span>
                <XMarkIcon className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>
          )}
        </div>
      </div>
    )
  }
)

Alert.displayName = 'Alert'
