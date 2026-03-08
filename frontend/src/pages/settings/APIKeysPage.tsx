/**
 * API Keys Page
 *
 * Allows users to create, view, and manage API keys for programmatic access
 * to the BigMCP platform. Essential for self-hosted deployments and developers.
 *
 * Now supports linking API keys to Toolboxs for fine-grained access control.
 */

import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { PlusIcon, ClipboardIcon, TrashIcon, KeyIcon, ArchiveBoxIcon } from '@heroicons/react/24/outline'
import { Button, Card, Badge } from '@/components/ui'
import { cn } from '@/utils/cn'
import { userApiKeysApi, toolGroupsApi, type UserAPIKey } from '@/services/marketplace'
import { useOrganization } from '@/hooks/useAuth'
import type { ToolGroup } from '@/types/marketplace'

// Re-export type for component compatibility
type APIKey = UserAPIKey

interface CreateAPIKeyModalProps {
  isOpen: boolean
  onClose: () => void
  onCreated: (key: APIKey, secret: string) => void
  toolGroups: ToolGroup[]
}

// Scope IDs mapped to translation keys
const SCOPE_KEYS = [
  { id: 'tools:read', labelKey: 'toolsRead', descKey: 'toolsReadDesc' },
  { id: 'tools:execute', labelKey: 'toolsExecute', descKey: 'toolsExecuteDesc' },
  { id: 'servers:read', labelKey: 'serversRead', descKey: 'serversReadDesc' },
  { id: 'servers:write', labelKey: 'serversWrite', descKey: 'serversWriteDesc' },
  { id: 'credentials:read', labelKey: 'credentialsRead', descKey: 'credentialsReadDesc' },
  { id: 'credentials:write', labelKey: 'credentialsWrite', descKey: 'credentialsWriteDesc' },
]

