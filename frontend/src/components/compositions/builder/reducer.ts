/**
 * Visual composition builder — reducer.
 *
 * Pure state transitions over `BuilderState`. Anticipates move /
 * duplicate / undo (Risque 2) by keeping all step ops keyed by
 * `step_id` — never by array index — so future undo/redo can store
 * action deltas verbatim.
 */

import type {
  BuilderAction,
  BuilderState,
  DurableStepType,
  StepDraft,
} from './types'

const EMPTY_INPUT_SCHEMA = `{
  "type": "object",
  "properties": {},
  "required": []
}`

export function createInitialState(): BuilderState {
  return {
    compositionId: null,
    name: '',
    description: '',
    inputSchemaJson: EMPTY_INPUT_SCHEMA,
    steps: [],
    status: 'temporary',
    visibility: 'private',
    isSaving: false,
  }
}

/** Build a fresh durable step draft with empty config. */
function makeStep(stepType: DurableStepType, stepId: string): StepDraft {
  switch (stepType) {
    case 'elicit':
      return {
        step_id: stepId,
        type: 'elicit',
        elicit: {
          message: '',
          schema: { type: 'object', properties: {}, required: [] },
        },
      }
    case 'wait_until':
      return {
        step_id: stepId,
        type: 'wait_until',
        wait_until: { wait_seconds: null, resume_at: null },
      }
    case 'wait_callback':
      return {
        step_id: stepId,
        type: 'wait_callback',
        wait_callback: {},
      }
    case 'subcomposition':
      return {
        step_id: stepId,
        type: 'subcomposition',
        subcomposition: { composition_id: '' },
      }
    case 'approval':
      return {
        step_id: stepId,
        type: 'approval',
        approval: { message: '', allowed_roles: [] },
      }
  }
}

/** Generate a step_id that doesn't collide with existing ones. */
function nextStepId(steps: StepDraft[]): string {
  const used = new Set(steps.map((s) => s.step_id))
  for (let i = 1; i < 10_000; i += 1) {
    const candidate = `step_${i}`
    if (!used.has(candidate)) return candidate
  }
  // Defensive: practically unreachable.
  return `step_${Date.now()}`
}

export function builderReducer(
  state: BuilderState,
  action: BuilderAction,
): BuilderState {
  switch (action.type) {
    case 'SET_HEADER':
      return { ...state, [action.field]: action.value }

    case 'SET_INPUT_SCHEMA':
      return { ...state, inputSchemaJson: action.value }

    case 'ADD_STEP': {
      const step = makeStep(action.stepType, nextStepId(state.steps))
      return { ...state, steps: [...state.steps, step] }
    }

    case 'UPDATE_STEP': {
      const steps = state.steps.map((s) => {
        if (s.step_id !== action.stepId) return s
        // The patch must preserve the discriminant (`type`) — the form
        // shouldn't try to change it, but we guard defensively.
        return { ...s, ...action.patch, type: s.type } as StepDraft
      })
      return { ...state, steps }
    }

    case 'DELETE_STEP':
      return {
        ...state,
        steps: state.steps.filter((s) => s.step_id !== action.stepId),
      }

    case 'MOVE_STEP': {
      const idx = state.steps.findIndex((s) => s.step_id === action.stepId)
      if (idx < 0) return state
      const targetIdx = action.direction === 'up' ? idx - 1 : idx + 1
      if (targetIdx < 0 || targetIdx >= state.steps.length) return state
      const next = state.steps.slice()
      const [moved] = next.splice(idx, 1)
      next.splice(targetIdx, 0, moved)
      return { ...state, steps: next }
    }

    case 'SET_SAVING':
      return { ...state, isSaving: action.value }

    case 'RESET':
      return action.state
  }
}
