/**
 * AssistantModal — one-shot LLM helper for the Services workspace.
 *
 * Flow:
 *   1. User describes a goal in natural language.
 *   2. Hit "Suggest" → backend scores enabled tools (poolApi.suggest) and
 *      returns the top N candidates with their in-pool flag.
 *   3. User reviews/unchecks suggestions, then "Load selected" to bulk-add
 *      to the pool. Optionally jumps to the Composed-Tools page to draft a
 *      composition from the same prompt.
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { SparklesIcon, BoltIcon, XMarkIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'

import { Button, Badge } from '@/components/ui'
import { cn } from '@/utils/cn'
import { poolApi } from '@/services/marketplace'

interface Suggestion {
  tool_id: string
  name: string
  server: string | null
  description: string
  score: number
  in_pool: boolean
}

interface AssistantModalProps {
  isOpen: boolean
  onClose: () => void
  onLoaded?: () => void
}

export function AssistantModal({ isOpen, onClose, onLoaded }: AssistantModalProps) {
  const { t } = useTranslation('dashboard')
  const queryClient = useQueryClient()
  const [goal, setGoal] = useState('')
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [note, setNote] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const reset = () => {
    setGoal('')
    setSuggestions(null)
    setSelectedIds(new Set())
    setNote(null)
    setIsLoading(false)
    setErrorMsg(null)
  }

  if (!isOpen) return null

  const askLLM = async () => {
    setIsLoading(true)
    setErrorMsg(null)
    try {
      const data = await poolApi.suggest(goal, 10)
      setSuggestions(data.suggestions)
      // Pre-select every match that is not already in the pool — the most
      // useful default action.
      setSelectedIds(
        new Set(data.suggestions.filter((s) => !s.in_pool).map((s) => s.tool_id)),
      )
      setNote(data.note ?? null)
    } catch (e: any) {
      setErrorMsg(e.response?.data?.detail || e.message || 'Failed')
    } finally {
      setIsLoading(false)
    }
  }

  const loadMutation = useMutation({
    mutationFn: (ids: string[]) => poolApi.load(ids, 'append'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspace-tools'] })
      queryClient.invalidateQueries({ queryKey: ['pool-state'] })
      toast.success(
        t('workspace.assistant.loadedToast', { defaultValue: 'Loaded into your pool.' }),
      )
      onLoaded?.()
      reset()
      onClose()
    },
    onError: (e: any) => setErrorMsg(e.response?.data?.detail || 'Load failed'),
  })

  const toggle = (id: string) => {
    const next = new Set(selectedIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedIds(next)
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] flex flex-col">
        <div className="p-6 border-b border-gray-200 flex-shrink-0 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              <SparklesIcon className="w-5 h-5 text-orange" />
              {t('workspace.assistant.title', { defaultValue: 'Suggest tools for a goal' })}
            </h2>
            <p className="text-sm text-gray-600 mt-1">
              {t('workspace.assistant.hint', {
                defaultValue:
                  'Describe what you want to do. The assistant looks across every connected server and proposes tools — load the relevant ones into your pool with one click.',
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

        <div className="p-6 overflow-y-auto flex-1 space-y-4">
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              {t('workspace.assistant.goalLabel', { defaultValue: 'Your goal' })}
            </label>
            <textarea
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              rows={3}
              className="w-full p-3 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-orange focus:border-transparent"
              placeholder={
                t('workspace.assistant.goalPlaceholder', {
                  defaultValue: 'e.g. Manage my Hostinger DNS records and notify a Slack channel',
                }) as string
              }
            />
          </div>

          {suggestions && suggestions.length > 0 && (
            <div className="border border-gray-200 rounded-lg p-3 bg-gray-50">
              <div className="flex items-baseline justify-between mb-2">
                <h3 className="text-sm font-semibold text-gray-900">
                  {t('workspace.assistant.suggestionsHeader', {
                    defaultValue: 'Suggestions ({{count}})',
                    count: suggestions.length,
                  })}
                </h3>
                <button
                  type="button"
                  onClick={() =>
                    setSelectedIds(
                      selectedIds.size === suggestions.length
                        ? new Set()
                        : new Set(suggestions.map((s) => s.tool_id)),
                    )
                  }
                  className="text-xs text-orange hover:underline"
                >
                  {selectedIds.size === suggestions.length
                    ? t('workspace.assistant.deselectAll', { defaultValue: 'Deselect all' })
                    : t('workspace.assistant.selectAll', { defaultValue: 'Select all' })}
                </button>
              </div>
              <div className="space-y-1.5">
                {suggestions.map((s) => (
                  <label
                    key={s.tool_id}
                    className={cn(
                      'flex items-start gap-2 p-2 rounded border cursor-pointer transition',
                      selectedIds.has(s.tool_id)
                        ? 'border-orange bg-orange/5'
                        : 'border-gray-200 bg-white hover:border-gray-300',
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={selectedIds.has(s.tool_id)}
                      onChange={() => toggle(s.tool_id)}
                      className="mt-1 accent-orange"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-gray-900 truncate">
                          {s.name}
                        </span>
                        {s.in_pool && (
                          <Badge variant="default" className="text-[10px]">
                            {t('workspace.assistant.alreadyInPool', { defaultValue: 'in pool' })}
                          </Badge>
                        )}
                      </div>
                      {s.server && (
                        <div className="text-xs text-gray-500">{s.server}</div>
                      )}
                      {s.description && (
                        <div className="text-xs text-gray-600 mt-1 line-clamp-2">
                          {s.description}
                        </div>
                      )}
                    </div>
                  </label>
                ))}
              </div>
            </div>
          )}

          {note && (
            <div className="text-xs text-gray-500 italic">{note}</div>
          )}

          {errorMsg && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">
              {errorMsg}
            </div>
          )}

          {goal.trim().length >= 4 && (
            <div className="text-xs text-gray-500 border-t border-gray-100 pt-3">
              {t('workspace.assistant.alsoCompose', {
                defaultValue: 'Want a single saved tool that runs the whole sequence?',
              })}{' '}
              <Link
                to={`/app/compositions?propose=${encodeURIComponent(goal)}`}
                className="text-orange hover:underline"
              >
                {t('workspace.assistant.gotoCompose', { defaultValue: 'Compose it →' })}
              </Link>
            </div>
          )}
        </div>

        <div className="p-6 border-t border-gray-200 flex justify-end gap-2 flex-shrink-0">
          <Button
            variant="secondary"
            onClick={() => {
              reset()
              onClose()
            }}
            disabled={isLoading || loadMutation.isPending}
          >
            {t('compositions.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            variant="secondary"
            onClick={askLLM}
            disabled={isLoading || goal.trim().length < 4}
          >
            <SparklesIcon className="w-4 h-4 mr-1.5" />
            {isLoading
              ? t('workspace.assistant.searching', { defaultValue: 'Searching…' })
              : suggestions
                ? t('workspace.assistant.refresh', { defaultValue: 'Refresh' })
                : t('workspace.assistant.suggest', { defaultValue: 'Suggest' })}
          </Button>
          {suggestions && suggestions.length > 0 && (
            <Button
              variant="primary"
              onClick={() => loadMutation.mutate(Array.from(selectedIds))}
              disabled={selectedIds.size === 0 || loadMutation.isPending}
            >
              <BoltIcon className="w-4 h-4 mr-1.5" />
              {t('workspace.assistant.loadSelection', {
                defaultValue: 'Load selected ({{count}})',
                count: selectedIds.size,
              })}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
