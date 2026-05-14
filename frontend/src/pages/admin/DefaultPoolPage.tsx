/**
 * Org default pool admin page (Phase 3).
 *
 * Lets the instance admin pin tools and compositions that every user of
 * the org will see in their pool the moment their MCP client connects.
 * Solves the cold-start problem (empty pool on first tools/list) without
 * forcing every agent to call `search` first.
 *
 * Two columns:
 * - Left: a searchable picker of every tool + production composition in
 *   the org. Adding a row promotes it to the org default.
 * - Right: the current default pool, ordered by position. Removing a row
 *   takes it out of the default (per-user pins are unaffected).
 */

import { useEffect, useMemo, useState } from 'react'
import {
  ArrowPathIcon,
  ExclamationTriangleIcon,
  MagnifyingGlassIcon,
  MapPinIcon,
  PlusIcon,
  SparklesIcon,
  TrashIcon,
  WrenchScrewdriverIcon,
} from '@heroicons/react/24/outline'
import { Card, Button, Badge } from '@/components/ui'
import {
  orgDefaultPoolApi,
  type OrgDefaultPoolEntry,
} from '@/services/persistentPool'
import {
  toolGroupsApi,
  compositionsApi,
  type ToolInfo,
  type Composition,
} from '@/services/marketplace'

type CatalogItem =
  | {
      kind: 'tool'
      id: string
      name: string
      serverName: string | null
      description: string
    }
  | {
      kind: 'composition'
      id: string
      name: string
      serverName: null
      description: string
    }

type CatalogFilter = 'all' | 'tools' | 'compositions' | 'inDefault'

