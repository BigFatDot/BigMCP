/**
 * SSO Provider detail page (Story I.3).
 *
 * Detail view for one configured OIDC provider.
 *
 * Sections:
 * 1. Header — name, status, "Test login flow" link (opens the real
 *    OIDC roundtrip in a new tab — completing it just logs the admin in
 *    via SSO, which IS the test).
 * 2. Configuration card — issuer, client_id (read-only), scopes,
 *    claim paths, provisioning policy. Inline Edit modal reuses the
 *    same form shape as Add Provider but pre-populated.
 * 3. Group mappings — list + create + delete inline. Each mapping
 *    can either grant a team membership (org + role) or grant
 *    instance-admin status (or both).
 *
 * Auto-link warning banner repeats here when enabled, in case the
 * admin landed on the detail page directly via the URL.
 */

import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeftIcon,
  PlusIcon,
  TrashIcon,
  ExclamationTriangleIcon,
  ArrowPathIcon,
  PuzzlePieceIcon,
  PlayIcon,
} from '@heroicons/react/24/outline'
import { Card, Button, Badge } from '@/components/ui'
import {
  listProviders,
  updateProvider,
  listMappings,
  createMapping,
  deleteMapping,
  listAllOrganizations,
  type OIDCProvider,
  type OIDCGroupMapping,
  type AdminOrganization,
  type OIDCProviderUpdatePayload,
} from '@/services/sso'

const ROLES = ['owner', 'admin', 'member', 'viewer']

interface MappingRowProps {
  mapping: OIDCGroupMapping
  orgsById: Map<string, AdminOrganization>
  onDelete: () => void
}

function MappingRow({ mapping, orgsById, onDelete }: MappingRowProps) {
  const orgName = mapping.organization_id
    ? orgsById.get(mapping.organization_id)?.name ?? '(unknown org)'
    : null
  return (
    <div className="flex items-center justify-between gap-3 px-3 py-2 border border-gray-200 rounded">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-sm">
          <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">
            {mapping.idp_group_name}
          </code>
          <span className="text-gray-400">→</span>
          {orgName ? (
            <span>
              <span className="font-medium">{orgName}</span>
              <Badge variant="gray" size="sm" className="ml-2">
                {mapping.role}
              </Badge>
            </span>
          ) : (
            <span className="italic text-gray-500">no team binding</span>
          )}
          {mapping.grants_instance_admin && (
            <Badge variant="warning" size="sm">
              grants instance-admin
            </Badge>
          )}
        </div>
      </div>
      <Button variant="ghost" size="sm" onClick={onDelete}>
        <TrashIcon className="h-4 w-4 text-red-500" />
      </Button>
    </div>
  )
}

interface CreateMappingProps {
  providerId: string
  organizations: AdminOrganization[]
  onCreated: () => void
}

