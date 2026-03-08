/**
 * ServerConfigForm - Unified credential and configuration form for MCP servers
 *
 * UX improvements:
 * 1. Clear separation between required credentials and optional config
 * 2. Shows default values and examples for optional fields
 * 3. Collapsible optional config section
 * 4. Better field labeling with display_name support
 */

import { useState, useMemo } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  EyeIcon,
  EyeSlashIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  KeyIcon,
  Cog6ToothIcon,
  InformationCircleIcon,
} from '@heroicons/react/24/outline'
import { Button, Input, Alert, Badge } from '@/components/ui'
import { marketplaceApi } from '@/services/marketplace'
import { useOrganization, useAuth } from '@/hooks/useAuth'
import type { MCPServer, CredentialField } from '@/types/marketplace'

export interface ServerConfigFormProps {
  server: MCPServer
  onSuccess: () => void
  onError: (error: string) => void
  onBack: () => void
  /** Whether this server has team configuration (partial or full) */
  hasTeamConfig?: boolean
}

export function ServerConfigForm({ server, onSuccess, onError, onBack, hasTeamConfig = false }: ServerConfigFormProps) {
  const [showValues, setShowValues] = useState<Record<string, boolean>>({})
  const [showOptionalConfig, setShowOptionalConfig] = useState(false)
  const [validationStatus, setValidationStatus] = useState<'idle' | 'validating' | 'success' | 'error'>('idle')
  const { organizationId } = useOrganization()
  const { isCloudSaaS } = useAuth()

  // Separate credentials by type
  const { requiredCredentials, optionalCredentials } = useMemo(() => {
    const allCreds = server.credentials || []

    // Filter by config_type based on edition
    const filteredCreds = isCloudSaaS
      ? allCreds.filter(c => c.config_type !== 'local')
      : allCreds

    return {
      requiredCredentials: filteredCreds.filter(c => c.required),
      optionalCredentials: filteredCreds.filter(c => !c.required),
    }
  }, [server.credentials, isCloudSaaS])

  const hasRequiredCredentials = requiredCredentials.length > 0
  const hasOptionalCredentials = optionalCredentials.length > 0

  // Build dynamic form schema from credential fields
  const buildSchema = () => {
    const schemaShape: Record<string, z.ZodType<any>> = {
      // Connection name field (required for multi-account support)
      connectionName: z.string().min(1, 'Connection name is required')
        .max(100, 'Connection name must be less than 100 characters'),
    }

    const allFields = [...requiredCredentials, ...optionalCredentials]

    allFields.forEach((field) => {
      let fieldSchema: z.ZodType<any>

      switch (field.type) {
        case 'secret':
        case 'string':
        case 'url':
          fieldSchema = z.string()
          if (field.required) {
            fieldSchema = fieldSchema.min(1, `${field.display_name || field.name} is required`)
          }
          if (field.validation_regex) {
            fieldSchema = (fieldSchema as z.ZodString).regex(
              new RegExp(field.validation_regex),
              `Invalid ${field.display_name || field.name} format`
            )
          }
          if (field.type === 'url') {
            fieldSchema = z.union([
              z.literal(''),
              (fieldSchema as z.ZodString).url('Must be a valid URL')
            ])
          }
          break
        case 'number':
          fieldSchema = z.coerce.number()
          if (field.required) {
            fieldSchema = fieldSchema.min(0)
          }
          break
        case 'boolean':
          fieldSchema = z.boolean()
          break
        default:
          fieldSchema = z.string()
      }

      if (!field.required) {
        fieldSchema = fieldSchema.optional().or(z.literal(''))
      }

      schemaShape[field.name] = fieldSchema
    })

    return z.object(schemaShape)
  }

  const schema = buildSchema()
  type FormData = z.infer<typeof schema>

  // Build default values from credential fields
  const buildDefaultValues = () => {
    const defaults: Record<string, any> = {
      connectionName: '',
    }

    const allFields = [...requiredCredentials, ...optionalCredentials]
    allFields.forEach((field) => {
      defaults[field.name] = field.default_value || ''
    })

    return defaults
  }

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: buildDefaultValues(),
  })

  // Connect server mutation
  const connectServerMutation = useMutation({
    mutationFn: async (data: FormData) => {
      const { connectionName, ...credentials } = data as any

      // Filter out empty optional values
      const filteredCredentials: Record<string, any> = {}
      Object.entries(credentials).forEach(([key, value]) => {
        if (value !== '' && value !== undefined) {
          filteredCredentials[key] = value
        }
      })

      if (!organizationId) {
        throw new Error('No organization selected. Please ensure you are logged in.')
      }

      // For team services with partial configuration, use org credentials + additional
      if (hasTeamConfig) {
        return await marketplaceApi.connectServer(
          server.id,
          organizationId,
          {}, // credentials empty - using org credentials
          connectionName,
          true, // auto_start
          true, // use_org_credentials
          filteredCredentials // additional_credentials - what user just provided
        )
      }

      // Normal flow - user provides all credentials
      return await marketplaceApi.connectServer(
        server.id,
        organizationId,
        filteredCredentials,
        connectionName,
        true // auto_start
      )
    },
    onSuccess: () => {
      setValidationStatus('success')
      setTimeout(() => {
        onSuccess()
      }, 1500)
    },
    onError: (err) => {
      setValidationStatus('error')
      onError(err instanceof Error ? err.message : 'Failed to connect server')
    },
  })

  const onSubmit = (data: FormData) => {
    setValidationStatus('validating')
    connectServerMutation.mutate(data)
  }

  const toggleShowValue = (fieldName: string) => {
    setShowValues((prev) => ({ ...prev, [fieldName]: !prev[fieldName] }))
  }

  // Render a single credential field
  const renderField = (field: CredentialField, isRequired: boolean) => (
    <div key={field.name} className="space-y-1.5">
      <div className="flex items-start justify-between">
        <label
          htmlFor={field.name}
          className="block text-sm font-medium text-gray-700"
        >
          {field.display_name || field.name}
          {isRequired && <span className="text-error ml-1">*</span>}
        </label>
        {field.documentation_url && (
          <a
            href={field.documentation_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-orange hover:underline flex items-center gap-1"
          >
            {field.type === 'secret' ? 'Get API key' : 'Documentation'} →
          </a>
        )}
      </div>

      <div className="relative">
        <Input
          id={field.name}
          type={
            field.type === 'secret' && !showValues[field.name]
              ? 'password'
              : field.type === 'number'
              ? 'number'
              : field.type === 'url'
              ? 'url'
              : 'text'
          }
          placeholder={field.placeholder || field.example || `Enter ${field.display_name || field.name}`}
          error={errors[field.name]?.message as string}
          {...register(field.name)}
        />

        {/* Show/Hide toggle for secrets */}
        {field.type === 'secret' && (
          <button
            type="button"
            onClick={() => toggleShowValue(field.name)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
          >
            {showValues[field.name] ? (
              <EyeSlashIcon className="h-5 w-5" />
            ) : (
              <EyeIcon className="h-5 w-5" />
            )}
          </button>
        )}
      </div>

      {/* Description */}
      {field.description && (
        <p className="text-xs text-gray-500">{field.description}</p>
      )}

      {/* Default value indicator for optional fields */}
      {!isRequired && field.default_value && (
        <p className="text-xs text-gray-400 flex items-center gap-1">
          <InformationCircleIcon className="h-3 w-3" />
          Default: <code className="bg-gray-100 px-1 rounded text-xs">{field.default_value}</code>
        </p>
      )}

      {/* Example for secrets/strings without default */}
      {field.example && !field.default_value && (
        <p className="text-xs text-gray-400">
          Example: <code className="bg-gray-100 px-1 rounded text-xs">{field.example}</code>
        </p>
      )}
    </div>
  )

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
      {/* Security Info */}
      <Alert variant="info" title="Secure Storage">
        Your credentials are encrypted and stored securely. They are only used to
        connect to {server.name} and are never shared.
      </Alert>

      {/* Validation Status */}
      {validationStatus === 'validating' && (
        <Alert variant="info" title="Connecting...">
          Setting up your connection to {server.name}...
        </Alert>
      )}

      {validationStatus === 'success' && (
        <Alert variant="success" title="Connected!">
          <CheckCircleIcon className="h-5 w-5 inline mr-2" />
          Successfully connected to {server.name}!
        </Alert>
      )}

      {validationStatus === 'error' && (
        <Alert variant="error" title="Connection Failed">
          <ExclamationCircleIcon className="h-5 w-5 inline mr-2" />
          Could not connect. Please check your credentials and try again.
        </Alert>
      )}

      {/* Connection Name */}
      <div className="space-y-1.5">
        <label
          htmlFor="connectionName"
          className="block text-sm font-medium text-gray-700"
        >
          Connection Name
          <span className="text-error ml-1">*</span>
        </label>
        <Input
          id="connectionName"
          type="text"
          placeholder={`e.g., "${server.name} Personal" or "${server.name} Work"`}
          error={errors.connectionName?.message as string}
          {...register('connectionName')}
        />
        <p className="text-xs text-gray-500">
          Give this connection a unique name to identify it
        </p>
      </div>

      {/* Required Credentials Section */}
      {hasRequiredCredentials && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 pb-2 border-b border-gray-200">
            <KeyIcon className="h-5 w-5 text-amber-600" />
            <h3 className="text-sm font-semibold text-gray-900">
              Required Credentials
            </h3>
            <Badge variant="warning" size="sm">
              {requiredCredentials.length} required
            </Badge>
          </div>

          <div className="space-y-4">
            {requiredCredentials.map((field) => renderField(field, true))}
          </div>
        </div>
      )}

      {/* Optional Configuration Section */}
      {hasOptionalCredentials && (
        <div className="space-y-4">
          <button
            type="button"
            onClick={() => setShowOptionalConfig(!showOptionalConfig)}
            className="flex items-center gap-2 w-full pb-2 border-b border-gray-200 text-left hover:bg-gray-50 -mx-2 px-2 rounded transition-colors"
          >
            <Cog6ToothIcon className="h-5 w-5 text-gray-500" />
            <h3 className="text-sm font-semibold text-gray-700 flex-1">
              Optional Configuration
            </h3>
            <Badge variant="gray" size="sm">
              {optionalCredentials.length} options
            </Badge>
            {showOptionalConfig ? (
              <ChevronUpIcon className="h-4 w-4 text-gray-400" />
            ) : (
              <ChevronDownIcon className="h-4 w-4 text-gray-400" />
            )}
          </button>

          {showOptionalConfig && (
            <div className="space-y-4 pl-2 border-l-2 border-gray-100">
              <p className="text-xs text-gray-500">
                These settings are optional. Default values will be used if left empty.
              </p>
              {optionalCredentials.map((field) => renderField(field, false))}
            </div>
          )}
        </div>
      )}

      {/* No credentials case */}
      {!hasRequiredCredentials && !hasOptionalCredentials && (
        <Alert variant="info" title="No Configuration Needed">
          This server doesn't require any credentials or configuration.
        </Alert>
      )}

      {/* Actions */}
      <div className="flex justify-between gap-3 pt-4 border-t border-gray-200">
        <Button
          type="button"
          variant="ghost"
          onClick={onBack}
          disabled={connectServerMutation.isPending || validationStatus === 'validating'}
        >
          Back
        </Button>
        <Button
          type="submit"
          variant="primary"
          isLoading={connectServerMutation.isPending || validationStatus === 'validating'}
          disabled={validationStatus === 'success'}
        >
          {validationStatus === 'validating'
            ? 'Connecting...'
            : validationStatus === 'success'
            ? 'Connected!'
            : hasRequiredCredentials
            ? 'Connect with Credentials'
            : 'Connect Server'}
        </Button>
      </div>
    </form>
  )
}
