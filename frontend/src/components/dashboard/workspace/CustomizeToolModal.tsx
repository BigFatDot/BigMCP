/**
 * CustomizeToolModal — turn a generic tool into a specialized "Custom tool".
 *
 * Pattern: a generic tool like ``grist_create_record(table_id, fields)``
 * is unwieldy for the LLM (it must know the upstream API + table). The
 * user wraps it by freezing the boring params (table_id="Appointments",
 * fields shape baked in) and exposing a clean interface
 * ``add_appointment(date, title, attendee)``.
 *
 * Storage: a 1-step composition with ``extra_metadata.kind='custom_tool'``
 * — same plumbing as multi-step workflows, no new backend model. The
 * compositions list page filters wrappers vs workflows by that flag.
 */

import { useEffect, useMemo, useState } from 'react'
import {
  XMarkIcon,
  ExclamationTriangleIcon,
  WrenchScrewdriverIcon,
} from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { Card, Button } from '@/components/ui'
import { compositionsApi, type ToolInfo } from '@/services/marketplace'

interface ParamDef {
  name: string
  jsonType: 'string' | 'number' | 'integer' | 'boolean' | 'object' | 'array' | 'unknown'
  description: string | null
  required: boolean
  defaultValue: unknown
  enumValues?: unknown[]
  rawSchema: Record<string, unknown>
}

type ParamMode = 'fixed' | 'expose' | 'hidden'

interface ParamConfig {
  mode: ParamMode
  fixedValue: string  // user-entered as text; coerced on save
  exposedName: string
  exposedDescription: string
  hiddenDefault: string
}

interface Props {
  source: ToolInfo
  prefixedName: string  // e.g., "Grist__create_record"
  isOpen: boolean
  onClose: () => void
  onCreated?: (compositionId: string) => void
}

function _flattenSchema(schema: Record<string, unknown> | undefined): ParamDef[] {
  if (!schema || typeof schema !== 'object') return []
  const properties = (schema.properties ?? {}) as Record<string, Record<string, unknown>>
  const required = new Set(((schema.required ?? []) as string[]) || [])
  const out: ParamDef[] = []
  for (const [name, def] of Object.entries(properties)) {
    const t = def?.type
    let jt: ParamDef['jsonType'] = 'unknown'
    if (t === 'string' || t === 'number' || t === 'integer' || t === 'boolean' || t === 'object' || t === 'array') {
      jt = t
    }
    out.push({
      name,
      jsonType: jt,
      description: (def?.description as string) ?? null,
      required: required.has(name),
      defaultValue: def?.default,
      enumValues: def?.enum as unknown[] | undefined,
      rawSchema: def,
    })
  }
  return out
}

function _coerce(value: string, jsonType: ParamDef['jsonType']): unknown {
  if (value === '') return undefined
  if (jsonType === 'boolean') {
    return value === 'true' || value === '1'
  }
  if (jsonType === 'number' || jsonType === 'integer') {
    const n = Number(value)
    return Number.isFinite(n) ? n : value
  }
  if (jsonType === 'object' || jsonType === 'array') {
    try {
      return JSON.parse(value)
    } catch {
      return value
    }
  }
  return value
}

function _slugify(s: string): string {
  return s.replace(/[^a-zA-Z0-9_]/g, '_').replace(/_+/g, '_').replace(/^_|_$/g, '')
}

