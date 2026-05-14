/**
 * SSO Providers admin page (Story I.2 + I.3).
 *
 * - Lists configured OIDC providers.
 * - "Add provider" modal: preset picker + advanced options exposing the
 *   provisioning policy (auto-link, reject_unmapped, fallback team/role).
 * - Inline Disable/Enable + Delete on each row.
 * - "Force SSO-only" toggle in the page header (instance-wide setting).
 * - Click a provider name → detail page (general + group mappings).
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  PuzzlePieceIcon,
  PlusIcon,
  TrashIcon,
  ExclamationTriangleIcon,
  ArrowPathIcon,
  LockClosedIcon,
} from '@heroicons/react/24/outline'
import { Card, Button, Badge } from '@/components/ui'
import {
  listProviders,
  listPresets,
  createProvider,
  deleteProvider,
  updateProvider,
  listAllOrganizations,
  getForceSsoOnly,
  setForceSsoOnly,
  type OIDCProvider,
  type OIDCPreset,
  type OIDCProviderCreatePayload,
  type AdminOrganization,
} from '@/services/sso'

const ROLES = ['owner', 'admin', 'member', 'viewer']

interface CreateModalProps {
  isOpen: boolean
  presets: OIDCPreset[]
  organizations: AdminOrganization[]
  onClose: () => void
  onCreated: () => void
}

function CreateProviderModal({
  isOpen,
  presets,
  organizations,
  onClose,
  onCreated,
}: CreateModalProps) {
  const emptyForm: OIDCProviderCreatePayload = {
    name: '',
    display_label: '',
    issuer_url: '',
    client_id: '',
    client_secret: '',
    auto_link_by_verified_email: false,
    require_email_verified: true,
    reject_unmapped_users: true,
    fallback_organization_id: null,
    fallback_role: 'member',
  }
  const [selectedPresetId, setSelectedPresetId] = useState<string | null>(null)
  const [form, setForm] = useState<OIDCProviderCreatePayload>(emptyForm)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isOpen) {
      setSelectedPresetId(null)
      setForm(emptyForm)
      setError(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen])

  const applyPreset = (preset: OIDCPreset) => {
    setSelectedPresetId(preset.id)
    setForm({
      ...emptyForm,
      name: preset.default_name,
      display_label: preset.default_display_label,
      issuer_url: preset.issuer_url_template,
      scopes: preset.scopes,
      groups_claim_path: preset.groups_claim_path,
      email_claim_path: preset.email_claim_path,
      name_claim_path: preset.name_claim_path,
      require_email_verified: preset.require_email_verified,
    })
  }

  const selectedPreset = presets.find((p) => p.id === selectedPresetId)

  // Live lockout warning that mirrors the backend guard
  const wouldLockout =
    !!form.reject_unmapped_users && !form.fallback_organization_id

  const handleSubmit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      await createProvider(form)
      onCreated()
      onClose()
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Create failed')
    } finally {
      setSubmitting(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-gray-200">
          <h2 className="text-xl font-bold text-gray-900">Add OIDC provider</h2>
          <p className="text-sm text-gray-600 mt-1">
            Pick a preset to pre-fill the configuration, or use Generic for
            full custom setup.
          </p>
        </div>

        <div className="p-6 space-y-5">
          {/* Preset picker */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Preset
            </label>
            <div className="grid grid-cols-2 gap-2">
              {presets.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => applyPreset(p)}
                  className={`text-left p-3 border rounded-lg transition-colors ${
                    selectedPresetId === p.id
                      ? 'border-orange bg-orange-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="text-sm font-medium text-gray-900">
                    {p.label}
                  </div>
                </button>
              ))}
            </div>
            {selectedPreset?.notes && (
              <p className="text-xs text-gray-500 mt-2">
                {selectedPreset.notes}
                {selectedPreset.docs_url && (
                  <>
                    {' '}
                    <a
                      href={selectedPreset.docs_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-orange hover:underline"
                    >
                      Docs
                    </a>
                  </>
                )}
              </p>
            )}
          </div>

          {selectedPresetId && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Provider name
                  </label>
                  <input
                    type="text"
                    value={form.name}
                    onChange={(e) =>
                      setForm({ ...form, name: e.target.value })
                    }
                    placeholder="Acme Keycloak"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Button label
                  </label>
                  <input
                    type="text"
                    value={form.display_label}
                    onChange={(e) =>
                      setForm({ ...form, display_label: e.target.value })
                    }
                    placeholder="Continue with SSO"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange text-sm"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Issuer URL
                </label>
                <input
                  type="text"
                  value={form.issuer_url}
                  onChange={(e) =>
                    setForm({ ...form, issuer_url: e.target.value })
                  }
                  placeholder={selectedPreset?.issuer_url_placeholder}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange text-sm font-mono"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Discovery via{' '}
                  <code>
                    {form.issuer_url || '<issuer>'}/.well-known/openid-configuration
                  </code>
                </p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Client ID
                  </label>
                  <input
                    type="text"
                    value={form.client_id}
                    onChange={(e) =>
                      setForm({ ...form, client_id: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange text-sm font-mono"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Client secret
                  </label>
                  <input
                    type="password"
                    value={form.client_secret}
                    onChange={(e) =>
                      setForm({ ...form, client_secret: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange text-sm font-mono"
                  />
                </div>
              </div>

              {/* Provisioning policy — exposed by default in I.3 */}
              <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg space-y-3">
                <div className="text-sm font-medium text-gray-700">
                  Provisioning policy
                </div>

                <label className="flex items-start gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={!!form.reject_unmapped_users}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        reject_unmapped_users: e.target.checked,
                      })
                    }
                    className="mt-0.5"
                  />
                  <span>
                    <span className="font-medium">Reject unmapped users</span>
                    <span className="block text-xs text-gray-500">
                      Refuse login if no group claim matches a configured
                      mapping. Recommended for strict environments.
                    </span>
                  </span>
                </label>

                <label className="flex items-start gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={!!form.require_email_verified}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        require_email_verified: e.target.checked,
                      })
                    }
                    className="mt-0.5"
                  />
                  <span>
                    <span className="font-medium">Require email_verified</span>
                    <span className="block text-xs text-gray-500">
                      Refuse login if the IdP does not assert
                      <code className="ml-1">email_verified=true</code>.
                    </span>
                  </span>
                </label>

                <label className="flex items-start gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={!!form.auto_link_by_verified_email}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        auto_link_by_verified_email: e.target.checked,
                      })
                    }
                    className="mt-0.5"
                  />
                  <span>
                    <span className="font-medium">
                      Auto-link by verified email
                    </span>
                    <span className="block text-xs text-amber-700">
                      Migration-only. Binds existing local users to this IdP
                      on first SSO login. Disable as soon as migration is
                      done.
                    </span>
                  </span>
                </label>

                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">
                    Fallback team (when no group claim matches)
                  </label>
                  <select
                    value={form.fallback_organization_id ?? ''}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        fallback_organization_id: e.target.value || null,
                      })
                    }
                    className="w-full px-2 py-1 border border-gray-300 rounded text-sm bg-white"
                  >
                    <option value="">— none (PERSONAL org auto-create) —</option>
                    {organizations.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">
                    Fallback role
                  </label>
                  <select
                    value={form.fallback_role ?? 'member'}
                    onChange={(e) =>
                      setForm({ ...form, fallback_role: e.target.value })
                    }
                    className="w-full px-2 py-1 border border-gray-300 rounded text-sm bg-white"
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </div>

                {wouldLockout && (
                  <div className="flex items-start gap-2 p-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800">
                    <ExclamationTriangleIcon className="h-4 w-4 text-amber-500 flex-shrink-0" />
                    <span>
                      With <code>reject_unmapped</code> on and no fallback team,
                      every login will fail until you add at least one group
                      mapping. You can save the provider now and add mappings
                      from its detail page.
                    </span>
                  </div>
                )}
              </div>
            </>
          )}

          {error && (
            <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-800">
              <ExclamationTriangleIcon className="h-5 w-5 text-red-500 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </div>

        <div className="p-6 border-t border-gray-200 flex justify-end gap-3">
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={
              submitting ||
              !selectedPresetId ||
              !form.name.trim() ||
              !form.client_id.trim() ||
              !form.client_secret.trim() ||
              !form.issuer_url.trim()
            }
          >
            {submitting ? 'Creating…' : 'Create provider'}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Force-SSO-only toggle component
// ---------------------------------------------------------------------------

function ForceSsoOnlyToggle() {
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getForceSsoOnly()
      .then(setEnabled)
      .catch((err) => setError(err?.response?.data?.detail || err.message))
  }, [])

  const handleToggle = async () => {
    if (enabled === null) return
    const next = !enabled
    if (
      next &&
      !window.confirm(
        'Enable force-SSO-only? Local password login will be disabled for everyone. ' +
          'You must keep at least one local-password instance admin (break-glass).',
      )
    ) {
      return
    }
    setLoading(true)
    setError(null)
    try {
      const result = await setForceSsoOnly(next)
      setEnabled(result)
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Update failed')
    } finally {
      setLoading(false)
    }
  }

  if (enabled === null && !error) return null

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={handleToggle}
        disabled={loading}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm font-medium transition-colors ${
          enabled
            ? 'bg-red-50 border-red-300 text-red-800 hover:bg-red-100'
            : 'bg-gray-50 border-gray-300 text-gray-700 hover:bg-gray-100'
        }`}
      >
        <LockClosedIcon className="h-4 w-4" />
        Force SSO-only: {enabled ? 'ON' : 'off'}
      </button>
      {error && <span className="text-xs text-red-700">{error}</span>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function SsoProvidersPage() {
  const [providers, setProviders] = useState<OIDCProvider[] | null>(null)
  const [presets, setPresets] = useState<OIDCPreset[]>([])
  const [organizations, setOrganizations] = useState<AdminOrganization[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)

  const refresh = async () => {
    setLoading(true)
    setError(null)
    try {
      const [provs, pres, orgs] = await Promise.all([
        listProviders(),
        listPresets(),
        listAllOrganizations(),
      ])
      setProviders(provs)
      setPresets(pres)
      setOrganizations(orgs)
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const handleToggleActive = async (provider: OIDCProvider) => {
    try {
      await updateProvider(provider.id, { is_active: !provider.is_active })
      await refresh()
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Update failed')
    }
  }

  const handleDelete = async (provider: OIDCProvider) => {
    if (
      !window.confirm(
        `Delete OIDC provider "${provider.name}"? Any user provisioned via this IdP will lose the binding (their account is preserved but they'll need to re-authenticate via another path).`,
      )
    )
      return
    try {
      await deleteProvider(provider.id)
      await refresh()
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Delete failed')
    }
  }

  const anyAutoLink = (providers ?? []).some(
    (p) => p.auto_link_by_verified_email,
  )

  return (
    <div className="container py-8 max-w-4xl">
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <PuzzlePieceIcon className="h-7 w-7 text-orange" />
            SSO Providers
          </h1>
          <p className="text-sm text-gray-600 mt-1 max-w-2xl">
            Configure OIDC identity providers (Keycloak, Google, Microsoft
            Entra, AgentConnect, …). Active providers appear as buttons on
            the login page. Group mappings are configured per provider.
          </p>
        </div>
        <div className="flex flex-col items-end gap-3">
          <ForceSsoOnlyToggle />
          <div className="flex gap-2">
            <Button variant="secondary" onClick={refresh} disabled={loading}>
              <ArrowPathIcon className="h-4 w-4 mr-2" />
              Refresh
            </Button>
            <Button onClick={() => setShowCreate(true)} disabled={loading}>
              <PlusIcon className="h-4 w-4 mr-2" />
              Add provider
            </Button>
          </div>
        </div>
      </div>

      {anyAutoLink && (
        <Card className="mb-4 p-4 bg-amber-50 border border-amber-300">
          <div className="flex items-start gap-3 text-sm text-amber-900">
            <ExclamationTriangleIcon className="h-5 w-5 text-amber-600 flex-shrink-0" />
            <div>
              <div className="font-medium">
                Auto-link by verified email is ENABLED on at least one provider
              </div>
              <div className="text-xs mt-1">
                This setting binds existing local accounts to SSO identities
                automatically on first login. Disable it as soon as migration
                is complete to prevent unintended account linking.
              </div>
            </div>
          </div>
        </Card>
      )}

      {error && (
        <Card className="mb-4 p-4 bg-red-50 border border-red-200">
          <div className="flex items-start gap-3 text-sm text-red-800">
            <ExclamationTriangleIcon className="h-5 w-5 text-red-500 flex-shrink-0" />
            <div>{error}</div>
          </div>
        </Card>
      )}

      {loading && providers === null && (
        <Card className="p-8 text-center text-sm text-gray-500">
          Loading SSO providers…
        </Card>
      )}

      {!loading && providers !== null && providers.length === 0 && (
        <Card className="p-8 text-center">
          <PuzzlePieceIcon className="h-12 w-12 mx-auto text-gray-300 mb-3" />
          <h2 className="text-base font-medium text-gray-900">
            No SSO provider configured
          </h2>
          <p className="text-sm text-gray-500 mt-2 max-w-md mx-auto">
            Add an OIDC provider so your users can sign in via your
            existing identity provider (Keycloak, AgentConnect, Google,
            Microsoft Entra, …).
          </p>
          <div className="mt-4">
            <Button onClick={() => setShowCreate(true)}>
              <PlusIcon className="h-4 w-4 mr-2" />
              Add provider
            </Button>
          </div>
        </Card>
      )}

      {providers && providers.length > 0 && (
        <div className="space-y-3">
          {providers.map((p) => (
            <Card key={p.id} className="p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <Link
                      to={`/app/admin/sso-providers/${p.id}`}
                      className="text-base font-semibold text-gray-900 truncate hover:text-orange"
                    >
                      {p.name}
                    </Link>
                    <Badge variant={p.is_active ? 'success' : 'gray'}>
                      {p.is_active ? 'active' : 'disabled'}
                    </Badge>
                    {p.auto_link_by_verified_email && (
                      <Badge variant="warning">auto-link ON</Badge>
                    )}
                  </div>
                  <div className="text-sm text-gray-600 mb-2">
                    Button label:{' '}
                    <span className="font-medium">{p.display_label}</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-500">
                    <div>
                      <span className="font-medium text-gray-700">Issuer:</span>{' '}
                      <code className="text-[10px]">{p.issuer_url}</code>
                    </div>
                    <div>
                      <span className="font-medium text-gray-700">
                        Group mappings:
                      </span>{' '}
                      {p.mapping_count}
                    </div>
                    <div>
                      <span className="font-medium text-gray-700">Scopes:</span>{' '}
                      <code className="text-[10px]">
                        {(p.scopes ?? []).join(' ')}
                      </code>
                    </div>
                    <div>
                      <span className="font-medium text-gray-700">
                        Groups claim:
                      </span>{' '}
                      <code className="text-[10px]">
                        {p.groups_claim_path ?? '(none)'}
                      </code>
                    </div>
                  </div>
                  {p.reject_unmapped_users &&
                    p.mapping_count === 0 &&
                    !p.fallback_organization_id && (
                      <div className="mt-2 flex items-start gap-2 p-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800">
                        <ExclamationTriangleIcon className="h-4 w-4 text-amber-500 flex-shrink-0" />
                        <span>
                          This provider would lock out every user — add a
                          group mapping or set a fallback organization
                          before activating.
                        </span>
                      </div>
                    )}
                </div>
                <div className="flex flex-col gap-2 flex-shrink-0">
                  <Link to={`/app/admin/sso-providers/${p.id}`}>
                    <Button variant="secondary" size="sm" className="w-full">
                      Manage
                    </Button>
                  </Link>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleToggleActive(p)}
                  >
                    {p.is_active ? 'Disable' : 'Enable'}
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => handleDelete(p)}
                  >
                    <TrashIcon className="h-4 w-4 mr-1" />
                    Delete
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <CreateProviderModal
        isOpen={showCreate}
        presets={presets}
        organizations={organizations}
        onClose={() => setShowCreate(false)}
        onCreated={refresh}
      />
    </div>
  )
}
