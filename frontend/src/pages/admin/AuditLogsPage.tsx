/**
 * Audit Logs admin page.
 *
 * Instance-admin only. The backend returns 403 to non-admins; this
 * page surfaces that gracefully. Filters compose with AND; an empty
 * field is ignored. Pagination uses limit/offset (50 per page).
 */

import { useEffect, useState } from 'react'
import { AxiosError } from 'axios'
import {
  listAuditLogs,
  type AuditLog,
  type AuditLogFilters,
} from '../../services/audit'

const PAGE_SIZE = 50

const COMMON_ACTIONS = [
  '',
  'auth.login_success',
  'auth.login_failed',
  'auth.logout',
  'auth.user_register',
  'auth.password_reset_request',
  'auth.password_reset_confirm',
  'oauth.client_register',
  'oauth.client_create',
  'oauth.consent_grant',
  'oauth.token_grant',
  'oauth.token_refresh',
  'security.apikey_scope_denied',
  'security.unauthorized_access',
  'credential.create',
  'credential.update',
  'credential.delete',
  'credential.access',
]

export function AuditLogsPage() {
  const [filters, setFilters] = useState<AuditLogFilters>({
    limit: PAGE_SIZE,
    offset: 0,
  })
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [total, setTotal] = useState<number>(0)
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    listAuditLogs(filters)
      .then((res) => {
        if (cancelled) return
        setLogs(res.items)
        setTotal(res.total)
      })
      .catch((err: AxiosError<{ detail?: string }>) => {
        if (cancelled) return
        if (err.response?.status === 403) {
          setError('Instance-admin privileges required to view audit logs.')
        } else if (err.response?.status === 401) {
          setError('Authentication required. Please log in again.')
        } else {
          setError(err.response?.data?.detail ?? err.message ?? 'Failed to load audit logs')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [filters])

  const offset = filters.offset ?? 0
  const limit = filters.limit ?? PAGE_SIZE
  const totalPages = Math.max(1, Math.ceil(total / limit))
  const currentPage = Math.floor(offset / limit) + 1

  function updateFilter<K extends keyof AuditLogFilters>(key: K, value: AuditLogFilters[K]) {
    setFilters((f) => ({ ...f, [key]: value, offset: 0 }))
  }

  function goToPage(page: number) {
    const clamped = Math.max(1, Math.min(page, totalPages))
    setFilters((f) => ({ ...f, offset: (clamped - 1) * limit }))
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900">Audit Logs</h1>
        <p className="text-sm text-gray-600 mt-1">
          Immutable, HMAC-signed audit trail for the entire instance.
          Filter by action, actor, organization, time range or IP.
        </p>
      </header>

      <section className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4 bg-white p-4 rounded shadow-sm border border-gray-200">
        <label className="flex flex-col text-sm">
          <span className="text-gray-700 mb-1">Action</span>
          <select
            className="border border-gray-300 rounded px-2 py-1"
            value={filters.action ?? ''}
            onChange={(e) => updateFilter('action', e.target.value || undefined)}
          >
            {COMMON_ACTIONS.map((a) => (
              <option key={a} value={a}>
                {a || '— any —'}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col text-sm">
          <span className="text-gray-700 mb-1">Actor ID</span>
          <input
            type="text"
            className="border border-gray-300 rounded px-2 py-1 font-mono text-xs"
            placeholder="UUID"
            value={filters.actor_id ?? ''}
            onChange={(e) => updateFilter('actor_id', e.target.value || undefined)}
          />
        </label>

        <label className="flex flex-col text-sm">
          <span className="text-gray-700 mb-1">Organization ID</span>
          <input
            type="text"
            className="border border-gray-300 rounded px-2 py-1 font-mono text-xs"
            placeholder="UUID"
            value={filters.organization_id ?? ''}
            onChange={(e) => updateFilter('organization_id', e.target.value || undefined)}
          />
        </label>

        <label className="flex flex-col text-sm">
          <span className="text-gray-700 mb-1">IP address</span>
          <input
            type="text"
            className="border border-gray-300 rounded px-2 py-1 font-mono text-xs"
            placeholder="e.g. 10.0.0.1"
            value={filters.ip_address ?? ''}
            onChange={(e) => updateFilter('ip_address', e.target.value || undefined)}
          />
        </label>

        <label className="flex flex-col text-sm">
          <span className="text-gray-700 mb-1">Since (UTC)</span>
          <input
            type="datetime-local"
            className="border border-gray-300 rounded px-2 py-1"
            value={filters.since ?? ''}
            onChange={(e) => updateFilter('since', e.target.value || undefined)}
          />
        </label>

        <label className="flex flex-col text-sm">
          <span className="text-gray-700 mb-1">Until (UTC)</span>
          <input
            type="datetime-local"
            className="border border-gray-300 rounded px-2 py-1"
            value={filters.until ?? ''}
            onChange={(e) => updateFilter('until', e.target.value || undefined)}
          />
        </label>

        <label className="flex flex-col text-sm">
          <span className="text-gray-700 mb-1">Resource type</span>
          <input
            type="text"
            className="border border-gray-300 rounded px-2 py-1"
            placeholder="e.g. user, api_key"
            value={filters.resource_type ?? ''}
            onChange={(e) => updateFilter('resource_type', e.target.value || undefined)}
          />
        </label>

        <div className="flex items-end">
          <button
            type="button"
            className="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-gray-50"
            onClick={() => setFilters({ limit: PAGE_SIZE, offset: 0 })}
          >
            Reset filters
          </button>
        </div>
      </section>

      {error && (
        <div className="p-3 mb-4 rounded border border-red-200 bg-red-50 text-red-800 text-sm">
          {error}
        </div>
      )}

      <section className="bg-white rounded shadow-sm border border-gray-200 overflow-hidden">
        <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 text-xs text-gray-600 flex justify-between">
          <span>
            {loading ? 'Loading…' : `${total} total event${total === 1 ? '' : 's'}`}
          </span>
          <span>
            Page {currentPage} / {totalPages}
          </span>
        </div>

        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-700">
            <tr>
              <th className="px-3 py-2 text-left font-medium">When (UTC)</th>
              <th className="px-3 py-2 text-left font-medium">Action</th>
              <th className="px-3 py-2 text-left font-medium">Actor</th>
              <th className="px-3 py-2 text-left font-medium">Resource</th>
              <th className="px-3 py-2 text-left font-medium">IP</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 && !loading ? (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-gray-500">
                  No audit logs match these filters.
                </td>
              </tr>
            ) : (
              logs.map((log) => (
                <tr key={log.id} className="border-t border-gray-100 hover:bg-gray-50">
                  <td className="px-3 py-2 font-mono text-xs whitespace-nowrap">
                    {new Date(log.timestamp).toISOString().replace('T', ' ').slice(0, 19)}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{log.action}</td>
                  <td className="px-3 py-2 font-mono text-xs text-gray-600">
                    {log.actor_id ? log.actor_id.slice(0, 8) : '—'}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-gray-600">
                    {log.resource_type}
                    {log.resource_id ? ` / ${log.resource_id.slice(0, 8)}` : ''}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{log.ip_address ?? '—'}</td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      className="text-blue-600 hover:underline text-xs"
                      onClick={() => setSelectedLog(log)}
                    >
                      Details
                    </button>
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

      {selectedLog && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50"
          onClick={() => setSelectedLog(null)}
        >
          <div
            className="bg-white rounded shadow-lg max-w-2xl w-full max-h-[80vh] overflow-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-4 border-b border-gray-200 flex justify-between">
              <h2 className="font-semibold">Audit log details</h2>
              <button
                type="button"
                className="text-gray-500 hover:text-gray-700"
                onClick={() => setSelectedLog(null)}
              >
                ✕
              </button>
            </div>
            <pre className="p-4 text-xs font-mono whitespace-pre-wrap break-all">
              {JSON.stringify(selectedLog, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}

export default AuditLogsPage
