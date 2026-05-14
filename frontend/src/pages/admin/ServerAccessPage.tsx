/**
 * Server access (RBAC) admin page.
 *
 * Lists every MCP server installed in the current organisation and lets
 * the instance admin set MCPServer.allowed_roles per server. Convention
 * mirrors Composition.allowed_roles:
 *   empty    -> all roles except VIEWER
 *   non-empty -> case-insensitive whitelist of UserRole values
 *
 * UI is admin-grade (no fancy multi-select widget): per-row checkbox grid
 * for the four canonical roles. Save fires PATCH /mcp-servers/{id} with
 * the freshly toggled list.
 */

import { useEffect, useState } from 'react'
import { AxiosError } from 'axios'
import { serverControlApi } from '../../services/marketplace'

const ALL_ROLES = ['owner', 'admin', 'member', 'viewer'] as const
type Role = typeof ALL_ROLES[number]

interface MCPServerRow {
  id: string
  server_id: string
  name: string
  enabled: boolean
  is_visible_to_oauth_clients: boolean
  allowed_roles: string[]
}

export function ServerAccessPage() {
  const [servers, setServers] = useState<MCPServerRow[]>([])
  const [pending, setPending] = useState<Record<string, Role[]>>({})
  const [savingId, setSavingId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedId, setSavedId] = useState<string | null>(null)

  function load() {
    setLoading(true)
    setError(null)
    serverControlApi
      .listServers()
      .then((rows) => {
        const cleaned: MCPServerRow[] = rows.map((r: any) => ({
          id: r.id,
          server_id: r.server_id,
          name: r.name,
          enabled: r.enabled,
          is_visible_to_oauth_clients: r.is_visible_to_oauth_clients,
          allowed_roles: Array.isArray(r.allowed_roles) ? r.allowed_roles : [],
        }))
        setServers(cleaned)
        // Seed pending state with current values so toggles work.
        const seed: Record<string, Role[]> = {}
        for (const s of cleaned) {
          seed[s.id] = s.allowed_roles.filter((r): r is Role =>
            ALL_ROLES.includes(r as Role),
          )
        }
        setPending(seed)
      })
      .catch((err: AxiosError<{ detail?: string }>) => {
        if (err.response?.status === 403) {
          setError('Instance-admin or org-admin privileges required.')
        } else {
          setError(err.response?.data?.detail ?? err.message ?? 'Failed to load servers')
        }
      })
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  function toggleRole(serverId: string, role: Role) {
    setPending((prev) => {
      const current = prev[serverId] ?? []
      const next = current.includes(role)
        ? current.filter((r) => r !== role)
        : [...current, role]
      return { ...prev, [serverId]: next }
    })
  }

  async function save(server: MCPServerRow) {
    setSavingId(server.id)
    setSavedId(null)
    try {
      const roles = pending[server.id] ?? []
      await serverControlApi.setServerAllowedRoles(server.id, roles)
      setServers((prev) =>
        prev.map((s) => (s.id === server.id ? { ...s, allowed_roles: roles } : s)),
      )
      setSavedId(server.id)
      window.setTimeout(() => setSavedId(null), 2000)
    } catch (err) {
      const ax = err as AxiosError<{ detail?: string }>
      alert(ax.response?.data?.detail ?? ax.message ?? 'Save failed')
    } finally {
      setSavingId(null)
    }
  }

  function dirty(serverId: string): boolean {
    const current = servers.find((s) => s.id === serverId)
    if (!current) return false
    const want = (pending[serverId] ?? []).slice().sort()
    const have = current.allowed_roles.slice().sort()
    if (want.length !== have.length) return true
    return want.some((r, i) => r !== have[i])
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900">Server access (RBAC)</h1>
        <p className="text-sm text-gray-600 mt-1">
          Restrict who in the organisation can use each MCP server at runtime.
          An empty selection means <em>all roles except VIEWER</em>; pick
          specific roles to whitelist them. Org admins can always edit
          regardless of this filter.
        </p>
      </header>

      {error && (
        <div className="p-3 mb-4 rounded border border-red-200 bg-red-50 text-red-800 text-sm">
          {error}
        </div>
      )}

      <section className="bg-white rounded shadow-sm border border-gray-200 overflow-hidden">
        <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 text-xs text-gray-600">
          {loading ? 'Loading…' : `${servers.length} server${servers.length === 1 ? '' : 's'}`}
        </div>

        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-700">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Server</th>
              <th className="px-3 py-2 text-left font-medium">Status</th>
              {ALL_ROLES.map((r) => (
                <th key={r} className="px-3 py-2 text-center font-medium capitalize">
                  {r}
                </th>
              ))}
              <th className="px-3 py-2 text-right font-medium">Save</th>
            </tr>
          </thead>
          <tbody>
            {servers.length === 0 && !loading ? (
              <tr>
                <td colSpan={ALL_ROLES.length + 3} className="px-3 py-6 text-center text-gray-500">
                  No MCP servers in this organisation yet.
                </td>
              </tr>
            ) : (
              servers.map((s) => (
                <tr key={s.id} className="border-t border-gray-100 hover:bg-gray-50">
                  <td className="px-3 py-2">
                    <div className="font-medium">{s.name}</div>
                    <div className="font-mono text-[10px] text-gray-500">{s.server_id}</div>
                    {(s.allowed_roles?.length ?? 0) === 0 && (
                      <div className="text-[10px] text-gray-500 italic mt-0.5">
                        default — all roles except viewer
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {s.enabled ? (
                      <span className="text-green-700 text-xs">enabled</span>
                    ) : (
                      <span className="text-gray-500 text-xs">disabled</span>
                    )}
                  </td>
                  {ALL_ROLES.map((role) => (
                    <td key={role} className="px-3 py-2 text-center">
                      <input
                        type="checkbox"
                        checked={(pending[s.id] ?? []).includes(role)}
                        onChange={() => toggleRole(s.id, role)}
                      />
                    </td>
                  ))}
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      className="px-2 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
                      onClick={() => save(s)}
                      disabled={!dirty(s.id) || savingId === s.id}
                    >
                      {savingId === s.id ? 'Saving…' : savedId === s.id ? '✓ Saved' : 'Save'}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      <p className="text-xs text-gray-500 mt-3">
        Tip: leaving every box unchecked keeps the default (all roles except VIEWER).
        Checking only <em>admin</em> + <em>owner</em> hides the server from regular members.
      </p>
    </div>
  )
}

export default ServerAccessPage
