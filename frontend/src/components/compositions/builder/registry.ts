/**
 * Visual composition builder — step form registry.
 *
 * Maps each durable step type to its `StepFormProps<T>` component.
 * `StepCard` looks up the form by `step.type` and renders it. Sprint
 * 2.0 ships `wait_until` only; the other four entries become non-null
 * in Sprint 2.1 (one PR per form).
 *
 * Keeping the registry typed as `Partial<...>` lets the builder render
 * a graceful fallback (read-only JSON viewer) for any durable step
 * whose form isn't shipped yet, mirroring the legacy-step behaviour.
 */

import type { ComponentType } from 'react'
import type { DurableStepType, StepFormProps } from './types'
import { WaitUntilStepForm } from './forms/WaitUntilStepForm'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyStepForm = ComponentType<StepFormProps<any>>

export const STEP_TYPE_FORMS: Partial<Record<DurableStepType, AnyStepForm>> = {
  wait_until: WaitUntilStepForm,
}
