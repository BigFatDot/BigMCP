/**
 * EditTeamServerModal - Edit shared credentials for team servers (Admin only)
 *
 * Allows updating:
 * - Name and description
 * - Visibility to members
 * - Credentials (masked, optional override)
 */

import { useState, useEffect } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  XMarkIcon,
  EyeIcon,
  EyeSlashIcon,
  BuildingOffice2Icon,
  UsersIcon,
  LockClosedIcon,
  KeyIcon,
} from '@heroicons/react/24/outline'
import { Button, Input, Alert } from '@/components/ui'
import { marketplaceApi, orgCredentialsApi } from '@/services/marketplace'
import type { OrganizationCredential } from '@/types/marketplace'
import { useTranslation } from 'react-i18next'

interface EditTeamServerModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
  /** The organization credential to edit */
  orgCredential: OrganizationCredential | null
  /** The associated MCP server data (for credential fields schema) */
  serverData?: {
    id: string
    name: string
    credentials?: Array<{
      name: string
      type: string
      required: boolean
      description?: string
      placeholder?: string
      documentation_url?: string
    }>
  } | null
}

export function EditTeamServerModal({
  isOpen,
  onClose,
  onSuccess,
  orgCredential,
  serverData,
}: EditTeamServerModalProps) {
  const { t } = useTranslation('dashboard')
  const [showValues, setShowValues] = useState<Record<string, boolean>>({})
  const [credentials, setCredentials] = useState<Record<string, string>>({})
  const [hasCredentialChanges, setHasCredentialChanges] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [visibleToUsers, setVisibleToUsers] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Fetch marketplace server data for credential schema if not provided
  const { data: fetchedServerData } = useQuery({
    queryKey: ['marketplace-server', orgCredential?.server_id],
    queryFn: async () => {
      if (!orgCredential?.server_id) return null
      // Try to find in marketplace by server env marker
      const servers = await marketplaceApi.listServers()
      // Match by server name pattern or marketplace ID in env
      const match = servers.find(
        (s) =>
          orgCredential.name?.includes(s.name) ||
          s.name === orgCredential.name?.replace(' (Team)', '').replace(' - Team', '')
      )
      return match || null
    },
    enabled: isOpen && !serverData && !!orgCredential,
  })

  const effectiveServerData = serverData || fetchedServerData

  // Update org credential mutation
  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!orgCredential) throw new Error('No credential to edit')

      const updateData: {
        name?: string
        description?: string
        visible_to_users?: boolean
        credentials?: Record<string, string>
      } = {
        name: name.trim(),
        description: description.trim() || undefined,
        visible_to_users: visibleToUsers,
      }

      // Only include credentials if they were changed
      if (hasCredentialChanges) {
        // Filter out empty values (keep existing)
        const filteredCredentials: Record<string, string> = {}
        for (const [key, value] of Object.entries(credentials)) {
          if (value.trim()) {
            filteredCredentials[key] = value.trim()
          }
        }
        if (Object.keys(filteredCredentials).length > 0) {
          updateData.credentials = filteredCredentials
        }
      }

      return orgCredentialsApi.updateOrgCredential(orgCredential.server_id, updateData)
    },
    onSuccess: () => {
      onSuccess()
      handleClose()
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : t('myServers.team.editFailed'))
    },
  })

  // Reset state when modal opens with new credential
  useEffect(() => {
    if (isOpen && orgCredential) {
      setName(orgCredential.name || '')
      setDescription(orgCredential.description || '')
      setVisibleToUsers(orgCredential.visible_to_users ?? true)
      setCredentials({})
      setHasCredentialChanges(false)
      setError(null)
      setShowValues({})
    }
  }, [isOpen, orgCredential])

  const handleClose = () => {
    setError(null)
    onClose()
  }

  const handleCredentialChange = (fieldName: string, value: string) => {
    setCredentials({ ...credentials, [fieldName]: value })
    setHasCredentialChanges(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    // Validate required fields
    if (!name.trim()) {
      setError(t('myServers.team.nameRequired'))
      return
    }

    updateMutation.mutate()
  }

  const toggleShowValue = (fieldName: string) => {
    setShowValues((prev) => ({ ...prev, [fieldName]: !prev[fieldName] }))
  }

  if (!isOpen || !orgCredential) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl max-w-lg w-full mx-4 max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-purple-100 dark:bg-purple-900/30 rounded-lg flex items-center justify-center">
                <BuildingOffice2Icon className="w-5 h-5 text-purple-600 dark:text-purple-400" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                  {t('myServers.team.editTitle')}
                </h2>
                <p className="text-sm text-gray-600 dark:text-gray-400">{orgCredential.name}</p>
              </div>
            </div>
            <button
              onClick={handleClose}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              <XMarkIcon className="w-6 h-6" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {error && (
            <Alert variant="error" title="Error" className="mb-4" onClose={() => setError(null)}>
              {error}
            </Alert>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Name & Description */}
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('myServers.team.nameLabel')} <span className="text-red-500">*</span>
                </label>
                <Input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t('myServers.team.namePlaceholder')}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('myServers.team.descriptionLabel')}
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder={t('myServers.team.descriptionPlaceholder')}
                  rows={2}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white"
                />
              </div>
            </div>

            {/* Visibility Toggle */}
            <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {visibleToUsers ? (
                    <UsersIcon className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                  ) : (
                    <LockClosedIcon className="w-5 h-5 text-gray-500" />
                  )}
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">
                      {visibleToUsers
                        ? t('myServers.team.visibleToAll')
                        : t('myServers.team.adminOnly')}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {visibleToUsers
                        ? t('myServers.team.visibleToAllDesc')
                        : t('myServers.team.adminOnlyDesc')}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setVisibleToUsers(!visibleToUsers)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    visibleToUsers ? 'bg-purple-600' : 'bg-gray-300 dark:bg-gray-600'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      visibleToUsers ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>
            </div>

            {/* Credential Fields - Optional Update */}
            {effectiveServerData?.credentials && effectiveServerData.credentials.length > 0 && (
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <KeyIcon className="w-5 h-5 text-gray-500" />
                  <h3 className="font-medium text-gray-900 dark:text-white">
                    {t('myServers.team.updateCredentials')}
                  </h3>
                </div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {t('myServers.team.updateCredentialsHint')}
                </p>
                {effectiveServerData.credentials.map((field) => (
                  <div key={field.name}>
                    <div className="flex items-start justify-between mb-1">
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                        {field.name}
                      </label>
                      {field.documentation_url && (
                        <a
                          href={field.documentation_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-purple-600 hover:underline"
                        >
                          {t('myServers.team.howToGet')}
                        </a>
                      )}
                    </div>
                    <div className="relative">
                      <Input
                        type={field.type === 'secret' && !showValues[field.name] ? 'password' : 'text'}
                        value={credentials[field.name] || ''}
                        onChange={(e) => handleCredentialChange(field.name, e.target.value)}
                        placeholder={t('myServers.team.leaveEmptyToKeep')}
                        helperText={field.description}
                      />
                      {field.type === 'secret' && (
                        <button
                          type="button"
                          onClick={() => toggleShowValue(field.name)}
                          className="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                        >
                          {showValues[field.name] ? (
                            <EyeSlashIcon className="h-5 w-5" />
                          ) : (
                            <EyeIcon className="h-5 w-5" />
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </form>
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
          <Button variant="secondary" onClick={handleClose}>
            {t('myServers.team.cancel')}
          </Button>
          <Button
            variant="primary"
            onClick={handleSubmit}
            isLoading={updateMutation.isPending}
            className="bg-purple-600 hover:bg-purple-700"
          >
            {updateMutation.isPending ? t('myServers.team.saving') : t('myServers.team.saveChanges')}
          </Button>
        </div>
      </div>
    </div>
  )
}
