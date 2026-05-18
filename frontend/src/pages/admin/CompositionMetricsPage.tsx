/**
 * Composition execution telemetry — B-1 adoption insights.
 *
 * Aggregates over composition_execution + execution_step_event from
 * the backend (GET /api/v1/admin/composition-metrics). Computed at
 * request time from the DB, not scraped from Prometheus, so it works
 * on a fresh instance without metrics history.
 *
 * What it shows:
 * - Live counts: running / suspended / queued
 * - Executions terminated within the selected window, by status
 * - Step events by type (started / suspended / succeeded / expired)
 * - Suspension reasons (which B-1 step types are actually used)
 *
 * Window is configurable (1–90 days) via the dropdown.
 */

import { useEffect, useState } from 'react'
import { ArrowPathIcon, ChartBarIcon } from '@heroicons/react/24/outline'
import { Card, Button } from '@/components/ui'
import { apiClient as api } from '@/services/api'

interface CompositionMetrics {
  window_days: number
  computed_at: string
  totals: {
    executions_in_window: number
    running: number
    suspended: number
    queued: number
  }
  by_status: Record<string, number>
  by_step_event: Record<string, number>
  by_suspension_reason: Record<string, number>
}

const STATUS_TONE: Record<string, string> = {
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
  cancelled: 'bg-gray-100 text-gray-700',
  expired: 'bg-amber-100 text-amber-700',
  running: 'bg-blue-100 text-blue-700',
  suspended: 'bg-purple-100 text-purple-700',
  queued: 'bg-gray-100 text-gray-700',
}

export function CompositionMetricsPage() {
  const [metrics, setMetrics] = useState<CompositionMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [windowDays, setWindowDays] = useState(7)

  const refresh = async (days = windowDays) => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await api.get<CompositionMetrics>(
        '/admin/composition-metrics',
        { params: { window_days: days } }
      )
      setMetrics(data)
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh(windowDays)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [windowDays])

  const stepEventEntries = metrics
    ? Object.entries(metrics.by_step_event).sort((a, b) => b[1] - a[1])
    : []
  const statusEntries = metrics
    ? Object.entries(metrics.by_status).sort((a, b) => b[1] - a[1])
    : []
  const reasonEntries = metrics
    ? Object.entries(metrics.by_suspension_reason).sort((a, b) => b[1] - a[1])
    : []

  return (
    <div className="container mx-auto px-4 py-8 max-w-6xl">
      <div className="flex items-baseline justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <ChartBarIcon className="w-6 h-6 text-orange" />
            Composition metrics
          </h1>
          <p className="text-sm text-gray-600 mt-1">
            B-1 adoption insights — which step types are actually used, and how
            workflows terminate.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={windowDays}
            onChange={(e) => setWindowDays(Number(e.target.value))}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-orange focus:border-orange"
          >
            <option value={1}>Last 24h</option>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <Button
            variant="secondary"
            onClick={() => refresh()}
            disabled={loading}
          >
            <ArrowPathIcon className="w-4 h-4" />
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <Card padding="md" className="mb-4 border-red-200 bg-red-50">
          <p className="text-sm text-red-700">{error}</p>
        </Card>
      )}

      {loading && !metrics ? (
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-gray-300 border-t-orange mx-auto" />
        </div>
      ) : metrics ? (
        <div className="space-y-6">
          {/* Live counts */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Total in window" value={metrics.totals.executions_in_window} />
            <StatCard label="Running" value={metrics.totals.running} tone="blue" />
            <StatCard label="Suspended" value={metrics.totals.suspended} tone="purple" />
            <StatCard label="Queued" value={metrics.totals.queued} tone="gray" />
          </div>

          {/* By status */}
          <Card padding="md">
            <h2 className="text-sm font-semibold text-gray-900 mb-3">
              Executions by status (last {metrics.window_days}d)
            </h2>
            {statusEntries.length === 0 ? (
              <p className="text-sm text-gray-500 italic">No executions in this window.</p>
            ) : (
              <div className="space-y-2">
                {statusEntries.map(([status, n]) => (
                  <BarRow
                    key={status}
                    label={status}
                    count={n}
                    total={metrics.totals.executions_in_window || 1}
                    tone={STATUS_TONE[status] || 'bg-gray-100 text-gray-700'}
                  />
                ))}
              </div>
            )}
          </Card>

          {/* Step events */}
          <Card padding="md">
            <h2 className="text-sm font-semibold text-gray-900 mb-3">
              Step events (last {metrics.window_days}d)
            </h2>
            {stepEventEntries.length === 0 ? (
              <p className="text-sm text-gray-500 italic">No step events.</p>
            ) : (
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {stepEventEntries.map(([evt, n]) => (
                  <div
                    key={evt}
                    className="flex items-baseline justify-between p-2 border border-gray-200 rounded"
                  >
                    <span className="text-xs text-gray-700">{evt}</span>
                    <span className="text-sm font-semibold text-gray-900">{n.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Suspension reasons → which B-1 step types are actually used */}
          <Card padding="md">
            <h2 className="text-sm font-semibold text-gray-900 mb-1">
              Suspension reasons (B-1 step type adoption)
            </h2>
            <p className="text-xs text-gray-600 mb-3">
              Every suspended step records its reason. This tells you which
              durable step types your users actually reach for.
            </p>
            {reasonEntries.length === 0 ? (
              <p className="text-sm text-gray-500 italic">
                No suspensions recorded in this window — either no workflow uses
                durable step types yet, or none reached a suspending step.
              </p>
            ) : (
              <div className="space-y-2">
                {reasonEntries.map(([reason, n]) => {
                  const total = reasonEntries.reduce((acc, [, x]) => acc + x, 0)
                  return (
                    <BarRow
                      key={reason}
                      label={reason}
                      count={n}
                      total={total || 1}
                      tone="bg-purple-100 text-purple-700"
                    />
                  )
                })}
              </div>
            )}
          </Card>

          <p className="text-xs text-gray-500 text-right">
            Computed at {new Date(metrics.computed_at).toLocaleString()}
          </p>
        </div>
      ) : null}
    </div>
  )
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone?: 'blue' | 'purple' | 'gray'
}) {
  const toneClass =
    tone === 'blue'
      ? 'text-blue-700'
      : tone === 'purple'
        ? 'text-purple-700'
        : tone === 'gray'
          ? 'text-gray-700'
          : 'text-gray-900'
  return (
    <Card padding="md">
      <div className="text-xs uppercase tracking-wide text-gray-600">{label}</div>
      <div className={`text-2xl font-bold mt-1 ${toneClass}`}>
        {value.toLocaleString()}
      </div>
    </Card>
  )
}

function BarRow({
  label,
  count,
  total,
  tone,
}: {
  label: string
  count: number
  total: number
  tone: string
}) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-sm text-gray-700 font-mono">{label}</span>
        <span className="text-sm font-semibold text-gray-900">
          {count.toLocaleString()}{' '}
          <span className="text-xs text-gray-500">({pct}%)</span>
        </span>
      </div>
      <div className="h-2 bg-gray-100 rounded overflow-hidden">
        <div
          className={`h-full ${tone.split(' ')[0]}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
