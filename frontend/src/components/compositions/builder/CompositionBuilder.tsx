/**
 * CompositionBuilder — visual builder root (Sprint 2.0 pilot).
 *
 * Wraps a `useReducer` state machine over `BuilderState` and exposes
 * the create/edit flow to the host modal. Pilot scope: header
 * (name/description), JSON input_schema, ordered step list with
 * `wait_until` as the only fully-typed form. Other durable step types
 * appear in the picker as "coming soon"; legacy steps from an existing
 * compo show a read-only viewer with an "Edit raw JSON" escape hatch.
 *
 * Wiring:
 *   - Save → `compositionsApi.update(initial.id, …)` if `initial` is
 *     passed, otherwise `compositionsApi.create(…)`. Always saves as
 *     `status: 'temporary'` / `visibility: 'private'`; promotion lives
 *     on the composition card.
 *   - Validation: client-thin (`validate.ts`) + backend authoritative
 *     (422 detail surfaced via `<Alert>`).
 *   - i18n: namespace `compositions`.
 */

import { useMemo, useReducer, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { PlusIcon } from '@heroicons/react/24/outline'
/* react-hot-toast removed — host (ProposeCompositionModal.onSaved)
 * owns the success toast so the message stays context-aware (draft
 * saved vs updated vs promoted). Errors surface inline via Alert. */
import { Alert, Button, Input } from '@/components/ui'
import {
  compositionsApi,
  type Composition,
} from '@/services/marketplace'
import { builderReducer, createInitialState } from './reducer'
import { serializeBuilderState } from './serialize'
import { validateBuilderState } from './validate'
import { STEP_TYPE_FORMS } from './registry'
import { StepCard } from './StepCard'
import { StepTypePicker } from './StepTypePicker'
import type { BuilderState, DurableStepType, StepDraft } from './types'

const DURABLE_TYPES: DurableStepType[] = [
  'elicit',
  'wait_until',
  'wait_callback',
  'subcomposition',
  'approval',
]

const LEGACY_TYPES = new Set(['tool', 'transform', 'foreach'])

interface CompositionBuilderProps {
  /** When provided, the builder hydrates from this compo and updates
   *  on save instead of creating. */
  initial?: Composition | null
  onSaved: (composition: Composition) => void
  onCancel: () => void
  /** Called when the user clicks "Edit raw JSON" on a legacy step or
   *  asks to bail to the Advanced JSON tab. The caller hosts the
   *  advanced editor (we don't render it ourselves). */
  onEditRawJson?: (prefilledJson: string) => void
}

/** Hydrate `BuilderState` from an existing Composition. Step types
 *  the builder doesn't (yet) know about are stored as legacy raw steps
 *  so they round-trip untouched. */
function hydrateFromComposition(composition: Composition): BuilderState {
  const steps: StepDraft[] = (composition.steps || []).map((s, idx) => {
    const stepId = s.step_id || s.id || `step_${idx + 1}`
    const type = (s.type || 'tool') as string
    if (type === 'wait_until') {
      const cfg = (s as unknown as { wait_until?: Record<string, unknown> })
        .wait_until || {}
      return {
        step_id: stepId,
        type: 'wait_until',
        wait_until: {
          wait_seconds:
            typeof cfg.wait_seconds === 'number'
              ? (cfg.wait_seconds as number)
              : null,
          resume_at:
            typeof cfg.resume_at === 'string' ? (cfg.resume_at as string) : null,
        },
      }
    }
    // Anything else we don't have a form for yet (durable or legacy)
    // is stored as a legacy raw step for safe round-trip. Once a form
    // ships in 2.1 it'll be parsed properly.
    if (
      LEGACY_TYPES.has(type) ||
      !DURABLE_TYPES.includes(type as DurableStepType) ||
      !STEP_TYPE_FORMS[type as DurableStepType]
    ) {
      return {
        step_id: stepId,
        type: (LEGACY_TYPES.has(type) ? type : 'tool') as
          | 'tool'
          | 'transform'
          | 'foreach',
        raw: s as unknown as Record<string, unknown>,
      }
    }
    // Defensive fallback — shouldn't reach (already handled wait_until above).
    return {
      step_id: stepId,
      type: 'tool',
      raw: s as unknown as Record<string, unknown>,
    }
  })

  return {
    compositionId: composition.id,
    name: composition.name,
    description: composition.description || '',
    inputSchemaJson: JSON.stringify(
      composition.input_schema ?? {
        type: 'object',
        properties: {},
        required: [],
      },
      null,
      2,
    ),
    steps,
    // Preserve lifecycle on edit — don't silently demote a production
    // / organization composition back to temporary / private (bug
    // flagged at pilot review).
    status: composition.status,
    visibility: composition.visibility,
    isSaving: false,
  }
}

export function CompositionBuilder({
  initial,
  onSaved,
  onCancel,
  onEditRawJson,
}: CompositionBuilderProps) {
  const { t } = useTranslation('compositions')

  const [state, dispatch] = useReducer(
    builderReducer,
    null,
    () => (initial ? hydrateFromComposition(initial) : createInitialState()),
  )
  const [pickerOpen, setPickerOpen] = useState(false)
  const [backendError, setBackendError] = useState<string | null>(null)
  const [inputSchemaError, setInputSchemaError] = useState<string | null>(null)

  const enabledTypes = useMemo(
    () =>
      new Set(
        DURABLE_TYPES.filter(
          (t) => STEP_TYPE_FORMS[t] !== undefined,
        ),
      ),
    [],
  )

  const validation = useMemo(() => validateBuilderState(state), [state])
  const isEditing = !!initial

  const handleSave = async () => {
    setBackendError(null)
    setInputSchemaError(null)
    if (!validation.valid) {
      return
    }
    const { payload, inputSchemaError: schemaErr } = serializeBuilderState(state)
    if (schemaErr || !payload) {
      setInputSchemaError(schemaErr)
      return
    }
    // Production guard: if we're editing a comp that was production at
    // mount, force the save back to `temporary` so the backend re-runs
    // validate_*_for_production at promotion time. Skipping this lets
    // an edited prod comp silently keep `status='production'` while
    // failing the canary checks (flagged in adversarial review).
    const wasProduction = isEditing && initial?.status === 'production'
    const finalPayload = wasProduction
      ? { ...payload, status: 'temporary' as const }
      : payload
    dispatch({ type: 'SET_SAVING', value: true })
    try {
      const saved = isEditing && state.compositionId
        ? await compositionsApi.update(state.compositionId, finalPayload)
        : await compositionsApi.create(finalPayload)
      // Toast lives in the host (ProposeCompositionModal.onSaved) so it
      // can stay context-aware (create vs update vs promote). Builder
      // stays silent on success — only surfaces errors via Alert below.
      onSaved(saved)
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } }; message?: string })
          ?.response?.data?.detail ||
        (e as { message?: string })?.message ||
        t('builder.toast.saveFailed')
      setBackendError(String(detail))
    } finally {
      dispatch({ type: 'SET_SAVING', value: false })
    }
  }

  const handleEditRawJson = (step: StepDraft) => {
    if (!onEditRawJson) return
    const raw = (step as { raw?: Record<string, unknown> }).raw
    if (!raw) return
    // Pre-fill the advanced editor with a 1-step snapshot so the user
    // can copy/edit just this step without redoing the whole compo.
    const snapshot = {
      name: state.name || 'untitled',
      description: state.description,
      input_schema:
        (() => {
          try {
            return JSON.parse(state.inputSchemaJson)
          } catch {
            return { type: 'object', properties: {}, required: [] }
          }
        })(),
      steps: [raw],
    }
    onEditRawJson(JSON.stringify(snapshot, null, 2))
  }

  const rootErrors = validation.errors.__root__ || []
  const showRootErrors = rootErrors.length > 0
  const hasSteps = state.steps.length > 0

  return (
    <div className="space-y-4">
      {/* Production-edit warning — see handleSave for the forced demotion. */}
      {isEditing && initial?.status === 'production' && (
        <Alert variant="warning" title={t('builder.productionEdit.title') as string}>
          {t('builder.productionEdit.message')}
        </Alert>
      )}

      {/* Header: name + description */}
      <div className="space-y-3">
        <Input
          label={t('builder.fields.name')}
          value={state.name}
          onChange={(e) =>
            dispatch({
              type: 'SET_HEADER',
              field: 'name',
              value: e.target.value,
            })
          }
          placeholder={t('builder.fields.namePlaceholder') as string}
          disabled={state.isSaving}
          required
        />
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">
            {t('builder.fields.description')}
          </label>
          <textarea
            value={state.description}
            onChange={(e) =>
              dispatch({
                type: 'SET_HEADER',
                field: 'description',
                value: e.target.value,
              })
            }
            rows={2}
            placeholder={t('builder.fields.descriptionPlaceholder') as string}
            disabled={state.isSaving}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-transparent text-sm"
          />
        </div>
        <details>
          <summary className="cursor-pointer text-sm font-medium text-gray-700">
            {t('builder.fields.inputSchemaSummary')}
          </summary>
          <p className="text-xs text-gray-500 mt-1 font-serif">
            {t('builder.fields.inputSchemaHint')}
          </p>
          <textarea
            value={state.inputSchemaJson}
            onChange={(e) =>
              dispatch({ type: 'SET_INPUT_SCHEMA', value: e.target.value })
            }
            rows={8}
            spellCheck={false}
            disabled={state.isSaving}
            className="w-full mt-2 p-3 border border-gray-300 rounded-lg text-xs font-mono focus:ring-2 focus:ring-orange focus:border-transparent"
          />
          {inputSchemaError && (
            <p className="mt-2 text-xs text-red-700">{inputSchemaError}</p>
          )}
        </details>
      </div>

      {/* Step list */}
      <div className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
            {t('builder.steps.heading')}
          </h3>
          <span className="text-xs text-gray-500">
            {t('builder.steps.count', { count: state.steps.length })}
          </span>
        </div>

        {!hasSteps && (
          <div className="border border-dashed border-gray-300 rounded-lg p-6 text-center text-sm text-gray-500 font-serif">
            {t('builder.steps.empty')}
          </div>
        )}

        {state.steps.map((step, idx) => (
          <StepCard
            key={step.step_id}
            step={step}
            index={idx}
            total={state.steps.length}
            errors={validation.errors[step.step_id]}
            disabled={state.isSaving}
            onChange={(patch) =>
              dispatch({
                type: 'UPDATE_STEP',
                stepId: step.step_id,
                patch,
              })
            }
            onMove={(direction) =>
              dispatch({
                type: 'MOVE_STEP',
                stepId: step.step_id,
                direction,
              })
            }
            onDelete={() =>
              dispatch({ type: 'DELETE_STEP', stepId: step.step_id })
            }
            onEditRawJson={
              onEditRawJson ? () => handleEditRawJson(step) : undefined
            }
          />
        ))}

        <Button
          variant="secondary"
          onClick={() => setPickerOpen(true)}
          disabled={state.isSaving}
        >
          <PlusIcon className="w-4 h-4 mr-1" />
          {t('builder.addStep')}
        </Button>
      </div>

      {/* Root-level validation errors (hidden until user tries to save) */}
      {showRootErrors && (
        <Alert variant="warning" title={t('builder.errors.fixBeforeSave') as string}>
          <ul className="list-disc list-inside text-sm space-y-0.5">
            {rootErrors.map((err) => (
              <li key={err}>{t(`builder.errors.${err}`, { defaultValue: err })}</li>
            ))}
          </ul>
        </Alert>
      )}

      {backendError && (
        <Alert variant="error" title={t('builder.toast.saveFailed') as string}>
          <p className="text-sm">{backendError}</p>
        </Alert>
      )}

      {/* Footer actions */}
      <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
        <Button
          variant="secondary"
          onClick={onCancel}
          disabled={state.isSaving}
        >
          {t('builder.cancel')}
        </Button>
        <Button
          variant="primary"
          onClick={handleSave}
          disabled={state.isSaving || !validation.valid}
        >
          {state.isSaving
            ? t('builder.saving')
            : isEditing
              ? t('builder.saveChanges')
              : t('builder.saveDraft')}
        </Button>
      </div>

      <StepTypePicker
        isOpen={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onPick={(stepType) => {
          dispatch({ type: 'ADD_STEP', stepType })
          setPickerOpen(false)
        }}
        enabledTypes={enabledTypes}
      />
    </div>
  )
}
