/**
 * Execution Result Display Component
 *
 * Displays composition execution results in a structured format:
 * - Status banner (success/partial/failed)
 * - Timeline of steps with their individual statuses
 * - Expandable details for each step
 * - Final output display
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  CheckCircleIcon,
  XCircleIcon,
  ExclamationTriangleIcon,
  ClockIcon,
  ChevronDownIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline'
import { cn } from '@/utils/cn'
import type { CompositionExecuteResponse, StepResult } from '@/services/marketplace'

interface ExecutionResultDisplayProps {
  result: CompositionExecuteResponse
  className?: string
}

interface StepCardProps {
  step: StepResult
  index: number
}

/**
 * Status icon component.
 */
function StatusIcon({ status, className }: { status: string; className?: string }) {
  switch (status) {
    case 'success':
      return <CheckCircleIcon className={cn("w-5 h-5 text-green-500", className)} />
    case 'partial':
      return <ExclamationTriangleIcon className={cn("w-5 h-5 text-amber-500", className)} />
    case 'failed':
    case 'error':
      return <XCircleIcon className={cn("w-5 h-5 text-red-500", className)} />
    case 'skipped':
      return <ClockIcon className={cn("w-5 h-5 text-gray-400", className)} />
    default:
      return <ClockIcon className={cn("w-5 h-5 text-gray-400", className)} />
  }
}

/**
 * Format milliseconds to human readable string.
 */
function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}min`
}

/**
 * Individual step result card.
 */
function StepCard({ step, index }: StepCardProps) {
  const { t } = useTranslation('dashboard')
  const [isExpanded, setIsExpanded] = useState(step.status === 'failed')

  const statusColors = {
    success: 'border-green-200 bg-green-50',
    failed: 'border-red-200 bg-red-50',
    skipped: 'border-gray-200 bg-gray-50',
  }

  return (
    <div
      className={cn(
        "border rounded-lg overflow-hidden",
        statusColors[step.status as keyof typeof statusColors] || 'border-gray-200'
      )}
    >
      {/* Header - always visible */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 flex items-center gap-3 hover:bg-black/5 transition-colors"
      >
        {/* Step number */}
        <div className={cn(
          "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold",
          step.status === 'success' && "bg-green-500 text-white",
          step.status === 'failed' && "bg-red-500 text-white",
          step.status === 'skipped' && "bg-gray-400 text-white"
        )}>
          {index}
        </div>

        {/* Tool name */}
        <div className="flex-1 text-left">
          <p className="font-medium text-gray-900">{step.tool}</p>
          <p className="text-xs text-gray-500">
            {step.step_id} • {formatDuration(step.duration_ms)}
            {step.retries && step.retries > 0 && (
              <span className="ml-2 text-amber-600">
                ({t('compositions.results.retries', { count: step.retries })})
              </span>
            )}
          </p>
        </div>

        {/* Status icon */}
        <StatusIcon status={step.status} />

        {/* Expand icon */}
        {isExpanded ? (
          <ChevronDownIcon className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronRightIcon className="w-4 h-4 text-gray-400" />
        )}
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="px-4 pb-4 border-t border-gray-200">
          {/* Error message */}
          {step.error && (
            <div className="mt-3 p-3 bg-red-100 border border-red-200 rounded-lg">
              <p className="text-sm text-red-800 font-medium">
                {t('compositions.results.error')}
              </p>
              <p className="text-sm text-red-700 mt-1 font-mono">
                {step.error}
              </p>
            </div>
          )}

          {/* Result */}
          {step.result && Object.keys(step.result).length > 0 && (
            <div className="mt-3">
              <p className="text-sm font-medium text-gray-700 mb-2">
                {t('compositions.results.stepOutput')}
              </p>
              <pre className="p-3 bg-gray-900 text-gray-100 rounded-lg overflow-auto text-xs font-mono max-h-48">
                {JSON.stringify(step.result, null, 2)}
              </pre>
            </div>
          )}

          {/* No result message for success without data */}
          {step.status === 'success' && (!step.result || Object.keys(step.result).length === 0) && (
            <p className="mt-3 text-sm text-gray-500 italic">
              {t('compositions.results.noOutput')}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Main execution result display component.
 */
export function ExecutionResultDisplay({ result, className }: ExecutionResultDisplayProps) {
  const { t } = useTranslation('dashboard')
  const [showOutput, setShowOutput] = useState(false)

  // Status banner styles
  const statusBannerStyles = {
    success: 'bg-green-50 border-green-200 text-green-800',
    partial: 'bg-amber-50 border-amber-200 text-amber-800',
    failed: 'bg-red-50 border-red-200 text-red-800',
    error: 'bg-red-50 border-red-200 text-red-800',
  }

  const statusLabels = {
    success: t('compositions.results.statusSuccess'),
    partial: t('compositions.results.statusPartial'),
    failed: t('compositions.results.statusFailed'),
    error: t('compositions.results.statusFailed'),
  }

  const successCount = result.step_results.filter(s => s.status === 'success').length
  const failedCount = result.step_results.filter(s => s.status === 'failed').length
  const totalSteps = result.step_results.length

  return (
    <div className={cn("space-y-4", className)}>
      {/* Status Banner */}
      <div className={cn(
        "p-4 rounded-lg border flex items-center gap-4",
        statusBannerStyles[result.status as keyof typeof statusBannerStyles]
      )}>
        <StatusIcon status={result.status} className="w-8 h-8" />
        <div className="flex-1">
          <p className="font-bold text-lg">
            {statusLabels[result.status as keyof typeof statusLabels]}
          </p>
          <p className="text-sm opacity-80">
            {t('compositions.results.summary', {
              success: successCount,
              failed: failedCount,
              total: totalSteps,
              duration: formatDuration(result.duration_ms)
            })}
          </p>
        </div>
      </div>

      {/* Global Error */}
      {result.error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="font-medium text-red-800">{t('compositions.results.globalError')}</p>
          <p className="text-sm text-red-700 mt-1">{result.error}</p>
        </div>
      )}

      {/* Steps Timeline */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">
          {t('compositions.results.stepsTitle')}
        </h3>
        <div className="space-y-2">
          {result.step_results.map((step, index) => (
            <StepCard key={step.step_id} step={step} index={index + 1} />
          ))}
        </div>
      </div>

      {/* Final Output */}
      {result.outputs && Object.keys(result.outputs).length > 0 && (
        <div>
          <button
            onClick={() => setShowOutput(!showOutput)}
            className="flex items-center gap-2 text-sm font-semibold text-gray-700 hover:text-gray-900"
          >
            {showOutput ? (
              <ChevronDownIcon className="w-4 h-4" />
            ) : (
              <ChevronRightIcon className="w-4 h-4" />
            )}
            {t('compositions.results.finalOutput')}
          </button>

          {showOutput && (
            <pre className="mt-2 p-4 bg-gray-900 text-gray-100 rounded-lg overflow-auto text-sm font-mono max-h-64">
              {JSON.stringify(result.outputs, null, 2)}
            </pre>
          )}
        </div>
      )}

      {/* Execution metadata */}
      <div className="text-xs text-gray-500 flex items-center gap-4">
        {result.execution_id && (
          <span>ID: {result.execution_id.slice(0, 8)}...</span>
        )}
        {result.started_at && (
          <span>
            {t('compositions.results.startedAt')}: {new Date(result.started_at).toLocaleTimeString()}
          </span>
        )}
        {result.completed_at && (
          <span>
            {t('compositions.results.completedAt')}: {new Date(result.completed_at).toLocaleTimeString()}
          </span>
        )}
      </div>
    </div>
  )
}

export default ExecutionResultDisplay
