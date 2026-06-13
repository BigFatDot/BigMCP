/**
 * ElicitStepForm — StepForm for the `elicit` durable step type (B-1).
 *
 * The author declares three things:
 *   - `message`: the prompt the runtime will show to the user
 *     (textarea; ${input.X} / ${step_id.path} substitutions are
 *     resolved at suspend time by the backend, we don't preview them
 *     here).
 *   - `schema`: a JSON Schema (object) describing the expected
 *     response. Edited as a JSON textarea — the visual schema editor
 *     is intentionally NOT duplicated here; at runtime
 *     `DynamicInputForm` / `ElicitForm` will render the fields from
 *     this schema. The backend re-validates on dispatch + resume.
 *   - `ttl_seconds`: optional, clamped server-side to [1, 86400].
 *
 * Pattern follows the adversarially-reviewed pilot
 * (`WaitUntilStepForm`): no toast, no nav, `onChange` is silent.
 *
 * For the schema textarea we keep a **local string state**
 * (`schemaJsonRaw`) so the user can mid-edit invalid JSON without
 * losing keystrokes; we only emit the parsed object onto `value.schema`
 * when the JSON parses to an object. While invalid we still emit the
 * other fields (and keep the last valid schema in the parent) so the
 * form never traps the user. An inline error message is shown.
 */

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui'
import type { ElicitConfig, StepFormProps } from '../types'

/** Default starter schema — matches `validate_config` minimum
 *  (object with `type` declared). */
const DEFAULT_SCHEMA: Record<string, unknown> = {
  type: 'object',
  properties: {},
}

/** Parse the raw JSON string. Returns the parsed object if it's a
 *  plain object, or an error message otherwise. Arrays / scalars are
 *  rejected here because `elicit.schema` must be an object per
 *  `validate_config`. */
function parseSchemaJson(
  raw: string,
): { ok: true; value: Record<string, unknown> } | { ok: false; error: string } {
  const trimmed = raw.trim()
  if (trimmed === '') {
    return { ok: false, error: 'empty' }
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch (e) {
    return { ok: false, error: (e as Error).message }
  }
  if (
    parsed === null ||
    typeof parsed !== 'object' ||
    Array.isArray(parsed)
  ) {
    return { ok: false, error: 'not-object' }
  }
  return { ok: true, value: parsed as Record<string, unknown> }
}

export function ElicitStepForm({
  value,
  onChange,
  disabled,
}: StepFormProps<ElicitConfig>) {
  const { t } = useTranslation('compositions')

  // Seed the textarea from value.schema once. We don't re-stringify on
  // every value change (that would clobber the user's whitespace + key
  // ordering mid-edit). Hydration on mount + external resets only.
  const [schemaJsonRaw, setSchemaJsonRaw] = useState<string>(() =>
    JSON.stringify(value.schema ?? DEFAULT_SCHEMA, null, 2),
  )
  const [schemaJsonError, setSchemaJsonError] = useState<string | null>(null)

  // If the parent fully resets / replaces the value (hydrate from an
  // existing composition), re-seed the textarea. Detect by comparing
  // a quick fingerprint to avoid feedback loops on our own emits.
  useEffect(() => {
    const incoming = JSON.stringify(value.schema ?? DEFAULT_SCHEMA)
    const current = (() => {
      const parsed = parseSchemaJson(schemaJsonRaw)
      return parsed.ok ? JSON.stringify(parsed.value) : null
    })()
    if (current !== incoming) {
      setSchemaJsonRaw(JSON.stringify(value.schema ?? DEFAULT_SCHEMA, null, 2))
      setSchemaJsonError(null)
    }
    // We intentionally only react to value.schema reference changes
    // coming from outside (parent reset). Including schemaJsonRaw would
    // fight the user's keystrokes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value.schema])

  const emit = (patch: Partial<ElicitConfig>) => {
    onChange({
      message: value.message,
      schema: value.schema,
      ttl_seconds: value.ttl_seconds,
      ...patch,
    })
  }

  const handleSchemaChange = (raw: string) => {
    setSchemaJsonRaw(raw)
    const parsed = parseSchemaJson(raw)
    if (parsed.ok) {
      setSchemaJsonError(null)
      emit({ schema: parsed.value })
    } else {
      // Keep the last valid schema on the parent — don't trap the user
      // with intermediate invalid JSON. validate.ts + the backend will
      // catch a save attempt with a stale schema if the user never
      // recovers (the textarea error message is the primary signal).
      setSchemaJsonError(
        parsed.error === 'empty'
          ? (t('builder.elicit.schemaJsonError') as string)
          : parsed.error === 'not-object'
            ? (t('builder.elicit.schemaJsonError') as string)
            : (t('builder.elicit.schemaJsonError') as string),
      )
    }
  }

  return (
    <div className="space-y-4">
      {/* message */}
      <div>
        <label
          htmlFor="elicit-message"
          className="block text-sm font-medium text-gray-700 mb-1.5"
        >
          {t('builder.elicit.messageLabel')}
        </label>
        <textarea
          id="elicit-message"
          value={value.message ?? ''}
          onChange={(e) => emit({ message: e.target.value })}
          rows={3}
          placeholder={t('builder.elicit.messagePlaceholder') as string}
          disabled={disabled}
          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-transparent text-sm"
        />
        <p className="mt-1 text-xs text-gray-500 font-serif">
          {t('builder.elicit.messageHint')}
        </p>
      </div>

      {/* schema (JSON textarea) */}
      <div>
        <label
          htmlFor="elicit-schema"
          className="block text-sm font-medium text-gray-700 mb-1.5"
        >
          {t('builder.elicit.schemaLabel')}
        </label>
        <textarea
          id="elicit-schema"
          value={schemaJsonRaw}
          onChange={(e) => handleSchemaChange(e.target.value)}
          rows={8}
          spellCheck={false}
          disabled={disabled}
          className="w-full p-3 border border-gray-300 rounded-lg text-xs font-mono focus:ring-2 focus:ring-orange focus:border-transparent"
        />
        {schemaJsonError ? (
          <p className="mt-1 text-xs text-red-700">{schemaJsonError}</p>
        ) : (
          <p className="mt-1 text-xs text-gray-500 font-serif">
            {t('builder.elicit.schemaHint')}
          </p>
        )}
      </div>

      {/* ttl_seconds */}
      <Input
        type="number"
        min={1}
        max={86400}
        step={1}
        inputMode="numeric"
        label={t('builder.elicit.ttlLabel')}
        placeholder="3600"
        value={
          value.ttl_seconds === undefined || value.ttl_seconds === null
            ? ''
            : String(value.ttl_seconds)
        }
        onChange={(e) => {
          const raw = e.target.value.trim()
          if (raw === '') {
            emit({ ttl_seconds: undefined })
            return
          }
          const parsed = Number(raw)
          emit({
            ttl_seconds: Number.isFinite(parsed) ? parsed : undefined,
          })
        }}
        disabled={disabled}
        helperText={t('builder.elicit.ttlHint') as string}
      />
    </div>
  )
}
