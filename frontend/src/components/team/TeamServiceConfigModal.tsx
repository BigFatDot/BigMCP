/**
 * TeamServiceConfigModal - Configure a marketplace server as a shared team service
 *
 * Allows admins to:
 * - Configure credentials (partial or complete) for a marketplace server
 * - Name the service for the team
 * - Control visibility to members
 * - Create an OrganizationCredential that members can use
 */

import { useState, useMemo } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  UserGroupIcon,
  EyeIcon,
  EyeSlashIcon,
  KeyIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline'
import { Modal, Button, Input, Alert, Badge } from '@/components/ui'
import { ServerIcon } from '../marketplace/ServerIcon'
import { useOrganization, useAuth } from '@/hooks/useAuth'
import { orgCredentialsApi } from '@/services/marketplace'
import type { MCPServer, CredentialField } from '@/types/marketplace'

export interface TeamServiceConfigModalProps {
  isOpen: boolean
  onClose: () => void
  server: MCPServer
  onSuccess: () => void
}

export function TeamServiceConfigModal({
  isOpen,
  onClose,
  server,
  onSuccess,
}: TeamServiceConfigModalProps) {
  const [showValues, setShowValues] = useState<Record<string, boolean>>({})
  const [error, setError] = useState<string | null>(null)
  const { organizationId } = useOrganization()
  const { isCloudSaaS } = useAuth()
  const queryClient = useQueryClient()

  // Filter credentials by edition
  const credentials = useMemo(() => {
    const allCreds = server.credentials || []
    return isCloudSaaS
      ? allCreds.filter(c => c.config_type !== 'local')
      : allCreds
  }, [server.credentials, isCloudSaaS])

  const requiredCreds = credentials.filter(c => c.required)
  const optionalCreds = credentials.filter(c => !c.required)

  // Build form schema
  const buildSchema = () => {
    const schemaShape: Record<string, z.ZodType<any>> = {
      serviceName: z.string().min(1, 'Service name is required')
        .max(100, 'Service name must be less than 100 characters'),
      description: z.string().optional(),
      visibleToUsers: z.boolean(),
    }

    credentials.forEach((field) => {
      let fieldSchema: z.ZodType<any>

      switch (field.type) {
        case 'secret':
        case 'string':
        case 'url':
          fieldSchema = z.string()
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
          break
        case 'boolean':
          fieldSchema = z.boolean()
          break
        default:
          fieldSchema = z.string()
      }

      // All credentials are optional for team services (can be partial)
      fieldSchema = fieldSchema.optional().or(z.literal(''))
      schemaShape[field.name] = fieldSchema
    })

    return z.object(schemaShape)
  }

  const schema = buildSchema()
  type FormData = z.infer<typeof schema>

  const buildDefaultValues = () => {
    const defaults: Record<string, any> = {
      serviceName: `${server.name} - Team`,
      description: '',
      visibleToUsers: true,
    }

    credentials.forEach((field) => {
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

  const createOrgCredentialMutation = useMutation({
    mutationFn: async (data: FormData) => {
      if (!organizationId) {
        throw new Error('No organization selected')
      }

      const { serviceName, description, visibleToUsers, ...credentialData } = data as any

      // Filter out empty credentials
      const credentials: Record<string, string> = {}
      Object.entries(credentialData).forEach(([key, value]) => {
        if (value && value !== '') {
          credentials[key] = value as string
        }
      })

      // Call org credentials API
      return await orgCredentialsApi.createOrgCredential(
        server.id, // marketplace server ID
        credentials,
        serviceName,
        visibleToUsers,
        description || undefined
      )
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['org-credentials'] })
      await queryClient.invalidateQueries({ queryKey: ['team-servers'] })
      onSuccess()
      onClose()
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : 'Failed to create team service')
    },
  })

  const onSubmit = (data: FormData) => {
    setError(null)
    createOrgCredentialMutation.mutate(data)
  }

  const toggleShowValue = (key: string) => {
    setShowValues(prev => ({ ...prev, [key]: !prev[key] }))
  }

  const renderCredentialField = (field: CredentialField) => {
    const displayName = field.display_name || field.name
    const isSecret = field.type === 'secret'
    const showValue = showValues[field.name] || !isSecret

    return (
      <div key={field.name} className="space-y-1.5">
        <label className="block text-sm font-medium text-gray-700">
          {displayName}
          {!field.required && (
            <span className="ml-1 text-xs text-gray-500">(optional)</span>
          )}
        </label>

        <div className="relative">
          <Input
            {...register(field.name as any)}
            type={showValue ? 'text' : 'password'}
            placeholder={field.placeholder || field.example || ''}
          />
          {isSecret && (
            <button
              type="button"
              onClick={() => toggleShowValue(field.name)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700"
            >
              {showValue ? (
                <EyeSlashIcon className="w-4 h-4" />
              ) : (
                <EyeIcon className="w-4 h-4" />
              )}
            </button>
          )}
        </div>

        {field.description && (
          <p className="text-xs text-gray-500">{field.description}</p>
        )}
        {errors[field.name as keyof typeof errors] && (
          <p className="text-xs text-red-600">
            {errors[field.name as keyof typeof errors]?.message as string}
          </p>
        )}
      </div>
    )
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="lg">
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-start gap-4 pb-4 border-b border-gray-200">
          <ServerIcon
            name={server.name}
            iconUrl={server.icon_url}
            iconUrls={(server as any).icon_urls}
            size="lg"
          />

          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <h2 className="text-xl font-bold text-gray-900">
                Configure and Share
              </h2>
              <Badge variant="primary" size="sm" className="bg-orange text-white flex items-center gap-1">
                <UserGroupIcon className="w-3 h-3" />
                Team
              </Badge>
            </div>
            <p className="text-sm text-gray-600 font-sans line-clamp-2">
              {server.name} - {server.description}
            </p>
          </div>
        </div>

        {/* Error Display */}
        {error && (
          <Alert variant="error" title="Configuration Failed" onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {/* Info Alert */}
        <Alert variant="info" title="Team Service Configuration">
          Configure credentials for this service. Members will use these credentials when connecting.
          You can provide partial credentials and members will complete the missing fields.
        </Alert>

        {/* Form */}
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">

        {/* Service Configuration */}
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
            <UserGroupIcon className="h-4 w-4" />
            Service Details
          </h3>

          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-gray-700">
              Service Name
            </label>
            <Input
              {...register('serviceName')}
              placeholder="e.g., GitHub - Company Repos"
              autoFocus
            />
            {errors.serviceName && (
              <p className="text-xs text-red-600">{errors.serviceName.message}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-gray-700">
              Description
              <span className="ml-1 text-xs text-gray-500">(optional)</span>
            </label>
            <Input
              {...register('description')}
              placeholder="e.g., Access to company repositories"
            />
          </div>

          <div className="flex items-center gap-2">
            <input
              {...register('visibleToUsers')}
              type="checkbox"
              id="visibleToUsers"
              className="rounded border-gray-300 text-orange focus:ring-orange"
            />
            <label htmlFor="visibleToUsers" className="text-sm text-gray-700">
              Visible to all team members
            </label>
          </div>
        </div>

        {/* Credentials Configuration */}
        {credentials.length > 0 && (
          <div className="space-y-4 pt-4 border-t border-gray-200">
            <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
              <KeyIcon className="h-4 w-4" />
              Credentials Configuration
              <span className="text-xs text-gray-500 font-normal ml-1">
                (All fields optional - provide what you want to share)
              </span>
            </h3>

            {requiredCreds.length > 0 && (
              <div className="space-y-3">
                <h4 className="text-xs font-medium text-gray-600 uppercase tracking-wide">
                  Typically Required
                </h4>
                {requiredCreds.map(renderCredentialField)}
              </div>
            )}

            {optionalCreds.length > 0 && (
              <div className="space-y-3">
                <h4 className="text-xs font-medium text-gray-600 uppercase tracking-wide">
                  Optional Configuration
                </h4>
                {optionalCreds.map(renderCredentialField)}
              </div>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-between gap-3 pt-4 border-t border-gray-200">
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={createOrgCredentialMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            isLoading={createOrgCredentialMutation.isPending}
            className="bg-orange hover:bg-orange-dark"
          >
            {createOrgCredentialMutation.isPending ? (
              'Creating...'
            ) : (
              <>
                <CheckCircleIcon className="w-4 h-4 mr-2" />
                Share with Team
              </>
            )}
          </Button>
        </div>
        </form>
      </div>
    </Modal>
  )
}
