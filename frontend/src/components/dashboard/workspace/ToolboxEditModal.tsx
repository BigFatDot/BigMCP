/**
 * ToolboxEditModal — edit, prune, or delete a toolbox.
 *
 * Lets the user rename / re-describe / re-color a ToolGroup, remove its
 * items one by one, or delete the toolbox entirely. All mutations are
 * optimistic: the workspace queries are invalidated on every success so
 * the surrounding UI stays in sync.
 */

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  XMarkIcon,
  TrashIcon,
  ArchiveBoxIcon,
  BoltIcon,
} from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'

import { Button, Badge } from '@/components/ui'
import { cn } from '@/utils/cn'
import { toolGroupsApi, poolApi } from '@/services/marketplace'

interface ToolboxEditModalProps {
  toolboxId: string | null
  isOpen: boolean
  onClose: () => void
}

const COLOR_OPTIONS = ['orange', 'blue', 'green', 'purple', 'red', 'gray']

export function ToolboxEditModal({ toolboxId, isOpen, onClose }: ToolboxEditModalProps) {
  const { t } = useTranslation('dashboard')
  const queryClient = useQueryClient()

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [color, setColor] = useState<string>('orange')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // All hooks must run on every render — keep early-return at the bottom.
  const groupQuery = useQuery({
    queryKey: ['tool-group', toolboxId],
    queryFn: () => toolGroupsApi.get(toolboxId as string),
    enabled: !!toolboxId && isOpen,
  })

  useEffect(() => {
    if (groupQuery.data) {
      setName(groupQuery.data.name)
      setDescription(groupQuery.data.description ?? '')
      setColor(groupQuery.data.color ?? 'orange')
    }
  }, [groupQuery.data])

  const saveMetadataMutation = useMutation({
    mutationFn: () =>
      toolGroupsApi.update(toolboxId as string, {
        name: name.trim(),
        description: description.trim() || undefined,
        color: color || 'orange',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tool-groups'] })
      queryClient.invalidateQueries({ queryKey: ['tool-group', toolboxId] })
      toast.success(
        t('workspace.toolboxEdit.savedToast', {
          defaultValue: 'Toolbox updated.',
        }) as string,
      )
    },
    onError: (e: any) =>
      setErrorMsg(e.response?.data?.detail || e.message || 'Failed to update'),
  })

  const removeItemMutation = useMutation({
    mutationFn: (itemId: string) =>
      toolGroupsApi.removeItem(toolboxId as string, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tool-groups'] })
      queryClient.invalidateQueries({ queryKey: ['tool-group', toolboxId] })
    },
    onError: (e: any) =>
      setErrorMsg(e.response?.data?.detail || e.message || 'Failed to remove'),
  })

  const loadIntoPoolMutation = useMutation({
    mutationFn: () => poolApi.loadToolbox(toolboxId as string),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['workspace-tools'] })
      queryClient.invalidateQueries({ queryKey: ['pool-state'] })
      toast.success(
        t('workspace.toolboxEdit.loadedToast', {
          count: data.loaded_count,
          defaultValue: '{{count}} tools loaded into the pool.',
        }) as string,
      )
    },
    onError: (e: any) =>
      setErrorMsg(e.response?.data?.detail || e.message || 'Failed to load'),
  })

  const deleteMutation = useMutation({
    mutationFn: () => toolGroupsApi.delete(toolboxId as string),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tool-groups'] })
      toast.success(
        t('workspace.toolboxEdit.deletedToast', {
          defaultValue: 'Toolbox deleted.',
        }) as string,
      )
      onClose()
    },
    onError: (e: any) =>
      setErrorMsg(e.response?.data?.detail || e.message || 'Failed to delete'),
  })

  if (!isOpen || !toolboxId) return null

  const group = groupQuery.data
  const items = group?.items ?? []
  const dirty =
    !!group &&
    (name.trim() !== (group.name ?? '') ||
      description.trim() !== (group.description ?? '') ||
      (color || 'orange') !== (group.color ?? 'orange'))

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] flex flex-col">
        <div className="p-6 border-b border-gray-200 flex-shrink-0 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              <ArchiveBoxIcon
                className="w-5 h-5"
                style={{ color: pillColor(color) }}
              />
              {t('workspace.toolboxEdit.title', { defaultValue: 'Edit toolbox' })}
            </h2>
            <p className="text-sm text-gray-600 mt-1">
              {t('workspace.toolboxEdit.hint', {
                defaultValue:
                  'Rename, recolor, prune the items, or delete this toolbox entirely.',
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

        {errorMsg && (
          <div className="px-6 pt-4">
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-md p-3">
              {errorMsg}
            </div>
          </div>
        )}

        <div className="p-6 overflow-y-auto flex-1 space-y-5">
          {groupQuery.isLoading || !group ? (
            <div className="text-sm text-gray-500 text-center py-6">…</div>
          ) : (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="sm:col-span-2 space-y-1">
                  <label className="block text-xs font-semibold text-gray-700">
                    {t('workspace.toolboxEdit.name', { defaultValue: 'Name' })}
                  </label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full p-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-orange focus:border-transparent"
                  />
                </div>
                <div className="space-y-1">
                  <label className="block text-xs font-semibold text-gray-700">
                    {t('workspace.toolboxEdit.color', { defaultValue: 'Color' })}
                  </label>
                  <div className="flex flex-wrap gap-1">
                    {COLOR_OPTIONS.map((c) => (
                      <button
                        type="button"
                        key={c}
                        onClick={() => setColor(c)}
                        className={cn(
                          'w-6 h-6 rounded-full border-2 transition',
                          color === c
                            ? 'border-gray-900 scale-110'
                            : 'border-transparent hover:border-gray-300',
                        )}
                        style={{ backgroundColor: pillColor(c) }}
                        aria-label={c}
                      />
                    ))}
                  </div>
                </div>
              </div>

              <div className="space-y-1">
                <label className="block text-xs font-semibold text-gray-700">
                  {t('workspace.toolboxEdit.description', {
                    defaultValue: 'Description',
                  })}
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={2}
                  className="w-full p-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-orange focus:border-transparent"
                />
              </div>

              <div>
                <div className="flex items-baseline justify-between mb-2">
                  <span className="text-xs font-semibold text-gray-700">
                    {t('workspace.toolboxEdit.itemsHeader', {
                      defaultValue: 'Tools in this toolbox',
                    })}{' '}
                    <span className="text-gray-500">({items.length})</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => loadIntoPoolMutation.mutate()}
                    disabled={loadIntoPoolMutation.isPending || items.length === 0}
                    className="text-xs text-orange hover:text-orange-dark disabled:opacity-50 inline-flex items-center gap-1"
                  >
                    <BoltIcon className="w-3.5 h-3.5" />
                    {t('workspace.toolboxEdit.loadIntoPool', {
                      defaultValue: 'Load all into pool',
                    })}
                  </button>
                </div>
                {items.length === 0 ? (
                  <div className="text-sm text-gray-500 italic">
                    {t('workspace.toolboxEdit.empty', {
                      defaultValue: 'This toolbox is empty.',
                    })}
                  </div>
                ) : (
                  <ul className="space-y-1.5 max-h-72 overflow-y-auto">
                    {items.map((it: any) => (
                      <li
                        key={it.id}
                        className="flex items-start justify-between gap-2 p-2 rounded-md border border-gray-200 bg-white"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="text-sm font-medium text-gray-900 truncate">
                              {it.tool_name || it.name || '—'}
                            </span>
                            {it.server_name && (
                              <Badge variant="default">{it.server_name}</Badge>
                            )}
                          </div>
                          {it.tool_description && (
                            <div className="text-xs text-gray-600 mt-0.5 line-clamp-2">
                              {it.tool_description}
                            </div>
                          )}
                        </div>
                        <button
                          type="button"
                          onClick={() => removeItemMutation.mutate(it.id)}
                          disabled={removeItemMutation.isPending}
                          className="text-gray-400 hover:text-red-600 flex-shrink-0"
                          title={
                            t('workspace.toolboxEdit.removeItem', {
                              defaultValue: 'Remove from this toolbox',
                            }) as string
                          }
                        >
                          <XMarkIcon className="w-4 h-4" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          )}
        </div>

        <div className="p-6 border-t border-gray-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 flex-shrink-0">
          <Button
            variant="ghost"
            onClick={() => {
              if (
                window.confirm(
                  t('workspace.toolboxEdit.deleteConfirm', {
                    defaultValue:
                      'Delete this toolbox? Tools themselves are kept.',
                  }) as string,
                )
              ) {
                deleteMutation.mutate()
              }
            }}
            disabled={deleteMutation.isPending}
            className="text-red-600 hover:text-red-700"
          >
            <TrashIcon className="w-4 h-4 mr-1" />
            {t('workspace.toolboxEdit.delete', {
              defaultValue: 'Delete toolbox',
            })}
          </Button>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onClose}>
              {t('workspace.toolboxEdit.close', { defaultValue: 'Close' })}
            </Button>
            <Button
              variant="primary"
              onClick={() => saveMetadataMutation.mutate()}
              disabled={
                !dirty ||
                saveMetadataMutation.isPending ||
                name.trim().length === 0
              }
            >
              {t('workspace.toolboxEdit.save', { defaultValue: 'Save' })}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

function pillColor(c: string): string {
  switch (c) {
    case 'orange':
      return '#f97316'
    case 'blue':
      return '#3b82f6'
    case 'green':
      return '#22c55e'
    case 'purple':
      return '#8b5cf6'
    case 'red':
      return '#ef4444'
    case 'gray':
    default:
      return '#9ca3af'
  }
}
