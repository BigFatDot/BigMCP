/**
 * Composition Execution — detail view (B-0 chunk 11).
 *
 * Header: status badge + cancel button (if non-terminal).
 * Body:   timeline of execution_step_event rows + current state.
 * Footer: result (if completed) or error (if failed).
 *
 * For ``suspended`` with ``_test_suspend`` reason, exposes a "Provide
 * test response" form so an operator can drive the resume flow from
 * the UI without curl. Production step types (elicit, wait_callback)
 * land in B-1+ — they'll get their own bespoke widgets.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeftIcon,
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
import { ElicitForm, type ElicitSchema } from '@/components/compositions'
import {
  executionsApi,
  type ExecutionDetail,
  type ExecutionStatus,
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
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded text-sm font-medium ${cfg.bg} ${cfg.text}`}
    >
      <Icon className="w-4 h-4" />
      {cfg.label}
    </span>
  )
}

function formatTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString()
}

export function ExecutionDetailPage() {
  const { executionId } = useParams<{ executionId: string }>()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<ExecutionDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [resumeText, setResumeText] = useState('{"value": 42}')
  const [resuming, setResuming] = useState(false)
  const [cancelling, setCancelling] = useState(false)

  const fetchDetail = useCallback(
    async (silent = false) => {
      if (!executionId) return
      if (!silent) setLoading(true)
      else setRefreshing(true)
      try {
        const resp = await executionsApi.get(executionId)
        setDetail(resp)
      } catch (err) {
        console.error(err)
        if (!silent) toast.error('Failed to load execution')
      } finally {
        if (!silent) setLoading(false)
        else setRefreshing(false)
      }
    },
    [executionId],
  )

  useEffect(() => {
    fetchDetail(false)
  }, [fetchDetail])

  // Poll while non-terminal
  useEffect(() => {
    if (!detail) return
    if (!NON_TERMINAL_STATUSES.includes(detail.status)) return
    const t = setInterval(() => fetchDetail(true), POLL_INTERVAL_MS)
    return () => clearInterval(t)
  }, [detail, fetchDetail])

  const handleCancel = async () => {
    if (!executionId) return
    const ok = window.confirm(
      'Cancel this execution? The current step will finish first.',
    )
    if (!ok) return
    setCancelling(true)
    try {
      const resp = await executionsApi.cancel(executionId)
      if (resp.cancel_requested) {
        toast.success('Cancel requested — landing at next step boundary')
      } else {
        toast(resp.detail || 'Already terminal')
      }
      await fetchDetail(true)
    } catch (err) {
      console.error(err)
      toast.error('Cancel failed')
    } finally {
      setCancelling(false)
    }
  }

  const handleResume = async () => {
    if (!executionId) return
    let parsed: unknown
    try {
      parsed = JSON.parse(resumeText)
    } catch {
      toast.error('Response must be valid JSON')
      return
    }
    setResuming(true)
    try {
      const resp = await executionsApi.resume(executionId, parsed)
      toast.success(`Resumed → ${resp.status}`)
      await fetchDetail(true)
    } catch (err: unknown) {
      const apiErr = err as { response?: { status?: number; data?: { detail?: string } } }
      const code = apiErr.response?.status
      const detailMsg = apiErr.response?.data?.detail
      toast.error(
        `Resume failed${code ? ` (${code})` : ''}${detailMsg ? `: ${detailMsg}` : ''}`,
      )
    } finally {
      setResuming(false)
    }
  }

  const suspension = useMemo(() => {
    if (!detail) return null
    return (
      ((detail.state as Record<string, unknown> | null)?.suspension as
        | {
            reason?: string
            payload?: { message?: string; schema?: ElicitSchema; step_id?: string }
          }
        | null
        | undefined) ?? null
    )
  }, [detail])
  const suspensionReason = suspension?.reason ?? null

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-12 text-center text-gray-500">
        Loading…
      </div>
    )
  }

  if (!detail) {
    return (
      <div className="container mx-auto px-4 py-12 text-center text-gray-500">
        Execution not found.{' '}
        <Link to="/app/compositions/executions" className="text-orange hover:underline">
          Back to list
        </Link>
      </div>
    )
  }

  const isNonTerminal = NON_TERMINAL_STATUSES.includes(detail.status)
  const canCancel = isNonTerminal && !detail.cancel_requested
  const canResumeTestSuspend =
    detail.status === 'suspended' && suspensionReason === '_test_suspend'
  const elicitPayload =
    detail.status === 'suspended' && suspensionReason === 'elicit'
      ? suspension?.payload
      : null
  const handleElicitSubmit = async (response: unknown) => {
    if (!executionId) return
    setResuming(true)
    try {
      const resp = await executionsApi.resume(executionId, response)
      toast.success(`Resumed → ${resp.status}`)
      await fetchDetail(true)
    } catch (err: unknown) {
      const apiErr = err as {
        response?: { status?: number; data?: { detail?: string } }
      }
      const code = apiErr.response?.status
      const detailMsg = apiErr.response?.data?.detail
      toast.error(
        `Resume failed${code ? ` (${code})` : ''}${detailMsg ? `: ${detailMsg}` : ''}`,
      )
    } finally {
      setResuming(false)
    }
  }

  return (
    <div className="container mx-auto px-4 py-6 max-w-5xl">
      <div className="mb-4">
        <button
          type="button"
          className="inline-flex items-center text-sm text-gray-600 hover:text-gray-900"
          onClick={() => navigate('/app/compositions/executions')}
        >
          <ArrowLeftIcon className="w-4 h-4 mr-1" />
          All executions
        </button>
      </div>

      {/* Header */}
      <Card padding="lg" className="mb-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-3 mb-2">
              <StatusBadge status={detail.status} />
              {detail.cancel_requested && isNonTerminal && (
                <span className="text-xs text-amber-700 font-medium">
                  cancel pending…
                </span>
              )}
            </div>
            <div className="text-xs font-mono text-gray-600 break-all">
              {detail.id}
            </div>
            <div className="text-xs text-gray-500 mt-1">
              composition <span className="font-mono">{detail.composition_id}</span>
              {' · '}trigger <span className="font-medium">{detail.trigger}</span>
              {detail.parent_execution_id && (
                <>
                  {' · '}
                  parent{' '}
                  <Link
                    to={`/app/compositions/executions/${detail.parent_execution_id}`}
                    className="font-mono text-orange hover:underline"
                  >
                    {detail.parent_execution_id.slice(0, 8)}…
                  </Link>
                </>
              )}
            </div>
            <div className="text-xs text-gray-500 mt-1">
              started {formatTime(detail.started_at)} · updated{' '}
              {formatTime(detail.updated_at)}
              {detail.expires_at && (
                <> · expires {formatTime(detail.expires_at)}</>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => fetchDetail(false)}
              disabled={refreshing}
            >
              <ArrowPathIcon
                className={`w-4 h-4 mr-1 ${refreshing ? 'animate-spin' : ''}`}
              />
              Refresh
            </Button>
            {canCancel && (
              <Button
                variant="secondary"
                size="sm"
                onClick={handleCancel}
                disabled={cancelling}
              >
                {cancelling ? 'Cancelling…' : 'Cancel'}
              </Button>
            )}
          </div>
        </div>
      </Card>

      {/* Elicit response form (B-1) */}
      {elicitPayload && elicitPayload.schema && (
        <Card padding="md" className="mb-4 border-amber-300 bg-amber-50">
          <h3 className="text-sm font-semibold text-amber-900 mb-2">
            Response required{elicitPayload.step_id && (
              <span className="font-mono text-xs ml-1">
                (step <span className="font-semibold">{elicitPayload.step_id}</span>)
              </span>
            )}
          </h3>
          <ElicitForm
            message={elicitPayload.message || ''}
            schema={elicitPayload.schema}
            onSubmit={handleElicitSubmit}
            submitting={resuming}
          />
        </Card>
      )}

      {/* Resume widget for _test_suspend */}
      {canResumeTestSuspend && (
        <Card padding="md" className="mb-4 border-amber-300 bg-amber-50">
          <h3 className="text-sm font-semibold text-amber-900 mb-2">
            Provide test response
          </h3>
          <p className="text-xs text-amber-800 mb-2">
            This execution is suspended on a <code>_test_suspend</code> step.
            Submit any JSON value below to inject it as the step's result and
            continue.
          </p>
          <textarea
            value={resumeText}
            onChange={(e) => setResumeText(e.target.value)}
            rows={3}
            className="w-full font-mono text-sm border border-amber-300 rounded p-2 mb-2"
          />
          <Button onClick={handleResume} disabled={resuming}>
            {resuming ? 'Resuming…' : 'Resume execution'}
          </Button>
        </Card>
      )}

      {/* Final outcome (terminal only) */}
      {detail.status === 'completed' && detail.result && (
        <Card padding="md" className="mb-4 border-green-300 bg-green-50">
          <h3 className="text-sm font-semibold text-green-900 mb-2">Result</h3>
          <pre className="text-xs font-mono whitespace-pre-wrap break-all bg-white border border-green-200 rounded p-2 max-h-72 overflow-auto">
            {JSON.stringify(detail.result, null, 2)}
          </pre>
        </Card>
      )}
      {(detail.status === 'failed' ||
        detail.status === 'expired' ||
        detail.status === 'cancelled') &&
        detail.error && (
          <Card padding="md" className="mb-4 border-red-300 bg-red-50">
            <h3 className="text-sm font-semibold text-red-900 mb-2">Error</h3>
            <p className="text-sm font-mono text-red-800 break-all">
              {detail.error}
            </p>
          </Card>
        )}

      {/* Timeline */}
      <Card padding="md" className="mb-4">
        <h3 className="text-sm font-semibold text-gray-900 mb-2">
          Step events ({detail.events.length})
        </h3>
        {detail.events.length === 0 ? (
          <p className="text-sm text-gray-500">No events yet.</p>
        ) : (
          <ol className="space-y-1.5 text-sm">
            {detail.events.map((e) => (
              <li key={e.id} className="flex items-start gap-2 font-mono">
                <span className="text-xs text-gray-500 whitespace-nowrap">
                  {new Date(e.timestamp).toLocaleTimeString()}
                </span>
                <span className="font-semibold">{e.step_id}</span>
                <span className="text-gray-700">→ {e.event_type}</span>
                {e.payload && Object.keys(e.payload).length > 0 && (
                  <span className="text-xs text-gray-500 truncate">
                    {JSON.stringify(e.payload)}
                  </span>
                )}
              </li>
            ))}
          </ol>
        )}
      </Card>

      {/* Raw state — collapsed by default */}
      <details className="mb-4">
        <summary className="cursor-pointer text-sm text-gray-600 hover:text-gray-900">
          Raw state (debug)
        </summary>
        <pre className="text-xs font-mono whitespace-pre-wrap break-all bg-gray-50 border border-gray-200 rounded p-2 mt-2 max-h-96 overflow-auto">
          {JSON.stringify(detail.state, null, 2)}
        </pre>
      </details>
    </div>
  )
}
