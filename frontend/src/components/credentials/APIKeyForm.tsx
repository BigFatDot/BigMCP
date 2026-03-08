/**
 * APIKeyForm - Manual credential entry form for MCP servers
 */

import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { EyeIcon, EyeSlashIcon, CheckCircleIcon, ExclamationCircleIcon } from '@heroicons/react/24/outline'
import { Button, Input, Alert } from '@/components/ui'
import { marketplaceApi } from '@/services/marketplace'
import { useOrganization } from '@/hooks/useAuth'
import type { MCPServer, CredentialField } from '@/types/marketplace'

export interface APIKeyFormProps {
  server: MCPServer
  onSuccess: () => void
  onError: (error: string) => void
  onBack: () => void
}

export function APIKeyForm({ server, onSuccess, onError, onBack }: APIKeyFormProps) {
  const [showValues, setShowValues] = useState<Record<string, boolean>>({})
  const [validationStatus, setValidationStatus] = useState<'idle' | 'validating' | 'success' | 'error'>('idle')
  const { organizationId } = useOrganization()

  // Build dynamic form schema from credential fields
  const buildSchema = () => {
    const schemaShape: Record<string, z.ZodType<any>> = {
      // Add connection name field (required for multi-account support)
      connectionName: z.string().min(1, 'Connection name is required')
        .max(100, 'Connection name must be less than 100 characters'),
    }

    if (!server.credentials) return z.object(schemaShape)

    server.credentials.forEach((field) => {
      let fieldSchema: z.ZodType<any>

      switch (field.type) {
        case 'secret':
        case 'string':
        case 'url':
          fieldSchema = z.string()
          if (field.required) {
            fieldSchema = fieldSchema.min(1, `${field.name} is required`)
          }
          if (field.validation_regex) {
            fieldSchema = (fieldSchema as z.ZodString).regex(
              new RegExp(field.validation_regex),
              `Invalid ${field.name} format`
            )
          }
          if (field.type === 'url') {
            fieldSchema = (fieldSchema as z.ZodString).url('Must be a valid URL')
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
        fieldSchema = fieldSchema.optional()
      }

      schemaShape[field.name] = fieldSchema
    })

    return z.object(schemaShape)
  }

  const schema = buildSchema()
  type FormData = z.infer<typeof schema>

  const {
    register,
    handleSubmit,
    formState: { errors },
    getValues,
  } = useForm<FormData>({
    resolver: zodResolver(schema),
  })

  // Connect server (install + configure credentials) mutation
  const connectServerMutation = useMutation({
    mutationFn: async (data: FormData) => {
      // Extract connection name and credentials
      const { connectionName, ...credentials } = data as any

      // Get organization_id from auth context
      if (!organizationId) {
        throw new Error('No organization selected. Please ensure you are logged in.')
      }

      return await marketplaceApi.connectServer(
        server.id,  // marketplace server_id (e.g., 'grist-mcp')
        organizationId,
        credentials,
        connectionName,  // Name for this connection (e.g., "Grist Personal")
        true  // auto_start - start server immediately with user credentials
      )
    },
    onSuccess: async (response) => {
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

  if (!server.credentials || server.credentials.length === 0) {
    return (
      <Alert variant="error" title="Configuration Error">
        This server doesn't have credentials defined.
      </Alert>
    )
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
      {/* Info Alert */}
      <Alert variant="info" title="Secure Storage">
        Your credentials are encrypted and stored securely. They are only used to
        connect to {server.name} and are never shared.
      </Alert>

      {/* Validation Status */}
      {validationStatus === 'validating' && (
        <Alert variant="info" title="Validating Credentials">
          Testing your credentials...
        </Alert>
      )}

      {validationStatus === 'success' && (
        <Alert variant="success" title="Credentials Valid">
          <CheckCircleIcon className="h-5 w-5 inline mr-2" />
          Your credentials have been validated and saved successfully!
        </Alert>
      )}

      {validationStatus === 'error' && (
        <Alert variant="error" title="Validation Failed">
          <ExclamationCircleIcon className="h-5 w-5 inline mr-2" />
          The credentials could not be validated. Please check and try again.
        </Alert>
      )}

      {/* Connection Name Field (for multi-account support) */}
      <div>
        <label
          htmlFor="connectionName"
          className="block text-sm font-medium text-gray-700 mb-1.5"
        >
          Connection Name
          <span className="text-error ml-1">*</span>
        </label>
        <Input
          id="connectionName"
          type="text"
          placeholder={`e.g., "${server.name} Personal" or "${server.name} Work"`}
          error={errors.connectionName?.message as string}
          helperText="Give this connection a unique name to distinguish it from other accounts"
          {...register('connectionName')}
        />
      </div>

      {/* Credential Fields */}
      <div className="space-y-4">
        {server.credentials?.map((field) => (
          <div key={field.name}>
            <div className="flex items-start justify-between mb-1.5">
              <label
                htmlFor={field.name}
                className="block text-sm font-medium text-gray-700"
              >
                {field.name}
                {field.required && <span className="text-error ml-1">*</span>}
              </label>
              {field.documentation_url && (
                <a
                  href={field.documentation_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-orange hover:underline"
                >
                  How to get this?
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
                placeholder={field.placeholder || `Enter ${field.name}`}
                error={errors[field.name]?.message as string}
                helperText={field.description}
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
          </div>
        ))}
      </div>

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
            : 'Install & Connect'}
        </Button>
      </div>
    </form>
  )
}
