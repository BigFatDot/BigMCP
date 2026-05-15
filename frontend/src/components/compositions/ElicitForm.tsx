/**
 * ElicitForm — B-1 chunk 3.
 *
 * Generates a form from the JSON Schema declared on a suspended
 * ``elicit`` step (``state.suspension.payload.schema``) and submits
 * the values via the existing /resume endpoint. Server-side
 * validation is authoritative — the UI form generator only handles
 * the common subset (top-level object with scalar properties + enum
 * + required) and lets the server return 422 for anything richer.
 *
 * Sub-objects, arrays, oneOf, conditional required → deferred to
 * B-1.1; we render those as a JSON textarea fallback so authors can
 * still ship them today.
 */

import { useMemo, useState } from 'react'
import { Button } from '@/components/ui'

export interface ElicitSchemaProperty {
  type?: 'string' | 'number' | 'integer' | 'boolean' | 'object' | 'array'
  enum?: string[]
  description?: string
  title?: string
  default?: unknown
  format?: string
  minLength?: number
  maxLength?: number
  minimum?: number
  maximum?: number
}

export interface ElicitSchema {
  type?: string
  properties?: Record<string, ElicitSchemaProperty>
  required?: string[]
}

interface ElicitFormProps {
  message: string
  schema: ElicitSchema
  onSubmit: (response: unknown) => Promise<void>
  submitting: boolean
}

function defaultForProperty(prop: ElicitSchemaProperty): unknown {
  if (prop.default !== undefined) return prop.default
  if (prop.type === 'boolean') return false
  if (prop.type === 'number' || prop.type === 'integer') return ''
  return ''
}

/**
 * Returns true when the form generator can render every property
 * declared on the schema. Anything else falls back to the JSON
 * textarea so the user can still respond.
 */
function canRenderForm(schema: ElicitSchema): boolean {
  if (schema.type !== 'object') return false
  const props = schema.properties || {}
  for (const prop of Object.values(props)) {
    if (
      prop.type !== 'string' &&
      prop.type !== 'number' &&
      prop.type !== 'integer' &&
      prop.type !== 'boolean'
    ) {
      return false
    }
  }
  return true
}

