import { HTMLAttributes, forwardRef } from 'react'
import { cn } from '@/utils/cn'

export interface SpinnerProps extends HTMLAttributes<HTMLDivElement> {
  size?: 'sm' | 'md' | 'lg' | 'xl'
  color?: 'orange' | 'white' | 'gray'
}

/**
 * Spinner component for loading states.
 *
 * @example
 * <Spinner />
 * <Spinner size="lg" color="white" />
 */
export const Spinner = forwardRef<HTMLDivElement, SpinnerProps>(
  (
    {
      className,
      size = 'md',
      color = 'orange',
      ...props
    },
    ref
  ) => {
    const sizes = {
      sm: 'h-4 w-4',
      md: 'h-8 w-8',
      lg: 'h-12 w-12',
      xl: 'h-16 w-16',
    }

    const colors = {
      orange: 'border-gray-300 border-t-orange',
      white: 'border-gray-300 border-t-white',
      gray: 'border-gray-200 border-t-gray-600',
    }

    return (
      <div
        ref={ref}
        role="status"
        aria-label="Loading"
        className={cn('inline-block', className)}
        {...props}
      >
        <div
          className={cn(
            'animate-spin rounded-full border-2',
            sizes[size],
            colors[color]
          )}
        />
        <span className="sr-only">Loading...</span>
      </div>
    )
  }
)

Spinner.displayName = 'Spinner'

/**
 * Centered spinner for full-page loading states
 */
export function CenteredSpinner({ size = 'lg', color = 'orange' }: SpinnerProps) {
  return (
    <div className="flex items-center justify-center min-h-[200px]">
      <Spinner size={size} color={color} />
    </div>
  )
}