function CreateAPIKeyModal({ isOpen, onClose, onCreated, toolGroups }: CreateAPIKeyModalProps) {
  const { t } = useTranslation('settings')
  const [name, setName] = useState('')
  const [selectedScopes, setSelectedScopes] = useState<string[]>(['tools:read', 'tools:execute'])
  const [expiresIn, setExpiresIn] = useState<string>('never')
  const [selectedToolGroup, setSelectedToolGroup] = useState<string>('')
  const [isLoading, setIsLoading] = useState(false)

  const handleScopeToggle = (scopeId: string) => {
    setSelectedScopes((prev) =>
      prev.includes(scopeId)
        ? prev.filter((s) => s !== scopeId)
        : [...prev, scopeId]
    )
  }

  const handleCreate = async () => {
    if (!name.trim()) return

    setIsLoading(true)
    try {
      // Calculate expiration date based on selection
      let expiresAt: string | undefined
      if (expiresIn !== 'never') {
        const now = new Date()
        if (expiresIn === '30d') {
          now.setDate(now.getDate() + 30)
        } else if (expiresIn === '90d') {
          now.setDate(now.getDate() + 90)
        } else if (expiresIn === '1y') {
          now.setFullYear(now.getFullYear() + 1)
        }
        expiresAt = now.toISOString()
      }

      const response = await userApiKeysApi.create({
        name: name.trim(),
        scopes: selectedScopes,
        expires_at: expiresAt,
        tool_group_id: selectedToolGroup || undefined,
      })
      onCreated(response.api_key as APIKey, response.secret)
    } catch (error) {
      console.error('Failed to create API key:', error)
    } finally {
      setIsLoading(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-gray-200">
          <h2 className="text-xl font-bold text-gray-900">{t('apiKeys.modal.title')}</h2>
          <p className="text-sm text-gray-600 mt-1">
            {t('apiKeys.modal.subtitle')}
          </p>
        </div>

        <div className="p-6 space-y-6">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              {t('apiKeys.name')}
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('apiKeys.namePlaceholder')}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange"
            />
          </div>

          {/* Scopes */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              {t('apiKeys.permissions.title')}
            </label>
            <div className="space-y-2">
              {SCOPE_KEYS.map((scope) => (
                <label
                  key={scope.id}
                  className={cn(
                    'flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors',
                    selectedScopes.includes(scope.id)
                      ? 'border-orange bg-orange-50'
                      : 'border-gray-200 hover:border-orange-200'
                  )}
                >
                  <input
                    type="checkbox"
                    checked={selectedScopes.includes(scope.id)}
                    onChange={() => handleScopeToggle(scope.id)}
                    className="mt-0.5 rounded border-gray-300 text-orange focus:ring-orange"
                  />
                  <div>
                    <p className="font-medium text-gray-900">{t(`apiKeys.permissions.${scope.labelKey}`)}</p>
                    <p className="text-sm text-gray-600">{t(`apiKeys.permissions.${scope.descKey}`)}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Expiration */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              {t('apiKeys.expiration.title')}
            </label>
            <select
              value={expiresIn}
              onChange={(e) => setExpiresIn(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange"
            >
              <option value="never">{t('apiKeys.expiration.never')}</option>
              <option value="30d">{t('apiKeys.expiration.30days')}</option>
              <option value="90d">{t('apiKeys.expiration.90days')}</option>
              <option value="1y">{t('apiKeys.expiration.1year')}</option>
            </select>
          </div>

          {/* Toolbox Restriction */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              {t('apiKeys.toolbox.title')}
              <span className="text-gray-400 font-normal ml-1">({t('apiKeys.toolbox.optional')})</span>
            </label>
            <select
              value={selectedToolGroup}
              onChange={(e) => setSelectedToolGroup(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange"
            >
              <option value="">{t('apiKeys.toolbox.noRestriction')}</option>
              {toolGroups.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.name} ({group.items?.length || 0} {t('apiKeys.toolbox.tools')})
                </option>
              ))}
            </select>
            <p className="text-xs text-gray-500 mt-1">
              {t('apiKeys.toolbox.hint')}{' '}
              <Link to="/app/tools" className="text-orange hover:underline">
                {t('apiKeys.toolbox.manageGroups')}
              </Link>
            </p>
          </div>
        </div>

        <div className="p-6 border-t border-gray-200 flex justify-end gap-3">
          <Button variant="secondary" onClick={onClose}>
            {t('account.cancel')}
          </Button>
          <Button
            variant="primary"
            onClick={handleCreate}
            disabled={!name.trim() || selectedScopes.length === 0 || isLoading}
          >
            {isLoading ? t('apiKeys.modal.creating') : t('apiKeys.modal.createButton')}
          </Button>
        </div>
      </div>
    </div>
  )
}

function APIKeyCard({ apiKey, onCopy, onRevoke, toolGroups }: {
  apiKey: APIKey
  onCopy: () => void
  onRevoke: () => void
  toolGroups: ToolGroup[]
}) {
  const { t } = useTranslation('settings')
  // Find linked tool group
  const linkedGroup = toolGroups.find((g) => g.id === apiKey.tool_group_id)

  return (
    <Card padding="lg">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-orange-100 rounded-full flex items-center justify-center">
            <KeyIcon className="w-5 h-5 text-orange" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">{apiKey.name}</h3>
            <p className="text-sm font-mono text-gray-500">{apiKey.key_prefix}...••••••</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onCopy}>
            <ClipboardIcon className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={onRevoke} className="text-red-600 hover:text-red-700">
            <TrashIcon className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Toolbox Badge */}
      {linkedGroup && (
        <div className="mt-3 flex items-center gap-2">
          <Badge variant="info" size="sm">
            <ArchiveBoxIcon className="w-3 h-3 mr-1 inline" />
            {linkedGroup.name}
          </Badge>
          <span className="text-xs text-gray-500">
            ({linkedGroup.items?.length || 0} {t('apiKeys.toolbox.tools')})
          </span>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        {apiKey.scopes.map((scope) => (
          <span
            key={scope}
            className="px-2 py-1 bg-gray-100 rounded text-xs font-medium text-gray-700"
          >
            {scope}
          </span>
        ))}
      </div>

      <div className="mt-4 text-xs text-gray-500 flex items-center gap-4">
        <span>{t('apiKeys.createdAt')}: {new Date(apiKey.created_at).toLocaleDateString()}</span>
        {apiKey.last_used_at && (
          <span>{t('apiKeys.lastUsed')}: {new Date(apiKey.last_used_at).toLocaleDateString()}</span>
        )}
        {apiKey.expires_at && (
          <span className="text-amber-600">
            {t('apiKeys.expires')}: {new Date(apiKey.expires_at).toLocaleDateString()}
          </span>
        )}
      </div>
    </Card>
  )
}

export function APIKeysPage() {
  const { t } = useTranslation('settings')
  const [apiKeys, setApiKeys] = useState<APIKey[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newKeySecret, setNewKeySecret] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { organizationId } = useOrganization()

  // Fetch tool groups for linking
  const { data: toolGroups = [] } = useQuery({
    queryKey: ['tool-groups'],
    queryFn: () => toolGroupsApi.list(),
  })

  useEffect(() => {
    loadApiKeys()
  }, [organizationId])

  const loadApiKeys = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const keys = await userApiKeysApi.list(organizationId || undefined)
      setApiKeys(keys)
    } catch (err) {
      console.error('Failed to load API keys:', err)
      setError('Failed to load API keys')
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyCreated = (key: APIKey, secret: string) => {
    setApiKeys((prev) => [key, ...prev])
    setNewKeySecret(secret)
    setShowCreateModal(false)
  }

  const handleCopyKey = async (keyPrefix: string) => {
    // In a real implementation, we would only have the prefix
    // The full key is only shown once at creation
    try {
      await navigator.clipboard.writeText(keyPrefix)
      // TODO: Show toast
    } catch (error) {
      console.error('Failed to copy:', error)
    }
  }

  const handleRevokeKey = async (keyId: string) => {
    if (!confirm(t('apiKeys.revokeConfirm'))) {
      return
    }
    try {
      await userApiKeysApi.revoke(keyId)
      setApiKeys((prev) => prev.filter((k) => k.id !== keyId))
    } catch (err) {
      console.error('Failed to revoke API key:', err)
      setError('Failed to revoke API key')
    }
  }

  return (
    <div className="container py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <h1 className="text-4xl font-bold text-gray-900 mb-2">{t('apiKeys.title')}</h1>
            <p className="text-lg text-gray-600 font-serif">
              {t('apiKeys.subtitle')}
            </p>
          </div>
          <Button variant="primary" onClick={() => setShowCreateModal(true)}>
            <PlusIcon className="w-5 h-5 mr-2" />
            {t('apiKeys.create')}
          </Button>
        </div>
      </div>

      {/* New Key Secret Banner */}
      {newKeySecret && (
        <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg">
          <div className="flex items-start justify-between">
            <div>
              <h3 className="font-semibold text-green-800">{t('apiKeys.newKey')}</h3>
              <p className="text-sm text-green-700 mt-1">
                {t('apiKeys.newKeyWarning')}
              </p>
              <code className="block mt-2 p-2 bg-white rounded font-mono text-sm break-all">
                {newKeySecret}
              </code>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                navigator.clipboard.writeText(newKeySecret)
                setNewKeySecret(null)
              }}
            >
              <ClipboardIcon className="w-4 h-4 mr-1" />
              {t('apiKeys.copyAndClose')}
            </Button>
          </div>
        </div>
      )}

      {/* API Keys List */}
      {isLoading ? (
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-gray-300 border-t-orange mx-auto" />
        </div>
      ) : apiKeys.length === 0 ? (
        <Card padding="lg">
          <div className="text-center py-12">
            <KeyIcon className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-gray-900 mb-2">{t('apiKeys.empty')}</h3>
            <p className="text-gray-600 font-serif mb-6">
              {t('apiKeys.emptyDescription')}
            </p>
            <Button variant="primary" onClick={() => setShowCreateModal(true)}>
              <PlusIcon className="w-5 h-5 mr-2" />
              {t('apiKeys.createFirst')}
            </Button>
          </div>
        </Card>
      ) : (
        <div className="space-y-4">
          {apiKeys.map((key) => (
            <APIKeyCard
              key={key.id}
              apiKey={key}
              onCopy={() => handleCopyKey(key.key_prefix)}
              onRevoke={() => handleRevokeKey(key.id)}
              toolGroups={toolGroups}
            />
          ))}
        </div>
      )}

      {/* Create Modal */}
      <CreateAPIKeyModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreated={handleKeyCreated}
        toolGroups={toolGroups}
      />
    </div>
  )
}
