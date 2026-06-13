/**
 * Visual composition builder — type model.
 *
 * Source of truth for the in-builder draft of a single step.
 * Each `type` matches the suspending step types defined in
 * `app/orchestration/composition_routing.SUSPENDING_STEP_TYPES`
 * (B-1 pilot covers `wait_until`; the other four are added in 2.1).
 *
 * Legacy step types — `tool`, `transform`, `foreach` — are NEVER
 * proposed by the builder but CAN appear when editing an existing
 * composition. They live in `LegacyStepDraft` (read-only viewer).
 */

import type { SuspensionReason } from '@/services/compositionExecutions'
import type { CompositionVisibility } from '@/services/marketplace'

/** Status lifecycle — mirrors the literal in `Composition.status`
 *  (not exported as alias by services/marketplace.ts). */
export type CompositionStatus = 'temporary' | 'validated' | 'production'

/** Step types the builder can author. Mirror of `SUSPENSION_BADGES`
 *  keys minus `_test_suspend` (which is an executor-only sentinel). */
export type DurableStepType = Exclude<SuspensionReason, '_test_suspend'>

/** Legacy step types we display read-only when editing an existing
 *  composition that pre-dates the builder. */
export type LegacyStepType = 'tool' | 'transform' | 'foreach'

export type StepType = DurableStepType | LegacyStepType

// --- Per-step config shapes (match backend validate_config) ----------------

export interface ElicitConfig {
  message: string
  /** Free-form JSON schema (object). UI uses a JSON textarea in B-1.0. */
  schema: Record<string, unknown>
  ttl_seconds?: number
}

/** Mutex: exactly one of `wait_seconds` (relative) or `resume_at` (ISO).
 *  Both nullable so the form can render an "empty" draft before the
 *  user has picked a mode. */
export interface WaitUntilConfig {
  wait_seconds?: number | null
  resume_at?: string | null
}

export interface WaitCallbackConfig {
  expected_schema?: Record<string, unknown>
  ttl_seconds?: number
}

export interface SubcompositionConfig {
  composition_id: string
  inputs?: Record<string, unknown>
}

export interface ApprovalConfig {
  message: string
  approver_user_ids?: string[]
  allowed_roles?: string[]
  response_schema?: Record<string, unknown>
  ttl_seconds?: number
  allow_self_approval?: boolean
}

// --- StepDraft discriminated union ----------------------------------------

interface StepDraftBase {
  step_id: string
  optional?: boolean
}

export interface ElicitStepDraft extends StepDraftBase {
  type: 'elicit'
  elicit: ElicitConfig
}

export interface WaitUntilStepDraft extends StepDraftBase {
  type: 'wait_until'
  wait_until: WaitUntilConfig
}

export interface WaitCallbackStepDraft extends StepDraftBase {
  type: 'wait_callback'
  wait_callback: WaitCallbackConfig
}

export interface SubcompositionStepDraft extends StepDraftBase {
  type: 'subcomposition'
  subcomposition: SubcompositionConfig
}

export interface ApprovalStepDraft extends StepDraftBase {
  type: 'approval'
  approval: ApprovalConfig
}

/** Legacy raw step — preserved verbatim, never edited in-place. */
export interface LegacyStepDraft extends StepDraftBase {
  type: LegacyStepType
  /** Full raw payload from the API (we round-trip it untouched). */
  raw: Record<string, unknown>
}

export type StepDraft =
  | ElicitStepDraft
  | WaitUntilStepDraft
  | WaitCallbackStepDraft
  | SubcompositionStepDraft
  | ApprovalStepDraft
  | LegacyStepDraft

// --- Builder state --------------------------------------------------------

export interface BuilderState {
  /** Composition.id when editing an existing draft, null when creating. */
  compositionId: string | null
  name: string
  description: string
  /** Raw JSON for the input_schema textarea. Validated at save time. */
  inputSchemaJson: string
  steps: StepDraft[]
  /** Lifecycle stage — preserved on edit so a production comp isn't
   *  silently demoted to `temporary`. Defaults to `'temporary'` on
   *  create. */
  status: CompositionStatus
  /** Visibility — preserved on edit so an `organization` comp isn't
   *  silently flipped to `private`. Defaults to `'private'` on create. */
  visibility: CompositionVisibility
  /** Set after a successful save; lets the modal close gracefully. */
  isSaving: boolean
}

// --- Reducer actions ------------------------------------------------------

export type BuilderAction =
  | { type: 'SET_HEADER'; field: 'name' | 'description'; value: string }
  | { type: 'SET_INPUT_SCHEMA'; value: string }
  | { type: 'ADD_STEP'; stepType: DurableStepType }
  | { type: 'UPDATE_STEP'; stepId: string; patch: Partial<StepDraft> }
  | { type: 'DELETE_STEP'; stepId: string }
  | { type: 'MOVE_STEP'; stepId: string; direction: 'up' | 'down' }
  | { type: 'SET_SAVING'; value: boolean }
  | { type: 'RESET'; state: BuilderState }

// --- StepForm contract ----------------------------------------------------

export interface StepFormProps<T> {
  value: T
  onChange: (next: T) => void
  disabled?: boolean
}
