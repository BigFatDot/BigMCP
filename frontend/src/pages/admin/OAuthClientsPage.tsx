/**
 * OAuth clients admin page (N2.2).
 *
 * Lists every OAuth client across the instance and exposes the
 * lifecycle actions — approve a pending DCR client, reject one we
 * don't recognise, or revoke any client outright. Filters cover the
 * usual axes: approval_status, registration_method, organisation,
 * substring on name.
 */

import { useEffect, useState } from 'react'
import { AxiosError } from 'axios'
import {
  listOAuthClients,
  approveOAuthClient,
  rejectOAuthClient,
  revokeOAuthClient,
  type ApprovalStatus,
  type OAuthClientAdminItem,
  type OAuthClientFilters,
  type RegistrationMethod,
} from '../../services/clientControl'

const PAGE_SIZE = 50

const STATUS_BADGE: Record<ApprovalStatus, string> = {
  auto_approved: 'bg-blue-100 text-blue-800',
  approved: 'bg-green-100 text-green-800',
  pending: 'bg-yellow-100 text-yellow-800',
  rejected: 'bg-red-100 text-red-800',
}

const METHOD_LABELS: Record<RegistrationMethod, string> = {
  dcr_open: 'DCR (open)',
  dcr_approved: 'DCR (approval)',
  cimd: 'CIMD',
  manual_admin: 'Manual',
  preloaded: 'Preloaded',
}

type ActionKind = 'approve' | 'reject' | 'revoke'

const ACTION_LABEL: Record<ActionKind, string> = {
  approve: 'Approve client',
  reject: 'Reject client',
  revoke: 'Revoke client',
}

const ACTION_HELP: Record<ActionKind, string> = {
  approve: 'Allows the client to complete /authorize from now on.',
  reject:
    'Marks the client as rejected. /authorize will refuse. The row is kept for audit.',
  revoke:
    'Sets is_active=False. Future authentication attempts fail. The row is kept for audit.',
}

