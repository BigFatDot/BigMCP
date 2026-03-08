/**
 * Compositions Page
 *
 * Displays and manages tool compositions (multi-step workflows).
 * Compositions can be temporary, validated, or promoted to production.
 * Supports visibility toggle for Team organizations.
 */

import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  BoltIcon,
  PlayIcon,
  ArrowUpCircleIcon,
  TrashIcon,
  MagnifyingGlassIcon,
  FunnelIcon,
  CheckCircleIcon,
  XCircleIcon,
  UserIcon,
  BuildingOfficeIcon,
  EyeIcon,
  EyeSlashIcon,
} from '@heroicons/react/24/outline'
import { Button, Card, Badge } from '@/components/ui'
import { DynamicInputForm, ExecutionResultDisplay } from '@/components/compositions'
import { cn } from '@/utils/cn'
import { compositionsApi, type Composition, type CompositionVisibility, type CompositionExecuteResponse, type InputSchema } from '@/services/marketplace'
import { useOrganization } from '@/hooks/useAuth'
import toast from 'react-hot-toast'

type CompositionStatus = 'temporary' | 'validated' | 'production'

interface ExecuteModalProps {
  composition: Composition | null
  isOpen: boolean
  onClose: () => void
  onExecute: (params: Record<string, unknown>) => void
}

const STATUS_STYLES: Record<CompositionStatus, { bg: string; text: string; labelKey: string }> = {
  temporary: { bg: 'bg-gray-100', text: 'text-gray-700', labelKey: 'compositions.status.temporary' },
  validated: { bg: 'bg-blue-100', text: 'text-blue-700', labelKey: 'compositions.status.validated' },
  production: { bg: 'bg-green-100', text: 'text-green-700', labelKey: 'compositions.status.production' },
}

const VISIBILITY_STYLES: Record<CompositionVisibility, { icon: typeof UserIcon; labelKey: string; color: string }> = {
  private: { icon: UserIcon, labelKey: 'compositions.visibility.private', color: 'bg-gray-100 text-gray-600' },
  organization: { icon: BuildingOfficeIcon, labelKey: 'compositions.visibility.organization', color: 'bg-purple-100 text-purple-700' },
  public: { icon: EyeIcon, labelKey: 'compositions.visibility.public', color: 'bg-blue-100 text-blue-700' },
}

