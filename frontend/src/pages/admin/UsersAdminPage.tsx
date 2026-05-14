/**
 * Users administration page (instance-admin only).
 *
 * Lists every user with lifecycle status and exposes the four
 * lifecycle actions (suspend / reactivate / soft-delete / revoke-all)
 * behind a confirmation modal that captures an optional reason.
 *
 * The backend gates with require_instance_admin and returns 403 for
 * non-admins; this page renders the error inline rather than redirecting.
 */

import { useEffect, useState } from 'react'
import { AxiosError } from 'axios'
import {
  listAdminUsers,
  suspendUser,
  reactivateUser,
  softDeleteUser,
  revokeAllSessions,
  type AdminUser,
  type AdminUserListFilters,
  type UserStatus,
} from '../../services/users'

const PAGE_SIZE = 50

type Action = 'suspend' | 'reactivate' | 'soft-delete' | 'revoke-all'

const ACTION_LABELS: Record<Action, string> = {
  suspend: 'Suspend account',
  reactivate: 'Reactivate account',
  'soft-delete': 'Soft-delete account',
  'revoke-all': 'Revoke all sessions',
}

const ACTION_DESCRIPTIONS: Record<Action, string> = {
  suspend:
    'Blocks login + invalidates JWT/API keys at next use. Reversible. Data retained.',
  reactivate:
    'Restores access. If the account was soft-deleted, also clears deleted_at.',
  'soft-delete':
    'Marks account as deleted. Data retained for the retention window. Reversible until purge.',
  'revoke-all':
    'Severs every active authentication surface (JWT, refresh tokens, API keys) atomically.',
}

const STATUS_BADGE: Record<UserStatus, string> = {
  active: 'bg-green-100 text-green-800',
  suspended: 'bg-yellow-100 text-yellow-800',
  deleted: 'bg-red-100 text-red-800',
}

