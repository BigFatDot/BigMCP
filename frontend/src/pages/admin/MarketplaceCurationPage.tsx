/**
 * Marketplace curation admin page (Phase 2).
 *
 * Lets the instance admin curate which marketplace servers their org
 * sees. Three states per server:
 * - default (no rule)  — server visible, ranks via popularity
 * - approved          — explicit OK, no ranking change
 * - featured          — bubbles to the top of the catalog (admin-set order)
 * - hidden            — invisible to non-admin users in the org
 *
 * Loads the global catalog (~200 servers) once and the org's curation
 * rules in parallel; the grid lets the admin flip the status per row.
 * Changes are batched and applied via PUT to keep the latency low.
 */

import { useEffect, useMemo, useState } from 'react'
import {
  ArrowPathIcon,
  CheckCircleIcon,
  EyeSlashIcon,
  StarIcon,
  ExclamationTriangleIcon,
  MagnifyingGlassIcon,
} from '@heroicons/react/24/outline'
import { Card, Button, Badge } from '@/components/ui'
import { marketplaceApi } from '@/services/marketplace'
import {
  listCurationRules,
  batchUpsertCuration,
  type CurationStatus,
  type CurationRule,
  type CurationUpdateItem,
} from '@/services/marketplaceCuration'
import type { MCPServer } from '@/types/marketplace'

type StatusFilter = 'all' | 'featured' | 'approved' | 'hidden' | 'unset'

const STATUS_LABEL: Record<CurationStatus, string> = {
  approved: 'Approved',
  featured: 'Featured',
  hidden: 'Hidden',
}

const STATUS_BADGE_VARIANT: Record<
  CurationStatus,
  'success' | 'orange' | 'gray'
> = {
  approved: 'success',
  featured: 'orange',
  hidden: 'gray',
}

function NextStatusButtons({
  current,
  onChange,
}: {
  current: CurationStatus | null
  onChange: (next: CurationStatus | null) => void
}) {
  const Btn = ({
    label,
    icon: Icon,
    target,
    activeColor,
  }: {
    label: string
    icon: React.ComponentType<{ className?: string }>
    target: CurationStatus | null
    activeColor: string
  }) => (
    <button
      type="button"
      onClick={() => onChange(current === target ? null : target)}
      className={`flex items-center gap-1 px-2 py-1 text-xs rounded border transition-colors ${
        current === target
          ? `${activeColor} text-white border-transparent`
          : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'
      }`}
      title={
        current === target ? `Currently ${label} — click to clear` : `Set ${label}`
      }
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </button>
  )

  return (
    <div className="flex gap-1.5">
      <Btn
        label="Featured"
        icon={StarIcon}
        target="featured"
        activeColor="bg-orange"
      />
      <Btn
        label="Approved"
        icon={CheckCircleIcon}
        target="approved"
        activeColor="bg-emerald-600"
      />
      <Btn
        label="Hidden"
        icon={EyeSlashIcon}
        target="hidden"
        activeColor="bg-gray-700"
      />
    </div>
  )
}