export function CustomizeToolModal({ source, prefixedName, isOpen, onClose, onCreated }: Props) {
  const params = useMemo(
    () => _flattenSchema(source.parameters_schema as Record<string, unknown> | undefined),
    [source.parameters_schema],
  )

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [config, setConfig] = useState<Record<string, ParamConfig>>({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Reset state when the modal opens for a new source
  useEffect(() => {
    if (!isOpen) return
    const initial: Record<string, ParamConfig> = {}
    for (const p of params) {
      // Default policy: required scalar params are exposed; everything
      // else is hidden with the upstream default. The user can flip any
      // row to "fixed" with a single click.
      const isComplex = p.jsonType === 'object' || p.jsonType === 'array' || p.jsonType === 'unknown'
      const defaultMode: ParamMode = p.required && !isComplex ? 'expose' : 'hidden'
      initial[p.name] = {
        mode: defaultMode,
        fixedValue: p.defaultValue !== undefined ? String(p.defaultValue) : '',
        exposedName: p.name,
        exposedDescription: p.description || '',
        hiddenDefault: p.defaultValue !== undefined ? String(p.defaultValue) : '',
      }
    }
    setConfig(initial)
    setName('')
    setDescription(source.description || '')
    setError(null)
  }, [isOpen, source.id, params, source.description])

  const update = (paramName: string, patch: Partial<ParamConfig>) => {
    setConfig((prev) => ({ ...prev, [paramName]: { ...prev[paramName], ...patch } }))
  }

  const handleSave = async () => {
    setError(null)
    const cleanName = _slugify(name)
    if (!cleanName) {
      setError('Choose a name for your custom tool.')
      return
    }
    if (cleanName.length > 60) {
      setError('Name must be 60 chars or less after sanitization.')
      return
    }

    // Build the composition payload
    const stepParameters: Record<string, unknown> = {}
    const exposedProps: Record<string, unknown> = {}
    const exposedRequired: string[] = []

    for (const p of params) {
      const cfg = config[p.name]
      if (!cfg) continue
      if (cfg.mode === 'fixed') {
        const val = _coerce(cfg.fixedValue, p.jsonType)
        if (val !== undefined) stepParameters[p.name] = val
      } else if (cfg.mode === 'hidden') {
        const val = _coerce(cfg.hiddenDefault, p.jsonType)
        if (val !== undefined) stepParameters[p.name] = val
      } else if (cfg.mode === 'expose') {
        const exposedKey = _slugify(cfg.exposedName) || p.name
        if (exposedProps[exposedKey]) {
          setError(`Duplicate exposed parameter name: ${exposedKey}`)
          return
        }
        const propSchema: Record<string, unknown> = {
          type: p.jsonType === 'unknown' ? 'string' : p.jsonType,
        }
        if (cfg.exposedDescription) propSchema.description = cfg.exposedDescription
        if (p.enumValues) propSchema.enum = p.enumValues
        if (p.defaultValue !== undefined) propSchema.default = p.defaultValue
        exposedProps[exposedKey] = propSchema
        if (p.required) exposedRequired.push(exposedKey)
        stepParameters[p.name] = `\${input.${exposedKey}}`
      }
    }

    setSaving(true)
    try {
      const created = await compositionsApi.create({
        name: cleanName,
        description: description || `Custom tool wrapping ${prefixedName}`,
        visibility: 'private',
        steps: [
          {
            // Runtime convention: step_id + tool + parameters.
            // The Pydantic schema in the backend uses `id` / `params`
            // historically but the executor only reads step_id /
            // parameters. We send the runtime shape so it actually
            // works at execute time.
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            ...({ step_id: '1', tool: prefixedName, parameters: stepParameters } as any),
          },
        ],
        data_mappings: [],
        input_schema: {
          type: 'object',
          properties: exposedProps,
          required: exposedRequired,
        },
        server_bindings: {},
        // Generic wrappers carry no extra runtime requirement — the
        // executor routes by the prefixed tool name. Hide kind in
        // extra_metadata so the compositions page can split wrappers
        // from workflows in the UI without backend changes.
        extra_metadata: {
          kind: 'custom_tool',
          source_tool_id: source.id,
          source_tool_name: prefixedName,
          source_server_name: source.server_name,
        },
        // Wrappers are usually ready to ship — start as 'validated' so
        // the user can promote to production with one click rather than
        // going through 'temporary' first.
        status: 'validated',
      })
      toast.success(
        `Custom tool "${cleanName}" created. Promote to production to expose it via MCP.`,
      )
      onCreated?.(created.id)
      onClose()
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <Card className="w-full max-w-3xl max-h-[90vh] flex flex-col bg-white">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 p-5 border-b border-gray-200">
          <div className="flex items-start gap-3 min-w-0">
            <WrenchScrewdriverIcon className="h-6 w-6 text-orange flex-shrink-0 mt-0.5" />
            <div className="min-w-0">
              <h2 className="text-lg font-bold text-gray-900">Customize tool</h2>
              <p className="text-xs text-gray-500 mt-0.5 truncate">
                Source: <span className="font-mono">{prefixedName}</span>
                {source.server_name && (
                  <span className="text-gray-400"> · {source.server_name}</span>
                )}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700"
            aria-label="Close customize tool"
          >
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Identity */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-gray-700">
                Name <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g., add_appointment"
                className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm font-mono"
              />
              <p className="text-[10px] text-gray-500 mt-0.5">
                Becomes <code>composition_{_slugify(name) || '<name>'}</code> in MCP.
              </p>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-700">
                What does it do? <span className="text-gray-400">(LLM hint)</span>
              </label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="e.g., Add an appointment to my calendar"
                className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
              />
            </div>
          </div>

          {/* Params */}
          <div>
            <h3 className="text-sm font-semibold text-gray-900 mb-2">Parameters</h3>
            {params.length === 0 ? (
              <Card className="p-4 text-sm text-gray-500 text-center">
                This tool has no parameters — wrapping it just gives it a friendlier name.
              </Card>
            ) : (
              <div className="space-y-2">
                {params.map((p) => {
                  const cfg = config[p.name]
                  if (!cfg) return null
                  const isComplex = p.jsonType === 'object' || p.jsonType === 'array' || p.jsonType === 'unknown'
                  return (
                    <Card key={p.name} className="p-3">
                      <div className="flex items-start gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-sm text-gray-900 truncate">
                              {p.name}
                            </span>
                            <span className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded">
                              {p.jsonType}
                            </span>
                            {p.required && (
                              <span className="text-xs px-1.5 py-0.5 bg-red-50 text-red-600 rounded">
                                required
                              </span>
                            )}
                          </div>
                          {p.description && (
                            <p className="text-xs text-gray-600 mt-0.5 line-clamp-2">
                              {p.description}
                            </p>
                          )}
                        </div>
                        <select
                          value={cfg.mode}
                          onChange={(e) => update(p.name, { mode: e.target.value as ParamMode })}
                          className="text-xs px-2 py-1 border border-gray-300 rounded bg-white"
                        >
                          <option value="expose">Expose to user</option>
                          <option value="fixed" disabled={isComplex}>
                            Fixed value{isComplex ? ' (use Hidden default)' : ''}
                          </option>
                          <option value="hidden">Hidden default</option>
                        </select>
                      </div>

                      {cfg.mode === 'expose' && (
                        <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2">
                          <div>
                            <label className="text-[10px] font-medium text-gray-600">
                              Exposed name
                            </label>
                            <input
                              type="text"
                              value={cfg.exposedName}
                              onChange={(e) => update(p.name, { exposedName: e.target.value })}
                              className="mt-0.5 w-full px-2 py-1 border border-gray-300 rounded text-xs font-mono"
                            />
                          </div>
                          <div>
                            <label className="text-[10px] font-medium text-gray-600">
                              Description for the LLM
                            </label>
                            <input
                              type="text"
                              value={cfg.exposedDescription}
                              onChange={(e) => update(p.name, { exposedDescription: e.target.value })}
                              className="mt-0.5 w-full px-2 py-1 border border-gray-300 rounded text-xs"
                            />
                          </div>
                        </div>
                      )}
                      {cfg.mode === 'fixed' && (
                        <div className="mt-2">
                          <label className="text-[10px] font-medium text-gray-600">
                            Fixed value
                          </label>
                          <input
                            type="text"
                            value={cfg.fixedValue}
                            onChange={(e) => update(p.name, { fixedValue: e.target.value })}
                            placeholder={p.jsonType === 'boolean' ? 'true | false' : ''}
                            className="mt-0.5 w-full px-2 py-1 border border-gray-300 rounded text-xs font-mono"
                          />
                        </div>
                      )}
                      {cfg.mode === 'hidden' && (
                        <div className="mt-2">
                          <label className="text-[10px] font-medium text-gray-600">
                            Hidden default {isComplex && '(JSON)'}
                          </label>
                          <input
                            type="text"
                            value={cfg.hiddenDefault}
                            onChange={(e) => update(p.name, { hiddenDefault: e.target.value })}
                            placeholder={isComplex ? '{ ... } or [ ... ]' : 'Leave empty to omit'}
                            className="mt-0.5 w-full px-2 py-1 border border-gray-300 rounded text-xs font-mono"
                          />
                        </div>
                      )}
                    </Card>
                  )
                })}
              </div>
            )}
          </div>

          {error && (
            <Card className="p-3 bg-red-50 border border-red-200">
              <div className="flex items-start gap-2 text-sm text-red-800">
                <ExclamationTriangleIcon className="h-5 w-5 text-red-500 flex-shrink-0" />
                <div>{error}</div>
              </div>
            </Card>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 p-5 border-t border-gray-200">
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving || !name.trim()}>
            {saving ? 'Creating…' : 'Create custom tool'}
          </Button>
        </div>
      </Card>
    </div>
  )
}
