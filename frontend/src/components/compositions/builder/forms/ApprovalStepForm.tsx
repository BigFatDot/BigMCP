/**
 * ApprovalStepForm — StepForm for the `approval` durable step type (B-1.4).
 *
 * Cross-user gate: the composition pauses until either a specific user
 * (by UUID) OR a role-holder (owner/admin/member/viewer) approves via
 * `/app/compositions/approvals`. Author config mirrors
 * `app/orchestration/approval_step.validate_config`:
 *   - `message`: required, non-empty (substitutions resolved at suspend).
 *   - `approver_user_ids?` + `allowed_roles?`: at least one must be set.
 *   - `response_schema?`: optional JSON Schema for extra fields the
 *     approver fills alongside the decision.
 *   - `ttl_seconds?`: 1..86400, default 86400 (24h).
 *   - `allow_self_approval?`: bool, default false. Dangerous — disables
 *     the four-eyes rule.
 *
 * Pattern follows the adversarially-reviewed pilot
 * (`WaitUntilStepForm`) and `ElicitStepForm`:
 *   - No toast, no nav, `onChange` is silent.
 *   - Local string state for the textareas (UUIDs newline-sep, response
 *     schema JSON) so mid-edit invalid input doesn't trap the user.
 *   - Inline error message via local `setXxxError`; the validator
 *     surfaces a save-blocker via `validate.ts` if it persists.
 *
 * The approver-set widget intentionally takes raw UUIDs (one per line)
 * — a "search users by email" picker is out of scope for B-1.0 and
 * would require a new backend endpoint. Authors copy UUIDs from
 * /app/admin/users for now.
 */

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Alert, Badge, Input } from '@/components/ui'
import type { ApprovalConfig, StepFormProps } from '../types'

/** Roles mirror `_VALID_ROLES` in `approval_step.py`. */
const ALLOWED_ROLES = ['owner', 'admin', 'member', 'viewer'] as const
type Role = (typeof ALLOWED_ROLES)[number]

/** Default starter schema — `validate_config` requires a top-level
 *  `type`. We keep it minimal so the collapsed default doesn't surprise
 *  the user; the field is optional. */
const DEFAULT_RESPONSE_SCHEMA: Record<string, unknown> = {
  type: 'object',
  properties: {},
}

/** Loose-but-correct UUID v1-5 regex. The backend re-validates via
 *  `uuid.UUID(...)` which is the authoritative gate; this is just UX
 *  to flag obvious typos before submit. */
const UUID_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

/** Parse the multiline UUID textarea. Splits on newlines, trims, drops
 *  empty lines, and dedups (the backend also dedups but we mirror so
 *  the user sees the same value they'll save). Returns the list of
 *  parsed UUIDs plus any line numbers (1-indexed) that look invalid. */
function parseUuidLines(raw: string): {
  uuids: string[]
  invalidLines: number[]
} {
  const uuids: string[] = []
  const invalidLines: number[] = []
  const seen = new Set<string>()
  const lines = raw.split(/\r?\n/)
  lines.forEach((line, idx) => {
    const trimmed = line.trim()
    if (trimmed === '') return
    if (!UUID_REGEX.test(trimmed)) {
      invalidLines.push(idx + 1)
      return
    }
    const lower = trimmed.toLowerCase()
    if (seen.has(lower)) return
    seen.add(lower)
    uuids.push(lower)
  })
  return { uuids, invalidLines }
}

/** Parse the response_schema JSON textarea. Same contract as the
 *  ElicitStepForm helper — must be a plain object (not array/scalar).
 *  Empty/whitespace means "unset" and is treated as a success with
 *  `value: null` so we can clear the field. */