export function DefaultPoolPage() {
  const [catalog, setCatalog] = useState<CatalogItem[] | null>(null)
  const [entries, setEntries] = useState<OrgDefaultPoolEntry[]>([])
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<CatalogFilter>('all')
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = async () => {
    setLoading(true)
    setError(null)
    try {
      const [tools, compsResult, current] = await Promise.all([
        toolGroupsApi.listAvailableTools(),
        compositionsApi.list({ status: 'production' }),
        orgDefaultPoolApi.list(),
      ])
      const toolItems: CatalogItem[] = (tools as ToolInfo[]).map((t) => ({
        kind: 'tool',
        id: String(t.id),
        name: t.display_name || t.tool_name,
        serverName: t.server_name || null,
        description: t.description || '',
      }))
      const comps = (compsResult.compositions || []) as Composition[]
      const compItems: CatalogItem[] = comps.map((c) => ({
        kind: 'composition',
        id: String(c.id),
        name: c.name,
        serverName: null,
        description: c.description || '',
      }))
      setCatalog([...toolItems, ...compItems])
      setEntries(current.entries)
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  // ---- Lookups -----------------------------------------------------------
  const inDefaultIds = useMemo(() => {
    const s = new Set<string>()
    for (const e of entries) {
      if (e.tool_id) s.add(`tool:${e.tool_id}`)
      if (e.composition_id) s.add(`composition:${e.composition_id}`)
    }
    return s
  }, [entries])

  const itemKey = (it: CatalogItem) => `${it.kind}:${it.id}`

  const catalogById = useMemo(() => {
    const m = new Map<string, CatalogItem>()
    for (const it of catalog || []) m.set(itemKey(it), it)
    return m
  }, [catalog])

  // ---- Add / remove ------------------------------------------------------
  const add = async (it: CatalogItem) => {
    const key = itemKey(it)
    setBusyId(key)
    setError(null)
    try {
      const ref =
        it.kind === 'tool' ? { tool_id: it.id } : { composition_id: it.id }
      const created = await orgDefaultPoolApi.add(ref)
      setEntries((prev) => [...prev, created].sort(
        (a, b) => a.position - b.position,
      ))
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Add failed')
    } finally {
      setBusyId(null)
    }
  }

  const remove = async (entry: OrgDefaultPoolEntry) => {
    setBusyId(entry.id)
    setError(null)
    try {
      await orgDefaultPoolApi.remove(entry.id)
      setEntries((prev) => prev.filter((e) => e.id !== entry.id))
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Remove failed')
    } finally {
      setBusyId(null)
    }
  }

  // ---- Filtering ---------------------------------------------------------
  const filteredCatalog = useMemo(() => {
    if (!catalog) return []
    let out = catalog
    if (filter === 'tools') out = out.filter((c) => c.kind === 'tool')
    else if (filter === 'compositions')
      out = out.filter((c) => c.kind === 'composition')
    else if (filter === 'inDefault')
      out = out.filter((c) => inDefaultIds.has(itemKey(c)))
    if (search) {
      const q = search.toLowerCase()
      out = out.filter(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          c.description.toLowerCase().includes(q) ||
          (c.serverName || '').toLowerCase().includes(q),
      )
    }
    return out.slice(0, 200)
  }, [catalog, filter, search, inDefaultIds])

  const counts = useMemo(() => {
    let tools = 0
    let compositions = 0
    for (const e of entries) {
      if (e.tool_id) tools += 1
      else if (e.composition_id) compositions += 1
    }
    return { tools, compositions }
  }, [entries])

  return (
    <div className="container py-8 max-w-6xl">
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <MapPinIcon className="h-7 w-7 text-orange" />
            Default pool
          </h1>
          <p className="text-sm text-gray-600 mt-1 max-w-3xl">
            Pin the tools and compositions that every user of your org
            should see the moment their MCP client connects. Solves the
            cold-start problem &mdash; first <code>tools/list</code>
            already returns a curated catalog, no <code>search</code> call
            needed.
          </p>
        </div>
        <Button variant="secondary" onClick={refresh} disabled={loading}>
          <ArrowPathIcon className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      <div className="flex items-center gap-3 mb-4 text-sm">
        <Badge variant="success">{counts.tools} tools</Badge>
        <Badge variant="orange">{counts.compositions} compositions</Badge>
        <span className="text-xs text-gray-500">
          (out of {catalog?.length ?? '…'} catalog entries)
        </span>
      </div>

      {error && (
        <Card className="mb-4 p-4 bg-red-50 border border-red-200">
          <div className="flex items-start gap-3 text-sm text-red-800">
            <ExclamationTriangleIcon className="h-5 w-5 text-red-500 flex-shrink-0" />
            <div>{error}</div>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Catalog */}
        <div>
          <div className="flex items-baseline justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
              Catalog
            </h2>
            <span className="text-xs text-gray-500">
              {filteredCatalog.length} shown
            </span>
          </div>
          <div className="flex flex-wrap gap-2 mb-3">
            <div className="relative flex-1 min-w-[200px]">
              <MagnifyingGlassIcon className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search tools, compositions…"
                className="w-full pl-8 pr-2 py-1.5 border border-gray-300 rounded text-sm"
              />
            </div>
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value as CatalogFilter)}
              className="px-2 py-1.5 border border-gray-300 rounded text-sm bg-white"
            >
              <option value="all">All</option>
              <option value="tools">Tools only</option>
              <option value="compositions">Compositions only</option>
              <option value="inDefault">In default pool</option>
            </select>
          </div>

          {loading && catalog === null && (
            <Card className="p-8 text-center text-sm text-gray-500">
              Loading catalog…
            </Card>
          )}

          {!loading && filteredCatalog.length === 0 && (
            <Card className="p-8 text-center text-sm text-gray-500">
              No catalog entries match the current filter.
            </Card>
          )}

          {filteredCatalog.length > 0 && (
            <div className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
              {filteredCatalog.map((it) => {
                const key = itemKey(it)
                const inDefault = inDefaultIds.has(key)
                const Icon =
                  it.kind === 'composition' ? SparklesIcon : WrenchScrewdriverIcon
                return (
                  <Card key={key} className="p-3">
                    <div className="flex items-start gap-2">
                      <Icon
                        className={
                          it.kind === 'composition'
                            ? 'h-4 w-4 mt-1 text-orange flex-shrink-0'
                            : 'h-4 w-4 mt-1 text-gray-500 flex-shrink-0'
                        }
                      />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-semibold text-gray-900 truncate">
                          {it.name}
                        </div>
                        {it.serverName && (
                          <div className="text-xs text-gray-500 truncate">
                            {it.serverName}
                          </div>
                        )}
                        {it.description && (
                          <div className="text-xs text-gray-600 mt-1 line-clamp-2">
                            {it.description}
                          </div>
                        )}
                      </div>
                      {inDefault ? (
                        <Badge variant="success" size="sm">
                          In default
                        </Badge>
                      ) : (
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={busyId === key}
                          onClick={() => add(it)}
                        >
                          <PlusIcon className="h-3.5 w-3.5 mr-1" />
                          Add
                        </Button>
                      )}
                    </div>
                  </Card>
                )
              })}
            </div>
          )}
        </div>

        {/* Default pool */}
        <div>
          <div className="flex items-baseline justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
              Org default pool
            </h2>
            <span className="text-xs text-gray-500">{entries.length} entries</span>
          </div>

          {entries.length === 0 ? (
            <Card className="p-8 text-center text-sm text-gray-500">
              Nothing pinned yet. Add tools or compositions from the catalog
              on the left.
            </Card>
          ) : (
            <div className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
              {entries.map((e) => {
                const key = e.tool_id
                  ? `tool:${e.tool_id}`
                  : `composition:${e.composition_id}`
                const it = catalogById.get(key)
                const fallbackName = e.tool_id
                  ? `Tool ${e.tool_id.slice(0, 8)}…`
                  : `Composition ${(e.composition_id || '').slice(0, 8)}…`
                const Icon = e.composition_id
                  ? SparklesIcon
                  : WrenchScrewdriverIcon
                return (
                  <Card key={e.id} className="p-3">
                    <div className="flex items-start gap-2">
                      <Icon
                        className={
                          e.composition_id
                            ? 'h-4 w-4 mt-1 text-orange flex-shrink-0'
                            : 'h-4 w-4 mt-1 text-gray-500 flex-shrink-0'
                        }
                      />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-semibold text-gray-900 truncate">
                          {it?.name || fallbackName}
                        </div>
                        {it?.serverName && (
                          <div className="text-xs text-gray-500 truncate">
                            {it.serverName}
                          </div>
                        )}
                        <div className="text-[10px] text-gray-400 mt-1">
                          position {e.position}
                          {!it && ' · entry references a deleted item'}
                        </div>
                      </div>
                      <button
                        type="button"
                        disabled={busyId === e.id}
                        onClick={() => remove(e)}
                        className="text-gray-400 hover:text-red-600 transition-colors p-1"
                        title="Remove from default pool"
                      >
                        <TrashIcon className="h-4 w-4" />
                      </button>
                    </div>
                  </Card>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
