/**
 * Client-control policy editor (instance admin).
 *
 * One-page form for the seven knobs of ClientControlPolicy. Reads the
 * resolved instance policy on mount, lets the admin edit, sends a
 * single PUT — partial updates aren't supported on purpose (the admin
 * should always see what they are committing).
 *
 * The composition rules (org can shrink but not relax) live in the
 * backend PolicyResolver; this UI does not need to know about org
 * overrides.
 */

import { useEffect, useState } from 'react'
import { AxiosError } from 'axios'
import {
  getClientPolicy,
  updateClientPolicy,
  DEFAULT_POLICY,
  type ClientControlPolicy,
  type DcrPolicy,
} from '../../services/clientControl'

const DCR_OPTIONS: { value: DcrPolicy; label: string; help: string }[] = [
  {
    value: 'open',
    label: 'Open',
    help: 'Anyone can register dynamically (RFC 7591 default).',
  },
  {
    value: 'admin_approval',
    label: 'Admin approval',
    help: 'New DCR clients land as PENDING; an instance admin must approve before /authorize succeeds.',
  },
  {
    value: 'denied',
    label: 'Denied',
    help: 'DCR is disabled. Only manually-created or pre-loaded clients can authenticate.',
  },
]

function listToTextarea(values: string[]): string {
  return values.join('\n')
}
function textareaToList(value: string): string[] {
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
}

