/**
 * Composition Approvals — pending list for the current user (B-1.4).
 *
 * Filtered server-side: only executions where the current user is in
 * the approver gate AND the four-eyes rule doesn't deny self-approval.
 * Click View → ExecutionDetailPage → approve/reject inline.
 *
 * Polls every 5s while ≥1 row is visible (mirrors ExecutionsListPage).
 */

import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowPathIcon, HandRaisedIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { Button, Card } from '@/components/ui'
import {
  executionsApi,
  type ExecutionSummary,
} from '@/services/compositionExecutions'

const POLL_INTERVAL_MS = 5_000

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

export function PendingApprovalsPage() {
  const [items, setItems] = useState<ExecutionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const fetchAll = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    else setRefreshing(true)
    try {
      const resp = await executionsApi.listPendingApprovals({ limit: 100 })
      setItems(resp.items)
    } catch (err) {
      console.error('failed to fetch pending approvals', err)
      if (!silent) toast.error('Failed to load pending approvals')
    } finally {
      if (!silent) setLoading(false)
      else setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    fetchAll(false)
  }, [fetchAll])

  useEffect(() => {
    const t = setInterval(() => fetchAll(true), POLL_INTERVAL_MS)
    return () => clearInterval(t)
  }, [fetchAll])

  return (
    <div className="container mx-auto px-4 py-6 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <HandRaisedIcon className="w-6 h-6 text-pink-600" />
            Pending approvals
          </h1>
          <p className="text-sm text-gray-600 mt-1">
            Compositions in your org are paused waiting for your decision.
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={() => fetchAll(false)}
          disabled={loading || refreshing}
        >
          <ArrowPathIcon
            className={`w-4 h-4 mr-1 ${refreshing ? 'animate-spin' : ''}`}
          />
          Refresh
        </Button>
      </div>

      {loading ? (
        <div className="text-center text-gray-500 py-12">Loading…</div>
      ) : items.length === 0 ? (
        <Card padding="lg" className="text-center text-gray-500">
          No approvals pending. New requests will appear here automatically.
        </Card>
      ) : (
        <div className="space-y-2">
          {items.map((it) => (
            <Card
              key={it.id}
              padding="md"
              className="hover:shadow-sm transition border-pink-200"
            >
              <div className="flex flex-wrap items-center gap-3">
                <span className="px-2 py-0.5 rounded bg-pink-100 text-pink-800 text-xs font-medium">
                  awaiting your decision
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-mono text-gray-500 truncate">
                    {it.id.slice(0, 8)}…
                  </div>
                  <div className="text-xs text-gray-600 mt-0.5">
                    trigger: <span className="font-medium">{it.trigger}</span>
                    {it.current_step_id && (
                      <>
                        {' · '}step:{' '}
                        <span className="font-mono">{it.current_step_id}</span>
                      </>
                    )}
                  </div>
                </div>
                <div className="text-xs text-gray-500 text-right">
                  <div>requested {formatRelative(it.started_at)}</div>
                  <div>updated {formatRelative(it.updated_at)}</div>
                </div>
                <Link
                  to={`/app/compositions/executions/${it.id}`}
                  className="text-sm font-medium text-pink-700 hover:underline"
                >
                  Review →
                </Link>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