function CompositionCard({
  composition,
  onExecute,
  onPromote,
  onDelete,
  onToggleVisibility,
  canEdit,
  isTeamOrg,
}: {
  composition: Composition
  onExecute: () => void
  onPromote: () => void
  onDelete: () => void
  onToggleVisibility: () => void
  canEdit: boolean
  isTeamOrg: boolean
}) {
  const { t } = useTranslation('dashboard')
  const statusStyle = STATUS_STYLES[composition.status]
  const visibility = composition.visibility || 'private'
  const visibilityStyle = VISIBILITY_STYLES[visibility]
  const VisibilityIcon = visibilityStyle.icon
  const stepCount = composition.steps?.length || 0
  const stepTools = composition.steps?.map((s) => s.tool).join(' → ') || t('compositions.noSteps')
  const executionCount = (composition.extra_metadata?.execution_count as number) || 0

  return (
    <Card padding="lg" className="hover:shadow-md transition-shadow flex flex-col h-full">
      {/* Header: Icon + Title + Badges */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 bg-orange-100 rounded-full flex items-center justify-center flex-shrink-0">
            <BoltIcon className="w-4 h-4 text-orange" />
          </div>
          <h3 className="text-lg font-bold text-gray-900">{composition.name}</h3>
        </div>
        <div className="flex flex-col gap-1 items-end flex-shrink-0">
          <span className={cn('px-2 py-1 rounded text-xs font-medium', statusStyle.bg, statusStyle.text)}>
            {t(statusStyle.labelKey)}
          </span>
          {isTeamOrg && (
            <span className={cn('px-2 py-0.5 rounded text-xs font-medium flex items-center gap-1', visibilityStyle.color)}>
              <VisibilityIcon className="w-3 h-3" />
              {t(visibilityStyle.labelKey)}
            </span>
          )}
        </div>
      </div>

      {/* Description */}
      {composition.description && (
        <p className="text-sm text-gray-600 font-serif mb-3">
          {composition.description}
        </p>
      )}

      {/* Steps preview */}
      <div className="flex items-start gap-2 text-sm text-gray-600 mb-3">
        <span className="font-medium flex-shrink-0">{t('compositions.steps', { count: stepCount })}</span>
        {stepCount > 0 && (
          <>
            <span className="flex-shrink-0">-</span>
            <span className="break-words">{stepTools}</span>
          </>
        )}
      </div>

      {/* Stats and Permissions - Fixed at bottom above actions */}
      <div className="mt-auto flex items-center gap-4 text-xs text-gray-500 pb-4">
        <span>{t('compositions.executedTimes', { count: executionCount })}</span>
        <span>{t('compositions.created', { date: new Date(composition.created_at).toLocaleDateString() })}</span>
        {composition.can_execute && (
          <span className="text-green-600 flex items-center gap-1">
            <CheckCircleIcon className="w-3 h-3" /> {t('compositions.canExecute')}
          </span>
        )}
        {!composition.can_execute && (
          <span className="text-gray-400 flex items-center gap-1">
            <XCircleIcon className="w-3 h-3" /> {t('compositions.noExecutePermission')}
          </span>
        )}
      </div>

      {/* Actions - Fixed at bottom */}
      <div className="pt-4 border-t border-gray-100 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          {composition.can_execute && (
            <Button variant="primary" size="sm" onClick={onExecute}>
              <PlayIcon className="w-4 h-4 mr-1" />
              <span className="hidden sm:inline">{t('compositions.execute')}</span>
            </Button>
          )}
          {canEdit && composition.status !== 'production' && (
            <Button variant="secondary" size="sm" onClick={onPromote}>
              <ArrowUpCircleIcon className="w-4 h-4 mr-1" />
              <span className="hidden sm:inline">{composition.status === 'temporary' ? t('compositions.validate') : t('compositions.promote')}</span>
            </Button>
          )}
          {/* Visibility Toggle for Team orgs */}
          {canEdit && isTeamOrg && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onToggleVisibility}
              title={visibility === 'private' ? t('compositions.shareWithTeam') : t('compositions.makePrivate')}
              className={cn(
                visibility === 'organization' ? 'text-purple-600 hover:text-purple-700' : 'text-gray-500'
              )}
            >
              {visibility === 'private' ? (
                <EyeSlashIcon className="w-4 h-4" />
              ) : (
                <EyeIcon className="w-4 h-4" />
              )}
            </Button>
          )}
        </div>
        {canEdit && (
          <Button variant="ghost" size="sm" onClick={onDelete} className="text-red-600 hover:text-red-700">
            <TrashIcon className="w-4 h-4" />
          </Button>
        )}
      </div>
    </Card>
  )
}

type ExecutePhase = 'input' | 'executing' | 'result'

