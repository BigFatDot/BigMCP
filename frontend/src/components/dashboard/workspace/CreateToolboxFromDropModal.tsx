/**
 * Light modal to create a toolbox initialized with one tool dropped on the
 * "+ New toolbox" zone. The user provides a name (required) and visibility,
 * the modal calls toolGroupsApi.create then toolGroupsApi.addTool in
 * sequence so the new toolbox starts non-empty.
 */

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArchiveBoxIcon, XMarkIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'

import { Button } from '@/components/ui'
import { toolGroupsApi } from '@/services/marketplace'
import type { ToolCardData } from './ToolCard'

interface Props {
  isOpen: boolean
  seedTool: ToolCardData | null
  canShareWithOrg: boolean
  onClose: () => void
}

export function CreateToolboxFromDropModal({ isOpen, seedTool, canShareWithOrg, onClose }: Props) {
  const { t } = useTranslation('dashboard')
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [visibility, setVisibility] = useState<'private' | 'organization'>('private')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  useEffect(() => {
    if (isOpen) {
      const seedName = seedTool?.serverName
        ? `${seedTool.serverName} toolbox`
        : ''
      setName(seedName)
      setDescription('')
      setVisibility('private')
      setErrorMsg(null)
    }
  }, [isOpen, seedTool])

  const createMutation = useMutation({
    mutationFn: async () => {
      const created = await toolGroupsApi.create({
        name: name.trim(),
        description: description.trim() || undefined,
        visibility: canShareWithOrg ? visibility : 'private',
      })
      if (seedTool) {
        try {
          await toolGroupsApi.addTool(created.id, seedTool.id)
        } catch (e) {
          // Log but don't fail the toolbox creation.
          console.warn('Failed to add seed tool to new toolbox', e)
        }
      }
      return created
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tool-groups'] })
      toast.success(
        t('workspace.newToolbox.created', { defaultValue: 'Toolbox created.' }),
      )
      onClose()
    },
    onError: (e: any) => setErrorMsg(e.response?.data?.detail || e.message || 'Failed'),
  })

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full mx-4 flex flex-col">
        <div className="p-6 border-b border-gray-200 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              <ArchiveBoxIcon className="w-5 h-5 text-orange" />
              {t('workspace.newToolbox.title', { defaultValue: 'New toolbox' })}
            </h2>
            <p className="text-sm text-gray-600 mt-1">
              {t('workspace.newToolbox.hint', {
                defaultValue:
                  'A toolbox bundles tools that can later scope an API key or be loaded into the pool in one click.',
              })}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 flex-shrink-0"
          >
            <XMarkIcon className="w-6 h-6" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {seedTool && (
            <div className="text-xs text-gray-600 bg-gray-50 rounded p-3 border border-gray-200">
              {t('workspace.newToolbox.seedNotice', { defaultValue: 'Will start with:' })}{' '}
              <span className="font-medium text-gray-900">{seedTool.name}</span>
              {seedTool.serverName && (
                <span className="text-gray-500"> · {seedTool.serverName}</span>
              )}
            </div>
          )}

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              {t('compositions.name', { defaultValue: 'Name' })}
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full p-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-orange focus:border-transparent"
              placeholder={
                t('workspace.newToolbox.namePlaceholder', {
                  defaultValue: 'e.g. Hostinger DNS toolbox',
                }) as string
              }
            />
          </div>

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              {t('compositions.description', { defaultValue: 'Description' })}
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full p-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-orange focus:border-transparent"
              placeholder={
                t('workspace.newToolbox.descriptionPlaceholder', {
                  defaultValue: 'What this toolbox is good for (optional)',
                }) as string
              }
            />
          </div>

          {canShareWithOrg && (
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1">
                {t('workspace.newToolbox.visibility', { defaultValue: 'Visibility' })}
              </label>
              <div className="flex gap-2 text-sm">
                <button
                  type="button"
                  onClick={() => setVisibility('private')}
                  className={`flex-1 px-3 py-2 rounded-lg border ${visibility === 'private' ? 'border-orange bg-orange/5 text-orange-dark' : 'border-gray-200 text-gray-600'}`}
                >
                  {t('compositions.private', { defaultValue: 'Private' })}
                </button>
                <button
                  type="button"
                  onClick={() => setVisibility('organization')}
                  className={`flex-1 px-3 py-2 rounded-lg border ${visibility === 'organization' ? 'border-orange bg-orange/5 text-orange-dark' : 'border-gray-200 text-gray-600'}`}
                >
                  {t('compositions.team', { defaultValue: 'Team' })}
                </button>
              </div>
            </div>
          )}

          {errorMsg && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">
              {errorMsg}
            </div>
          )}
        </div>

        <div className="p-6 border-t border-gray-200 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={createMutation.isPending}>
            {t('compositions.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            variant="primary"
            onClick={() => createMutation.mutate()}
            disabled={createMutation.isPending || name.trim().length < 1}
          >
            {createMutation.isPending
              ? t('workspace.newToolbox.creating', { defaultValue: 'Creating…' })
              : t('workspace.newToolbox.create', { defaultValue: 'Create toolbox' })}
          </Button>
        </div>
      </div>
    </div>
  )
}
