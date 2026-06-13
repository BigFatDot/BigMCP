/**
 * SubcompositionStepForm — StepForm for the `subcomposition` durable step type (B-1.3).
 *
 * The composition author picks ANOTHER composition (status `production`,
 * same org context) and optionally provides an `inputs` map that will
 * satisfy the target's `input_schema`. The parent suspends with
 * `reason="subcomposition"` until the child reaches a terminal state;
 * backend handles the resume + result propagation (see
 * `app/orchestration/subcomposition_step.py`).
 *
 * Backend contract (validate_config):
 *   - `composition_id`: UUID (non-empty string). Production-status +
 *     same-org checks happen server-side at promote + dispatch time, so
 *     the form just needs to enforce "is a real UUID we know about".
 *   - `inputs?`: dict that satisfies the target's `input_schema`. Free
 *     JSON textarea here — the input_schema visual editor is out of
 *     scope for B-1 (matches the existing inputSchema pattern in
 *     CompositionBuilder).
 *
 * Pattern follows `WaitUntilStepForm` + `WaitCallbackStepForm` post the
 * adversarial review:
 *   - Local raw-string state for the JSON textarea (mid-edit invalid
 *     JSON doesn't clobber the parent or lose keystrokes).
 *   - `onChange` is silent — no toast/nav. Errors surface inline.
 *   - External hydration via fingerprint compare (no feedback loops).
 *
 * The list of production compositions is fetched once at mount with
 * `useQuery` (cached at the react-query layer, same pattern as
 * `ToolsWorkspace`/`DefaultPoolPage`). If the user creates a new
 * production composition AFTER this form mounted, they need to close +
 * reopen the picker — auto-refresh is out of scope here.
 */

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Alert, EmptyState, Spinner } from '@/components/ui'
import { compositionsApi } from '@/services/marketplace'
import type { Composition } from '@/services/marketplace'
import type { StepFormProps, SubcompositionConfig } from '../types'

/** Parse the raw JSON string for `inputs`. Returns the parsed object
 *  if it's a plain object, or an error tag. Arrays / scalars are
 *  rejected because validate_config requires a dict (object) when
 *  present. Empty string is reported as "intentionally unset". */
