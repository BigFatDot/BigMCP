/**
 * WaitUntilStepForm — pilot StepForm for the visual builder (Sprint 2.0).
 *
 * Radio mutex over the two backend-accepted modes:
 *   - `wait_seconds`: positive integer, relative duration in seconds
 *   - `resume_at`:    ISO-8601 timestamp (UTC or with offset)
 *
 * Both empty is also accepted at edit time (the Save button gates it
 * via `validate.ts`). The form NEVER sends both at once.
 */

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui'
import type { StepFormProps, WaitUntilConfig } from '../types'

type Mode = 'wait_seconds' | 'resume_at'

/** Local <input type="datetime-local"> emits naive strings like
 *  "2026-06-13T18:00". The backend (`_parse_iso`) treats naive as UTC,
 *  so we round-trip through Date to attach the user's offset. */
function localInputToISO(raw: string): string | null {
  if (!raw) return null
  const d = new Date(raw)
  return Number.isNaN(d.getTime()) ? null : d.toISOString()
}

/** Render an ISO timestamp back into the `YYYY-MM-DDTHH:mm` shape the
 *  datetime-local input expects, in the user's local timezone. */
function isoToLocalInput(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  )
}

export function WaitUntilStepForm({
  value,
  onChange,
  disabled,
}: StepFormProps<WaitUntilConfig>) {
  const { t } = useTranslation('compositions')

  // Mode is local state — deriving it purely from `value` traps the user
  // when both fields are null (the "fresh draft" case), because
  // switchMode would emit the same null/null shape and the derived mode
  // wouldn't move. We seed from value on mount, then follow value only
  // when an actual field gets populated (external hydration).
  const [mode, setMode] = useState<Mode>(() =>
    value.resume_at !== null && value.resume_at !== undefined && value.resume_at !== ''
      ? 'resume_at'
      : 'wait_seconds',
  )

  useEffect(() => {
    if (value.resume_at !== null && value.resume_at !== undefined && value.resume_at !== '') {
      setMode('resume_at')
    } else if (
      value.wait_seconds !== null &&
      value.wait_seconds !== undefined &&
      mode === 'resume_at'
    ) {
      setMode('wait_seconds')
    }
    // No else: don't auto-flip during user edits in either direction.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value.resume_at, value.wait_seconds])

  const switchMode = (next: Mode) => {
    if (next === mode) return
    setMode(next)
    // Clear the inactive field so the validator sees the mutex respected.
    onChange({ wait_seconds: null, resume_at: null })
  }

  return (
    <div className="space-y-4">
      <fieldset className="space-y-2" disabled={disabled}>
        <legend className="text-sm font-medium text-gray-700">
          {t('builder.waitUntil.modeLegend')}
        </legend>
        <label className="flex items-start gap-2 cursor-pointer">
          <input
            type="radio"
            name="wait_until_mode"
            value="wait_seconds"
            checked={mode === 'wait_seconds'}
            onChange={() => switchMode('wait_seconds')}
            className="mt-1 text-orange focus:ring-orange"
          />
          <div>
            <div className="text-sm font-medium text-gray-900">
              {t('builder.waitUntil.relativeLabel')}
            </div>
            <div className="text-xs text-gray-500 font-serif">
              {t('builder.waitUntil.relativeHint')}
            </div>
          </div>
        </label>
        <label className="flex items-start gap-2 cursor-pointer">
          <input
            type="radio"
            name="wait_until_mode"
            value="resume_at"
            checked={mode === 'resume_at'}
            onChange={() => switchMode('resume_at')}
            className="mt-1 text-orange focus:ring-orange"
          />
          <div>
            <div className="text-sm font-medium text-gray-900">
              {t('builder.waitUntil.absoluteLabel')}
            </div>
            <div className="text-xs text-gray-500 font-serif">
              {t('builder.waitUntil.absoluteHint')}
            </div>
          </div>
        </label>
      </fieldset>

      {mode === 'wait_seconds' && (
        <Input
          type="number"
          min={1}
          step={1}
          inputMode="numeric"
          label={t('builder.waitUntil.waitSecondsLabel')}
          placeholder="60"
          value={
            value.wait_seconds === null || value.wait_seconds === undefined
              ? ''
              : String(value.wait_seconds)
          }
          onChange={(e) => {
            const raw = e.target.value.trim()
            if (raw === '') {
              onChange({ wait_seconds: null, resume_at: null })
              return
            }
            const parsed = Number(raw)
            onChange({
              wait_seconds: Number.isFinite(parsed) ? parsed : null,
              resume_at: null,
            })
          }}
          disabled={disabled}
          helperText={t('builder.waitUntil.waitSecondsHelper')}
        />
      )}

      {mode === 'resume_at' && (
        <Input
          type="datetime-local"
          label={t('builder.waitUntil.resumeAtLabel')}
          value={isoToLocalInput(value.resume_at)}
          onChange={(e) => {
            const raw = e.target.value
            onChange({
              wait_seconds: null,
              resume_at: localInputToISO(raw),
            })
          }}
          disabled={disabled}
          helperText={t('builder.waitUntil.resumeAtHelper')}
        />
      )}
    </div>
  )
}
