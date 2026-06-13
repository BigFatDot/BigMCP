/**
 * WaitCallbackStepForm — StepForm for the `wait_callback` durable step type (B-1.5).
 *
 * The runtime generates a per-execution HMAC-protected callback URL the
 * external system has to POST to in order to resume the composition.
 * The author only declares:
 *   - `expected_schema?`: an optional JSON Schema (object) that the
 *     callback payload is validated against. Most webhooks accept any
 *     payload — left empty, the endpoint accepts anything. Collapsed in
 *     a `<details>` so the form stays compact for the default case.
 *   - `ttl_seconds?`: clamped server-side to [1, 86400] (24h hard cap).
 *
 * The actual callback URL is NOT available at design time: the runtime
 * generates token + URL when the step suspends. We surface this with an
 * info Alert so authors aren't confused about where the URL comes from.
 *
 * Pattern follows the adversarially-reviewed pilot
 * (`WaitUntilStepForm`) and `ElicitStepForm`: no toast, no nav,
 * `onChange` is silent. Local string state for the JSON textarea (so
 * mid-edit invalid JSON doesn't lose keystrokes) — the parent keeps the
 * last valid schema until the user recovers.
 */

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Alert, Input } from '@/components/ui'
import type { StepFormProps, WaitCallbackConfig } from '../types'

/** Parse the raw JSON string for `expected_schema`. Returns the parsed
 *  object if it's a plain object, or an error tag otherwise. Arrays /
 *  scalars are rejected because `validate_config` requires an object
 *  (JSON Schema object) or absent. Empty string is reported separately
 *  so the form can treat it as "clear the field" rather than an error. */
function parseExpectedSchemaJson(
  raw: string,
):
  | { ok: true; value: Record<string, unknown> | undefined }
  | { ok: false; error: 'parse' | 'not-object' } {
  const trimmed = raw.trim()
  if (trimmed === '') {
    // Empty textarea → field is intentionally unset, accept all payloads.
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

export function WaitCallbackStepForm({
  value,
  onChange,
  disabled,
}: StepFormProps<WaitCallbackConfig>) {
  const { t } = useTranslation('compositions')

  // Local string state for the raw JSON textarea — same pattern as
  // ElicitStepForm.schemaJsonRaw and CompositionBuilder.inputSchemaJson.
  // Seeded once from value.expected_schema; we don't re-stringify on
  // every value change (clobbers user's whitespace + key ordering).
  const [schemaJsonRaw, setSchemaJsonRaw] = useState<string>(() =>
    value.expected_schema === undefined || value.expected_schema === null
      ? ''
      : JSON.stringify(value.expected_schema, null, 2),
  )
  const [schemaJsonError, setSchemaJsonError] = useState<string | null>(null)

  // External hydration only (parent reset / edit-existing). Detect via a
  // canonical-JSON fingerprint to avoid feedback loops on our own emits.
  useEffect(() => {
    const incoming =
      value.expected_schema === undefined || value.expected_schema === null
        ? ''
        : JSON.stringify(value.expected_schema)
    const current = (() => {
      const parsed = parseExpectedSchemaJson(schemaJsonRaw)
      if (!parsed.ok) return null
      return parsed.value === undefined ? '' : JSON.stringify(parsed.value)
    })()
    if (current !== incoming) {
      setSchemaJsonRaw(
        value.expected_schema === undefined || value.expected_schema === null
          ? ''
          : JSON.stringify(value.expected_schema, null, 2),
      )
      setSchemaJsonError(null)
    }
    // Only react to outside changes on value.expected_schema. Including
    // schemaJsonRaw would fight the user's keystrokes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value.expected_schema])

  const emit = (patch: Partial<WaitCallbackConfig>) => {
    onChange({
      expected_schema: value.expected_schema,
      ttl_seconds: value.ttl_seconds,
      ...patch,
    })
  }

  const handleSchemaChange = (raw: string) => {
    setSchemaJsonRaw(raw)
    const parsed = parseExpectedSchemaJson(raw)
    if (parsed.ok) {
      setSchemaJsonError(null)
      emit({ expected_schema: parsed.value })
    } else {
      // Keep last valid schema on parent — don't trap user with stale
      // invalid JSON mid-edit. validate.ts + backend catch a save with
      // unrecovered invalid JSON; the inline error is the primary signal.
      setSchemaJsonError(t('builder.waitCallback.expectedSchemaJsonError') as string)
    }
  }

  return (
    <div className="space-y-4">
      {/* Runtime URL notice — the callback URL is generated at suspend
          time, the builder can't show it here. */}
      <Alert variant="info">{t('builder.waitCallback.runtimeNote')}</Alert>

      {/* expected_schema — collapsed by default (most callbacks accept
          any payload, the field is purely opt-in). */}
      <details>
        <summary className="cursor-pointer text-sm font-medium text-gray-700">
          {t('builder.waitCallback.expectedSchemaSummary')}
        </summary>
        <p className="text-xs text-gray-500 mt-1 font-serif">
          {t('builder.waitCallback.expectedSchemaHint')}
        </p>
        <textarea
          value={schemaJsonRaw}
          onChange={(e) => handleSchemaChange(e.target.value)}
          rows={8}
          spellCheck={false}
          disabled={disabled}
          className="w-full mt-2 p-3 border border-gray-300 rounded-lg text-xs font-mono focus:ring-2 focus:ring-orange focus:border-transparent"
        />
        {schemaJsonError && (
          <p className="mt-1 text-xs text-red-700">{schemaJsonError}</p>
        )}
      </details>

      {/* ttl_seconds — clamped [1, 86400] server-side. */}
      <Input
        type="number"
        min={1}
        max={86400}
        step={1}
        inputMode="numeric"
        label={t('builder.waitCallback.ttlLabel')}
        placeholder="86400"
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
        helperText={t('builder.waitCallback.ttlHint') as string}
      />
    </div>
  )
}
