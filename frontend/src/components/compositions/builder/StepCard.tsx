/**
 * StepCard — wrapper around a single StepDraft in the visual builder.
 *
 * Responsibilities:
 *   - Header: position badge + step type badge (from SUSPENSION_BADGES)
 *   - Move up / down + delete (delete gated by `useConfirm`)
 *   - Renders the step-type-specific form from `STEP_TYPE_FORMS`
 *   - For legacy `tool` / `transform` / `foreach`: read-only JSON view
 *     + "Edit raw JSON" CTA that closes the builder (caller's job).
 */

import { useTranslation } from 'react-i18next'
import {
  ArrowDownIcon,
  ArrowUpIcon,
  CodeBracketIcon,
  TrashIcon,
} from '@heroicons/react/24/outline'
import { Button, Card, useConfirm } from '@/components/ui'
import { SUSPENSION_BADGES } from '@/services/compositionExecutions'
import { cn } from '@/utils/cn'
import { STEP_TYPE_FORMS } from './registry'
import type { DurableStepType, StepDraft } from './types'

interface StepCardProps {
  step: StepDraft
  index: number
  total: number
  errors?: string[]
  disabled?: boolean
  onChange: (patch: Partial<StepDraft>) => void
  onMove: (direction: 'up' | 'down') => void
  onDelete: () => void
  /** Fired when the user clicks "Edit raw JSON" on a legacy step. */
  onEditRawJson?: () => void
}

const LEGACY_TYPES = new Set(['tool', 'transform', 'foreach'])

export function StepCard({
  step,
  index,
  total,
  errors,
  disabled,
  onChange,
  onMove,
  onDelete,
  onEditRawJson,
}: StepCardProps) {
  const { t } = useTranslation('compositions')
  const confirm = useConfirm()

  const isLegacy = LEGACY_TYPES.has(step.type)
  const durableType = step.type as DurableStepType
  const badge = !isLegacy ? SUSPENSION_BADGES[durableType] : null
  const FormComponent = !isLegacy ? STEP_TYPE_FORMS[durableType] : undefined

  const askDelete = async () => {
    const ok = await confirm({
      title: t('builder.deleteStep.title'),
      message: t('builder.deleteStep.message', { stepId: step.step_id }),
      confirmLabel: t('builder.deleteStep.confirm'),
      cancelLabel: t('builder.deleteStep.cancel'),
      danger: true,
    })
    if (ok) onDelete()
  }

  return (
    <Card padding="md" className="space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-orange text-white text-xs font-semibold flex-shrink-0">
            {index + 1}
          </span>
          <code className="text-xs text-gray-600 bg-gray-100 px-1.5 py-0.5 rounded">
            {step.step_id}
          </code>
          {badge ? (
            <span
              className={cn(
                'px-2 py-0.5 rounded text-xs font-medium',
                badge.bg,
                badge.text,
              )}
              title={t(`builder.stepTypes.${durableType}.title`) as string}
            >
              {badge.label}
            </span>
          ) : (
            <span
              className="px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700"
              title={t('builder.legacy.tooltip') as string}
            >
              {step.type}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <Button
            variant="ghost"
            size="sm"
            disabled={disabled || index === 0}
            onClick={() => onMove('up')}
            aria-label={t('builder.moveUp') as string}
            title={t('builder.moveUp') as string}
          >
            <ArrowUpIcon className="w-4 h-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={disabled || index === total - 1}
            onClick={() => onMove('down')}
            aria-label={t('builder.moveDown') as string}
            title={t('builder.moveDown') as string}
          >
            <ArrowDownIcon className="w-4 h-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={disabled}
            onClick={askDelete}
            className="text-red-600 hover:text-red-700"
            aria-label={t('builder.deleteStep.confirm') as string}
            title={t('builder.deleteStep.confirm') as string}
          >
            <TrashIcon className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {isLegacy ? (
        <div className="space-y-2">
          <p className="text-xs text-gray-600 font-serif">
            {t('builder.legacy.notice')}
          </p>
          <pre className="text-[11px] bg-gray-50 border border-gray-200 rounded p-3 overflow-auto max-h-48 font-mono text-gray-700">
            {JSON.stringify(
              (step as { raw: Record<string, unknown> }).raw,
              null,
              2,
            )}
          </pre>
          {onEditRawJson && (
            <Button variant="secondary" size="sm" onClick={onEditRawJson}>
              <CodeBracketIcon className="w-4 h-4 mr-1" />
              {t('builder.legacy.editRawJson')}
            </Button>
          )}
        </div>
      ) : FormComponent ? (
        <FormComponent
          // The form receives only its own slice. We trust the
          // discriminated union: when step.type === 'wait_until',
          // step.wait_until exists.
          value={
            (step as unknown as Record<string, unknown>)[
              durableType
            ] as unknown
          }
          onChange={(next: unknown) =>
            onChange({ [durableType]: next } as Partial<StepDraft>)
          }
          disabled={disabled}
        />
      ) : (
        <div className="text-xs text-gray-500 font-serif italic">
          {t('builder.formNotShipped', { type: durableType })}
        </div>
      )}

      {errors && errors.length > 0 && (
        <ul className="text-xs text-red-700 list-disc list-inside space-y-0.5">
          {errors.map((err) => (
            <li key={err}>{t(`builder.errors.${err}`, { defaultValue: err })}</li>
          ))}
        </ul>
      )}
    </Card>
  )
}
