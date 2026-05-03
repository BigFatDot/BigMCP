/**
 * ToolCard — uniform draggable card for any pool entry (tool or composition).
 *
 * Used in three places: Catalog (drag source), Pool (drag source + drop sort),
 * Toolbox drawer. Identical layout everywhere so the user can drag-and-drop
 * the same atom of meaning across zones.
 */

import { useDraggable } from '@dnd-kit/core'
import { CSS } from '@dnd-kit/utilities'
import { CheckCircleIcon, SparklesIcon, WrenchScrewdriverIcon } from '@heroicons/react/24/outline'
import { cn } from '@/utils/cn'

export interface ToolCardData {
  id: string
  name: string
  serverName?: string | null
  description?: string | null
  kind: 'tool' | 'composition'
}

interface ToolCardProps {
  data: ToolCardData
  inPool?: boolean
  selected?: boolean
  onClick?: () => void
  /** Identifier scope so drag origin can be recovered server-side. */
  origin: 'catalog' | 'pool' | 'toolbox'
  toolboxId?: string
  /** Optional inline action button (e.g. + or ×). */
  actionLabel?: string
  onAction?: () => void
  draggable?: boolean
}

export function ToolCard({
  data,
  inPool,
  selected,
  onClick,
  origin,
  toolboxId,
  actionLabel,
  onAction,
  draggable = true,
}: ToolCardProps) {
  const dragId = `${origin}:${data.id}${toolboxId ? `:${toolboxId}` : ''}`
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: dragId,
    disabled: !draggable,
    data: { tool: data, origin, toolboxId },
  })

  const style = transform
    ? { transform: CSS.Translate.toString(transform), zIndex: 50 }
    : undefined

  const Icon = data.kind === 'composition' ? SparklesIcon : WrenchScrewdriverIcon

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...listeners}
      {...attributes}
      onClick={onClick}
      className={cn(
        'group relative rounded-lg border bg-white px-3 py-2 transition shadow-sm',
        draggable && 'cursor-grab active:cursor-grabbing',
        isDragging && 'opacity-60 shadow-lg ring-2 ring-orange',
        selected ? 'border-orange ring-2 ring-orange/30' : 'border-gray-200 hover:border-gray-300',
        inPool && !selected && 'border-emerald-300 bg-emerald-50/40',
      )}
    >
      <div className="flex items-start gap-2">
        <Icon
          className={cn(
            'w-4 h-4 mt-0.5 flex-shrink-0',
            data.kind === 'composition' ? 'text-orange' : 'text-gray-500',
          )}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-medium text-gray-900 truncate">{data.name}</span>
            {inPool && (
              <CheckCircleIcon className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" aria-label="In pool" />
            )}
          </div>
          {data.serverName && (
            <div className="text-xs text-gray-500 truncate">{data.serverName}</div>
          )}
          {data.description && (
            <div className="text-xs text-gray-600 mt-1 line-clamp-2">
              {data.description}
            </div>
          )}
        </div>
        {onAction && actionLabel && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onAction()
            }}
            className="text-xs font-medium text-orange hover:text-orange-dark px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity"
          >
            {actionLabel}
          </button>
        )}
      </div>
    </div>
  )
}
