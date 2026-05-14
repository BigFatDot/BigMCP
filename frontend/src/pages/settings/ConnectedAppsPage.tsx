/**
 * Connected Apps Page (N2.4 / Story H).
 *
 * User-self-service view of every OAuth client the caller has authorized
 * (Claude Desktop, custom MCP clients, third-party DCR/CIMD integrations).
 *
 * Per row:
 *  - app name + registration source badge
 *  - first-authorized + last-seen timestamps
 *  - "Revoke access" → DELETE /auth/connected-apps/{uuid}
 *
 * The instance-admin view of OAuth clients (approve/reject/revoke a
 * client globally) lives under /app/admin/oauth-clients and is gated
 * to is_instance_admin users.
 */

import { useEffect, useState } from 'react'
import {
  PuzzlePieceIcon,
  TrashIcon,
  ArrowPathIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline'
import { Card, Button, Badge } from '@/components/ui'
import {
  listConnectedApps,
  revokeConnectedApp,
  type ConnectedApp,
} from '@/services/connectedApps'

function formatRegistrationMethod(method: ConnectedApp['registration_method']): string {
  switch (method) {
    case 'cimd':
      return 'CIMD'
    case 'dcr_open':
      return 'DCR'
    case 'dcr_approved':
      return 'DCR (admin approved)'
    case 'manual_admin':
      return 'Manual admin'
    case 'preloaded':
      return 'Preloaded'
    default:
      return method
  }
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

export function ConnectedAppsPage() {
  const [apps, setApps] = useState<ConnectedApp[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [revokingId, setRevokingId] = useState<string | null>(null)

  const refresh = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listConnectedApps()
      setApps(data)
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const handleRevoke = async (app: ConnectedApp) => {
    const ok = window.confirm(
      `Revoke access for "${app.name}"?\n\n` +
        `All ${app.session_count} active session${app.session_count > 1 ? 's' : ''} ` +
        `will be invalidated immediately.`,
    )
    if (!ok) return
    setRevokingId(app.client_uuid)
    try {
      await revokeConnectedApp(app.client_uuid)
      await refresh()
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ||
          err.message ||
          'Failed to revoke connected app',
      )
    } finally {
      setRevokingId(null)
    }
  }

  return (
    <div className="container py-8 max-w-4xl">
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <PuzzlePieceIcon className="h-7 w-7 text-orange" />
            Connected apps
          </h1>
          <p className="text-sm text-gray-600 mt-1 max-w-2xl">
            Third-party applications that you've granted OAuth access to your
            BigMCP account. Revoking an app immediately invalidates the access
            and refresh tokens it currently holds — you don't need to log out
            of BigMCP yourself.
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={refresh}
          disabled={loading}
        >
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

      {loading && apps === null && (
        <Card className="p-8 text-center text-sm text-gray-500">
          Loading connected apps…
        </Card>
      )}

      {!loading && apps !== null && apps.length === 0 && (
        <Card className="p-8 text-center">
          <PuzzlePieceIcon className="h-12 w-12 mx-auto text-gray-300 mb-3" />
          <h2 className="text-base font-medium text-gray-900">
            No connected apps yet
          </h2>
          <p className="text-sm text-gray-500 mt-2 max-w-md mx-auto">
            When you authorize an app like Claude Desktop or a custom MCP
            client to use BigMCP, it will show up here.
          </p>
        </Card>
      )}

      {apps && apps.length > 0 && (
        <div className="space-y-3">
          {apps.map((app) => (
            <Card key={app.client_uuid} className="p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="text-base font-semibold text-gray-900 truncate">
                      {app.name}
                    </h3>
                    <Badge variant="default">
                      {formatRegistrationMethod(app.registration_method)}
                    </Badge>
                  </div>
                  {app.description && (
                    <p className="text-sm text-gray-600 mb-2">
                      {app.description}
                    </p>
                  )}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-x-4 gap-y-1 text-xs text-gray-500">
                    <div>
                      <span className="font-medium text-gray-700">
                        First authorized:
                      </span>{' '}
                      {formatTimestamp(app.first_authorized_at)}
                    </div>
                    <div>
                      <span className="font-medium text-gray-700">
                        Last used:
                      </span>{' '}
                      {formatTimestamp(app.last_seen_at)}
                    </div>
                    <div>
                      <span className="font-medium text-gray-700">
                        Active sessions:
                      </span>{' '}
                      {app.session_count}
                    </div>
                  </div>
                  {app.cimd_url && (
                    <div className="text-xs text-gray-500 mt-1 truncate">
                      <span className="font-medium text-gray-700">CIMD:</span>{' '}
                      <a
                        href={app.cimd_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-orange hover:underline"
                      >
                        {app.cimd_url}
                      </a>
                    </div>
                  )}
                  <div className="text-[11px] text-gray-400 font-mono mt-1 truncate">
                    client_id: {app.client_id}
                  </div>
                </div>
                <div className="flex-shrink-0">
                  <Button
                    variant="danger"
                    onClick={() => handleRevoke(app)}
                    disabled={revokingId === app.client_uuid}
                  >
                    <TrashIcon className="h-4 w-4 mr-2" />
                    {revokingId === app.client_uuid
                      ? 'Revoking…'
                      : 'Revoke access'}
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
