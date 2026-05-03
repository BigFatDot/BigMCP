/**
 * AssistantModal — LLM-first toolbox builder.
 *
 * Flow:
 *   1. User describes a persona / intent / recurring task in natural language.
 *   2. "Propose" → backend scores the org catalog and the LLM picks 3-15 tools
 *      with a name + description for the toolbox, optionally suggesting a
 *      multi-step composition.
 *   3. User reviews the draft (rename, edit description, uncheck tools, etc.),
 *      then either "Create toolbox" (saves a ToolGroup) or "Create + load
 *      into pool" (saves and pushes every tool into the active pool).
 *   4. If a composition is suggested, a one-click hop to the Compositions
 *      page pre-fills the propose modal there.
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { SparklesIcon, ArchiveBoxIcon, XMarkIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'

import { Button, Badge } from '@/components/ui'
import { cn } from '@/utils/cn'
import { poolApi, toolGroupsApi } from '@/services/marketplace'

interface ProposedTool {
  tool_id: string
  name: string
  server: string | null
  rationale?: string | null
}

interface ProposedCompositionSuggestion {
  name: string
  description: string
  rationale?: string | null
}

interface ProposedToolbox {
  name: string
  description: string
  color: string | null
  intent: string
  tools: ProposedTool[]
  candidate_count: number
  composition_suggestion: ProposedCompositionSuggestion | null
  note?: string | null
}

interface AssistantModalProps {
  isOpen: boolean
  onClose: () => void
  onLoaded?: () => void
}

const COLOR_OPTIONS = ['orange', 'blue', 'green', 'purple', 'red', 'gray']

export function AssistantModal({ isOpen, onClose, onLoaded }: AssistantModalProps) {
  const { t } = useTranslation('dashboard')
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const [intent, setIntent] = useState('')
  const [draft, setDraft] = useState<ProposedToolbox | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [color, setColor] = useState('orange')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [isProposing, setIsProposing] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Hooks must run on every render — keep early-return AFTER all hooks.
  const createMutation = useMutation({
    mutationFn: async ({ alsoLoad }: { alsoLoad: boolean }) => {
      const group = await toolGroupsApi.create({
        name: name.trim() || (draft?.name ?? 'Toolbox'),
        description: description.trim() || undefined,
        color: color || 'orange',
        visibility: 'private',
      })
      const toolIds = Array.from(selectedIds)
      // Sequential to keep order stable; the API doesn't expose bulk-add.
      for (let i = 0; i < toolIds.length; i++) {
        await toolGroupsApi.addTool(group.id, toolIds[i], i)
      }
      if (alsoLoad && toolIds.length > 0) {
        await poolApi.load(toolIds, 'append')
      }
      return { groupId: group.id, count: toolIds.length, alsoLoaded: alsoLoad }
    },
    onSuccess: ({ count, alsoLoaded }) => {
      queryClient.invalidateQueries({ queryKey: ['tool-groups'] })
      queryClient.invalidateQueries({ queryKey: ['workspace-tools'] })
      queryClient.invalidateQueries({ queryKey: ['pool-state'] })
      if (alsoLoaded) {
        toast.success(
          t('workspace.assistant.toolboxCreatedAndLoaded', {
            count,
            defaultValue: 'Toolbox created and {{count}} tools loaded into the pool.',
          }) as string,
        )
        onLoaded?.()
      } else {
        toast.success(
          t('workspace.assistant.toolboxCreated', {
            defaultValue: 'Toolbox created.',
          }) as string,
        )
      }
      reset()
      onClose()
    },
    onError: (e: any) =>
      setErrorMsg(e.response?.data?.detail || e.message || 'Failed to create toolbox'),
  })

  function reset() {
    setIntent('')
    setDraft(null)
    setName('')
    setDescription('')
    setColor('orange')
    setSelectedIds(new Set())
    setIsProposing(false)
    setErrorMsg(null)
  }

  if (!isOpen) return null

  const askLLM = async () => {
    setIsProposing(true)
    setErrorMsg(null)
    try {
      const data = (await toolGroupsApi.propose(intent)) as ProposedToolbox
      setDraft(data)
      setName(data.name)
      setDescription(data.description)
      setColor(data.color || 'orange')
      setSelectedIds(new Set(data.tools.map((t) => t.tool_id)))
    } catch (e: any) {
      setErrorMsg(e.response?.data?.detail || e.message || 'Failed to propose')
    } finally {
      setIsProposing(false)
    }
  }

  const toggle = (id: string) => {
    const next = new Set(selectedIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedIds(next)
  }

  const goCompose = () => {
    if (!draft?.composition_suggestion) return
    // Pre-seed the Compositions page with the suggested intent. The propose
    // modal there reads the `compose` query param if present.
    const seed = encodeURIComponent(
      [
        draft.composition_suggestion.description,
        draft.composition_suggestion.rationale,
      ]
        .filter(Boolean)
        .join('\n\n') || draft.intent,
    )
    onClose()
    navigate(`/app/compositions?compose=${seed}`)
  }

  const canCreate = !!draft && name.trim().length > 0 && selectedIds.size > 0

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-3xl w-full mx-4 max-h-[90vh] flex flex-col">
        <div className="p-6 border-b border-gray-200 flex-shrink-0 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              <SparklesIcon className="w-5 h-5 text-orange" />
              {t('workspace.assistant.toolboxTitle', {
                defaultValue: 'Build a toolbox by intent',
              })}
            </h2>
            <p className="text-sm text-gray-600 mt-1">
              {t('workspace.assistant.toolboxHint', {
                defaultValue:
                  'Describe a persona, a recurring task, or the kind of help you want. The assistant scores your enabled tools and proposes a ready-to-save toolbox.',
              })}
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              reset()
              onClose()
            }}
            className="text-gray-400 hover:text-gray-600 flex-shrink-0"
          >
            <XMarkIcon className="w-6 h-6" />
          </button>
        </div>

        <div className="p-6 overflow-y-auto flex-1 space-y-5">
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              {t('workspace.assistant.intentLabel', { defaultValue: 'Intent / persona' })}
            </label>
            <textarea
              value={intent}
              onChange={(e) => setIntent(e.target.value)}
              rows={3}
              className="w-full p-3 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-orange focus:border-transparent"
              placeholder={
                t('workspace.assistant.intentPlaceholder', {
                  defaultValue:
                    'e.g. DevOps assistant for managing my Hostinger DNS, VPS and billing',
                }) as string
              }
            />
          </div>

          {draft && (
            <div className="border border-gray-200 rounded-xl p-4 space-y-4 bg-gray-50/40">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="sm:col-span-2 space-y-1">
                  <label className="block text-xs font-semibold text-gray-700">
                    {t('workspace.assistant.toolboxName', { defaultValue: 'Toolbox name' })}
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
                    {t('workspace.assistant.toolboxColor', { defaultValue: 'Color' })}
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
                  {t('workspace.assistant.toolboxDescription', {
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
                    {t('workspace.assistant.toolsHeader', {
                      defaultValue: 'Selected tools',
                    })}{' '}
                    <span className="text-gray-500">
                      ({selectedIds.size}/{draft.tools.length})
                    </span>
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      if (selectedIds.size === draft.tools.length) {
                        setSelectedIds(new Set())
                      } else {
                        setSelectedIds(new Set(draft.tools.map((t) => t.tool_id)))
                      }
                    }}
                    className="text-xs text-orange hover:text-orange-dark"
                  >
                    {selectedIds.size === draft.tools.length
                      ? t('workspace.assistant.deselectAll', { defaultValue: 'Deselect all' })
                      : t('workspace.assistant.selectAll', { defaultValue: 'Select all' })}
                  </button>
                </div>
                {draft.tools.length === 0 ? (
                  <div className="text-sm text-gray-500 italic">
                    {draft.note ||
                      t('workspace.assistant.noPick', {
                        defaultValue:
                          'The LLM did not select any tool. Try a more specific intent.',
                      })}
                  </div>
                ) : (
                  <ul className="space-y-1.5 max-h-72 overflow-y-auto">
                    {draft.tools.map((tool) => {
                      const checked = selectedIds.has(tool.tool_id)
                      return (
                        <li
                          key={tool.tool_id}
                          onClick={() => toggle(tool.tool_id)}
                          className={cn(
                            'flex items-start gap-2 p-2 rounded-md cursor-pointer border transition',
                            checked
                              ? 'border-orange bg-orange/5'
                              : 'border-gray-200 hover:border-gray-300 bg-white',
                          )}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggle(tool.tool_id)}
                            onClick={(e) => e.stopPropagation()}
                            className="mt-1 accent-orange"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <span className="text-sm font-medium text-gray-900 truncate">
                                {tool.name}
                              </span>
                              {tool.server && (
                                <Badge variant="default">{tool.server}</Badge>
                              )}
                            </div>
                            {tool.rationale && (
                              <div className="text-xs text-gray-600 mt-0.5">
                                {tool.rationale}
                              </div>
                            )}
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                )}
              </div>

              {draft.composition_suggestion && (
                <div className="rounded-md border border-orange/30 bg-orange/5 p-3 text-sm">
                  <div className="flex items-center gap-2 mb-1">
                    <SparklesIcon className="w-4 h-4 text-orange" />
                    <span className="font-semibold text-gray-900">
                      {t('workspace.assistant.compositionSuggestionTitle', {
                        defaultValue: 'Suggested composition',
                      })}
                      : {draft.composition_suggestion.name}
                    </span>
                  </div>
                  <p className="text-gray-700">{draft.composition_suggestion.description}</p>
                  {draft.composition_suggestion.rationale && (
                    <p className="text-xs text-gray-500 mt-1">
                      {draft.composition_suggestion.rationale}
                    </p>
                  )}
                  <button
                    type="button"
                    onClick={goCompose}
                    className="mt-2 text-xs font-medium text-orange hover:text-orange-dark"
                  >
                    {t('workspace.assistant.compose', {
                      defaultValue: 'Open the composition builder →',
                    })}
                  </button>
                </div>
              )}
            </div>
          )}

          {errorMsg && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-md p-3">
              {errorMsg}
            </div>
          )}
        </div>

        <div className="p-6 border-t border-gray-200 flex flex-col sm:flex-row sm:justify-end gap-2 flex-shrink-0">
          <Button
            variant="secondary"
            onClick={() => {
              reset()
              onClose()
            }}
            disabled={isProposing || createMutation.isPending}
          >
            {t('workspace.assistant.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            variant="secondary"
            onClick={askLLM}
            disabled={isProposing || createMutation.isPending || intent.trim().length < 4}
          >
            {isProposing
              ? t('workspace.assistant.thinking', { defaultValue: 'Thinking…' })
              : draft
                ? t('workspace.assistant.regenerate', { defaultValue: 'Regenerate' })
                : t('workspace.assistant.propose', { defaultValue: 'Propose' })}
          </Button>
          {draft && (
            <>
              <Button
                variant="secondary"
                onClick={() => createMutation.mutate({ alsoLoad: false })}
                disabled={!canCreate || createMutation.isPending}
              >
                <ArchiveBoxIcon className="w-4 h-4 mr-1" />
                {t('workspace.assistant.createToolbox', {
                  defaultValue: 'Create toolbox',
                })}
              </Button>
              <Button
                variant="primary"
                onClick={() => createMutation.mutate({ alsoLoad: true })}
                disabled={!canCreate || createMutation.isPending}
              >
                <ArchiveBoxIcon className="w-4 h-4 mr-1" />
                {t('workspace.assistant.createAndLoad', {
                  defaultValue: 'Create + load into pool',
                })}
              </Button>
            </>
          )}
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
