/**
 * WorkspaceView — orchestrates the 3-column drag-and-drop UX.
 *
 * Responsibilities:
 * - Fetch tools, toolboxes, pool state, productions compositions
 * - Wire DnD: drop tool to pool / unload / add to toolbox / spawn new toolbox
 * - Hold cross-column state (selection, server filters)
 * - Trigger optimistic updates + invalidate queries
 *
 * Sub-components handle their own presentation (Catalog / Pool / Toolboxes).
 */

import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import toast from 'react-hot-toast'
import {
  poolApi,
  toolGroupsApi,
  compositionsApi,
  type ToolInfo,
  type ToolGroup,
  type Composition,
} from '@/services/marketplace'
import { CatalogColumn } from './CatalogColumn'
import { PoolColumn } from './PoolColumn'
import { ToolboxesColumn } from './ToolboxesColumn'
import { ToolCard, type ToolCardData } from './ToolCard'
import type { CatalogTool, DragPayload, ToolboxSummary } from './types'

interface WorkspaceViewProps {
  onOpenAssistant?: () => void
  onCreateToolboxFromTools?: (toolIds: string[]) => void
  onOpenToolbox?: (toolboxId: string) => void
}

export function WorkspaceView({
  onOpenAssistant,
  onCreateToolboxFromTools,
  onOpenToolbox,
}: WorkspaceViewProps) {
  const { t } = useTranslation('dashboard')
  const queryClient = useQueryClient()

  const [serverFilters, setServerFilters] = useState<Record<string, boolean>>({})
  const [selectedToolIds, setSelectedToolIds] = useState<Set<string>>(new Set())
  const [activeDrag, setActiveDrag] = useState<DragPayload | null>(null)

  const { data: rawTools = [], isLoading: isLoadingTools } = useQuery({
    queryKey: ['available-tools'],
    queryFn: () => toolGroupsApi.listAvailableTools(),
  })
  const { data: groups = [], isLoading: isLoadingGroups } = useQuery({
    queryKey: ['tool-groups'],
    queryFn: () => toolGroupsApi.list(),
  })
  const { data: poolState } = useQuery({
    queryKey: ['pool-state'],
    queryFn: () => poolApi.getState(),
    refetchInterval: 15000,
  })
  const { data: compositionList = { compositions: [], total: 0 } } = useQuery({
    queryKey: ['compositions', 'production'],
    queryFn: () => compositionsApi.list({ status: 'production' }),
  })

  const catalogTools: CatalogTool[] = useMemo(
    () =>
      (rawTools as ToolInfo[]).map((tool) => ({
        id: tool.id,
        name: tool.display_name || tool.tool_name,
        serverName: tool.server_name,
        serverId: tool.server_id,
        description: tool.description,
        kind: 'tool' as const,
        inPool: tool.is_visible_to_oauth_clients,
      })),
    [rawTools],
  )

  const poolTools = useMemo(
    () => catalogTools.filter((t) => t.inPool),
    [catalogTools],
  )

  const productionCompositions: CatalogTool[] = useMemo(() => {
    const list = compositionList.compositions || []
    return (list as Composition[]).map((comp) => ({
      id: comp.id,
      name: comp.name,
      serverName: null,
      description: comp.description,
      kind: 'composition' as const,
      inPool: true,
    }))
  }, [compositionList])

  const toolboxes: ToolboxSummary[] = useMemo(
    () =>
      (groups as ToolGroup[]).map((g) => ({
        id: g.id,
        name: g.name,
        description: g.description ?? null,
        color: g.color ?? null,
        visibility: g.visibility === 'public' ? 'organization' : (g.visibility as any),
        itemCount: g.items?.length ?? 0,
        toolIds: new Set(
          (g.items ?? [])
            .filter((i) => i.item_type === 'tool' && i.tool_id)
            .map((i) => i.tool_id as string),
        ),
      })),
    [groups],
  )

  const loadMutation = useMutation({
    mutationFn: (toolIds: string[]) => poolApi.load(toolIds, 'append'),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['pool-state'] })
      queryClient.invalidateQueries({ queryKey: ['available-tools'] })
      toast.success(
        t('tools.workspace.toastLoaded', {
          count: data.loaded_count,
          defaultValue: '{{count}} outil(s) chargé(s) dans le pool',
        }) as string,
      )
    },
    onError: (e: any) =>
      toast.error(e.response?.data?.detail || e.message || 'Failed to load'),
  })

  const unloadMutation = useMutation({
    mutationFn: (toolIds: string[]) => poolApi.unload(toolIds),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['pool-state'] })
      queryClient.invalidateQueries({ queryKey: ['available-tools'] })
      toast.success(
        t('tools.workspace.toastUnloaded', {
          count: data.unloaded_count,
          defaultValue: '{{count}} outil(s) retiré(s) du pool',
        }) as string,
      )
    },
    onError: (e: any) =>
      toast.error(e.response?.data?.detail || e.message || 'Failed to unload'),
  })

  const clearMutation = useMutation({
    mutationFn: () => poolApi.clear(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pool-state'] })
      queryClient.invalidateQueries({ queryKey: ['available-tools'] })
    },
  })

  const loadToolboxMutation = useMutation({
    mutationFn: (toolboxId: string) => poolApi.loadToolbox(toolboxId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['pool-state'] })
      queryClient.invalidateQueries({ queryKey: ['available-tools'] })
      toast.success(
        t('tools.workspace.toastToolboxLoaded', {
          count: data.loaded_count,
          defaultValue: 'Boîte chargée — {{count}} outil(s) ajoutés au pool',
        }) as string,
      )
    },
    onError: (e: any) =>
      toast.error(e.response?.data?.detail || e.message || 'Failed'),
  })

  const addToToolboxMutation = useMutation({
    mutationFn: async ({ toolboxId, toolIds }: { toolboxId: string; toolIds: string[] }) => {
      // Reuse existing toolGroupsApi addItem if available, else patch
      for (const id of toolIds) {
        await toolGroupsApi.addItem(toolboxId, { item_type: 'tool', tool_id: id })
      }
    },
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: ['tool-groups'] })
      toast.success(
        t('tools.workspace.toastToolboxAdded', {
          count: vars.toolIds.length,
          defaultValue: '{{count}} outil(s) ajoutés à la boîte',
        }) as string,
      )
    },
    onError: (e: any) =>
      toast.error(e.response?.data?.detail || e.message || 'Failed'),
  })

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  )

  const handleToggleServer = (serverName: string) => {
    setServerFilters((prev) => ({
      ...prev,
      [serverName]: prev[serverName] === false,
    }))
  }

  const handleToggleSelected = (toolId: string) => {
    setSelectedToolIds((prev) => {
      const next = new Set(prev)
      if (next.has(toolId)) next.delete(toolId)
      else next.add(toolId)
      return next
    })
  }

  const onDragStart = (event: DragStartEvent) => {
    const data = event.active.data.current as DragPayload | undefined
    if (data) setActiveDrag(data)
  }

  const onDragEnd = (event: DragEndEvent) => {
    setActiveDrag(null)
    if (!event.over) return
    const drag = event.active.data.current as DragPayload | undefined
    if (!drag) return

    const dropId = String(event.over.id)
    const draggedIds = selectedToolIds.has(drag.tool.id)
      ? Array.from(selectedToolIds)
      : [drag.tool.id]

    if (dropId === 'drop:pool') {
      if (drag.origin === 'pool') return
      const onlyTools = draggedIds.filter((id) => {
        const t = catalogTools.find((c) => c.id === id)
        return t && t.kind === 'tool'
      })
      if (onlyTools.length) {
        loadMutation.mutate(onlyTools)
        setSelectedToolIds(new Set())
      }
      return
    }

    if (dropId === 'drop:catalog') {
      if (drag.origin === 'pool' && drag.tool.kind === 'tool') {
        unloadMutation.mutate([drag.tool.id])
      }
      return
    }

    if (dropId === 'drop:toolbox:new') {
      if (onCreateToolboxFromTools) {
        onCreateToolboxFromTools(draggedIds)
        setSelectedToolIds(new Set())
      }
      return
    }

    if (dropId.startsWith('drop:toolbox:')) {
      const toolboxId = dropId.replace('drop:toolbox:', '')
      const onlyTools = draggedIds.filter((id) => {
        const t = catalogTools.find((c) => c.id === id)
        return t && t.kind === 'tool'
      })
      if (onlyTools.length) {
        addToToolboxMutation.mutate({ toolboxId, toolIds: onlyTools })
        setSelectedToolIds(new Set())
      }
      return
    }
  }

  return (
    <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 min-h-[600px]">
        <CatalogColumn
          tools={catalogTools}
          isLoading={isLoadingTools}
          serverFilters={serverFilters}
          onToggleServer={handleToggleServer}
          selectedToolIds={selectedToolIds}
          onToggleSelected={handleToggleSelected}
          onAddToPool={(tool) => loadMutation.mutate([tool.id])}
        />
        <PoolColumn
          poolTools={poolTools}
          productionCompositions={productionCompositions}
          poolSize={poolState?.pool_size ?? poolTools.length}
          compositionCount={poolState?.composition_count ?? productionCompositions.length}
          isLoading={isLoadingTools}
          onUnload={(tool) => unloadMutation.mutate([tool.id])}
          onClearPool={() => {
            if (
              window.confirm(
                t('tools.workspace.clearConfirm', {
                  defaultValue: 'Vider le pool actif ? Votre client MCP devra rappeler search.',
                }) as string,
              )
            ) {
              clearMutation.mutate()
            }
          }}
          isClearing={clearMutation.isPending}
          onOpenAssistant={onOpenAssistant}
        />
        <ToolboxesColumn
          toolboxes={toolboxes}
          isLoading={isLoadingGroups}
          onLoadToolboxIntoPool={(id) => loadToolboxMutation.mutate(id)}
          onOpenToolbox={onOpenToolbox}
        />
      </div>

      <DragOverlay>
        {activeDrag ? (
          <ToolCard
            data={activeDrag.tool as ToolCardData}
            origin={activeDrag.origin}
            draggable={false}
          />
        ) : null}
      </DragOverlay>
    </DndContext>
  )
}