function parseResponseSchemaJson(
  raw: string,
):
  | { ok: true; value: Record<string, unknown> | null }
  | { ok: false; error: string } {
  const trimmed = raw.trim()
  if (trimmed === '') {
    return { ok: true, value: null }
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch (e) {
    return { ok: false, error: (e as Error).message }
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { ok: false, error: 'not-object' }
  }
  return { ok: true, value: parsed as Record<string, unknown> }
}

export function ApprovalStepForm({
  value,
  onChange,
  disabled,
}: StepFormProps<ApprovalConfig>) {
  const { t } = useTranslation('compositions')

  // Local textarea state for UUIDs — we don't re-stringify on every
  // value change, so the user can mid-edit "almost-a-uuid" without
  // losing keystrokes. Seeded from value on mount.
  const [approverIdsRaw, setApproverIdsRaw] = useState<string>(() =>
    (value.approver_user_ids ?? []).join('\n'),
  )
  const [approverIdsInvalidLines, setApproverIdsInvalidLines] = useState<
    number[]
  >([])

  // Same pattern as ElicitStepForm for the JSON textarea.
  const [responseSchemaRaw, setResponseSchemaRaw] = useState<string>(() =>
    value.response_schema
      ? JSON.stringify(value.response_schema, null, 2)
      : '',
  )
  const [responseSchemaError, setResponseSchemaError] = useState<string | null>(
    null,
  )

  // External hydration: if parent fully replaces `value` (e.g. loading
  // an existing composition), re-seed the textareas. Detect via a quick
  // fingerprint comparison to avoid feedback loops on our own emits.
  useEffect(() => {
    const incoming = (value.approver_user_ids ?? []).join('\n')
    const current = parseUuidLines(approverIdsRaw).uuids.join('\n')
    if (current !== incoming) {
      setApproverIdsRaw(incoming)
      setApproverIdsInvalidLines([])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value.approver_user_ids])

  useEffect(() => {
    const incoming = value.response_schema
      ? JSON.stringify(value.response_schema)
      : ''
    const current = (() => {
      const parsed = parseResponseSchemaJson(responseSchemaRaw)
      if (!parsed.ok) return null
      return parsed.value ? JSON.stringify(parsed.value) : ''
    })()
    if (current !== incoming) {
      setResponseSchemaRaw(
        value.response_schema
          ? JSON.stringify(value.response_schema, null, 2)
          : '',
      )
      setResponseSchemaError(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value.response_schema])

  /** Emit a patched value while preserving every other field. */
  const emit = (patch: Partial<ApprovalConfig>) => {
    onChange({
      message: value.message,
      approver_user_ids: value.approver_user_ids,
      allowed_roles: value.allowed_roles,
      response_schema: value.response_schema,
      ttl_seconds: value.ttl_seconds,
      allow_self_approval: value.allow_self_approval,
      ...patch,
    })
  }

  const handleApproverIdsChange = (raw: string) => {
    setApproverIdsRaw(raw)
    const { uuids, invalidLines } = parseUuidLines(raw)
    setApproverIdsInvalidLines(invalidLines)
    // Always emit the parsed list (even if some lines are invalid —
    // we keep the valid ones so the user can fix the typo without
    // losing the others). undefined when empty so the backend treats
    // the field as unset.
    emit({ approver_user_ids: uuids.length > 0 ? uuids : undefined })
  }

  const handleResponseSchemaChange = (raw: string) => {
    setResponseSchemaRaw(raw)
    const parsed = parseResponseSchemaJson(raw)
    if (parsed.ok) {
      setResponseSchemaError(null)
      emit({ response_schema: parsed.value ?? undefined })
    } else {
      setResponseSchemaError(t('builder.approval.responseSchemaJsonError') as string)
      // Keep the last valid schema on the parent — same trap-avoidance
      // pattern as ElicitStepForm.
    }
  }

  const toggleRole = (role: Role) => {
    const current = new Set((value.allowed_roles ?? []) as string[])
    if (current.has(role)) {
      current.delete(role)
    } else {
      current.add(role)
    }
    const next = ALLOWED_ROLES.filter((r) => current.has(r))
    emit({ allowed_roles: next.length > 0 ? next : undefined })
  }

  const selectedRoles = new Set<string>((value.allowed_roles ?? []) as string[])
  const hasApproverIds = (value.approver_user_ids ?? []).length > 0
  const hasRoles = selectedRoles.size > 0
  const noApproverSelected = !hasApproverIds && !hasRoles

  return (
    <div className="space-y-4">
      {/* message */}
      <div>
        <label
          htmlFor="approval-message"
          className="block text-sm font-medium text-gray-700 mb-1.5"
        >
          {t('builder.approval.messageLabel')}
        </label>
        <textarea
          id="approval-message"
          value={value.message ?? ''}
          onChange={(e) => emit({ message: e.target.value })}
          rows={3}
          placeholder={t('builder.approval.messagePlaceholder') as string}
          disabled={disabled}
          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-transparent text-sm"
        />
        <p className="mt-1 text-xs text-gray-500 font-serif">
          {t('builder.approval.messageHint')}
        </p>
      </div>

      {/* allowed_roles (chips) */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1.5">
          {t('builder.approval.allowedRolesLabel')}
        </label>
        <div className="flex flex-wrap gap-2">
          {ALLOWED_ROLES.map((role) => {
            const selected = selectedRoles.has(role)
            return (
              <button
                key={role}
                type="button"
                onClick={() => toggleRole(role)}
                disabled={disabled}
                aria-pressed={selected}
                className="focus:outline-none focus:ring-2 focus:ring-orange rounded-full disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Badge variant={selected ? 'primary' : 'gray'}>{role}</Badge>
              </button>
            )
          })}
        </div>
        <p className="mt-1 text-xs text-gray-500 font-serif">
          {t('builder.approval.allowedRolesHint')}
        </p>
      </div>

      {/* approver_user_ids (UUID textarea) */}
      <div>
        <label
          htmlFor="approval-user-ids"
          className="block text-sm font-medium text-gray-700 mb-1.5"
        >
          {t('builder.approval.approverUserIdsLabel')}
        </label>
        <textarea
          id="approval-user-ids"
          value={approverIdsRaw}
          onChange={(e) => handleApproverIdsChange(e.target.value)}
          rows={3}
          spellCheck={false}
          placeholder={'00000000-0000-4000-8000-000000000000'}
          disabled={disabled}
          className="w-full p-3 border border-gray-300 rounded-lg text-xs font-mono focus:ring-2 focus:ring-orange focus:border-transparent"
        />
        {approverIdsInvalidLines.length > 0 ? (
          <p className="mt-1 text-xs text-red-700">
            {t('builder.approval.approverUserIdsInvalid', {
              lines: approverIdsInvalidLines.join(', '),
            })}
          </p>
        ) : (
          <p className="mt-1 text-xs text-gray-500 font-serif">
            {t('builder.approval.approverUserIdsHint')}
          </p>
        )}
      </div>

      {/* "at least one approver" warning */}
      {noApproverSelected && (
        <Alert variant="warning">
          {t('builder.approval.noApproverSelected')}
        </Alert>
      )}

      {/* response_schema (collapsible JSON textarea) */}
      <details className="border border-gray-200 rounded-lg">
        <summary className="cursor-pointer px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 rounded-lg">
          {t('builder.approval.responseSchemaSummary')}
        </summary>
        <div className="px-4 pt-2 pb-3 space-y-2">
          <textarea
            id="approval-response-schema"
            value={responseSchemaRaw}
            onChange={(e) => handleResponseSchemaChange(e.target.value)}
            rows={6}
            spellCheck={false}
            placeholder={JSON.stringify(DEFAULT_RESPONSE_SCHEMA, null, 2)}
            disabled={disabled}
            className="w-full p-3 border border-gray-300 rounded-lg text-xs font-mono focus:ring-2 focus:ring-orange focus:border-transparent"
          />
          {responseSchemaError ? (
            <p className="text-xs text-red-700">{responseSchemaError}</p>
          ) : (
            <p className="text-xs text-gray-500 font-serif">
              {t('builder.approval.responseSchemaHint')}
            </p>
          )}
        </div>
      </details>

      {/* ttl_seconds */}
      <Input
        type="number"
        min={1}
        max={86400}
        step={1}
        inputMode="numeric"
        label={t('builder.approval.ttlLabel')}
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
        helperText={t('builder.approval.ttlHint') as string}
      />

      {/* allow_self_approval */}
      <div>
        <label className="flex items-start gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={!!value.allow_self_approval}
            onChange={(e) =>
              emit({ allow_self_approval: e.target.checked || undefined })
            }
            disabled={disabled}
            className="mt-1 rounded text-orange focus:ring-orange"
          />
          <div>
            <div className="text-sm font-medium text-gray-900">
              {t('builder.approval.allowSelfApprovalLabel')}
            </div>
            <div className="text-xs text-amber-700 font-serif">
              {t('builder.approval.allowSelfApprovalHint')}
            </div>
          </div>
        </label>
      </div>
    </div>
  )
}
