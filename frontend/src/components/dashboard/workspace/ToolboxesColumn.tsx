/**
 * ToolboxesColumn — right pane.
 *
 * Lists existing toolboxes (tool groups) as droppable cards. Drop a tool
 * onto one to add it to the toolbox, drop it onto the "+ New toolbox"
 * area to spawn the create-toolbox flow.
 */

import { useTranslation } from 'react-i18next'
import { useDroppable } from '@dnd-kit/core'
import { ArchiveBoxIcon, PlusIcon, BoltIcon } from '@heroicons/react/24/outline'
import { cn } from '@/utils/cn'
import type { ToolboxSummary } from './types'

interface ToolboxesColumnProps {
  toolboxes: ToolboxSummary[]
  isLoading?: boolean
  onLoadToolboxIntoPool: (toolboxId: string) => void
  onOpenToolbox?: (toolboxId: string) => void
}

function ToolboxRow({
  toolbox,
  onLoadIntoPool,
  onOpen,
}: {
  toolbox: ToolboxSummary
  onLoadIntoPool: () => void
  onOpen?: () => void
}) {
  const { t } = useTranslation('dashboard')
  const { setNodeRef, isOver } = useDroppable({
    id: `drop:toolbox:${toolbox.id}`,
    data: { toolboxId: toolbox.id },
  })

  return (
    <div
      ref={setNodeRef}
      className={cn(
        'rounded-lg border bg-white px-3 py-3 transition shadow-sm',
        isOver
          ? 'border-orange ring-2 ring-orange/30 bg-orange/5'
          : 'border-gray-200 hover:border-gray-300',
      )}
    >
      <div className="flex items-start gap-2">
        <ArchiveBoxIcon
          className="w-4 h-4 mt-0.5 flex-shrink-0"
          style={{ color: toolbox.color || '#f97316' }}
        />
        <div className="flex-1 min-w-0">
          <button
            type="button"
            onClick={onOpen}
            className="text-sm font-medium text-gray-900 truncate text-left hover:text-orange"
          >
            {toolbox.name}
          </button>
          <div className="text-xs text-gray-500">
            {toolbox.itemCount}{' '}
            {t('tools.workspace.toolboxToolCount', { defaultValue: 'outils' })}
          </div>
          {toolbox.description && (
            <div className="text-xs text-gray-600 mt-1 line-clamp-2">
              {toolbox.description}
            </div>
          )}
        </div>
      </div>
      <div className="mt-2 flex justify-end">
        <button
          type="button"
          onClick={onLoadIntoPool}
          className="text-xs font-medium text-orange hover:text-orange-dark"
        >
          <BoltIcon className="w-3.5 h-3.5 inline mr-1" />
          {t('tools.workspace.loadToolbox', { defaultValue: 'Charger dans le pool' })}
        </button>
      </div>
    </div>
  )
}

export function ToolboxesColumn({
  toolboxes,
  isLoading,
  onLoadToolboxIntoPool,
  onOpenToolbox,
}: ToolboxesColumnProps) {
  const { t } = useTranslation('dashboard')
  const { setNodeRef: setNewRef, isOver: isOverNew } = useDroppable({
    id: 'drop:toolbox:new',
  })

  return (
    <div className="flex flex-col bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden h-full">
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50/60">
        <h3 className="text-sm font-semibold text-gray-900">
          {t('tools.workspace.toolboxesTitle', { defaultValue: 'Boîtes à outils' })}
        </h3>
        <p className="text-xs text-gray-500 mt-0.5">
          {t('tools.workspace.toolboxesHint', {
            defaultValue: 'Collections nommées · droppez des outils dessus pour les ajouter.',
          })}
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {isLoading ? (
          <div className="text-sm text-gray-500 text-center py-6">…</div>
        ) : toolboxes.length === 0 ? (
          <div className="text-sm text-gray-500 text-center py-6">
            {t('tools.workspace.toolboxesEmpty', {
              defaultValue: 'Aucune boîte à outils — déposez plusieurs outils sur la zone "Nouvelle boîte" pour en créer une.',
            })}
          </div>
        ) : (
          toolboxes.map((toolbox) => (
            <ToolboxRow
              key={toolbox.id}
              toolbox={toolbox}
              onLoadIntoPool={() => onLoadToolboxIntoPool(toolbox.id)}
              onOpen={onOpenToolbox ? () => onOpenToolbox(toolbox.id) : undefined}
            />
          ))
        )}

        <div
          ref={setNewRef}
          className={cn(
            'mt-3 rounded-lg border-2 border-dashed p-4 text-center text-sm transition',
            isOverNew
              ? 'border-orange bg-orange/5 text-orange'
              : 'border-gray-300 text-gray-500',
          )}
        >
          <PlusIcon className="w-5 h-5 mx-auto mb-1" />
          {t('tools.workspace.newToolbox', { defaultValue: 'Nouvelle boîte à outils' })}
          <div className="text-xs mt-1">
            {t('tools.workspace.newToolboxHint', {
              defaultValue: 'Glissez ici un ou plusieurs outils.',
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
