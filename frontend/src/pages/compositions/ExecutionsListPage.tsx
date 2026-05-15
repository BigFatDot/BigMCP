/**
 * Composition Executions — list view (B-0 chunk 11).
 *
 * Default filter: non-terminal statuses (queued / running / suspended).
 * Toggle "show terminal" extends to completed/failed/expired/cancelled.
 *
 * Polls every 5s while ≥1 row is non-terminal so the UI stays fresh
 * without manual refresh. SSE polish (subscribe to
 * composition://executions/{id}) lands later — this is the B-0 polling
 * fallback.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  ArrowPathIcon,
  CheckCircleIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  PauseCircleIcon,
  PlayCircleIcon,
  StopCircleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { Button, Card } from '@/components/ui'
import {
  executionsApi,
  type ExecutionStatus,
  type ExecutionSummary,
  NON_TERMINAL_STATUSES,
} from '@/services/compositionExecutions'

const POLL_INTERVAL_MS = 5_000

const STATUS_BADGES: Record<
  ExecutionStatus,
  { label: string; bg: string; text: string; Icon: typeof PlayCircleIcon }
> = {
  queued: { label: 'queued', bg: 'bg-gray-100', text: 'text-gray-700', Icon: ClockIcon },
  running: { label: 'running', bg: 'bg-blue-100', text: 'text-blue-700', Icon: PlayCircleIcon },
  suspended: {
    label: 'suspended',
    bg: 'bg-amber-100',
    text: 'text-amber-800',
    Icon: PauseCircleIcon,
  },
  completed: {
    label: 'completed',
    bg: 'bg-green-100',
    text: 'text-green-700',
    Icon: CheckCircleIcon,
  },
  failed: { label: 'failed', bg: 'bg-red-100', text: 'text-red-700', Icon: XCircleIcon },
  expired: {
    label: 'expired',
    bg: 'bg-gray-200',
    text: 'text-gray-700',
    Icon: ExclamationTriangleIcon,
  },
  cancelled: {
    label: 'cancelled',
    bg: 'bg-slate-200',
    text: 'text-slate-700',
    Icon: StopCircleIcon,
  },
}

function StatusBadge({ status }: { status: ExecutionStatus }) {
  const cfg = STATUS_BADGES[status]
  const Icon = cfg.Icon
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${cfg.bg} ${cfg.text}`}
    >
      <Icon className="w-3.5 h-3.5" />
      {cfg.label}
    </span>
  )
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime()
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export function ExecutionsListPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const initialIncludeTerminal = searchParams.get('include_terminal') === 'true'
  const initialStatusFilter = searchParams.get('status')

  const [includeTerminal, setIncludeTerminal] = useState(initialIncludeTerminal)
  const [statusFilter, setStatusFilter] = useState<ExecutionStatus | null>(
    (initialStatusFilter as ExecutionStatus | null) ?? null,
  )
  const [items, setItems] = useState<ExecutionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [cancellingIds, setCancellingIds] = useState<Set<string>>(new Set())

  const fetchExecutions = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true)
      else setRefreshing(true)
      try {
        const resp = await executionsApi.list({
          status: statusFilter ? [statusFilter] : undefined,
          includeTerminal,
          limit: 100,
        })
        setItems(resp.items)
      } catch (err) {
        // Don't toast on silent polls — only when the user actively
        // triggered the fetch. The console keeps a record either way.
        console.error('failed to fetch executions', err)
        if (!silent) toast.error('Failed to load executions')
      } finally {
        if (!silent) setLoading(false)
        else setRefreshing(false)
      }
    },
    [includeTerminal, statusFilter],
  )

  useEffect(() => {
    fetchExecutions(false)
  }, [fetchExecutions])

  // Poll only while at least one row is non-terminal — terminal-only
  // lists never change, no point hammering the server.
  const hasNonTerminal = useMemo(
    () => items.some((it) => NON_TERMINAL_STATUSES.includes(it.status)),
    [items],
  )

  useEffect(() => {
    if (!hasNonTerminal) return
    const t = setInterval(() => {
      fetchExecutions(true)
    }, POLL_INTERVAL_MS)
    return () => clearInterval(t)
  }, [hasNonTerminal, fetchExecutions])

  const handleToggleTerminal = (next: boolean) => {
    setIncludeTerminal(next)
    const sp = new URLSearchParams(searchParams)
    if (next) sp.set('include_terminal', 'true')
    else sp.delete('include_terminal')
    setSearchParams(sp, { replace: true })
  }

  const handleStatusChip = (status: ExecutionStatus | null) => {
    setStatusFilter(status)
    const sp = new URLSearchParams(searchParams)
    if (status) sp.set('status', status)
    else sp.delete('status')
    setSearchParams(sp, { replace: true })
  }

  const handleCancel = async (executionId: string) => {
    const ok = window.confirm(
      'Cancel this execution? The current step will finish first; the execution will land in cancelled at the next boundary.',
    )
    if (!ok) return
    setCancellingIds((s) => new Set(s).add(executionId))
    try {
      const resp = await executionsApi.cancel(executionId)
      if (resp.cancel_requested) {
        toast.success('Cancel requested — landing at next step boundary')
      } else {
        toast(resp.detail || 'Already terminal')
      }
      await fetchExecutions(true)
    } catch (err) {
      console.error(err)
      toast.error('Cancel failed')
    } finally {
      setCancellingIds((s) => {
        const next = new Set(s)
        next.delete(executionId)
        return next
      })
    }
  }

  const filteredCount = items.length

  return (
    <div className="container mx-auto px-4 py-6 max-w-6xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            Composition Executions
          </h1>
          <p className="text-sm text-gray-600 mt-1">
            Track running, suspended, and completed runs of your compositions.
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={() => fetchExecutions(false)}
          disabled={loading || refreshing}
        >
          <ArrowPathIcon
            className={`w-4 h-4 mr-1 ${refreshing ? 'animate-spin' : ''}`}
          />
          Refresh
        </Button>
      </div>

      {/* Filter bar */}
      <Card padding="md" className="mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm font-medium text-gray-700">Status:</span>
          <button
            type="button"
            className={`px-3 py-1 rounded text-xs font-medium border ${
              statusFilter === null
                ? 'bg-orange-100 text-orange-800 border-orange-300'
                : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
            }`}
            onClick={() => handleStatusChip(null)}
          >
            All
          </button>
          {(['running', 'suspended', 'queued'] as ExecutionStatus[]).map((s) => (
            <button
              key={s}
              type="button"
              className={`px-3 py-1 rounded text-xs font-medium border ${
                statusFilter === s
                  ? 'bg-orange-100 text-orange-800 border-orange-300'
                  : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
              }`}
              onClick={() => handleStatusChip(s)}
            >
              {s}
            </button>
          ))}

          <div className="ml-auto flex items-center gap-2">
            <label className="inline-flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={includeTerminal}
                onChange={(e) => handleToggleTerminal(e.target.checked)}
                className="rounded border-gray-300"
              />
              Show terminal (completed / failed / cancelled / expired)
            </label>
          </div>
        </div>
      </Card>

      {/* List */}
      {loading ? (
        <div className="text-center text-gray-500 py-12">Loading…</div>
      ) : filteredCount === 0 ? (
        <Card padding="lg" className="text-center text-gray-500">
          No executions match the current filter.
          {!includeTerminal && (
            <>
              {' '}
              <button
                type="button"
                className="text-orange hover:underline"
                onClick={() => handleToggleTerminal(true)}
              >
                Include terminal?
              </button>
            </>
          )}
        </Card>
      ) : (
        <div className="space-y-2">
          {items.map((it) => {
            const isCancelling = cancellingIds.has(it.id)
            const canCancel =
              !it.cancel_requested &&
              NON_TERMINAL_STATUSES.includes(it.status)
            return (
              <Card key={it.id} padding="md" className="hover:shadow-sm transition">
                <div className="flex flex-wrap items-center gap-3">
                  <StatusBadge status={it.status} />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-mono text-gray-500 truncate">
                      {it.id.slice(0, 8)}…
                    </div>
                    <div className="text-xs text-gray-600 mt-0.5">
                      trigger: <span className="font-medium">{it.trigger}</span>
                      {it.current_step_id && (
                        <>
                          {' · '}
                          step:{' '}
                          <span className="font-mono">{it.current_step_id}</span>
                        </>
                      )}
                      {it.suspension_reason && (
                        <>
                          {' · '}
                          waiting on:{' '}
                          <span className="font-mono">
                            {it.suspension_reason}
                          </span>
                        </>
                      )}
                    </div>
                    {it.error && (
                      <div className="text-xs text-red-700 mt-0.5 truncate">
                        error: {it.error}
                      </div>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 text-right">
                    <div>started {formatRelative(it.started_at)}</div>
                    <div>updated {formatRelative(it.updated_at)}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Link
                      to={`/app/compositions/executions/${it.id}`}
                      className="text-sm text-orange hover:underline"
                    >
                      View
                    </Link>
                    {canCancel && (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => handleCancel(it.id)}
                        disabled={isCancelling}
                      >
                        {isCancelling ? 'Cancelling…' : 'Cancel'}
                      </Button>
                    )}
                    {it.cancel_requested &&
                      NON_TERMINAL_STATUSES.includes(it.status) && (
                        <span className="text-xs text-amber-700 font-medium">
                          cancel pending…
                        </span>
                      )}
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
