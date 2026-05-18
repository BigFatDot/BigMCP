/**
 * Pin suggestions banner (Phase 5).
 *
 * Surfaces up to 3 tools/compositions the user has been calling
 * frequently but hasn't pinned yet. One-click pin promotes the entry
 * to the user's persistent pool so it survives across sessions and
 * is exposed to MCP clients without needing a `search` call.
 *
 * The banner stays out of the way: hidden when there are no
 * suggestions, dismissible per session via a small × button (state
 * persisted in sessionStorage).
 */

import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  BookmarkIcon,
  XMarkIcon,
  SparklesIcon,
  WrenchScrewdriverIcon,
} from '@heroicons/react/24/outline'
import { userPinApi, type PinSuggestion } from '@/services/persistentPool'

const DISMISS_KEY = 'bigmcp_pin_suggestions_dismissed'
const SKIPPED_KEY = 'bigmcp_pin_suggestions_skipped'

function readSkipped(): Set<string> {
  try {
    const raw = sessionStorage.getItem(SKIPPED_KEY)
    if (!raw) return new Set()
    return new Set(JSON.parse(raw))
  } catch {
    return new Set()
  }
}

function writeSkipped(s: Set<string>): void {
  try {
    sessionStorage.setItem(SKIPPED_KEY, JSON.stringify(Array.from(s)))
  } catch {
    /* sessionStorage unavailable */
  }
}

function suggestionKey(s: PinSuggestion): string {
  return `${s.kind}:${s.tool_id || s.composition_id || s.name}`
}

export function PinSuggestionsBanner() {
  const queryClient = useQueryClient()
  const [dismissed, setDismissed] = useState<boolean>(() => {
    try {
      return sessionStorage.getItem(DISMISS_KEY) === '1'
    } catch {
      return false
    }
  })
  const [skipped, setSkipped] = useState<Set<string>>(() => readSkipped())

  const suggestionsQuery = useQuery({
    queryKey: ['pin-suggestions'],
    queryFn: () => userPinApi.suggestions({ days: 7, limit: 5, min_count: 3 }),
    refetchInterval: 60_000,
    enabled: !dismissed,
  })

  const pinMutation = useMutation({
    mutationFn: async (s: PinSuggestion) => {
      if (s.kind === 'tool' && s.tool_id) {
        await userPinApi.pin({ tool_id: s.tool_id })
      } else if (s.kind === 'composition' && s.composition_id) {
        await userPinApi.pin({ composition_id: s.composition_id })
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-pins'] })
      queryClient.invalidateQueries({ queryKey: ['pin-suggestions'] })
    },
  })

  const dismiss = () => {
    setDismissed(true)
    try {
      sessionStorage.setItem(DISMISS_KEY, '1')
    } catch {
      /* sessionStorage unavailable — degrade silently */
    }
  }

  const top = useMemo(
    () =>
      (suggestionsQuery.data?.suggestions ?? [])
        .filter((s) => !skipped.has(suggestionKey(s)))
        .slice(0, 3),
    [suggestionsQuery.data, skipped],
  )

  const skipOne = (s: PinSuggestion) => {
    setSkipped((prev) => {
      const next = new Set(prev)
      next.add(suggestionKey(s))
      writeSkipped(next)
      return next
    })
  }

  if (dismissed) return null
  if (top.length === 0) return null

  return (
    <div className="mb-4 rounded-lg border border-orange/30 bg-orange/5 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <BookmarkIcon className="h-4 w-4 text-orange flex-shrink-0" />
            <span className="text-sm font-semibold text-gray-900">
              You use these often — pin them to make them stick across sessions
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            {top.map((s) => {
              const Icon =
                s.kind === 'composition' ? SparklesIcon : WrenchScrewdriverIcon
              return (
                <span
                  key={suggestionKey(s)}
                  className="group inline-flex items-stretch rounded-md border border-orange/40 bg-white text-xs hover:border-orange transition-colors"
                >
                  <button
                    type="button"
                    disabled={pinMutation.isPending}
                    onClick={() => pinMutation.mutate(s)}
                    className="flex items-center gap-1.5 px-2 py-1 hover:bg-orange/10 rounded-l-md transition-colors disabled:opacity-50"
                    title={`Used ${s.count}× in the last ${s.days} days — click to pin`}
                  >
                    <Icon
                      className={
                        s.kind === 'composition'
                          ? 'h-3.5 w-3.5 text-orange'
                          : 'h-3.5 w-3.5 text-gray-500'
                      }
                    />
                    <span className="font-medium text-gray-900 truncate max-w-[180px]">
                      {s.name}
                    </span>
                    {s.server_name && (
                      <span className="text-gray-400 truncate max-w-[100px]">
                        · {s.server_name}
                      </span>
                    )}
                    <span className="text-gray-500">({s.count}×)</span>
                    <BookmarkIcon className="h-3 w-3 text-orange opacity-0 group-hover:opacity-100 transition-opacity" />
                  </button>
                  <button
                    type="button"
                    onClick={() => skipOne(s)}
                    title="Don't suggest this one again this session"
                    className="px-1.5 border-l border-orange/30 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-r-md opacity-0 group-hover:opacity-100 transition-opacity"
                    aria-label={`Skip suggestion ${s.name}`}
                  >
                    <XMarkIcon className="h-3 w-3" />
                  </button>
                </span>
              )
            })}
          </div>
        </div>
        <button
          type="button"
          onClick={dismiss}
          title="Dismiss for this session"
          className="text-gray-400 hover:text-gray-700 p-1"
        >
          <XMarkIcon className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