export function OAuthClientsPage() {
  const [filters, setFilters] = useState<OAuthClientFilters>({
    limit: PAGE_SIZE,
    offset: 0,
  })
  const [clients, setClients] = useState<OAuthClientAdminItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<{ kind: ActionKind; client: OAuthClientAdminItem } | null>(
    null,
  )
  const [reason, setReason] = useState('')
  const [actionInFlight, setActionInFlight] = useState(false)

  function fetchClients() {
    setLoading(true)
    setError(null)
    listOAuthClients(filters)
      .then((res) => {
        setClients(res.items)
        setTotal(res.total)
      })
      .catch((err: AxiosError<{ detail?: string }>) => {
        if (err.response?.status === 403) {
          setError('Instance-admin privileges required.')
        } else if (err.response?.status === 401) {
          setError('Authentication required. Please log in again.')
        } else {
          setError(err.response?.data?.detail ?? err.message ?? 'Failed to load clients')
        }
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchClients()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(filters)])

  const offset = filters.offset ?? 0
  const limit = filters.limit ?? PAGE_SIZE
  const totalPages = Math.max(1, Math.ceil(total / limit))
  const currentPage = Math.floor(offset / limit) + 1

  function updateFilter<K extends keyof OAuthClientFilters>(
    key: K,
    value: OAuthClientFilters[K],
  ) {
    setFilters((f) => ({ ...f, [key]: value, offset: 0 }))
  }

  function goToPage(page: number) {
    const clamped = Math.max(1, Math.min(page, totalPages))
    setFilters((f) => ({ ...f, offset: (clamped - 1) * limit }))
  }

  function openAction(kind: ActionKind, client: OAuthClientAdminItem) {
    setPending({ kind, client })
    setReason('')
  }

  async function confirm() {
    if (!pending) return
    setActionInFlight(true)
    try {
      const { kind, client } = pending
      if (kind === 'approve') await approveOAuthClient(client.id, reason)
      else if (kind === 'reject') await rejectOAuthClient(client.id, reason)
      else if (kind === 'revoke') await revokeOAuthClient(client.id)
      setPending(null)
      fetchClients()
    } catch (err) {
      const ax = err as AxiosError<{ detail?: string }>
      alert(ax.response?.data?.detail ?? ax.message ?? 'Action failed')
    } finally {
      setActionInFlight(false)
    }
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900">OAuth clients</h1>
        <p className="text-sm text-gray-600 mt-1">
          Every OAuth application registered against this instance. Approve
          pending DCR registrations, reject unrecognised clients, or revoke
          access entirely. All actions are audited.
        </p>
      </header>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4 bg-white p-4 rounded shadow-sm border border-gray-200">
        <label className="flex flex-col text-sm">
          <span className="text-gray-700 mb-1">Approval status</span>
          <select
            className="border border-gray-300 rounded px-2 py-1"
            value={filters.approval_status ?? ''}
            onChange={(e) =>
              updateFilter('approval_status', (e.target.value || undefined) as ApprovalStatus | undefined)
            }
          >
            <option value="">— any —</option>
            <option value="pending">pending</option>
            <option value="approved">approved</option>
            <option value="auto_approved">auto_approved</option>
            <option value="rejected">rejected</option>
          </select>
        </label>

        <label className="flex flex-col text-sm">
          <span className="text-gray-700 mb-1">Registration method</span>
          <select
            className="border border-gray-300 rounded px-2 py-1"
            value={filters.registration_method ?? ''}
            onChange={(e) =>
              updateFilter(
                'registration_method',
                (e.target.value || undefined) as RegistrationMethod | undefined,
              )
            }
          >
            <option value="">— any —</option>
            {(Object.keys(METHOD_LABELS) as RegistrationMethod[]).map((m) => (
              <option key={m} value={m}>
                {METHOD_LABELS[m]}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col text-sm">
          <span className="text-gray-700 mb-1">Search (name)</span>
          <input
            type="text"
            className="border border-gray-300 rounded px-2 py-1"
            placeholder="case-insensitive substring"
            value={filters.search ?? ''}
            onChange={(e) => updateFilter('search', e.target.value || undefined)}
          />
        </label>
      </section>

      {error && (
        <div className="p-3 mb-4 rounded border border-red-200 bg-red-50 text-red-800 text-sm">
          {error}
        </div>
      )}

      <section className="bg-white rounded shadow-sm border border-gray-200 overflow-hidden">
        <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 text-xs text-gray-600 flex justify-between">
          <span>{loading ? 'Loading…' : `${total} client${total === 1 ? '' : 's'}`}</span>
          <span>
            Page {currentPage} / {totalPages}
          </span>
        </div>

        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-700">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Client</th>
              <th className="px-3 py-2 text-left font-medium">Method</th>
              <th className="px-3 py-2 text-left font-medium">Status</th>
              <th className="px-3 py-2 text-left font-medium">Active</th>
              <th className="px-3 py-2 text-left font-medium">Created</th>
              <th className="px-3 py-2 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {clients.length === 0 && !loading ? (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-gray-500">
                  No clients match these filters.
                </td>
              </tr>
            ) : (
              clients.map((c) => (
                <tr key={c.id} className="border-t border-gray-100 hover:bg-gray-50 align-top">
                  <td className="px-3 py-2">
                    <div className="font-medium">{c.name}</div>
                    <div className="font-mono text-[10px] text-gray-500 break-all">
                      {c.client_id}
                    </div>
                    {c.cimd_url && (
                      <div className="font-mono text-[10px] text-blue-700 mt-0.5 break-all">
                        ↪ {c.cimd_url}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs">{METHOD_LABELS[c.registration_method]}</td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${STATUS_BADGE[c.approval_status]}`}
                    >
                      {c.approval_status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {c.is_active ? (
                      <span className="text-green-700">yes</span>
                    ) : (
                      <span className="text-gray-500">revoked</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-600">
                    {new Date(c.created_at).toISOString().slice(0, 10)}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    {c.approval_status === 'pending' && (
                      <>
                        <button
                          type="button"
                          className="text-green-700 hover:underline text-xs mr-3"
                          onClick={() => openAction('approve', c)}
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          className="text-red-700 hover:underline text-xs mr-3"
                          onClick={() => openAction('reject', c)}
                        >
                          Reject
                        </button>
                      </>
                    )}
                    {c.is_active && c.approval_status !== 'pending' && (
                      <button
                        type="button"
                        className="text-orange-700 hover:underline text-xs"
                        onClick={() => openAction('revoke', c)}
                      >
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>

        <div className="px-4 py-2 bg-gray-50 border-t border-gray-200 flex justify-between text-xs">
          <button
            type="button"
            className="px-2 py-1 border border-gray-300 rounded disabled:opacity-50"
            disabled={currentPage <= 1}
            onClick={() => goToPage(currentPage - 1)}
          >
            ← Previous
          </button>
          <button
            type="button"
            className="px-2 py-1 border border-gray-300 rounded disabled:opacity-50"
            disabled={currentPage >= totalPages}
            onClick={() => goToPage(currentPage + 1)}
          >
            Next →
          </button>
        </div>
      </section>

      {pending && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50"
          onClick={() => !actionInFlight && setPending(null)}
        >
          <div
            className="bg-white rounded shadow-lg max-w-lg w-full"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-4 border-b border-gray-200">
              <h2 className="font-semibold text-gray-900">{ACTION_LABEL[pending.kind]}</h2>
              <p className="text-xs text-gray-600 mt-1">{ACTION_HELP[pending.kind]}</p>
            </div>
            <div className="p-4 space-y-3">
              <div className="text-sm">
                <div className="text-gray-700">Target client:</div>
                <div className="font-medium">{pending.client.name}</div>
                <div className="font-mono text-xs text-gray-500 break-all">
                  {pending.client.client_id}
                </div>
              </div>
              {pending.kind !== 'revoke' && (
                <label className="block text-sm">
                  <span className="text-gray-700">Reason (optional)</span>
                  <input
                    type="text"
                    className="mt-1 w-full border border-gray-300 rounded px-2 py-1"
                    placeholder="e.g. CIMD verified offline"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    disabled={actionInFlight}
                  />
                </label>
              )}
            </div>
            <div className="p-4 border-t border-gray-200 flex justify-end gap-2">
              <button
                type="button"
                className="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-gray-50"
                onClick={() => setPending(null)}
                disabled={actionInFlight}
              >
                Cancel
              </button>
              <button
                type="button"
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                onClick={confirm}
                disabled={actionInFlight}
              >
                {actionInFlight ? 'Working…' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default OAuthClientsPage
