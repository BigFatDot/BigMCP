import { HTMLAttributes, forwardRef } from 'react'
import { cn } from '@/utils/cn'

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: 'orange' | 'gray' | 'success' | 'error' | 'info' | 'warning' | 'primary' | 'default'
  size?: 'sm' | 'md' | 'lg'
}

/**
 * Badge component for tags, status indicators, and labels.
 *
 * @example
 * <Badge variant="success">Active</Badge>
 * <Badge variant="orange" size="lg">Pro</Badge>
 */
export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  (
    {
      className,
      variant = 'gray',
      size = 'md',
      children,
      ...props
    },
    ref
  ) => {
    const baseStyles = 'inline-flex items-center rounded-full font-medium'

    const variants = {
      orange: 'bg-orange-100 text-orange-800',
      gray: 'bg-gray-100 text-gray-800',
      success: 'bg-green-100 text-green-800',
      error: 'bg-red-100 text-red-800',
      info: 'bg-blue-100 text-blue-800',
      warning: 'bg-amber-100 text-amber-800',
      // ``default`` is a neutral fallback alias for callers that don't
      // need to pick a semantic color. ``primary`` is the brand badge.
      default: 'bg-gray-100 text-gray-800',
      primary: 'bg-orange-100 text-orange-800',
    }

    const sizes = {
      sm: 'px-2 py-0.5 text-xs',
      md: 'px-2.5 py-0.5 text-sm',
      lg: 'px-3 py-1 text-base',
    }

    return (
      <span
        ref={ref}
        className={cn(
          baseStyles,
          variants[variant],
          sizes[size],
          className
        )}
        {...props}
      >
        {children}
      </span>
    )
  }
)

Badge.displayName = 'Badge'