export function ClientPolicyPage() {
  const [policy, setPolicy] = useState<ClientControlPolicy>(DEFAULT_POLICY)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedAt, setSavedAt] = useState<number | null>(null)

  // Local string state for the textareas; we sync to the policy on change.
  const [trustedUrls, setTrustedUrls] = useState('')
  const [redirectDomains, setRedirectDomains] = useState('')

  function applyPolicy(p: ClientControlPolicy) {
    setPolicy(p)
    setTrustedUrls(listToTextarea(p.trusted_cimd_urls))
    setRedirectDomains(listToTextarea(p.allowed_redirect_domains))
  }

  useEffect(() => {
    setLoading(true)
    setError(null)
    getClientPolicy()
      .then(applyPolicy)
      .catch((err: AxiosError<{ detail?: string }>) => {
        if (err.response?.status === 403) {
          setError('Instance-admin privileges required to view the client-control policy.')
        } else if (err.response?.status === 401) {
          setError('Authentication required. Please log in again.')
        } else {
          setError(err.response?.data?.detail ?? err.message ?? 'Failed to load policy')
        }
      })
      .finally(() => setLoading(false))
  }, [])

  async function save() {
    setSaving(true)
    setSavedAt(null)
    try {
      const next: ClientControlPolicy = {
        ...policy,
        trusted_cimd_urls: textareaToList(trustedUrls),
        allowed_redirect_domains: textareaToList(redirectDomains),
      }
      const result = await updateClientPolicy(next)
      applyPolicy(result)
      setSavedAt(Date.now())
    } catch (err) {
      const ax = err as AxiosError<{ detail?: string }>
      alert(ax.response?.data?.detail ?? ax.message ?? 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900">Client-control policy</h1>
        <p className="text-sm text-gray-600 mt-1">
          Instance-wide policy for OAuth client registration. Org admins can
          tighten these settings for their own organisation but never relax
          them. Changes are audited (action <code>instance.policy_changed</code>).
        </p>
      </header>

      {loading && <div className="text-sm text-gray-500 mb-4">Loading…</div>}
      {error && (
        <div className="p-3 mb-4 rounded border border-red-200 bg-red-50 text-red-800 text-sm">
          {error}
        </div>
      )}

      <section className="bg-white rounded shadow-sm border border-gray-200 p-5 space-y-6">
        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            checked={policy.enabled}
            onChange={(e) => setPolicy((p) => ({ ...p, enabled: e.target.checked }))}
            className="mt-1"
          />
          <div>
            <div className="font-medium text-gray-900">Enable client-control policy</div>
            <div className="text-xs text-gray-600">
              When unchecked the policy lies dormant — DCR behaves exactly as
              before this feature shipped.
            </div>
          </div>
        </label>

        <fieldset className="space-y-2">
          <legend className="text-sm font-medium text-gray-900">DCR policy</legend>
          {DCR_OPTIONS.map((opt) => (
            <label key={opt.value} className="flex items-start gap-3 text-sm">
              <input
                type="radio"
                name="dcr_policy"
                value={opt.value}
                checked={policy.dcr_policy === opt.value}
                onChange={() => setPolicy((p) => ({ ...p, dcr_policy: opt.value }))}
                className="mt-1"
              />
              <div>
                <div className="font-medium">{opt.label}</div>
                <div className="text-xs text-gray-600">{opt.help}</div>
              </div>
            </label>
          ))}
        </fieldset>

        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            checked={policy.require_cimd}
            onChange={(e) => setPolicy((p) => ({ ...p, require_cimd: e.target.checked }))}
            className="mt-1"
          />
          <div>
            <div className="font-medium text-gray-900">Require CIMD (SEP-991)</div>
            <div className="text-xs text-gray-600">
              Reject any DCR request that does not include a
              <code> client_id_metadata_document</code> URL.
            </div>
          </div>
        </label>

        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            checked={policy.auto_approve_cimd}
            onChange={(e) => setPolicy((p) => ({ ...p, auto_approve_cimd: e.target.checked }))}
            className="mt-1"
          />
          <div>
            <div className="font-medium text-gray-900">Auto-approve trusted CIMD</div>
            <div className="text-xs text-gray-600">
              When a CIMD URL is on the trusted list (below) and validation
              succeeds, skip the admin-approval gate.
            </div>
          </div>
        </label>

        <div className="text-sm">
          <label className="block">
            <span className="font-medium text-gray-900">Trusted CIMD URLs</span>
            <span className="block text-xs text-gray-600 mb-1">
              One HTTPS URL per line. An empty list means "trust any valid CIMD"
              when auto-approve is on.
            </span>
            <textarea
              rows={4}
              value={trustedUrls}
              onChange={(e) => setTrustedUrls(e.target.value)}
              className="w-full border border-gray-300 rounded px-2 py-1 font-mono text-xs"
              placeholder="https://claude.ai/.well-known/cimd"
            />
          </label>
        </div>

        <div className="text-sm">
          <label className="block">
            <span className="font-medium text-gray-900">Allowed redirect domains</span>
            <span className="block text-xs text-gray-600 mb-1">
              Glob patterns matching the host part of redirect_uri. One per
              line. Empty list = any host accepted.
            </span>
            <textarea
              rows={3}
              value={redirectDomains}
              onChange={(e) => setRedirectDomains(e.target.value)}
              className="w-full border border-gray-300 rounded px-2 py-1 font-mono text-xs"
              placeholder="*.cerema.fr"
            />
          </label>
        </div>

        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            checked={policy.notify_admins_on_new_client}
            onChange={(e) =>
              setPolicy((p) => ({ ...p, notify_admins_on_new_client: e.target.checked }))
            }
            className="mt-1"
          />
          <div>
            <div className="font-medium text-gray-900">Notify admins on new client</div>
            <div className="text-xs text-gray-600">
              Email instance admins (and org admins for org-scoped clients)
              every time a new client registers.
            </div>
          </div>
        </label>

        <div className="border-t border-gray-200 pt-4 flex items-center gap-3">
          <button
            type="button"
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            onClick={save}
            disabled={saving || loading}
          >
            {saving ? 'Saving…' : 'Save policy'}
          </button>
          {savedAt && (
            <span className="text-xs text-green-700">
              ✓ saved at {new Date(savedAt).toLocaleTimeString()}
            </span>
          )}
        </div>
      </section>
    </div>
  )
}

export default ClientPolicyPage
