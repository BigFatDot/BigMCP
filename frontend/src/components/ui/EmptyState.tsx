/**
 * EmptyState - Display when no data is available
 */

import { ReactNode } from 'react'
import { Button } from './Button'
import { cn } from '@/utils/cn'

export interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description?: string
  action?: {
    label: string
    onClick: () => void
  }
  className?: string
}

/**
 * EmptyState component for displaying when no data is available.
 *
 * @example
 * <EmptyState
 *   icon={<ServerIcon />}
 *   title="No servers connected"
 *   description="Get started by connecting your first MCP server"
 *   action={{ label: "Browse Marketplace", onClick: () => navigate('/marketplace') }}
 * />
 */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div className={cn('text-center py-12', className)}>
      {/* Icon */}
      {icon && (
        <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-100 flex items-center justify-center text-gray-400">
          {icon}
        </div>
      )}

      {/* Title */}
      <h3 className="text-xl font-bold text-gray-900 mb-2">{title}</h3>

      {/* Description */}
      {description && (
        <p className="text-gray-600 font-serif mb-6 max-w-md mx-auto">
          {description}
        </p>
      )}

      {/* Action */}
      {action && (
        <Button variant="primary" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  )
}
