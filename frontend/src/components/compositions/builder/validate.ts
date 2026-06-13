/**
 * Visual composition builder — client-side validation.
 *
 * Intentionally thin. Backend `validate_config` (per step type) is
 * authoritative; 422 responses are surfaced via an `<Alert>` on the
 * builder root. This module only catches the obvious shape errors so
 * we don't bother the server with empty drafts.
 *
 * Keys returned in `errors`:
 *   - `__root__` → composition-level errors (name missing, no steps)
 *   - `<step_id>` → step-level errors (e.g. `step_1: wait_until.must_pick_mode`)
 */

import type { BuilderState, StepDraft } from './types'

export interface ValidationResult {
  valid: boolean
  errors: Record<string, string[]>
}

/** Loose ISO-8601 / offset detection. The backend re-parses with
 *  `datetime.fromisoformat` so we only reject obvious garbage. */
function looksLikeIsoTimestamp(value: string): boolean {
  // Accept "2026-06-13T18:00", "2026-06-13T18:00:00", with optional
  // seconds, fractional, and timezone suffix (Z or ±HH:MM).
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/.test(
    value,
  )
}

function validateStep(step: StepDraft): string[] {
  const errors: string[] = []
  switch (step.type) {
    case 'wait_until': {
      const { wait_seconds, resume_at } = step.wait_until
      const hasRelative = wait_seconds != null && wait_seconds !== undefined
      const hasAbsolute = !!resume_at && resume_at.trim() !== ''
      if (!hasRelative && !hasAbsolute) {
        errors.push('wait_until.mustPickMode')
      } else if (hasRelative && hasAbsolute) {
        errors.push('wait_until.mutuallyExclusive')
      } else if (hasRelative) {
        if (!Number.isFinite(wait_seconds) || (wait_seconds as number) <= 0) {
          errors.push('wait_until.waitSecondsPositive')
        }
      } else if (hasAbsolute) {
        if (!looksLikeIsoTimestamp(resume_at as string)) {
          errors.push('wait_until.resumeAtFormat')
        }
      }
      break
    }
    case 'elicit': {
      const { message, schema } = step.elicit
      if (!message || message.trim() === '') {
        errors.push('elicit.messageRequired')
      }
      if (!schema || typeof schema !== 'object' || Array.isArray(schema)) {
        errors.push('elicit.schemaInvalid')
      }
      break
    }
    case 'wait_callback':
      // Both fields are optional — backend accepts a bare {} (defaults
      // ttl to 86400 and expected_schema to free-form). Nothing to
      // gate client-side.
      break
    case 'subcomposition': {
      const { composition_id } = step.subcomposition
      if (!composition_id || composition_id.trim() === '') {
        errors.push('subcomposition.compositionIdRequired')
      }
      break
    }
    case 'approval': {
      const { message, approver_user_ids, allowed_roles } = step.approval
      if (!message || message.trim() === '') {
        errors.push('approval.messageRequired')
      }
      const hasUsers = (approver_user_ids?.length ?? 0) > 0
      const hasRoles = (allowed_roles?.length ?? 0) > 0
      if (!hasUsers && !hasRoles) {
        errors.push('approval.noApprover')
      }
      break
    }
    case 'tool':
    case 'transform':
    case 'foreach':
      // Legacy steps are read-only — never validated client-side.
      break
  }
  return errors
}

export function validateBuilderState(state: BuilderState): ValidationResult {
  const errors: Record<string, string[]> = {}
  const root: string[] = []
  if (!state.name.trim()) root.push('root.nameRequired')
  if (state.steps.length === 0) root.push('root.atLeastOneStep')
  if (root.length > 0) errors.__root__ = root

  for (const step of state.steps) {
    const stepErrors = validateStep(step)
    if (stepErrors.length > 0) errors[step.step_id] = stepErrors
  }

  return { valid: Object.keys(errors).length === 0, errors }
}
