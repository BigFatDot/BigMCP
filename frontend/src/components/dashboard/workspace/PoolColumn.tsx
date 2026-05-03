/**
 * PoolColumn — center pane.
 *
 * Shows the active pool: tools currently loaded for OAuth MCP clients,
 * plus production compositions (always-on). Drop a tool here to add it,
 * drag a tool out of here to remove it, or click × on a card.
 */

import { useTranslation } from 'react-i18next'
import { useDroppable } from '@dnd-kit/core'
import { TrashIcon, SparklesIcon } from '@heroicons/react/24/outline'
import { Button } from '@/components/ui'
import { cn } from '@/utils/cn'
import { ToolCard } from './ToolCard'
import type { CatalogTool } from './types'

interface PoolColumnProps {
  poolTools: CatalogTool[]
  productionCompositions: CatalogTool[]
  poolSize: number
  compositionCount: number
  isLoading?: boolean
  onUnload: (tool: CatalogTool) => void
  onClearPool: () => void
  isClearing?: boolean
  onOpenAssistant?: () => void
}

export function PoolColumn({
  poolTools,
  productionCompositions,
  poolSize,
  compositionCount,
  isLoading,
  onUnload,
  onClearPool,
  isClearing,
  onOpenAssistant,
}: PoolColumnProps) {
  const { t } = useTranslation('dashboard')
  const { setNodeRef, isOver } = useDroppable({ id: 'drop:pool' })
  const totalCards = poolTools.length + productionCompositions.length

  return (
    <div
      ref={setNodeRef}
      className={cn(
        'flex flex-col rounded-xl border-2 shadow-sm overflow-hidden h-full transition',
        isOver
          ? 'border-orange bg-orange/5'
          : 'border-emerald-300 bg-emerald-50/30',
      )}
    >
      <div className="px-4 py-3 border-b border-emerald-200 bg-emerald-50/60">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-gray-900">
              {t('tools.workspace.poolTitle', { defaultValue: 'Pool actif' })}
            </h3>
            <p className="text-xs text-gray-600">
              {poolSize}{' '}
              {t('tools.workspace.poolToolsLoaded', { defaultValue: 'outils chargés' })}
              {compositionCount > 0 && (
                <>
                  {' · '}
                  {compositionCount}{' '}
                  {t('tools.workspace.poolCompositions', {
                    defaultValue: 'tools composés',
                  })}
                </>
              )}
            </p>
          </div>
          <div className="flex gap-2">
            {onOpenAssistant && (
              <Button variant="secondary" onClick={onOpenAssistant}>
                <SparklesIcon className="w-4 h-4 mr-1" />
                {t('tools.workspace.assistant', { defaultValue: 'Assistant' })}
              </Button>
            )}
            <Button
              variant="secondary"
              onClick={onClearPool}
              disabled={isClearing || poolSize === 0}
            >
              <TrashIcon className="w-4 h-4 mr-1" />
              {t('tools.workspace.clearPool', { defaultValue: 'Vider' })}
            </Button>
          </div>
        </div>
        <p className="mt-2 text-xs text-gray-500">
          {t('tools.workspace.poolHint', {
            defaultValue:
              'Glissez des outils ici depuis le catalogue, ou laissez votre client MCP les charger automatiquement via search.',
          })}
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {isLoading ? (
          <div className="text-sm text-gray-500 text-center py-6">…</div>
        ) : totalCards === 0 ? (
          <div className="border-2 border-dashed border-emerald-300 rounded-lg p-8 text-center text-sm text-gray-500">
            {t('tools.workspace.poolEmpty', {
              defaultValue: 'Pool vide — déposez ici les outils que vous voulez exposer à votre client MCP.',
            })}
          </div>
        ) : (
          <>
            {productionCompositions.map((comp) => (
              <ToolCard
                key={comp.id}
                data={comp}
                origin="pool"
                inPool
                draggable={false}
              />
            ))}
            {poolTools.map((tool) => (
              <ToolCard
                key={tool.id}
                data={tool}
                origin="pool"
                inPool
                actionLabel="×"
                onAction={() => onUnload(tool)}
              />
            ))}
          </>
        )}
      </div>
    </div>
  )
}
