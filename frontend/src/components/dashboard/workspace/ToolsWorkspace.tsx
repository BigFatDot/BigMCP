/**
 * ToolsWorkspace — three-column drag-and-drop UI for managing the Services.
 *
 * Layout: [Catalog] [Active Pool] [Toolboxes]
 * Drag a tool card across columns to:
 *   - Catalog → Pool: load into pool
 *   - Pool → Catalog: unload from pool
 *   - Catalog/Pool → Toolbox: add to toolbox
 *   - Toolbox → Pool: load full toolbox into pool (alternative: dedicated button)
 *
 * The tool is the unit of meaning — servers fade into chips/filters.
 * Toolboxes (ToolGroup model) get their own column so users can compose
 * collections that double as API-key scopes (existing behavior preserved).
 */

import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  useDroppable,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import {
  ArchiveBoxIcon,
  ArrowPathIcon,
  BoltIcon,
  MagnifyingGlassIcon,
  PencilSquareIcon,
  PlusIcon,
  SparklesIcon,
  TrashIcon,
} from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'

import { Button, Badge } from '@/components/ui'
import { cn } from '@/utils/cn'
import {
  poolApi,
  toolGroupsApi,
  compositionsApi,
  credentialsApi,
  type ToolGroup,
} from '@/services/marketplace'
import type { Composition } from '@/services/marketplace'
import { useOrganization } from '@/hooks/useAuth'

import { ToolCard, type ToolCardData } from './ToolCard'
import { AssistantModal } from './AssistantModal'
import { CreateToolboxFromDropModal } from './CreateToolboxFromDropModal'
import { ToolboxEditModal } from './ToolboxEditModal'
import type { CatalogTool, DragPayload, ToolboxSummary } from './types'

interface DropZoneProps {
  id: string
  children: React.ReactNode
  className?: string
  activeClassName?: string
}

function DropZone({ id, children, className, activeClassName }: DropZoneProps) {
  const { setNodeRef, isOver } = useDroppable({ id })
  return (
    <div
      ref={setNodeRef}
      className={cn(className, isOver && (activeClassName ?? 'ring-2 ring-orange ring-offset-2'))}
    >
      {children}
    </div>
  )
}