export function MarketplaceCurationPage() {
  const [servers, setServers] = useState<MCPServer[] | null>(null)
  const [rulesByServerId, setRulesByServerId] = useState<
    Map<string, CurationRule>
  >(new Map())
  const [counts, setCounts] = useState<{
    approved: number
    featured: number
    hidden: number
  }>({ approved: 0, featured: 0, hidden: 0 })
  const [pending, setPending] = useState<Map<string, CurationStatus | null>>(
    new Map(),
  )
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = async () => {
    setLoading(true)
    setError(null)
    try {
      // Pull the full catalog (admin gets the unfiltered view) + the
      // org's rules in parallel.
      const [catalog, curation] = await Promise.all([
        marketplaceApi.listServers({ limit: 200 }),
        listCurationRules(),
      ])
      setServers(catalog)
      const map = new Map<string, CurationRule>()
      curation.rules.forEach((r) => map.set(r.server_id, r))
      setRulesByServerId(map)
      setCounts(curation.counts)
      setPending(new Map())
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const effectiveStatusFor = (serverId: string): CurationStatus | null => {
    if (pending.has(serverId)) return pending.get(serverId) ?? null
    return rulesByServerId.get(serverId)?.status ?? null
  }

  const setStatusFor = (serverId: string, next: CurationStatus | null) => {
    setPending((prev) => {
      const m = new Map(prev)
      const original = rulesByServerId.get(serverId)?.status ?? null
      if (next === original) {
        m.delete(serverId)
      } else {
        m.set(serverId, next)
      }
      return m
    })
  }

  const handleSave = async () => {
    if (pending.size === 0) return
    setSaving(true)
    setError(null)
    try {
      const items: CurationUpdateItem[] = []
      pending.forEach((status, server_id) => {
        items.push({ server_id, status })
      })
      const updated = await batchUpsertCuration(items)
      const map = new Map<string, CurationRule>()
      updated.rules.forEach((r) => map.set(r.server_id, r))
      setRulesByServerId(map)
      setCounts(updated.counts)
      setPending(new Map())
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const filteredServers = useMemo(() => {
    if (!servers) return []
    let result = servers
    if (search) {
      const q = search.toLowerCase()
      result = result.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          s.description.toLowerCase().includes(q) ||
          (s.author || '').toLowerCase().includes(q),
      )
    }
    if (statusFilter !== 'all') {
      result = result.filter((s) => {
        const status = effectiveStatusFor(s.id)
        if (statusFilter === 'unset') return status === null
        return status === statusFilter
      })
    }
    return result
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [servers, search, statusFilter, pending, rulesByServerId])

  return (
    <div className="container py-8 max-w-5xl">
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <StarIcon className="h-7 w-7 text-orange" />
            Marketplace curation
          </h1>
          <p className="text-sm text-gray-600 mt-1 max-w-3xl">
            Pick which marketplace servers your org's users see, and which
            ones get pinned to the top. Servers without a rule stay visible
            (default). Hidden ones disappear from the user-facing
            marketplace; featured ones bubble to the top with a badge.
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <Button variant="secondary" onClick={refresh} disabled={loading || saving}>
            <ArrowPathIcon className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Button
            onClick={handleSave}
            disabled={pending.size === 0 || saving}
          >
            {saving
              ? 'Saving…'
              : pending.size === 0
              ? 'No changes'
              : `Save ${pending.size} change${pending.size > 1 ? 's' : ''}`}
          </Button>
        </div>
      </div>

      {/* Counts */}
      <div className="flex items-center gap-3 mb-4 text-sm">
        <Badge variant="orange">{counts.featured} featured</Badge>
        <Badge variant="success">{counts.approved} approved</Badge>
        <Badge variant="gray">{counts.hidden} hidden</Badge>
        <span className="text-xs text-gray-500">
          (out of {servers?.length ?? '…'} catalog servers)
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

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <div className="relative flex-1 min-w-[200px]">
          <MagnifyingGlassIcon className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search servers (name, description, author)…"
            className="w-full pl-8 pr-2 py-1.5 border border-gray-300 rounded text-sm"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
          className="px-2 py-1.5 border border-gray-300 rounded text-sm bg-white"
        >
          <option value="all">All</option>
          <option value="featured">Featured only</option>
          <option value="approved">Approved only</option>
          <option value="hidden">Hidden only</option>
          <option value="unset">No rule (default)</option>
        </select>
      </div>

      {loading && servers === null && (
        <Card className="p-8 text-center text-sm text-gray-500">
          Loading marketplace catalog + org curation…
        </Card>
      )}

      {!loading && filteredServers.length === 0 && (
        <Card className="p-8 text-center text-sm text-gray-500">
          No servers match the current filters.
        </Card>
      )}

      {filteredServers.length > 0 && (
        <div className="space-y-2">
          {filteredServers.map((s) => {
            const status = effectiveStatusFor(s.id)
            const isDirty = pending.has(s.id)
            return (
              <Card
                key={s.id}
                className={`p-3 ${isDirty ? 'ring-2 ring-orange/40' : ''}`}
              >
                <div className="flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold text-gray-900 truncate">
                        {s.name}
                      </h3>
                      {status && (
                        <Badge variant={STATUS_BADGE_VARIANT[status]} size="sm">
                          {STATUS_LABEL[status]}
                        </Badge>
                      )}
                      {isDirty && (
                        <span className="text-xs text-orange font-medium">
                          unsaved
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-500 line-clamp-1 mt-0.5">
                      {s.description}
                    </p>
                    <div className="flex items-center gap-2 mt-1 text-[10px] text-gray-400">
                      <span className="font-mono">{s.id}</span>
                      {s.author && <span>· by {s.author}</span>}
                      {s.category && (
                        <span>· {Array.isArray(s.category) ? s.category.join(', ') : s.category}</span>
                      )}
                    </div>
                  </div>
                  <NextStatusButtons
                    current={status}
                    onChange={(next) => setStatusFor(s.id, next)}
                  />
                </div>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