export function ElicitForm({
  message,
  schema,
  onSubmit,
  submitting,
}: ElicitFormProps) {
  const renderable = useMemo(() => canRenderForm(schema), [schema])
  const required = useMemo(() => new Set(schema.required || []), [schema])

  const [values, setValues] = useState<Record<string, unknown>>(() => {
    if (!renderable) return {}
    const initial: Record<string, unknown> = {}
    for (const [name, prop] of Object.entries(schema.properties || {})) {
      initial[name] = defaultForProperty(prop)
    }
    return initial
  })
  const [jsonText, setJsonText] = useState('{}')
  const [jsonError, setJsonError] = useState<string | null>(null)

  const handleFieldChange = (name: string, raw: unknown) => {
    setValues((cur) => ({ ...cur, [name]: raw }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (renderable) {
      // Coerce numeric fields to numbers before submit
      const out: Record<string, unknown> = {}
      for (const [name, prop] of Object.entries(schema.properties || {})) {
        const v = values[name]
        if (
          (prop.type === 'number' || prop.type === 'integer') &&
          typeof v === 'string' &&
          v.trim() !== ''
        ) {
          const n = prop.type === 'integer' ? parseInt(v, 10) : parseFloat(v)
          out[name] = Number.isNaN(n) ? v : n
        } else if (
          (prop.type === 'string') &&
          v === '' &&
          !required.has(name)
        ) {
          // Skip empty optional strings so the schema's required check
          // doesn't see them as present-but-empty.
          continue
        } else {
          out[name] = v
        }
      }
      await onSubmit(out)
      return
    }
    // Fallback: parse the raw JSON the user typed
    let parsed: unknown
    try {
      parsed = JSON.parse(jsonText)
      setJsonError(null)
    } catch (err) {
      setJsonError(`Invalid JSON: ${(err as Error).message}`)
      return
    }
    await onSubmit(parsed)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <p className="text-sm text-amber-900 whitespace-pre-wrap">{message}</p>

      {renderable ? (
        <div className="space-y-2">
          {Object.entries(schema.properties || {}).map(([name, prop]) => {
            const fieldId = `elicit-field-${name}`
            const label = prop.title || name
            const isRequired = required.has(name)
            const desc = prop.description
            const value = values[name]

            if (prop.type === 'boolean') {
              return (
                <div key={name} className="flex items-start gap-2">
                  <input
                    id={fieldId}
                    type="checkbox"
                    checked={Boolean(value)}
                    onChange={(e) => handleFieldChange(name, e.target.checked)}
                    className="mt-1 rounded border-gray-300"
                  />
                  <label htmlFor={fieldId} className="text-sm">
                    <span className="font-medium">{label}</span>
                    {isRequired && <span className="text-red-600">*</span>}
                    {desc && <div className="text-xs text-gray-600">{desc}</div>}
                  </label>
                </div>
              )
            }

            if (prop.enum && prop.enum.length > 0) {
              return (
                <div key={name} className="flex flex-col gap-1">
                  <label htmlFor={fieldId} className="text-sm font-medium">
                    {label}
                    {isRequired && <span className="text-red-600">*</span>}
                  </label>
                  {desc && <span className="text-xs text-gray-600">{desc}</span>}
                  <select
                    id={fieldId}
                    value={String(value ?? '')}
                    onChange={(e) => handleFieldChange(name, e.target.value)}
                    className="border border-gray-300 rounded p-1.5 text-sm"
                    required={isRequired}
                  >
                    <option value="">— select —</option>
                    {prop.enum.map((v) => (
                      <option key={v} value={v}>
                        {v}
                      </option>
                    ))}
                  </select>
                </div>
              )
            }

            const inputType =
              prop.type === 'number' || prop.type === 'integer'
                ? 'number'
                : prop.format === 'email'
                  ? 'email'
                  : prop.format === 'uri'
                    ? 'url'
                    : 'text'

            return (
              <div key={name} className="flex flex-col gap-1">
                <label htmlFor={fieldId} className="text-sm font-medium">
                  {label}
                  {isRequired && <span className="text-red-600">*</span>}
                </label>
                {desc && <span className="text-xs text-gray-600">{desc}</span>}
                <input
                  id={fieldId}
                  type={inputType}
                  value={String(value ?? '')}
                  onChange={(e) => handleFieldChange(name, e.target.value)}
                  className="border border-gray-300 rounded p-1.5 text-sm"
                  required={isRequired}
                  minLength={prop.minLength}
                  maxLength={prop.maxLength}
                  min={prop.minimum}
                  max={prop.maximum}
                  step={prop.type === 'integer' ? 1 : undefined}
                />
              </div>
            )
          })}
        </div>
      ) : (
        <div className="space-y-1">
          <p className="text-xs text-amber-800">
            This schema needs a structured response. Edit the JSON below to
            match it (server-side validation will tell you if anything's off).
          </p>
          <textarea
            value={jsonText}
            onChange={(e) => {
              setJsonText(e.target.value)
              setJsonError(null)
            }}
            rows={6}
            className="w-full font-mono text-sm border border-amber-300 rounded p-2"
          />
          <details className="text-xs">
            <summary className="cursor-pointer text-amber-900">
              Show schema
            </summary>
            <pre className="mt-1 text-xs font-mono whitespace-pre-wrap bg-white border border-amber-200 rounded p-2 max-h-40 overflow-auto">
              {JSON.stringify(schema, null, 2)}
            </pre>
          </details>
          {jsonError && (
            <p className="text-xs text-red-700">{jsonError}</p>
          )}
        </div>
      )}

      <Button type="submit" disabled={submitting}>
        {submitting ? 'Submitting…' : 'Submit response'}
      </Button>
    </form>
  )
}