export function ToolsWorkspace() {
  const { t } = useTranslation('dashboard')
  const { organizationId: currentOrgId } = useOrganization()
  const queryClient = useQueryClient()

  const [searchQuery, setSearchQuery] = useState('')
  const [serverFilter, setServerFilter] = useState<Set<string>>(new Set())
  const [activeDrag, setActiveDrag] = useState<DragPayload | null>(null)
  const [showAssistant, setShowAssistant] = useState(false)
  const [seedToolForNewToolbox, setSeedToolForNewToolbox] = useState<ToolCardData | null>(null)
  const [editingToolboxId, setEditingToolboxId] = useState<string | null>(null)
  const [mobileColumn, setMobileColumn] = useState<'catalog' | 'pool' | 'toolboxes'>('catalog')

  // ---- Queries ----
  const credentialsQuery = useQuery({
    queryKey: ['credentials'],
    queryFn: () => credentialsApi.listUserCredentials(),
  })

  // The /tool-groups/available-tools endpoint is the canonical, org-scoped
  // tool catalog: persisted Tool rows from every enabled MCP server, with
  // their server name and current pool flag attached. No runtime status
  // dependency, no cache shape mismatch (unlike /api/v1/tools).
  const toolsQuery = useQuery({
    queryKey: ['workspace-tools', currentOrgId],
    queryFn: () => toolGroupsApi.listAvailableTools(),
    enabled: !!currentOrgId,
    refetchInterval: 30000,
  })

  const poolStateQuery = useQuery({
    queryKey: ['pool-state'],
    queryFn: () => poolApi.getState(),
    refetchInterval: 15000,
  })

  const toolGroupsQuery = useQuery({
    queryKey: ['tool-groups'],
    queryFn: () => toolGroupsApi.list(true),
  })

  const compositionsQuery = useQuery({
    queryKey: ['workspace-compositions'],
    queryFn: () => compositionsApi.list({ status: 'production' }),
  })

  // ---- Derived ----
  const allTools: CatalogTool[] = useMemo(() => {
    const rows: any[] = (toolsQuery.data as any[]) || []
    return rows.map((r) => ({
      id: String(r.id),
      name: r.display_name || r.tool_name || r.name,
      serverId: r.server_id ?? null,
      // The endpoint returns server_name directly. Fall back to the user
      // credential lookup for legacy callers that don't carry it inline.
      serverName:
        r.server_name ??
        (credentialsQuery.data || []).find(
          (c: any) => c.server_id === r.server_id || c.id === r.server_id,
        )?.name ??
        null,
      description: r.description ?? null,
      kind: 'tool' as const,
      inPool: !!r.is_visible_to_oauth_clients,
    }))
  }, [toolsQuery.data, credentialsQuery.data])

  const productionCompositions: ToolCardData[] = useMemo(() => {
    const list = (compositionsQuery.data?.compositions || []) as Composition[]
    return list.map((c) => ({
      id: String(c.id),
      name: c.name,
      description: c.description ?? null,
      kind: 'composition' as const,
      serverName: null,
    }))
  }, [compositionsQuery.data])

  const allServers = useMemo(() => {
    const map = new Map<string, { name: string; toolIds: string[] }>()
    for (const t of allTools) {
      if (!t.serverId) continue
      const entry = map.get(t.serverId) || { name: t.serverName || t.serverId, toolIds: [] }
      entry.toolIds.push(t.id)
      map.set(t.serverId, entry)
    }
    return Array.from(map.entries()).map(([id, { name, toolIds }]) => {
      // Match the server with the user's credential (so we can revoke it).
      const credential = (credentialsQuery.data || []).find(
        (c: any) => String(c.server_id) === String(id) || String(c.id) === String(id),
      )
      return {
        id,
        name,
        toolIds,
        credentialId: credential?.id ?? null,
      }
    })
  }, [allTools, credentialsQuery.data])

  const revokeServerMutation = useMutation({
    mutationFn: (credentialId: string) => credentialsApi.deleteUserCredential(credentialId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['credentials'] })
      queryClient.invalidateQueries({ queryKey: ['workspace-tools'] })
      queryClient.invalidateQueries({ queryKey: ['pool-state'] })
      toast.success(
        t('workspace.servers.revokedToast', {
          defaultValue: 'Service revoked.',
        }) as string,
      )
    },
    onError: (e: any) =>
      toast.error(e.response?.data?.detail || e.message || 'Failed to revoke'),
  })

  const filteredCatalog = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return allTools.filter((t) => {
      if (serverFilter.size > 0 && t.serverId && !serverFilter.has(t.serverId)) return false
      if (!q) return true
      return (
        t.name.toLowerCase().includes(q) ||
        (t.description || '').toLowerCase().includes(q) ||
        (t.serverName || '').toLowerCase().includes(q)
      )
    })
  }, [allTools, searchQuery, serverFilter])

  const poolTools = useMemo(() => allTools.filter((t) => t.inPool), [allTools])

  const toolboxes: ToolboxSummary[] = useMemo(() => {
    const list = (toolGroupsQuery.data || []) as ToolGroup[]
    return list.map((g) => ({
      id: g.id,
      name: g.name,
      description: g.description,
      color: g.color,
      visibility: g.visibility === 'public' ? 'organization' : g.visibility,
      itemCount: (g.items || []).length,
      toolIds: new Set((g.items || []).map((i: any) => i.tool_id).filter(Boolean)),
    }))
  }, [toolGroupsQuery.data])

  // ---- Mutations ----
  const toolsQueryKey = ['workspace-tools', currentOrgId] as const
  const poolStateKey = ['pool-state'] as const

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ['workspace-tools'] })
    queryClient.invalidateQueries({ queryKey: ['pool-state'] })
    queryClient.invalidateQueries({ queryKey: ['tool-groups'] })
  }

  // Optimistic helper: flip `is_visible_to_oauth_clients` for a set of
  // tool IDs in the cached catalog so the UI moves instantly. We snapshot
  // the previous value to roll back if the server rejects.
  function flipPoolFlagOptimistic(toolIds: string[], next: boolean) {
    const previous = queryClient.getQueryData<any[]>(toolsQueryKey)
    queryClient.setQueryData<any[]>(toolsQueryKey, (old) => {
      if (!old) return old
      const set = new Set(toolIds)
      return old.map((row) =>
        set.has(String(row.id))
          ? { ...row, is_visible_to_oauth_clients: next }
          : row,
      )
    })
    // Pool size stays approximate during the round-trip (we don't know how
    // many were already in the pool); bump the cached counter optimistically.
    queryClient.setQueryData<any>(poolStateKey, (old) => {
      if (!old) return old
      const delta = next
        ? toolIds.filter((id) => {
            const row = (previous || []).find((r) => String(r.id) === id)
            return row && !row.is_visible_to_oauth_clients
          }).length
        : -toolIds.filter((id) => {
            const row = (previous || []).find((r) => String(r.id) === id)
            return row && row.is_visible_to_oauth_clients
          }).length
      return { ...old, pool_size: Math.max(0, (old.pool_size ?? 0) + delta) }
    })
    return previous
  }

  const loadMutation = useMutation({
    mutationFn: (toolIds: string[]) => poolApi.load(toolIds, 'append'),
    onMutate: async (toolIds) => {
      await queryClient.cancelQueries({ queryKey: toolsQueryKey })
      const previous = flipPoolFlagOptimistic(toolIds, true)
      return { previous }
    },
    onError: (e: any, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(toolsQueryKey, context.previous)
      toast.error(e.response?.data?.detail || 'Load failed')
    },
    onSuccess: () => {
      toast.success(t('workspace.toast.loaded', { defaultValue: 'Loaded into pool' }))
    },
    onSettled: invalidateAll,
  })

  const unloadMutation = useMutation({
    mutationFn: (toolIds: string[]) => poolApi.unload(toolIds),
    onMutate: async (toolIds) => {
      await queryClient.cancelQueries({ queryKey: toolsQueryKey })
      const previous = flipPoolFlagOptimistic(toolIds, false)
      return { previous }
    },
    onError: (e: any, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(toolsQueryKey, context.previous)
      toast.error(e.response?.data?.detail || 'Unload failed')
    },
    onSuccess: () => {
      toast.success(t('workspace.toast.unloaded', { defaultValue: 'Removed from pool' }))
    },
    onSettled: invalidateAll,
  })

  const clearMutation = useMutation({
    mutationFn: () => poolApi.clear(),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: toolsQueryKey })
      const previous = queryClient.getQueryData<any[]>(toolsQueryKey)
      queryClient.setQueryData<any[]>(toolsQueryKey, (old) =>
        (old || []).map((row) => ({ ...row, is_visible_to_oauth_clients: false })),
      )
      queryClient.setQueryData<any>(poolStateKey, (old) =>
        old ? { ...old, pool_size: 0 } : old,
      )
      return { previous }
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(toolsQueryKey, ctx.previous)
    },
    onSuccess: () => {
      toast.success(t('workspace.toast.cleared', { defaultValue: 'Pool cleared' }))
    },
    onSettled: invalidateAll,
  })

  const addToToolboxMutation = useMutation({
    mutationFn: ({ groupId, toolId }: { groupId: string; toolId: string }) =>
      toolGroupsApi.addTool(groupId, toolId),
    onMutate: async ({ groupId, toolId }) => {
      await queryClient.cancelQueries({ queryKey: ['tool-groups'] })
      const previous = queryClient.getQueryData<any[]>(['tool-groups'])
      queryClient.setQueryData<any[]>(['tool-groups'], (old) =>
        (old || []).map((g) => {
          if (g.id !== groupId) return g
          if ((g.items || []).some((i: any) => i.tool_id === toolId)) return g
          return {
            ...g,
            items: [
              ...(g.items || []),
              { id: `tmp-${toolId}`, tool_group_id: groupId, item_type: 'tool', tool_id: toolId, order: 0, config: {} },
            ],
          }
        }),
      )
      return { previous }
    },
    onError: (e: any, _v, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(['tool-groups'], ctx.previous)
      toast.error(e.response?.data?.detail || 'Add to toolbox failed')
    },
    onSuccess: () => {
      toast.success(t('workspace.toast.toolboxAdded', { defaultValue: 'Added to toolbox' }))
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['tool-groups'] }),
  })

  const loadToolboxMutation = useMutation({
    mutationFn: (groupId: string) => poolApi.loadToolbox(groupId),
    onMutate: async (groupId) => {
      await queryClient.cancelQueries({ queryKey: toolsQueryKey })
      const tg = (toolGroupsQuery.data || []).find((g: any) => g.id === groupId)
      const ids = (tg?.items || [])
        .filter((i: any) => i.item_type === 'tool' && i.tool_id)
        .map((i: any) => String(i.tool_id))
      const previous = flipPoolFlagOptimistic(ids, true)
      return { previous }
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(toolsQueryKey, ctx.previous)
    },
    onSuccess: () => {
      toast.success(t('workspace.toast.toolboxLoaded', { defaultValue: 'Toolbox loaded into pool' }))
    },
    onSettled: invalidateAll,
  })

  // ---- DnD callbacks ----
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor),
  )

  const onDragStart = (e: DragStartEvent) => {
    const data = e.active.data.current as DragPayload | undefined
    if (data) setActiveDrag(data)
  }

  const onDragEnd = (e: DragEndEvent) => {
    setActiveDrag(null)
    const payload = e.active.data.current as DragPayload | undefined
    const overId = e.over?.id
    if (!payload || !overId) return

    if (overId === 'pool-drop') {
      if (payload.origin === 'pool') return
      // For tools the load endpoint is the right thing.
      if (payload.tool.kind === 'tool') {
        loadMutation.mutate([payload.tool.id])
      } else {
        toast(t('workspace.toast.compositionAlwaysIn', { defaultValue: 'Composed tools are always in the pool.' }))
      }
      return
    }

    if (overId === 'catalog-drop') {
      if (payload.origin === 'pool' && payload.tool.kind === 'tool') {
        unloadMutation.mutate([payload.tool.id])
      }
      return
    }

    if (typeof overId === 'string' && overId.startsWith('toolbox-drop:')) {
      const groupId = overId.slice('toolbox-drop:'.length)
      if (payload.tool.kind === 'tool') {
        addToToolboxMutation.mutate({ groupId, toolId: payload.tool.id })
      } else {
        toast.error(t('workspace.toast.compositionToolboxBlocked', { defaultValue: 'Compositions cannot be added to toolboxes yet.' }))
      }
      return
    }

    if (overId === 'toolbox-new-drop') {
      if (payload.tool.kind === 'tool') {
        setSeedToolForNewToolbox(payload.tool)
      } else {
        toast.error(t('workspace.toast.compositionToolboxBlocked', { defaultValue: 'Compositions cannot be added to toolboxes yet.' }))
      }
    }
  }

  // ---- Render ----
  return (
    <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
      <div className="container py-8">
        <div className="mb-6 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
          <div>
            <h1 className="text-4xl font-bold text-gray-900 mb-1">
              {t('tools.title')}
            </h1>
            <p className="text-gray-600 font-serif">
              {t('workspace.subtitle', {
                defaultValue:
                  "Drag tools between Catalog, your active Pool, and Toolboxes. Your MCP client also drives the pool through `search`/`execute`.",
              })}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm">
              <div className="text-xs uppercase tracking-wide text-gray-500">
                {t('tools.pool.label', { defaultValue: 'Active pool' })}
              </div>
              <div className="text-2xl font-semibold text-gray-900">
                {poolStateQuery.data?.pool_size ?? '…'}{' '}
                <span className="text-sm font-normal text-gray-500">
                  {t('tools.pool.toolsLoaded', { defaultValue: 'tools loaded' })}
                </span>
              </div>
              {(poolStateQuery.data?.composition_count ?? 0) > 0 && (
                <div className="text-xs text-gray-500">
                  +{poolStateQuery.data?.composition_count}{' '}
                  {t('tools.pool.composedTools', { defaultValue: 'composed tools always-on' })}
                </div>
              )}
            </div>
            <Button
              variant="secondary"
              onClick={() => {
                if (
                  window.confirm(
                    t('tools.pool.clearConfirm', {
                      defaultValue:
                        'Clear the active pool? Your MCP client will need to call `search` again to reload tools.',
                    }),
                  )
                ) {
                  clearMutation.mutate()
                }
              }}
              disabled={clearMutation.isPending || (poolStateQuery.data?.pool_size ?? 0) === 0}
            >
              <TrashIcon className="w-4 h-4 mr-1.5" />
              {t('tools.pool.clear', { defaultValue: 'Clear pool' })}
            </Button>
          </div>
        </div>

        {/* Search bar */}
        <div className="mb-4 flex flex-col sm:flex-row gap-2">
          <div className="relative flex-1">
            <MagnifyingGlassIcon className="w-5 h-5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder={
                t('workspace.searchPlaceholder', {
                  defaultValue: 'Search tools by name, server or description…',
                }) as string
              }
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange"
            />
          </div>
          <Button
            variant="secondary"
            onClick={() => {
              const ids = filteredCatalog.filter((t) => !t.inPool).map((t) => t.id)
              if (ids.length === 0) return
              if (
                ids.length > 20 &&
                !window.confirm(
                  t('workspace.bulkLoadConfirm', {
                    defaultValue:
                      'Load {{count}} tools into the pool? Large pools can clutter your MCP client.',
                    count: ids.length,
                  }),
                )
              ) {
                return
              }
              loadMutation.mutate(ids)
            }}
            disabled={loadMutation.isPending}
          >
            <BoltIcon className="w-4 h-4 mr-1.5" />
            {t('workspace.loadFiltered', {
              defaultValue: 'Load all matches ({{count}})',
              count: filteredCatalog.filter((t) => !t.inPool).length,
            })}
          </Button>
          <Button
            variant="primary"
            onClick={() => setShowAssistant(true)}
          >
            <SparklesIcon className="w-4 h-4 mr-1.5" />
            {t('workspace.askAssistant', { defaultValue: 'Ask assistant' })}
          </Button>
        </div>

        {/* Server filter chips with hover actions: load-all-into-pool + revoke */}
        {allServers.length > 0 && (
          <div className="mb-4 flex flex-wrap gap-2">
            {allServers.map((s) => {
              const active = serverFilter.has(s.id)
              return (
                <div
                  key={s.id}
                  className={cn(
                    'group inline-flex items-stretch rounded-full border transition overflow-hidden',
                    active
                      ? 'border-orange bg-orange/10 text-orange-dark'
                      : 'border-gray-200 text-gray-600 hover:border-gray-300',
                  )}
                >
                  <button
                    type="button"
                    onClick={() => {
                      const next = new Set(serverFilter)
                      if (next.has(s.id)) next.delete(s.id)
                      else next.add(s.id)
                      setServerFilter(next)
                    }}
                    className="text-xs px-2.5 py-1"
                  >
                    {s.name}{' '}
                    <span className="text-gray-400">({s.toolIds.length})</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => loadMutation.mutate(s.toolIds)}
                    title={
                      t('workspace.servers.loadAllHint', {
                        defaultValue: 'Load every tool from this service into the pool',
                      }) as string
                    }
                    className="px-1.5 border-l border-current/20 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-orange/10"
                  >
                    <BoltIcon className="w-3 h-3" />
                  </button>
                  {s.credentialId && (
                    <button
                      type="button"
                      onClick={() => {
                        if (
                          window.confirm(
                            t('workspace.servers.revokeConfirm', {
                              name: s.name,
                              defaultValue:
                                'Revoke "{{name}}"? Stored credentials are deleted; tools will no longer reach this service.',
                            }) as string,
                          )
                        ) {
                          revokeServerMutation.mutate(s.credentialId as string)
                        }
                      }}
                      title={
                        t('workspace.servers.revokeHint', {
                          defaultValue: 'Revoke this service (delete its credentials)',
                        }) as string
                      }
                      className="px-1.5 border-l border-current/20 opacity-0 group-hover:opacity-100 transition-opacity text-red-600 hover:bg-red-50"
                    >
                      <TrashIcon className="w-3 h-3" />
                    </button>
                  )}
                </div>
              )
            })}
            {serverFilter.size > 0 && (
              <button
                type="button"
                onClick={() => setServerFilter(new Set())}
                className="text-xs px-2.5 py-1 text-gray-500 hover:text-gray-900"
              >
                {t('workspace.clearFilters', { defaultValue: 'Clear filters' })}
              </button>
            )}
          </div>
        )}

        {/* Mobile tab switcher (md:hidden) */}
        <div className="mb-3 flex md:hidden bg-gray-100 rounded-lg p-1 text-sm">
          {(['catalog', 'pool', 'toolboxes'] as const).map((col) => (
            <button
              key={col}
              type="button"
              onClick={() => setMobileColumn(col)}
              className={cn(
                'flex-1 px-3 py-1.5 rounded-md font-medium transition',
                mobileColumn === col ? 'bg-white shadow-sm text-gray-900' : 'text-gray-600',
              )}
            >
              {col === 'catalog'
                ? t('workspace.catalog', { defaultValue: 'Catalog' })
                : col === 'pool'
                  ? t('workspace.pool', { defaultValue: 'Pool' })
                  : t('tools.viewToggle.toolboxes', { defaultValue: 'Toolboxes' })}
            </button>
          ))}
        </div>

        {/* Three columns */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-start">
          {/* Catalog */}
          <DropZone
            id="catalog-drop"
            className={cn(
              'rounded-xl border border-gray-200 bg-gray-50/50 p-3 min-h-[400px]',
              mobileColumn !== 'catalog' && 'hidden md:block',
            )}
          >
            <div className="flex items-baseline justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">
                {t('workspace.catalog', { defaultValue: 'Catalog' })}
              </h2>
              <span className="text-xs text-gray-500">
                {filteredCatalog.length} / {allTools.length}
              </span>
            </div>
            <div className="space-y-1.5 max-h-[60vh] overflow-y-auto pr-1">
              {filteredCatalog.length === 0 ? (
                <div className="text-sm text-gray-500 text-center py-8">
                  {searchQuery
                    ? t('workspace.empty.noMatch', { defaultValue: 'No tool matches your search.' })
                    : t('workspace.empty.catalog', {
                        defaultValue: 'Connect a server in the Marketplace to populate the catalog.',
                      })}
                </div>
              ) : (
                filteredCatalog.map((tool) => (
                  <ToolCard
                    key={tool.id}
                    data={tool}
                    inPool={tool.inPool}
                    origin="catalog"
                    onAction={() =>
                      tool.inPool
                        ? unloadMutation.mutate([tool.id])
                        : loadMutation.mutate([tool.id])
                    }
                    actionLabel={tool.inPool ? '−' : '+'}
                  />
                ))
              )}
            </div>
          </DropZone>

          {/* Pool */}
          <DropZone
            id="pool-drop"
            className={cn(
              'rounded-xl border-2 border-dashed border-emerald-300 bg-emerald-50/30 p-3 min-h-[400px]',
              mobileColumn !== 'pool' && 'hidden md:block',
            )}
            activeClassName="bg-emerald-100/60 border-emerald-500"
          >
            <div className="flex items-baseline justify-between mb-3">
              <h2 className="text-sm font-semibold text-emerald-900 uppercase tracking-wide">
                {t('workspace.pool', { defaultValue: 'Active Pool' })}
              </h2>
              <span className="text-xs text-emerald-700">
                {poolTools.length} {t('workspace.toolsShort', { defaultValue: 'tools' })}
              </span>
            </div>
            <div className="space-y-1.5 max-h-[60vh] overflow-y-auto pr-1">
              {poolTools.length === 0 && productionCompositions.length === 0 && (
                <div className="text-sm text-gray-500 text-center py-8">
                  {t('workspace.empty.pool', {
                    defaultValue:
                      'Drop tools here, or click + on a catalog tool. Your MCP client also fills the pool via `search`.',
                  })}
                </div>
              )}
              {productionCompositions.map((c) => (
                <ToolCard
                  key={`comp-${c.id}`}
                  data={c}
                  origin="pool"
                  draggable={false}
                  inPool
                />
              ))}
              {poolTools.map((tool) => (
                <ToolCard
                  key={tool.id}
                  data={tool}
                  inPool
                  origin="pool"
                  onAction={() => unloadMutation.mutate([tool.id])}
                  actionLabel="×"
                />
              ))}
            </div>
          </DropZone>

          {/* Toolboxes */}
          <div
            className={cn(
              'rounded-xl border border-gray-200 bg-gray-50/50 p-3 min-h-[400px]',
              mobileColumn !== 'toolboxes' && 'hidden md:block',
            )}
          >
            <div className="flex items-baseline justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide flex items-center gap-1">
                <ArchiveBoxIcon className="w-4 h-4" />
                {t('tools.viewToggle.toolboxes', { defaultValue: 'Toolboxes' })}
              </h2>
              <span className="text-xs text-gray-500">{toolboxes.length}</span>
            </div>
            <div className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
              {toolboxes.length === 0 && (
                <div className="text-sm text-gray-500 text-center py-8">
                  {t('workspace.empty.toolboxes', {
                    defaultValue:
                      'Drop tools onto a toolbox to add them, or create a new one from the Toolboxes tab.',
                  })}
                </div>
              )}
              {toolboxes.map((tb) => (
                <DropZone
                  key={tb.id}
                  id={`toolbox-drop:${tb.id}`}
                  className="rounded-lg border border-gray-200 bg-white p-3 transition"
                >
                  <div className="flex items-center justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => setEditingToolboxId(tb.id)}
                      className="flex-1 min-w-0 text-left hover:text-orange-dark transition"
                      title={t('workspace.toolboxEdit.openHint', {
                        defaultValue: 'Click to edit this toolbox',
                      }) as string}
                    >
                      <div className="text-sm font-medium text-gray-900 truncate">{tb.name}</div>
                      <div className="text-xs text-gray-500">
                        {tb.itemCount} {t('workspace.toolsShort', { defaultValue: 'tools' })} ·{' '}
                        {tb.visibility === 'organization'
                          ? t('compositions.team', { defaultValue: 'team' })
                          : t('compositions.private', { defaultValue: 'private' })}
                      </div>
                    </button>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => loadToolboxMutation.mutate(tb.id)}
                        disabled={loadToolboxMutation.isPending}
                        title={t('workspace.toolboxLoadHint', {
                          defaultValue: 'Load every tool of this toolbox into the pool',
                        })}
                      >
                        <BoltIcon className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditingToolboxId(tb.id)}
                        title={t('workspace.toolboxEdit.editHint', {
                          defaultValue: 'Edit toolbox',
                        })}
                      >
                        <PencilSquareIcon className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </DropZone>
              ))}
              <DropZone
                id="toolbox-new-drop"
                className="rounded-lg border border-dashed border-gray-300 bg-white/50 p-3 transition text-center hover:border-orange/60"
                activeClassName="bg-orange/5 border-orange"
              >
                <div className="text-sm text-gray-600 flex items-center justify-center gap-1.5">
                  <PlusIcon className="w-4 h-4" />
                  {t('workspace.newToolboxDrop', {
                    defaultValue: 'Drop a tool here to create a new toolbox',
                  })}
                </div>
              </DropZone>
            </div>
          </div>
        </div>
      </div>

      <DragOverlay>
        {activeDrag ? (
          <ToolCard data={activeDrag.tool} origin={activeDrag.origin} draggable={false} />
        ) : null}
      </DragOverlay>

      <AssistantModal
        isOpen={showAssistant}
        onClose={() => setShowAssistant(false)}
        onLoaded={invalidateAll}
      />

      <CreateToolboxFromDropModal
        isOpen={!!seedToolForNewToolbox}
        seedTool={seedToolForNewToolbox}
        canShareWithOrg={!!toolGroupsQuery.data?.length}
        onClose={() => setSeedToolForNewToolbox(null)}
      />

      <ToolboxEditModal
        toolboxId={editingToolboxId}
        isOpen={!!editingToolboxId}
        onClose={() => setEditingToolboxId(null)}
      />
    </DndContext>
  )
}