function ExecuteModal({ composition, isOpen, onClose, onExecute }: ExecuteModalProps) {
  const { t } = useTranslation('dashboard')
  const [phase, setPhase] = useState<ExecutePhase>('input')
  const [inputs, setInputs] = useState<Record<string, unknown>>({})
  const [result, setResult] = useState<CompositionExecuteResponse | null>(null)

  // Reset state when modal opens/closes or composition changes
  useEffect(() => {
    if (isOpen) {
      setPhase('input')
      setInputs({})
      setResult(null)

      // Pre-fill defaults from input_schema
      const schema = composition?.input_schema as InputSchema | undefined
      if (schema?.properties) {
        const defaults: Record<string, unknown> = {}
        Object.entries(schema.properties).forEach(([key, prop]) => {
          if (prop.default !== undefined) {
            defaults[key] = prop.default
          }
        })
        setInputs(defaults)
      }
    }
  }, [isOpen, composition])

  if (!isOpen || !composition) return null

  const inputSchema = composition.input_schema as InputSchema | undefined
  const hasInputs = inputSchema?.properties && Object.keys(inputSchema.properties).length > 0
  const steps = composition.steps || []

  const handleExecute = async () => {
    setPhase('executing')
    try {
      const response = await compositionsApi.execute(composition.id, inputs)
      setResult(response)
      setPhase('result')

      // Call parent onExecute for stats update
      onExecute(inputs)
    } catch (error: any) {
      setResult({
        composition_id: composition.id,
        status: 'failed',
        outputs: {},
        duration_ms: 0,
        step_results: [],
        error: error.response?.data?.detail || error.message || t('compositions.results.unknownError')
      })
      setPhase('result')
    }
  }

  const handleReExecute = () => {
    setPhase('input')
    setResult(null)
  }

  const handleInputChange = (key: string, value: unknown) => {
    setInputs(prev => ({ ...prev, [key]: value }))
  }

  // Validate required fields
  const requiredFields = inputSchema?.required || []
  const isValid = requiredFields.every(field => {
    const value = inputs[field]
    return value !== undefined && value !== null && value !== ''
  })

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-gray-200 flex-shrink-0">
          <h2 className="text-xl font-bold text-gray-900">
            {phase === 'result'
              ? t('compositions.executeModal.resultsTitle')
              : t('compositions.executeModal.title')
            }
          </h2>
          <p className="text-sm text-gray-600 mt-1">{composition.name}</p>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1">
          {/* Phase: Input */}
          {phase === 'input' && (
            <>
              {/* Input form if has inputs */}
              {hasInputs && (
                <div className="mb-6">
                  <h3 className="text-sm font-semibold text-gray-700 mb-3">
                    {t('compositions.executeModal.inputsTitle')}
                  </h3>
                  <DynamicInputForm
                    inputSchema={inputSchema!}
                    values={inputs}
                    onChange={handleInputChange}
                  />
                </div>
              )}

              {/* Steps preview */}
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-3">
                  {t('compositions.executeModal.stepsPreview')}
                </h3>
                {steps.length > 0 ? (
                  <div className="space-y-2">
                    {steps.map((step, index) => (
                      <div key={step.id} className="flex items-center gap-3">
                        <div className="w-6 h-6 rounded-full bg-orange text-white flex items-center justify-center text-sm font-medium">
                          {index + 1}
                        </div>
                        <div className="flex-1 p-3 bg-gray-50 rounded-lg">
                          <p className="font-medium text-gray-900">{step.tool}</p>
                          <p className="text-xs text-gray-500">
                            {t('compositions.parameters', { count: Object.keys(step.params || {}).length })}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-gray-500 text-center py-4">{t('compositions.noSteps')}</p>
                )}
              </div>
            </>
          )}

          {/* Phase: Executing */}
          {phase === 'executing' && (
            <div className="flex flex-col items-center justify-center py-12">
              <div className="w-12 h-12 border-4 border-gray-200 border-t-orange rounded-full animate-spin mb-4" />
              <p className="text-gray-600 font-medium">{t('compositions.executing')}</p>
              <p className="text-sm text-gray-500 mt-1">
                {t('compositions.executeModal.executingSteps', { count: steps.length })}
              </p>
            </div>
          )}

          {/* Phase: Result */}
          {phase === 'result' && result && (
            <ExecutionResultDisplay result={result} />
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-gray-200 flex justify-end gap-3 flex-shrink-0">
          {phase === 'input' && (
            <>
              <Button variant="secondary" onClick={onClose}>
                {t('compositions.cancel')}
              </Button>
              <Button
                variant="primary"
                onClick={handleExecute}
                disabled={hasInputs && !isValid}
              >
                {t('compositions.execute')}
              </Button>
            </>
          )}

          {phase === 'executing' && (
            <Button variant="secondary" onClick={onClose} disabled>
              {t('compositions.cancel')}
            </Button>
          )}

          {phase === 'result' && (
            <>
              <Button variant="secondary" onClick={onClose}>
                {t('compositions.close')}
              </Button>
              <Button variant="primary" onClick={handleReExecute}>
                {t('compositions.executeAgain')}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export function CompositionsPage() {
  const { t } = useTranslation('dashboard')
  const { isTeamOrg } = useOrganization()
  const [compositions, setCompositions] = useState<Composition[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<CompositionStatus | 'all'>('all')
  const [visibilityFilter, setVisibilityFilter] = useState<'all' | 'mine' | 'team'>('all')
  const [selectedComposition, setSelectedComposition] = useState<Composition | null>(null)
  const [showExecuteModal, setShowExecuteModal] = useState(false)

  // Load compositions from API
  const loadCompositions = useCallback(async () => {
    setIsLoading(true)
    try {
      const filters: { status?: string; visibility?: string; mine_only?: boolean } = {}
      if (statusFilter !== 'all') {
        filters.status = statusFilter
      }
      if (visibilityFilter === 'mine') {
        filters.mine_only = true
      } else if (visibilityFilter === 'team') {
        filters.visibility = 'organization'
      }
      const result = await compositionsApi.list(filters)
      setCompositions(result.compositions)
    } catch (error) {
      console.error('Failed to load compositions:', error)
      toast.error('Failed to load compositions')
    } finally {
      setIsLoading(false)
    }
  }, [statusFilter, visibilityFilter])

  useEffect(() => {
    loadCompositions()
  }, [loadCompositions])

  const filteredCompositions = compositions.filter((comp) => {
    const matchesSearch =
      searchQuery === '' ||
      comp.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (comp.description || '').toLowerCase().includes(searchQuery.toLowerCase())

    return matchesSearch
  })

  const handleExecute = (composition: Composition) => {
    setSelectedComposition(composition)
    setShowExecuteModal(true)
  }

  const handlePromote = async (composition: Composition) => {
    const newStatus: 'validated' | 'production' =
      composition.status === 'temporary' ? 'validated' : 'production'

    if (!confirm(t('compositions.promoteConfirm', { name: composition.name, status: t(`compositions.status.${newStatus}`) }))) {
      return
    }

    try {
      const updated = await compositionsApi.promote(composition.id, newStatus)
      toast.success(t('compositions.promotedSuccess', { status: t(`compositions.status.${newStatus}`) }))
      setCompositions((prev) =>
        prev.map((c) => (c.id === composition.id ? updated : c))
      )
    } catch (error: any) {
      toast.error(error.response?.data?.detail || t('compositions.results.failed'))
    }
  }

  const handleDelete = async (composition: Composition) => {
    if (!confirm(t('compositions.deleteConfirm', { name: composition.name }))) {
      return
    }

    try {
      await compositionsApi.delete(composition.id)
      toast.success(t('compositions.deletedSuccess'))
      setCompositions((prev) => prev.filter((c) => c.id !== composition.id))
    } catch (error: any) {
      toast.error(error.response?.data?.detail || t('compositions.results.failed'))
    }
  }

  const handleExecuteConfirm = async (params: Record<string, unknown>) => {
    // Just reload to update execution count - modal handles the execution
    loadCompositions()
  }

  const handleToggleVisibility = async (composition: Composition) => {
    const newVisibility: CompositionVisibility =
      composition.visibility === 'private' ? 'organization' : 'private'

    try {
      const updated = await compositionsApi.update(composition.id, { visibility: newVisibility })
      toast.success(
        newVisibility === 'organization'
          ? t('compositions.sharedSuccess')
          : t('compositions.madePrivate')
      )
      setCompositions((prev) =>
        prev.map((c) => (c.id === composition.id ? updated : c))
      )
    } catch (error: any) {
      toast.error(error.response?.data?.detail || t('compositions.results.failed'))
    }
  }

  return (
    <div className="container py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-gray-900 mb-2">{t('compositions.title')}</h1>
        <p className="text-lg text-gray-600 font-serif">
          {t('compositions.subtitle')}
        </p>
      </div>

      {/* Filters */}
      <div className="mb-6 flex flex-col sm:flex-row items-start sm:items-center gap-3 sm:gap-4">
        <div className="relative flex-1 w-full sm:max-w-md">
          <MagnifyingGlassIcon className="w-5 h-5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder={t('compositions.search')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange"
          />
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <FunnelIcon className="w-5 h-5 text-gray-400 hidden sm:block" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as CompositionStatus | 'all')}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange text-sm"
          >
            <option value="all">{t('compositions.filters.allStatus')}</option>
            <option value="temporary">{t('compositions.status.temporary')}</option>
            <option value="validated">{t('compositions.status.validated')}</option>
            <option value="production">{t('compositions.status.production')}</option>
          </select>
          {isTeamOrg && (
            <select
              value={visibilityFilter}
              onChange={(e) => setVisibilityFilter(e.target.value as 'all' | 'mine' | 'team')}
              className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange text-sm"
            >
              <option value="all">{t('compositions.filters.allCompositions')}</option>
              <option value="mine">{t('compositions.filters.myCompositions')}</option>
              <option value="team">{t('compositions.filters.teamShared')}</option>
            </select>
          )}
        </div>
      </div>

      {/* Compositions Grid */}
      {isLoading ? (
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-gray-300 border-t-orange mx-auto" />
        </div>
      ) : filteredCompositions.length === 0 ? (
        <Card padding="lg">
          <div className="text-center py-12">
            <BoltIcon className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-gray-900 mb-2">{t('compositions.empty.title')}</h3>
            <p className="text-gray-600 font-serif mb-6 max-w-md mx-auto">
              {searchQuery || statusFilter !== 'all'
                ? t('compositions.empty.noMatch')
                : t('compositions.empty.description')}
            </p>
          </div>
        </Card>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4 items-stretch">
          {filteredCompositions.map((composition) => (
            <CompositionCard
              key={composition.id}
              composition={composition}
              onExecute={() => handleExecute(composition)}
              onPromote={() => handlePromote(composition)}
              onDelete={() => handleDelete(composition)}
              onToggleVisibility={() => handleToggleVisibility(composition)}
              canEdit={composition.can_edit ?? false}
              isTeamOrg={isTeamOrg}
            />
          ))}
        </div>
      )}

      {/* Execute Modal */}
      <ExecuteModal
        composition={selectedComposition}
        isOpen={showExecuteModal}
        onClose={() => {
          setShowExecuteModal(false)
          setSelectedComposition(null)
        }}
        onExecute={handleExecuteConfirm}
      />
    </div>
  )
}
