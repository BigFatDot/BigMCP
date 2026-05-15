/**
 * Org-share review queue (Phase 4).
 *
 * Admin reviews compositions a non-admin user has asked to share with
 * the organization. Approving flips the composition to
 * (visibility=organization, status=production) so it appears in the
 * default pool. Rejecting keeps the composition private and stamps a
 * note for the requester to read in their own composition list.
 */

import { useEffect, useMemo, useState } from 'react'
import {
  ArrowPathIcon,
  BoltIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  ShieldCheckIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline'
import { Card, Button, Badge } from '@/components/ui'
import { compositionsApi, type Composition } from '@/services/marketplace'

export function CompositionsReviewPage() {
  const [pending, setPending] = useState<Composition[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notesById, setNotesById] = useState<Record<string, string>>({})

  const refresh = async () => {
    setLoading(true)
    setError(null)
    try {
      const { compositions } = await compositionsApi.listShareRequests()
      setPending(compositions)
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const approve = async (comp: Composition) => {
    setBusyId(comp.id)
    setError(null)
    try {
      await compositionsApi.approveShareRequest(comp.id, notesById[comp.id])
      setPending((prev) => (prev ? prev.filter((c) => c.id !== comp.id) : prev))
      setNotesById((prev) => {
        const { [comp.id]: _, ...rest } = prev
        return rest
      })
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Approve failed')
    } finally {
      setBusyId(null)
    }
  }

  const reject = async (comp: Composition) => {
    const notes = notesById[comp.id] || ''
    if (!notes.trim()) {
      setError('A short rationale is required when rejecting a request.')
      return
    }
    setBusyId(comp.id)
    setError(null)
    try {
      await compositionsApi.rejectShareRequest(comp.id, notes)
      setPending((prev) => (prev ? prev.filter((c) => c.id !== comp.id) : prev))
      setNotesById((prev) => {
        const { [comp.id]: _, ...rest } = prev
        return rest
      })
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Reject failed')
    } finally {
      setBusyId(null)
    }
  }

  const sortedPending = useMemo(() => {
    if (!pending) return []
    return [...pending].sort((a, b) => {
      const ta = a.share_requested_at ? new Date(a.share_requested_at).getTime() : 0
      const tb = b.share_requested_at ? new Date(b.share_requested_at).getTime() : 0
      return ta - tb
    })
  }, [pending])

  return (
    <div className="container py-8 max-w-4xl">
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <ShieldCheckIcon className="h-7 w-7 text-orange" />
            Compositions review
          </h1>
          <p className="text-sm text-gray-600 mt-1 max-w-3xl">
            Compositions a member has asked to share with the organization.
            Approving makes them visible to everyone and exposes them in
            the MCP pool as <code>composition_&lt;name&gt;</code>. Rejecting
            keeps them private and stamps your note on the request so the
            requester can iterate.
          </p>
        </div>
        <Button variant="secondary" onClick={refresh} disabled={loading}>
          <ArrowPathIcon className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      {error && (
        <Card className="mb-4 p-4 bg-red-50 border border-red-200">
          <div className="flex items-start gap-3 text-sm text-red-800">
            <ExclamationTriangleIcon className="h-5 w-5 text-red-500 flex-shrink-0" />
            <div>{error}</div>
          </div>
        </Card>
      )}

      {loading && pending === null && (
        <Card className="p-8 text-center text-sm text-gray-500">
          Loading review queue…
        </Card>
      )}

      {!loading && sortedPending.length === 0 && (
        <Card className="p-8 text-center text-sm text-gray-500">
          No pending share requests. The queue is empty.
        </Card>
      )}

      {sortedPending.length > 0 && (
        <div className="space-y-3">
          {sortedPending.map((comp) => {
            const requestedAt = comp.share_requested_at
              ? new Date(comp.share_requested_at).toLocaleString()
              : '—'
            const notes = notesById[comp.id] || ''
            return (
              <Card key={comp.id} className="p-4">
                <div className="flex items-start gap-3 mb-3">
                  <div className="w-8 h-8 bg-orange-100 rounded-full flex items-center justify-center flex-shrink-0">
                    <BoltIcon className="w-4 h-4 text-orange" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-base font-bold text-gray-900 truncate">
                        {comp.name}
                      </h3>
                      <Badge variant="orange" size="sm">
                        {comp.steps?.length || 0} steps
                      </Badge>
                      <Badge variant="gray" size="sm">
                        {comp.status}
                      </Badge>
                    </div>
                    {comp.description && (
                      <p className="text-sm text-gray-600 mt-1">
                        {comp.description}
                      </p>
                    )}
                    <div className="text-xs text-gray-500 mt-1">
                      Requested {requestedAt} · by {comp.share_requested_by || 'unknown'}
                    </div>
                  </div>
                </div>

                {/* Steps preview */}
                {comp.steps && comp.steps.length > 0 && (
                  <div className="text-xs font-mono bg-gray-50 border border-gray-200 rounded px-2 py-1.5 mb-3 truncate">
                    {comp.steps.map((s) => s.tool).join(' → ')}
                  </div>
                )}

                <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
                  <textarea
                    value={notes}
                    onChange={(e) =>
                      setNotesById((prev) => ({ ...prev, [comp.id]: e.target.value }))
                    }
                    placeholder="Notes (required to reject, optional to approve)"
                    className="flex-1 px-2 py-1.5 border border-gray-300 rounded text-sm resize-y min-h-[40px]"
                    rows={1}
                  />
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="primary"
                      disabled={busyId === comp.id}
                      onClick={() => approve(comp)}
                    >
                      <CheckCircleIcon className="h-4 w-4 mr-1" />
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busyId === comp.id}
                      onClick={() => reject(comp)}
                      className="text-red-600 hover:text-red-700"
                    >
                      <XCircleIcon className="h-4 w-4 mr-1" />
                      Reject
                    </Button>
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
