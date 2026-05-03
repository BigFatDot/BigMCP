/**
 * CatalogColumn — left pane of the Services workspace.
 *
 * Lists every tool from the user's enabled servers, with server checkbox
 * filters and a free-text search. Each tool is a draggable ToolCard that
 * the user drops into the Pool or onto a Toolbox.
 */

import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useDroppable } from '@dnd-kit/core'
import { MagnifyingGlassIcon, BoltIcon } from '@heroicons/react/24/outline'
import { cn } from '@/utils/cn'
import { ToolCard } from './ToolCard'
import type { CatalogTool } from './types'

interface CatalogColumnProps {
  tools: CatalogTool[]
  isLoading?: boolean
  serverFilters: Record<string, boolean>
  onToggleServer: (serverName: string) => void
  selectedToolIds: Set<string>
  onToggleSelected: (toolId: string) => void
  onAddToPool?: (tool: CatalogTool) => void
}

export function CatalogColumn({
  tools,
  isLoading,
  serverFilters,
  onToggleServer,
  selectedToolIds,
  onToggleSelected,
  onAddToPool,
}: CatalogColumnProps) {
  const { t } = useTranslation('dashboard')
  const [query, setQuery] = useState('')

  const { setNodeRef, isOver } = useDroppable({ id: 'drop:catalog' })

  const servers = useMemo(() => {
    const set = new Map<string, number>()
    for (const tool of tools) {
      if (!tool.serverName) continue
      set.set(tool.serverName, (set.get(tool.serverName) ?? 0) + 1)
    }
    return Array.from(set.entries()).map(([name, count]) => ({ name, count }))
  }, [tools])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return tools.filter((tool) => {
      if (tool.serverName && serverFilters[tool.serverName] === false) return false
      if (!q) return true
      return (
        tool.name.toLowerCase().includes(q) ||
        (tool.description ?? '').toLowerCase().includes(q) ||
        (tool.serverName ?? '').toLowerCase().includes(q)
      )
    })
  }, [tools, query, serverFilters])

  return (
    <div
      ref={setNodeRef}
      className={cn(
        'flex flex-col bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden h-full',
        isOver && 'ring-2 ring-orange/40',
      )}
    >
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50/60">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-gray-900">
            {t('tools.workspace.catalogTitle', { defaultValue: 'Catalogue' })}
          </h3>
          <span className="text-xs text-gray-500">
            {filtered.length}/{tools.length}
          </span>
        </div>
        <div className="relative mb-2">
          <MagnifyingGlassIcon className="w-4 h-4 text-gray-400 absolute left-2 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={
              t('tools.workspace.catalogSearch', { defaultValue: 'Rechercher un outil…' }) as string
            }
            className="w-full pl-8 pr-2 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-orange focus:border-transparent"
          />
        </div>
        {servers.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {servers.map(({ name, count }) => {
              const enabled = serverFilters[name] !== false
              return (
                <button
                  key={name}
                  type="button"
                  onClick={() => onToggleServer(name)}
                  className={cn(
                    'text-xs px-2 py-0.5 rounded-full border transition',
                    enabled
                      ? 'bg-orange/10 border-orange text-orange'
                      : 'bg-white border-gray-300 text-gray-500',
                  )}
                >
                  <BoltIcon className="w-3 h-3 inline mr-1" />
                  {name} ({count})
                </button>
              )
            })}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {isLoading ? (
          <div className="text-sm text-gray-500 text-center py-6">
            {t('tools.workspace.loading', { defaultValue: 'Chargement…' })}
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-sm text-gray-500 text-center py-6">
            {tools.length === 0
              ? t('tools.workspace.catalogEmpty', {
                  defaultValue: 'Aucun outil — connectez d\'abord un serveur dans le Marketplace.',
                })
              : t('tools.workspace.catalogNoMatch', {
                  defaultValue: 'Aucun outil ne correspond à ce filtre.',
                })}
          </div>
        ) : (
          filtered.map((tool) => (
            <ToolCard
              key={tool.id}
              data={tool}
              origin="catalog"
              inPool={tool.inPool}
              selected={selectedToolIds.has(tool.id)}
              onClick={() => onToggleSelected(tool.id)}
              actionLabel={tool.inPool ? undefined : '+'}
              onAction={onAddToPool ? () => onAddToPool(tool) : undefined}
            />
          ))
        )}
      </div>

      {selectedToolIds.size > 0 && (
        <div className="px-4 py-2 border-t border-gray-200 bg-orange/5 text-xs text-orange-dark">
          {t('tools.workspace.selectedCount', {
            count: selectedToolIds.size,
            defaultValue: '{{count}} outil(s) sélectionné(s) — glissez vers le pool ou une boîte',
          })}
        </div>
      )}
    </div>
  )
}