function parseInputsJson(
  raw: string,
):
  | { ok: true; value: Record<string, unknown> | undefined }
  | { ok: false; error: 'parse' | 'not-object' } {
  const trimmed = raw.trim()
  if (trimmed === '') {
    return { ok: true, value: undefined }
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch {
    return { ok: false, error: 'parse' }
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { ok: false, error: 'not-object' }
  }
  return { ok: true, value: parsed as Record<string, unknown> }
}

export function SubcompositionStepForm({
  value,
  onChange,
  disabled,
}: StepFormProps<SubcompositionConfig>) {
  const { t } = useTranslation('compositions')
  const navigate = useNavigate()

  // Lazy-load production compositions. react-query cache key is shared
  // org-wide; the small select doesn't justify pagination yet.
  const prodQuery = useQuery({
    queryKey: ['builder', 'subcomposition', 'productions'],
    queryFn: () => compositionsApi.list({ status: 'production' }),
  })

  // Local raw-string state for the inputs JSON textarea — same pattern
  // as ElicitStepForm.schemaJsonRaw / WaitCallbackStepForm.schemaJsonRaw.
  const [inputsJsonRaw, setInputsJsonRaw] = useState<string>(() =>
    value.inputs === undefined || value.inputs === null
      ? ''
      : JSON.stringify(value.inputs, null, 2),
  )
  const [inputsJsonError, setInputsJsonError] = useState<string | null>(null)

  // External hydration only (parent reset or edit-existing). Detect via
  // a canonical-JSON fingerprint to avoid feedback loops with our own
  // emits. Including `inputsJsonRaw` in deps would fight keystrokes.
  useEffect(() => {
    const incoming =
      value.inputs === undefined || value.inputs === null
        ? ''
        : JSON.stringify(value.inputs)
    const current = (() => {
      const parsed = parseInputsJson(inputsJsonRaw)
      if (!parsed.ok) return null
      return parsed.value === undefined ? '' : JSON.stringify(parsed.value)
    })()
    if (current !== incoming) {
      setInputsJsonRaw(
        value.inputs === undefined || value.inputs === null
          ? ''
          : JSON.stringify(value.inputs, null, 2),
      )
      setInputsJsonError(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value.inputs])

  const emit = (patch: Partial<SubcompositionConfig>) => {
    onChange({
      composition_id: value.composition_id,
      inputs: value.inputs,
      ...patch,
    })
  }

  const handleInputsChange = (raw: string) => {
    setInputsJsonRaw(raw)
    const parsed = parseInputsJson(raw)
    if (parsed.ok) {
      setInputsJsonError(null)
      emit({ inputs: parsed.value })
    } else {
      setInputsJsonError(t('builder.subcomposition.inputsJsonError') as string)
    }
  }

  // ---- Productions list states -------------------------------------------

  if (prodQuery.isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-600">
        <Spinner size="sm" />
        <span>{t('builder.subcomposition.loading')}</span>
      </div>
    )
  }

  if (prodQuery.isError) {
    const message =
      (prodQuery.error as { message?: string })?.message ||
      (t('builder.subcomposition.fetchError') as string)
    return (
      <Alert variant="warning" title={t('builder.subcomposition.fetchError') as string}>
        {message}
      </Alert>
    )
  }

  const productions: Composition[] = prodQuery.data?.compositions ?? []

  if (productions.length === 0) {
    return (
      <EmptyState
        title={t('builder.subcomposition.emptyTitle')}
        description={t('builder.subcomposition.emptyMessage') as string}
        action={{
          label: t('builder.subcomposition.emptyAction') as string,
          onClick: () => navigate('/docs/guides/compositions'),
        }}
      />
    )
  }

  // ---- Render ------------------------------------------------------------

  return (
    <div className="space-y-4">
      {/* Target composition — native <select> styled to match Input. */}
      <div className="w-full">
        <label
          htmlFor="subcomposition-composition-id"
          className="block text-sm font-medium text-gray-700 mb-1.5"
        >
          {t('builder.subcomposition.compositionLabel')}
        </label>
        <select
          id="subcomposition-composition-id"
          value={value.composition_id || ''}
          onChange={(e) => emit({ composition_id: e.target.value })}
          disabled={disabled}
          className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white transition-all focus:ring-2 focus:ring-orange focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed"
        >
          <option value="" disabled>
            {t('builder.subcomposition.compositionPlaceholder')}
          </option>
          {productions.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} ({c.id.slice(0, 8)})
            </option>
          ))}
        </select>
        <p className="mt-1.5 text-sm text-gray-600">
          {t('builder.subcomposition.compositionHint')}
        </p>
      </div>

      {/* Inputs map — collapsed by default (most sub-compositions take
          their inputs via ${input.X} substitution, the field is opt-in). */}
      <details>
        <summary className="cursor-pointer text-sm font-medium text-gray-700">
          {t('builder.subcomposition.inputsSummary')}
        </summary>
        <p className="text-xs text-gray-500 mt-1 font-serif">
          {t('builder.subcomposition.inputsHint')}
        </p>
        <textarea
          value={inputsJsonRaw}
          onChange={(e) => handleInputsChange(e.target.value)}
          rows={8}
          spellCheck={false}
          disabled={disabled}
          placeholder={'{\n  "key": "${input.X}"\n}'}
          className="w-full mt-2 p-3 border border-gray-300 rounded-lg text-xs font-mono focus:ring-2 focus:ring-orange focus:border-transparent"
        />
        {inputsJsonError && (
          <p className="mt-1 text-xs text-red-700">{inputsJsonError}</p>
        )}
      </details>
    </div>
  )
}
