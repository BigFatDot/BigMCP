/**
 * Visual composition builder — step form registry.
 *
 * Maps each durable step type to its `StepFormProps<T>` component.
 * `StepCard` looks up the form by `step.type` and renders it. Fan-out
 * Sprint 2.1 wires the four remaining forms (elicit, wait_callback,
 * subcomposition, approval) authored in parallel; the integrator
 * (this module) is the only place they get composed together.
 *
 * Keeping the registry typed as `Partial<...>` keeps the option of
 * adding a step type whose form isn't shipped yet — `StepCard` falls
 * back to the read-only JSON viewer, mirroring legacy-step behaviour.
 */

import type { ComponentType } from 'react'
import type { DurableStepType, StepFormProps } from './types'
import { WaitUntilStepForm } from './forms/WaitUntilStepForm'
import { ElicitStepForm } from './forms/ElicitStepForm'
import { WaitCallbackStepForm } from './forms/WaitCallbackStepForm'
import { SubcompositionStepForm } from './forms/SubcompositionStepForm'
import { ApprovalStepForm } from './forms/ApprovalStepForm'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyStepForm = ComponentType<StepFormProps<any>>

export const STEP_TYPE_FORMS: Partial<Record<DurableStepType, AnyStepForm>> = {
  wait_until: WaitUntilStepForm,
  elicit: ElicitStepForm,
  wait_callback: WaitCallbackStepForm,
  subcomposition: SubcompositionStepForm,
  approval: ApprovalStepForm,
}
