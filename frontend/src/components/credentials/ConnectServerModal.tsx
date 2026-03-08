/**
 * ConnectServerModal - Handle server connection with credential and config setup
 *
 * UX flow:
 * 1. Shows server info header
 * 2. Displays ServerConfigForm for credentials/config
 * 3. Handles both required credentials and optional config cases
 */

import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  WrenchScrewdriverIcon,
  KeyIcon,
  Cog6ToothIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline'
import { Modal, Button, Alert, Badge, Input } from '@/components/ui'
import { ServerIcon } from '../marketplace/ServerIcon'
import { ServerConfigForm } from './ServerConfigForm'
import { useAuth, useOrganization } from '@/hooks/useAuth'
import { marketplaceApi } from '@/services/marketplace'
import type { MCPServer } from '@/types/marketplace'

export interface ConnectServerModalProps {
  isOpen: boolean
  onClose: () => void
  server: MCPServer
  onComplete: () => void
}

export function ConnectServerModal({
  isOpen,
  onClose,
  server,
  onComplete,
}: ConnectServerModalProps) {
  const [error, setError] = useState<string | null>(null)
  const [connectionName, setConnectionName] = useState('')
  const [isConnecting, setIsConnecting] = useState(false)
  const { isCloudSaaS } = useAuth()
  const { organizationId } = useOrganization()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Check if server has team configuration
  const teamConfig = (server as any)._teamConfig
  const hasTeamConfig = !!teamConfig
  const isFullyConfigured = (server as any)._isFullyConfigured || false
  const teamCredentialKeys = teamConfig?.credential_keys || []

  // Mutation to connect servers without credentials (or with team credentials)
  const connectMutation = useMutation({
    mutationFn: async () => {
      if (!organizationId) {
        throw new Error('No organization selected')
      }

      // If server has fully configured team credentials, use them
      if (hasTeamConfig && isFullyConfigured) {
        return await marketplaceApi.connectServer(
          server.id,
          organizationId,
          {}, // No personal credentials needed
          connectionName || `${server.name} (Team)`,
          true, // auto_start
          true, // use_org_credentials
          {} // no additional credentials needed
        )
      }

      // Otherwise, normal flow (no credentials)
      return await marketplaceApi.connectServer(
        server.id,
        organizationId,
        {}, // No credentials
        connectionName || server.name,
        true // auto_start
      )
    },
    onSuccess: async () => {
      setIsConnecting(false)
      // Invalidate queries to refresh data
      await queryClient.invalidateQueries({ queryKey: ['user-credentials'] })
      await queryClient.invalidateQueries({ queryKey: ['available-tools'] })
      onComplete()
      // Navigate to Services page
      navigate('/app/tools')
    },
    onError: (err) => {
      setIsConnecting(false)
      setError(err instanceof Error ? err.message : 'Failed to connect server')
    },
  })

  // Compute credential info
  const { hasRequiredCredentials, hasOptionalCredentials, hasAnyConfig, missingTeamCredentials } = useMemo(() => {
    const allCreds = server.credentials || []

    // Filter by config_type based on edition
    const filteredCreds = isCloudSaaS
      ? allCreds.filter(c => c.config_type !== 'local')
      : allCreds

    // If team credentials exist, find which credentials are missing
    let credsToCheck: typeof filteredCreds = filteredCreds
    if (hasTeamConfig && !isFullyConfigured) {
      const missingCreds = filteredCreds.filter(c => !teamCredentialKeys.includes(c.name))
      credsToCheck = missingCreds
    }

    const required = credsToCheck.filter(c => c.required)
    const optional = credsToCheck.filter(c => !c.required)

    return {
      hasRequiredCredentials: required.length > 0,
      hasOptionalCredentials: optional.length > 0,
      hasAnyConfig: credsToCheck.length > 0,
      missingTeamCredentials: credsToCheck,
    }
  }, [server.credentials, isCloudSaaS, hasTeamConfig, isFullyConfigured, teamCredentialKeys])

  // Create filtered server with only missing credentials for team services
  const filteredServer = useMemo(() => {
    if (hasTeamConfig && !isFullyConfigured && missingTeamCredentials.length > 0) {
      return {
        ...server,
        credentials: missingTeamCredentials
      }
    }
    return server
  }, [server, hasTeamConfig, isFullyConfigured, missingTeamCredentials])

  const handleConnectionSuccess = async () => {
    // Invalidate queries to refresh data
    await queryClient.invalidateQueries({ queryKey: ['user-credentials'] })
    await queryClient.invalidateQueries({ queryKey: ['available-tools'] })
    onComplete()
    // Navigate to Services page
    navigate('/app/tools')
  }

  const handleConnectionError = (errorMessage: string) => {
    setError(errorMessage)
  }

  const handleBack = () => {
    onClose()
  }

  // Get tools count
  const toolsCount = server.tools?.length || server.tools_preview?.length || 0

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="lg"
    >
      <div className="space-y-6">
        {/* Server Header */}
        <div className="flex items-start gap-4 pb-4 border-b border-gray-200">
          <ServerIcon
            name={server.name}
            iconUrl={server.icon_url}
            iconUrls={(server as any).icon_urls}
            size="lg"
          />

          <div className="flex-1">
            <h2 className="text-xl font-bold text-gray-900 mb-1">
              Connect {server.name}
            </h2>
            <p className="text-sm text-gray-600 font-sans line-clamp-2">
              {server.description}
            </p>

            {/* Quick info badges */}
            <div className="flex flex-wrap gap-2 mt-3">
              {toolsCount > 0 && (
                <Badge variant="gray" size="sm" className="flex items-center gap-1">
                  <WrenchScrewdriverIcon className="h-3 w-3" />
                  {toolsCount} tools
                </Badge>
              )}
              {hasRequiredCredentials && (
                <Badge variant="warning" size="sm" className="flex items-center gap-1">
                  <KeyIcon className="h-3 w-3" />
                  Credentials required
                </Badge>
              )}
              {hasOptionalCredentials && !hasRequiredCredentials && (
                <Badge variant="gray" size="sm" className="flex items-center gap-1">
                  <Cog6ToothIcon className="h-3 w-3" />
                  Optional config
                </Badge>
              )}
              {hasTeamConfig && isFullyConfigured && (
                <Badge variant="primary" size="sm" className="bg-orange text-white flex items-center gap-1">
                  <CheckCircleIcon className="h-3 w-3" />
                  Ready with Team Credentials
                </Badge>
              )}
              {hasTeamConfig && !isFullyConfigured && missingTeamCredentials.length > 0 && (
                <Badge variant="warning" size="sm" className="flex items-center gap-1">
                  <KeyIcon className="h-3 w-3" />
                  {missingTeamCredentials.length} credential{missingTeamCredentials.length > 1 ? 's' : ''} needed
                </Badge>
              )}
              {!hasAnyConfig && !hasTeamConfig && (
                <Badge variant="success" size="sm" className="flex items-center gap-1">
                  <CheckCircleIcon className="h-3 w-3" />
                  No setup needed
                </Badge>
              )}
            </div>
          </div>
        </div>

        {/* Error Display */}
        {error && (
          <Alert variant="error" title="Connection Failed" onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {/* Team Credentials Info */}
        {hasTeamConfig && isFullyConfigured && (
          <Alert variant="info" title="Pre-configured by Your Team">
            This service has been fully configured by your team admin. You can connect with one click!
          </Alert>
        )}
        {hasTeamConfig && !isFullyConfigured && missingTeamCredentials.length > 0 && (
          <Alert variant="info" title="Partially Configured by Your Team">
            Your team admin has pre-configured some credentials. You only need to provide {missingTeamCredentials.length} additional credential{missingTeamCredentials.length > 1 ? 's' : ''}.
          </Alert>
        )}

        {/* Configuration Form or Direct Connect */}
        {hasAnyConfig && !(hasTeamConfig && isFullyConfigured) ? (
          <ServerConfigForm
            server={filteredServer}
            onSuccess={handleConnectionSuccess}
            onError={handleConnectionError}
            onBack={handleBack}
            hasTeamConfig={hasTeamConfig}
          />
        ) : (
          <>
            {/* No Configuration Needed */}
            <Alert variant="info" title="Ready to Connect">
              This server doesn't require any credentials or configuration.
              Just give it a name and click "Connect Server".
            </Alert>

            {/* Connection Name Input */}
            <div className="space-y-1.5">
              <label
                htmlFor="connectionName"
                className="block text-sm font-medium text-gray-700"
              >
                Connection Name
              </label>
              <Input
                id="connectionName"
                type="text"
                placeholder={`e.g., "${server.name} Work" or "${server.name} Personal"`}
                value={connectionName}
                onChange={(e) => setConnectionName(e.target.value)}
              />
              <p className="text-xs text-gray-500">
                Optional: Give this connection a name to identify it (defaults to "{server.name}")
              </p>
            </div>

            {/* Tools Preview */}
            {toolsCount > 0 && (
              <div className="bg-gray-50 rounded-lg p-4">
                <h4 className="text-sm font-medium text-gray-700 mb-2">
                  Available Tools
                </h4>
                <div className="flex flex-wrap gap-2">
                  {(server.tools_preview || server.tools?.map(t => t.name) || [])
                    .slice(0, 5)
                    .map((tool) => (
                      <span
                        key={typeof tool === 'string' ? tool : tool}
                        className="px-2 py-1 bg-white border border-gray-200 rounded text-xs font-mono text-gray-700"
                      >
                        {typeof tool === 'string' ? tool : tool}
                      </span>
                    ))}
                  {toolsCount > 5 && (
                    <span className="px-2 py-1 text-xs text-gray-500">
                      +{toolsCount - 5} more
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Actions for no-config case */}
            <div className="flex justify-between gap-3 pt-4 border-t border-gray-200">
              <Button variant="ghost" onClick={onClose} disabled={connectMutation.isPending}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={() => {
                  setIsConnecting(true)
                  connectMutation.mutate()
                }}
                isLoading={connectMutation.isPending}
              >
                {connectMutation.isPending ? 'Connecting...' : 'Connect Server'}
              </Button>
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}