function CreateMappingForm({
  providerId,
  organizations,
  onCreated,
}: CreateMappingProps) {
  const [groupName, setGroupName] = useState('')
  const [orgId, setOrgId] = useState('')
  const [role, setRole] = useState('member')
  const [grantsAdmin, setGrantsAdmin] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleAdd = async () => {
    setSubmitting(true)
    setError(null)
    try {
      await createMapping(providerId, {
        idp_group_name: groupName.trim(),
        organization_id: orgId || null,
        role: orgId ? role : null,
        grants_instance_admin: grantsAdmin,
      })
      setGroupName('')
      setOrgId('')
      setRole('member')
      setGrantsAdmin(false)
      onCreated()
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Create failed')
    } finally {
      setSubmitting(false)
    }
  }

  const canSubmit =
    !!groupName.trim() && (grantsAdmin || (orgId && role)) && !submitting

  return (
    <div className="p-3 bg-gray-50 border border-dashed border-gray-300 rounded">
      <div className="text-xs font-medium text-gray-700 mb-2">
        Add a group mapping
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-2">
        <input
          type="text"
          value={groupName}
          onChange={(e) => setGroupName(e.target.value)}
          placeholder="engineering-team"
          className="px-2 py-1 border border-gray-300 rounded text-sm font-mono"
        />
        <select
          value={orgId}
          onChange={(e) => setOrgId(e.target.value)}
          className="px-2 py-1 border border-gray-300 rounded text-sm bg-white"
        >
          <option value="">— no team binding —</option>
          {organizations.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </select>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          disabled={!orgId}
          className="px-2 py-1 border border-gray-300 rounded text-sm bg-white disabled:bg-gray-100"
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <Button
          onClick={handleAdd}
          disabled={!canSubmit}
          size="sm"
          className="w-full"
        >
          <PlusIcon className="h-4 w-4 mr-1" />
          Add
        </Button>
      </div>
      <label className="mt-2 flex items-center gap-2 text-xs text-gray-700 cursor-pointer">
        <input
          type="checkbox"
          checked={grantsAdmin}
          onChange={(e) => setGrantsAdmin(e.target.checked)}
        />
        Grant instance-admin status
      </label>
      {error && (
        <div className="mt-2 text-xs text-red-700">{error}</div>
      )}
    </div>
  )
}

export function SsoProviderDetailPage() {
  const { providerId } = useParams<{ providerId: string }>()
  const [provider, setProvider] = useState<OIDCProvider | null>(null)
  const [mappings, setMappings] = useState<OIDCGroupMapping[]>([])
  const [organizations, setOrganizations] = useState<AdminOrganization[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = async () => {
    if (!providerId) return
    setLoading(true)
    setError(null)
    try {
      const [provs, maps, orgs] = await Promise.all([
        listProviders(),
        listMappings(providerId),
        listAllOrganizations(),
      ])
      const matched = provs.find((p) => p.id === providerId) ?? null
      setProvider(matched)
      setMappings(maps)
      setOrganizations(orgs)
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providerId])

  const handleQuickUpdate = async (
    payload: OIDCProviderUpdatePayload,
  ): Promise<void> => {
    if (!providerId) return
    try {
      await updateProvider(providerId, payload)
      await refresh()
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Update failed')
    }
  }

  const handleDeleteMapping = async (mappingId: string) => {
    if (!providerId) return
    if (!window.confirm('Delete this mapping?')) return
    try {
      await deleteMapping(providerId, mappingId)
      await refresh()
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Delete failed')
    }
  }

  const orgsById = new Map(organizations.map((o) => [o.id, o]))

  if (loading && !provider) {
    return (
      <div className="container py-8 max-w-4xl">
        <Card className="p-8 text-center text-sm text-gray-500">
          Loading…
        </Card>
      </div>
    )
  }

  if (!provider) {
    return (
      <div className="container py-8 max-w-4xl">
        <Card className="p-8 text-center text-sm text-red-700">
          Provider not found.
        </Card>
        <div className="mt-4">
          <Link to="/app/admin/sso-providers">
            <Button variant="secondary">
              <ArrowLeftIcon className="h-4 w-4 mr-2" />
              Back to providers
            </Button>
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="container py-8 max-w-4xl">
      <div className="mb-4">
        <Link
          to="/app/admin/sso-providers"
          className="text-sm text-gray-600 hover:text-orange flex items-center gap-1"
        >
          <ArrowLeftIcon className="h-4 w-4" />
          All providers
        </Link>
      </div>

      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <PuzzlePieceIcon className="h-7 w-7 text-orange" />
            {provider.name}
          </h1>
          <div className="flex items-center gap-2 mt-2">
            <Badge variant={provider.is_active ? 'success' : 'gray'}>
              {provider.is_active ? 'active' : 'disabled'}
            </Badge>
            {provider.auto_link_by_verified_email && (
              <Badge variant="warning">auto-link ON</Badge>
            )}
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <a
            href={`/api/v1/auth/oidc/${provider.id}/login`}
            target="_blank"
            rel="noopener noreferrer"
          >
            <Button variant="secondary">
              <PlayIcon className="h-4 w-4 mr-2" />
              Test login flow
            </Button>
          </a>
          <Button variant="secondary" onClick={refresh}>
            <ArrowPathIcon className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>

      {provider.auto_link_by_verified_email && (
        <Card className="mb-4 p-4 bg-amber-50 border border-amber-300">
          <div className="flex items-start gap-3 text-sm text-amber-900">
            <ExclamationTriangleIcon className="h-5 w-5 text-amber-600 flex-shrink-0" />
            <div>
              <div className="font-medium">
                Auto-link by verified email is ENABLED
              </div>
              <div className="text-xs mt-1">
                On first SSO login, an existing local account with the same
                verified email will be silently bound to this IdP. Disable as
                soon as your migration is complete.
              </div>
              <button
                onClick={() =>
                  handleQuickUpdate({ auto_link_by_verified_email: false })
                }
                className="mt-2 text-xs font-medium text-amber-900 underline hover:text-amber-700"
              >
                Disable auto-link now
              </button>
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

      {/* ---------------- Configuration ---------------- */}
      <Card className="p-5 mb-4">
        <h2 className="text-sm font-semibold text-gray-900 mb-3">
          Configuration
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <div>
            <span className="text-gray-500 text-xs">Button label</span>
            <div>{provider.display_label}</div>
          </div>
          <div>
            <span className="text-gray-500 text-xs">Issuer URL</span>
            <div className="font-mono text-xs break-all">
              {provider.issuer_url}
            </div>
          </div>
          <div>
            <span className="text-gray-500 text-xs">Client ID</span>
            <div className="font-mono text-xs break-all">
              {provider.client_id}
            </div>
          </div>
          <div>
            <span className="text-gray-500 text-xs">Scopes</span>
            <div className="font-mono text-xs">
              {(provider.scopes ?? []).join(' ')}
            </div>
          </div>
          <div>
            <span className="text-gray-500 text-xs">Groups claim path</span>
            <div className="font-mono text-xs">
              {provider.groups_claim_path ?? '(none)'}
            </div>
          </div>
          <div>
            <span className="text-gray-500 text-xs">Email claim path</span>
            <div className="font-mono text-xs">{provider.email_claim_path}</div>
          </div>
        </div>
        <div className="mt-3 pt-3 border-t border-gray-100 text-xs text-gray-500">
          Editing the secret or rotating credentials is not yet exposed in
          this UI — use the API directly or recreate the provider. (Will land
          in a follow-up.)
        </div>
      </Card>

      {/* ---------------- Provisioning policy ---------------- */}
      <Card className="p-5 mb-4">
        <h2 className="text-sm font-semibold text-gray-900 mb-3">
          Provisioning policy
        </h2>
        <div className="space-y-2 text-sm">
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={provider.reject_unmapped_users}
              onChange={(e) =>
                handleQuickUpdate({ reject_unmapped_users: e.target.checked })
              }
              className="mt-0.5"
            />
            <span>
              <span className="font-medium">Reject unmapped users</span>
              <span className="block text-xs text-gray-500">
                Refuse login when no group claim matches a mapping below.
              </span>
            </span>
          </label>
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={provider.require_email_verified}
              onChange={(e) =>
                handleQuickUpdate({
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
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={provider.auto_link_by_verified_email}
              onChange={(e) =>
                handleQuickUpdate({
                  auto_link_by_verified_email: e.target.checked,
                })
              }
              className="mt-0.5"
            />
            <span>
              <span className="font-medium">
                Auto-link by verified email (migration-only)
              </span>
            </span>
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Fallback team (no group match)
              </label>
              <select
                value={provider.fallback_organization_id ?? ''}
                onChange={(e) =>
                  handleQuickUpdate({
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
                value={provider.fallback_role}
                onChange={(e) =>
                  handleQuickUpdate({ fallback_role: e.target.value })
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
          </div>
        </div>
      </Card>

      {/* ---------------- Group mappings ---------------- */}
      <Card className="p-5">
        <h2 className="text-sm font-semibold text-gray-900 mb-3">
          Group mappings ({mappings.length})
        </h2>
        <p className="text-xs text-gray-500 mb-3">
          When a user logs in, BigMCP reads the IdP's <code>groups</code>{' '}
          claim and binds the user to the matching teams (and roles). A
          mapping with <strong>grants instance-admin</strong> additionally
          flips the user's instance-admin flag.
        </p>

        <CreateMappingForm
          providerId={provider.id}
          organizations={organizations}
          onCreated={refresh}
        />

        {mappings.length === 0 ? (
          <div className="text-xs text-gray-500 mt-3 italic">
            No mappings yet. Without mappings, only the fallback team
            applies (or login is refused if{' '}
            <code>reject_unmapped_users</code> is on and no fallback is set).
          </div>
        ) : (
          <div className="space-y-2 mt-3">
            {mappings.map((m) => (
              <MappingRow
                key={m.id}
                mapping={m}
                orgsById={orgsById}
                onDelete={() => handleDeleteMapping(m.id)}
              />
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
