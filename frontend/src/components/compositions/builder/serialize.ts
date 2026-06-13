/**
 * Visual composition builder — serialise BuilderState → API payload.
 *
 * Pure function. Strips empty optional fields so we don't ship `{}`
 * or `null` for things the backend treats as "set". `status` /
 * `visibility` come from the BuilderState — on create they default to
 * `'temporary'` / `'private'`; on edit they round-trip the existing
 * composition's lifecycle so we don't silently demote a production
 * comp back to draft.
 */

import type { CreateCompositionRequest } from '@/services/marketplace'
import type { BuilderState, StepDraft } from './types'

/** Drop `undefined` / `null` / empty-string values from an object. */
function compact<T extends Record<string, unknown>>(obj: T): T {
  const out = {} as Record<string, unknown>
  for (const [k, v] of Object.entries(obj)) {
    if (v === undefined || v === null) continue
    if (typeof v === 'string' && v.trim() === '') continue
    out[k] = v
  }
  return out as T
}

function serializeStep(step: StepDraft): Record<string, unknown> {
  const base: Record<string, unknown> = { step_id: step.step_id, type: step.type }
  if (step.optional) base.optional = true

  switch (step.type) {
    case 'elicit':
      return {
        ...base,
        elicit: compact({
          message: step.elicit.message,
          schema: step.elicit.schema,
          ttl_seconds: step.elicit.ttl_seconds,
        }),
      }
    case 'wait_until':
      return {
        ...base,
        wait_until: compact({
          wait_seconds: step.wait_until.wait_seconds ?? undefined,
          resume_at: step.wait_until.resume_at ?? undefined,
        }),
      }
    case 'wait_callback':
      return {
        ...base,
        wait_callback: compact({
          expected_schema: step.wait_callback.expected_schema,
          ttl_seconds: step.wait_callback.ttl_seconds,
        }),
      }
    case 'subcomposition':
      return {
        ...base,
        subcomposition: compact({
          composition_id: step.subcomposition.composition_id,
          inputs: step.subcomposition.inputs,
        }),
      }
    case 'approval':
      return {
        ...base,
        approval: compact({
          message: step.approval.message,
          approver_user_ids: step.approval.approver_user_ids,
          allowed_roles: step.approval.allowed_roles,
          response_schema: step.approval.response_schema,
          ttl_seconds: step.approval.ttl_seconds,
          allow_self_approval: step.approval.allow_self_approval,
        }),
      }
    case 'tool':
    case 'transform':
    case 'foreach':
      // Legacy steps round-trip verbatim — we never mutate them.
      return { ...step.raw, step_id: step.step_id, type: step.type }
  }
}

/**
 * Parse the input_schema textarea content. Returns `null` if the JSON
 * is malformed (the caller surfaces the parse error to the user).
 */
function parseInputSchema(json: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(json)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
    return null
  } catch {
    return null
  }
}

export interface SerializeResult {
  payload: CreateCompositionRequest | null
  inputSchemaError: string | null
}

export function serializeBuilderState(state: BuilderState): SerializeResult {
  const schema = parseInputSchema(state.inputSchemaJson)
  if (schema === null) {
    return {
      payload: null,
      inputSchemaError: 'Input schema must be a valid JSON object.',
    }
  }
  const payload: CreateCompositionRequest = {
    name: state.name.trim(),
    description: state.description.trim() || undefined,
    visibility: state.visibility,
    status: state.status,
    input_schema: schema,
    // The shared `CreateCompositionRequest.steps` shape is the legacy
    // tool-step one; we ship the durable-step payloads through it. The
    // backend accepts any step shape that matches its dispatcher, so
    // this cast is the documented escape hatch (see Advanced JSON mode
    // in CompositionsPage which does the same thing).
    steps: state.steps.map(serializeStep) as unknown as CreateCompositionRequest['steps'],
  }
  return { payload, inputSchemaError: null }
}
