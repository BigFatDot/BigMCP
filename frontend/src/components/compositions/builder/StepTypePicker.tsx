/**
 * StepTypePicker — modal that surfaces the 5 durable step types.
 *
 * The builder NEVER offers legacy `tool` / `transform` / `foreach`
 * here (Risque 3). Those still appear when editing a legacy compo
 * but can't be added anew.
 *
 * Labels + colours come from `SUSPENSION_BADGES` so the picker stays
 * in sync with the executions list and detail pages without a second
 * source of truth.
 */

import { useTranslation } from 'react-i18next'
import { Modal } from '@/components/ui'
import { SUSPENSION_BADGES } from '@/services/compositionExecutions'
import { cn } from '@/utils/cn'
import type { DurableStepType } from './types'

const ORDERED_TYPES: DurableStepType[] = [
  'elicit',
  'wait_until',
  'wait_callback',
  'subcomposition',
  'approval',
]

interface StepTypePickerProps {
  isOpen: boolean
  onClose: () => void
  onPick: (stepType: DurableStepType) => void
  /** Disable types whose StepForm isn't shipped yet. */
  enabledTypes: ReadonlySet<DurableStepType>
}

export function StepTypePicker({
  isOpen,
  onClose,
  onPick,
  enabledTypes,
}: StepTypePickerProps) {
  const { t } = useTranslation('compositions')

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t('builder.picker.title')}
      description={t('builder.picker.description')}
      size="md"
    >
      <ul className="space-y-2">
        {ORDERED_TYPES.map((stepType) => {
          const badge = SUSPENSION_BADGES[stepType]
          const enabled = enabledTypes.has(stepType)
          return (
            <li key={stepType}>
              <button
                type="button"
                onClick={() => {
                  if (!enabled) return
                  onPick(stepType)
                  onClose()
                }}
                disabled={!enabled}
                className={cn(
                  'w-full text-left border rounded-lg p-3 flex items-start gap-3',
                  'transition focus:outline-none focus:ring-2 focus:ring-orange',
                  enabled
                    ? 'border-gray-200 hover:border-orange hover:bg-orange-50/40 bg-white'
                    : 'border-gray-200 bg-gray-50 cursor-not-allowed opacity-60',
                )}
              >
                <span
                  className={cn(
                    'inline-flex items-center px-2 py-0.5 rounded text-xs font-medium flex-shrink-0',
                    badge.bg,
                    badge.text,
                  )}
                >
                  {badge.label}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-gray-900">
                    {t(`builder.stepTypes.${stepType}.title`)}
                  </div>
                  <div className="text-xs text-gray-600 font-serif">
                    {t(`builder.stepTypes.${stepType}.description`)}
                  </div>
                </div>
                {!enabled && (
                  <span className="text-[10px] uppercase tracking-wide text-gray-400 self-center">
                    {t('builder.picker.comingSoon')}
                  </span>
                )}
              </button>
            </li>
          )
        })}
      </ul>
    </Modal>
  )
}