export function UsersAdminPage() {
  const [filters, setFilters] = useState<AdminUserListFilters>({
    limit: PAGE_SIZE,
    offset: 0,
  })
  const [users, setUsers] = useState<AdminUser[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pendingAction, setPendingAction] = useState<{
    action: Action
    user: AdminUser
  } | null>(null)
  const [reason, setReason] = useState('')
  const [actionInFlight, setActionInFlight] = useState(false)

  function fetchUsers() {
    setLoading(true)
    setError(null)
    listAdminUsers(filters)
      .then((res) => {
        setUsers(res.items)
        setTotal(res.total)
      })
      .catch((err: AxiosError<{ detail?: string }>) => {
        if (err.response?.status === 403) {
          setError('Instance-admin privileges required.')
        } else if (err.response?.status === 401) {
          setError('Authentication required. Please log in again.')
        } else {
          setError(err.response?.data?.detail ?? err.message ?? 'Failed to load users')
        }
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchUsers()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(filters)])

  const offset = filters.offset ?? 0
  const limit = filters.limit ?? PAGE_SIZE
  const totalPages = Math.max(1, Math.ceil(total / limit))
  const currentPage = Math.floor(offset / limit) + 1

  function updateFilter<K extends keyof AdminUserListFilters>(
    key: K,
    value: AdminUserListFilters[K],
  ) {
    setFilters((f) => ({ ...f, [key]: value, offset: 0 }))
  }

  function goToPage(page: number) {
    const clamped = Math.max(1, Math.min(page, totalPages))
    setFilters((f) => ({ ...f, offset: (clamped - 1) * limit }))
  }

  function openAction(action: Action, user: AdminUser) {
    setPendingAction({ action, user })
    setReason('')
  }

  async function confirmAction() {
    if (!pendingAction) return
    setActionInFlight(true)
    try {
      const { action, user } = pendingAction
      if (action === 'suspend') await suspendUser(user.id, reason)
      else if (action === 'reactivate') await reactivateUser(user.id, reason)
      else if (action === 'soft-delete') await softDeleteUser(user.id, reason)
      else if (action === 'revoke-all') await revokeAllSessions(user.id, reason)
      setPendingAction(null)
      fetchUsers()
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
        <h1 className="text-2xl font-semibold text-gray-900">Users</h1>
        <p className="text-sm text-gray-600 mt-1">
          Lifecycle administration. Suspend, reactivate, soft-delete, or
          severe every active session for any user. All actions are audited.
        </p>
      </header>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4 bg-white p-4 rounded shadow-sm border border-gray-200">
        <label className="flex flex-col text-sm">
          <span className="text-gray-700 mb-1">Status</span>
          <select
            className="border border-gray-300 rounded px-2 py-1"
            value={filters.status ?? ''}
            onChange={(e) =>
              updateFilter('status', (e.target.value || undefined) as UserStatus | undefined)
            }
          >
            <option value="">— any —</option>
            <option value="active">active</option>
            <option value="suspended">suspended</option>
            <option value="deleted">deleted</option>
          </select>
        </label>

        <label className="flex flex-col text-sm md:col-span-2">
          <span className="text-gray-700 mb-1">Search (email or name)</span>
          <input
            type="text"
            className="border border-gray-300 rounded px-2 py-1"
            placeholder="substring, case-insensitive"
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
          <span>{loading ? 'Loading…' : `${total} user${total === 1 ? '' : 's'}`}</span>
          <span>
            Page {currentPage} / {totalPages}
          </span>
        </div>

        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-700">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Email</th>
              <th className="px-3 py-2 text-left font-medium">Name</th>
              <th className="px-3 py-2 text-left font-medium">Status</th>
              <th className="px-3 py-2 text-left font-medium">Last login</th>
              <th className="px-3 py-2 text-left font-medium">Created</th>
              <th className="px-3 py-2 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.length === 0 && !loading ? (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-gray-500">
                  No users match these filters.
                </td>
              </tr>
            ) : (
              users.map((u) => (
                <tr key={u.id} className="border-t border-gray-100 hover:bg-gray-50 align-top">
                  <td className="px-3 py-2">
                    <div className="font-mono text-xs">{u.email}</div>
                    {u.is_instance_admin && (
                      <div className="text-[10px] uppercase tracking-wide text-blue-600 mt-0.5">
                        instance admin
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2">{u.name ?? '—'}</td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${STATUS_BADGE[u.status]}`}
                    >
                      {u.status}
                    </span>
                    {u.status_reason && (
                      <div className="text-[10px] text-gray-500 mt-0.5 italic">
                        “{u.status_reason}”
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-600">
                    {u.last_login_at
                      ? new Date(u.last_login_at).toISOString().slice(0, 19).replace('T', ' ')
                      : '—'}
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-600">
                    {new Date(u.created_at).toISOString().slice(0, 10)}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    {u.status === 'active' && (
                      <>
                        <button
                          type="button"
                          className="text-yellow-700 hover:underline text-xs mr-3"
                          onClick={() => openAction('suspend', u)}
                        >
                          Suspend
                        </button>
                        <button
                          type="button"
                          className="text-red-700 hover:underline text-xs mr-3"
                          onClick={() => openAction('soft-delete', u)}
                        >
                          Soft-delete
                        </button>
                        <button
                          type="button"
                          className="text-orange-700 hover:underline text-xs"
                          onClick={() => openAction('revoke-all', u)}
                        >
                          Revoke sessions
                        </button>
                      </>
                    )}
                    {u.status === 'suspended' && (
                      <>
                        <button
                          type="button"
                          className="text-green-700 hover:underline text-xs mr-3"
                          onClick={() => openAction('reactivate', u)}
                        >
                          Reactivate
                        </button>
                        <button
                          type="button"
                          className="text-red-700 hover:underline text-xs"
                          onClick={() => openAction('soft-delete', u)}
                        >
                          Soft-delete
                        </button>
                      </>
                    )}
                    {u.status === 'deleted' && (
                      <button
                        type="button"
                        className="text-green-700 hover:underline text-xs"
                        onClick={() => openAction('reactivate', u)}
                      >
                        Reactivate
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

      {pendingAction && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50"
          onClick={() => !actionInFlight && setPendingAction(null)}
        >
          <div
            className="bg-white rounded shadow-lg max-w-lg w-full"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-4 border-b border-gray-200">
              <h2 className="font-semibold text-gray-900">
                {ACTION_LABELS[pendingAction.action]}
              </h2>
              <p className="text-xs text-gray-600 mt-1">
                {ACTION_DESCRIPTIONS[pendingAction.action]}
              </p>
            </div>
            <div className="p-4 space-y-3">
              <div className="text-sm">
                <div className="text-gray-700">Target user:</div>
                <div className="font-mono text-xs mt-1">{pendingAction.user.email}</div>
              </div>
              <label className="block text-sm">
                <span className="text-gray-700">Reason (optional)</span>
                <input
                  type="text"
                  className="mt-1 w-full border border-gray-300 rounded px-2 py-1"
                  placeholder="e.g. HR offboarding 2026-05-14"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  disabled={actionInFlight}
                />
              </label>
            </div>
            <div className="p-4 border-t border-gray-200 flex justify-end gap-2">
              <button
                type="button"
                className="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-gray-50"
                onClick={() => setPendingAction(null)}
                disabled={actionInFlight}
              >
                Cancel
              </button>
              <button
                type="button"
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                onClick={confirmAction}
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

export default UsersAdminPage
