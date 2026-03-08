/**
 * Dynamic Input Form Component
 *
 * Generates form fields from JSON Schema (input_schema).
 * Supports: string, number, boolean, select (enum), array, object.
 */

import { useTranslation } from 'react-i18next'
import { cn } from '@/utils/cn'
import type { InputSchema, InputSchemaProperty } from '@/services/marketplace'

interface DynamicInputFormProps {
  /** JSON Schema defining the input structure */
  inputSchema: InputSchema
  /** Current form values */
  values: Record<string, unknown>
  /** Callback when a value changes */
  onChange: (key: string, value: unknown) => void
  /** Whether the form is disabled (e.g., during execution) */
  disabled?: boolean
  /** Optional CSS class */
  className?: string
}

interface FieldProps {
  name: string
  schema: InputSchemaProperty
  value: unknown
  onChange: (value: unknown) => void
  required: boolean
  disabled?: boolean
}

/**
 * Render a single form field based on its schema type.
 */
function InputField({ name, schema, value, onChange, required, disabled }: FieldProps) {
  const { t } = useTranslation('dashboard')

  const label = name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  const description = schema.description
  const fieldId = `input-${name}`

  // Common label component
  const Label = () => (
    <label htmlFor={fieldId} className="block text-sm font-medium text-gray-700 mb-1">
      {label}
      {required && <span className="text-red-500 ml-1">*</span>}
    </label>
  )

  // Common description component
  const Description = () => description ? (
    <p className="text-xs text-gray-500 mt-1">{description}</p>
  ) : null

  // Render based on type
  switch (schema.type) {
    case 'string':
      // Check if it's an enum (select)
      if (schema.enum && schema.enum.length > 0) {
        return (
          <div>
            <Label />
            <select
              id={fieldId}
              value={(value as string) || ''}
              onChange={(e) => onChange(e.target.value)}
              disabled={disabled}
              required={required}
              className={cn(
                "w-full px-3 py-2 border border-gray-300 rounded-lg",
                "focus:ring-2 focus:ring-orange focus:border-orange",
                "disabled:bg-gray-100 disabled:cursor-not-allowed"
              )}
            >
              <option value="">{t('compositions.inputForm.selectOption')}</option>
              {schema.enum.map((opt) => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
            <Description />
          </div>
        )
      }

      // Check if it should be textarea (long text)
      const isLongText = (schema.maxLength && schema.maxLength > 200) ||
                         name.toLowerCase().includes('description') ||
                         name.toLowerCase().includes('content') ||
                         name.toLowerCase().includes('body')

      if (isLongText) {
        return (
          <div>
            <Label />
            <textarea
              id={fieldId}
              value={(value as string) || ''}
              onChange={(e) => onChange(e.target.value)}
              disabled={disabled}
              required={required}
              rows={4}
              placeholder={schema.default as string}
              className={cn(
                "w-full px-3 py-2 border border-gray-300 rounded-lg",
                "focus:ring-2 focus:ring-orange focus:border-orange",
                "disabled:bg-gray-100 disabled:cursor-not-allowed",
                "font-mono text-sm"
              )}
            />
            <Description />
          </div>
        )
      }

      // Default: text input
      return (
        <div>
          <Label />
          <input
            type="text"
            id={fieldId}
            value={(value as string) || ''}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            required={required}
            placeholder={schema.default as string}
            className={cn(
              "w-full px-3 py-2 border border-gray-300 rounded-lg",
              "focus:ring-2 focus:ring-orange focus:border-orange",
              "disabled:bg-gray-100 disabled:cursor-not-allowed"
            )}
          />
          <Description />
        </div>
      )

    case 'number':
    case 'integer':
      return (
        <div>
          <Label />
          <input
            type="number"
            id={fieldId}
            value={(value as number) ?? (schema.default as number) ?? ''}
            onChange={(e) => onChange(e.target.value ? Number(e.target.value) : undefined)}
            disabled={disabled}
            required={required}
            min={schema.minimum}
            max={schema.maximum}
            step={schema.type === 'integer' ? 1 : 'any'}
            className={cn(
              "w-full px-3 py-2 border border-gray-300 rounded-lg",
              "focus:ring-2 focus:ring-orange focus:border-orange",
              "disabled:bg-gray-100 disabled:cursor-not-allowed"
            )}
          />
          <Description />
        </div>
      )

    case 'boolean':
      return (
        <div className="flex items-start gap-3">
          <input
            type="checkbox"
            id={fieldId}
            checked={Boolean(value ?? schema.default)}
            onChange={(e) => onChange(e.target.checked)}
            disabled={disabled}
            className={cn(
              "mt-1 w-4 h-4 rounded border-gray-300",
              "text-orange focus:ring-orange",
              "disabled:cursor-not-allowed"
            )}
          />
          <div>
            <label htmlFor={fieldId} className="text-sm font-medium text-gray-700">
              {label}
            </label>
            <Description />
          </div>
        </div>
      )

    case 'array':
    case 'object':
      // Complex types: render as JSON textarea
      const jsonValue = value ? JSON.stringify(value, null, 2) : ''
      return (
        <div>
          <Label />
          <textarea
            id={fieldId}
            value={jsonValue}
            onChange={(e) => {
              try {
                const parsed = JSON.parse(e.target.value)
                onChange(parsed)
              } catch {
                // Keep raw value while user is typing
                onChange(e.target.value)
              }
            }}
            disabled={disabled}
            required={required}
            rows={4}
            placeholder={schema.type === 'array' ? '[]' : '{}'}
            className={cn(
              "w-full px-3 py-2 border border-gray-300 rounded-lg",
              "focus:ring-2 focus:ring-orange focus:border-orange",
              "disabled:bg-gray-100 disabled:cursor-not-allowed",
              "font-mono text-sm"
            )}
          />
          <p className="text-xs text-gray-500 mt-1">
            {t('compositions.inputForm.jsonFormat', { type: schema.type })}
            {description && ` - ${description}`}
          </p>
        </div>
      )

    default:
      // Fallback to text input
      return (
        <div>
          <Label />
          <input
            type="text"
            id={fieldId}
            value={String(value || '')}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            required={required}
            className={cn(
              "w-full px-3 py-2 border border-gray-300 rounded-lg",
              "focus:ring-2 focus:ring-orange focus:border-orange",
              "disabled:bg-gray-100 disabled:cursor-not-allowed"
            )}
          />
          <Description />
        </div>
      )
  }
}

/**
 * Dynamic form that generates fields from JSON Schema.
 */
export function DynamicInputForm({
  inputSchema,
  values,
  onChange,
  disabled = false,
  className
}: DynamicInputFormProps) {
  const { t } = useTranslation('dashboard')

  const properties = inputSchema?.properties || {}
  const required = inputSchema?.required || []
  const propertyEntries = Object.entries(properties)

  if (propertyEntries.length === 0) {
    return (
      <div className={cn("text-center py-4 text-gray-500", className)}>
        <p>{t('compositions.inputForm.noInputsRequired')}</p>
      </div>
    )
  }

  return (
    <div className={cn("space-y-4", className)}>
      {propertyEntries.map(([key, propSchema]) => (
        <InputField
          key={key}
          name={key}
          schema={propSchema}
          value={values[key]}
          onChange={(val) => onChange(key, val)}
          required={required.includes(key)}
          disabled={disabled}
        />
      ))}
    </div>
  )
}

export default DynamicInputForm
