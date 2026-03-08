/**
 * ServerDetailModal - Detailed view of an MCP server with connection options
 *
 * UX priorities:
 * 1. Credentials/config BEFORE tools (no scrolling to connect)
 * 2. Tools collapsible with preview
 * 3. Required vs optional credentials clearly separated
 * 4. Edition-aware display (SaaS vs Self-hosted)
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  CheckBadgeIcon,
  ShieldCheckIcon,
  LinkIcon,
  BookOpenIcon,
  CodeBracketIcon,
  KeyIcon,
  Cog6ToothIcon,
  WrenchScrewdriverIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline'
import { Modal, Button, Badge, Alert } from '@/components/ui'
import { ServerIcon } from './ServerIcon'
import { ConnectServerModal } from '../credentials/ConnectServerModal'
import { TeamServiceConfigModal } from '../team/TeamServiceConfigModal'
import { useAuth, useOrganization } from '@/hooks/useAuth'
import type { MCPServer, CredentialField } from '@/types/marketplace'

export interface ServerDetailModalProps {
  isOpen: boolean
  onClose: () => void
  server: MCPServer
  isConnected: boolean
}

const TOOLS_PREVIEW_LIMIT = 5

export function ServerDetailModal({
  isOpen,
  onClose,
  server,
  isConnected,
}: ServerDetailModalProps) {
  const { t } = useTranslation('marketplace')
  const { isCloudSaaS } = useAuth()
  const { isAdmin } = useOrganization()
  const [showConnectModal, setShowConnectModal] = useState(false)
  const [showTeamConfigModal, setShowTeamConfigModal] = useState(false)
  const [showAllTools, setShowAllTools] = useState(false)

  // Check if server has team configuration
  const teamConfig = (server as any)._teamConfig
  const hasTeamConfig = !!teamConfig
  const isFullyConfigured = (server as any)._isFullyConfigured || false

  // For team services, use the custom name from team config
  const displayName = teamConfig?.name || server.name

  // Check if server is available for this edition
  const isUnavailableInCloud = isCloudSaaS && server.requires_local_access

  // Get team credential keys (credentials already configured by admin)
  const teamCredentialKeys: string[] = teamConfig?.credential_keys || []

  // Separate credentials by type
  const allCredentials = server.credentials || []
  const requiredCredentials = allCredentials.filter(c => c.required)
  const optionalCredentials = allCredentials.filter(c => !c.required)

  // Filter by config type based on edition
  // In SaaS mode: only show remote credentials (API keys)
  // In Self-hosted mode: show all credentials
  const getFilteredCredentials = (creds: CredentialField[]) => {
    let filtered = creds

    // Filter by config_type for SaaS
    if (isCloudSaaS) {
      filtered = filtered.filter(c => c.config_type !== 'local')
    }

    // For team services that are partially configured, hide credentials already set by admin
    if (hasTeamConfig && !isFullyConfigured && teamCredentialKeys.length > 0) {
      filtered = filtered.filter(c => !teamCredentialKeys.includes(c.name))
    }

    return filtered
  }

  const filteredRequiredCredentials = getFilteredCredentials(requiredCredentials)
  const filteredOptionalCredentials = getFilteredCredentials(optionalCredentials)

  const hasRequiredCredentials = filteredRequiredCredentials.length > 0
  const hasOptionalCredentials = filteredOptionalCredentials.length > 0
  const hasAnyCredentials = hasRequiredCredentials || hasOptionalCredentials

  // Tools
  const tools = server.tools || []
  const toolsPreview = server.tools_preview || []
  const totalTools = tools.length || toolsPreview.length
  const visibleTools = showAllTools ? tools : tools.slice(0, TOOLS_PREVIEW_LIMIT)
  const hasMoreTools = tools.length > TOOLS_PREVIEW_LIMIT

  const handleConnect = () => {
    setShowConnectModal(true)
  }

  const handleConnectionComplete = () => {
    setShowConnectModal(false)
    onClose()
  }

  const handleShareAsTeamService = () => {
    setShowTeamConfigModal(true)
  }

  const handleTeamConfigSuccess = () => {
    setShowTeamConfigModal(false)
    onClose()
  }

  return (
    <>
      <Modal
        isOpen={isOpen && !showConnectModal && !showTeamConfigModal}
        onClose={onClose}
        size="xl"
      >
        <div className="space-y-6">
          {/* Header */}
          <div className="flex items-start gap-4">
            <ServerIcon
              name={server.name}
              iconUrl={server.icon_url}
              iconUrls={(server as any).icon_urls}
              size="lg"
            />

            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <h2 className="text-3xl font-bold text-gray-900">{displayName}</h2>
                {server.is_official && (
                  <Badge variant="primary" size="sm" className="bg-orange text-white">
                    {t('server.official')}
                  </Badge>
                )}
                {server.is_verified && !server.is_official && (
                  <ShieldCheckIcon
                    className="h-6 w-6 text-success"
                    title={t('server.verifiedByBigMCP')}
                  />
                )}
                {hasTeamConfig && (
                  <Badge variant="info" size="sm" className="flex items-center gap-1">
                    <UserGroupIcon className="w-3 h-3" />
                    {t('server.teamConfigured')}
                  </Badge>
                )}
              </div>
              <p className="text-sm text-gray-600 font-sans">
                {t('server.by')} {server.author}
                {server.version && ` • v${server.version}`}
              </p>
            </div>

            <div className="flex items-center gap-2">
              {isConnected && (
                <Badge variant="success">{t('server.connected')}</Badge>
              )}
              {totalTools > 0 && (
                <Badge variant="gray" className="flex items-center gap-1">
                  <WrenchScrewdriverIcon className="h-3 w-3" />
                  {t('server.nToolsCount', { count: totalTools })}
                </Badge>
              )}
            </div>
          </div>

          {/* Description */}
          <p className="text-gray-700 font-serif leading-relaxed">
            {server.description}
          </p>

          {/* Tags - compact */}
          {server.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {server.tags.slice(0, 6).map((tag) => (
                <Badge key={tag} variant="gray" size="sm">
                  {tag}
                </Badge>
              ))}
              {server.tags.length > 6 && (
                <Badge variant="gray" size="sm">+{server.tags.length - 6}</Badge>
              )}
            </div>
          )}

          {/* Local Access Warning - show early if relevant */}
          {server.requires_local_access && (
            <Alert
              variant={isUnavailableInCloud ? 'error' : 'info'}
              title={isUnavailableInCloud ? t('server.selfHostedOnly') : t('server.requiresLocalAccess')}
            >
              {isUnavailableInCloud ? t('server.cloudWarning') : t('server.localAccessNote')}
            </Alert>
          )}

          {/* ===== CREDENTIALS SECTION (BEFORE TOOLS) ===== */}
          {hasAnyCredentials && !isUnavailableInCloud && (
            <div className="space-y-4 py-4 border-y border-gray-200">
              <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                <KeyIcon className="h-5 w-5" />
                {t('detail.configuration')}
                {isCloudSaaS && (
                  <Badge variant="primary" size="sm">{t('detail.cloudEdition')}</Badge>
                )}
              </h3>

              {/* Required Credentials */}
              {hasRequiredCredentials && (
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                    {t('detail.requiredCredentials', { count: filteredRequiredCredentials.length })}
                    <span className="text-xs text-gray-500 font-normal">
                      {t('detail.mustProvide')}
                    </span>
                  </h4>
                  <div className="space-y-2">
                    {filteredRequiredCredentials.map((cred) => (
                      <CredentialCard key={cred.name} credential={cred} variant="required" />
                    ))}
                  </div>
                </div>
              )}

              {/* Optional Credentials */}
              {hasOptionalCredentials && (
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                    <Cog6ToothIcon className="h-4 w-4" />
                    {t('detail.optionalConfig', { count: filteredOptionalCredentials.length })}
                    <span className="text-xs text-gray-500 font-normal">
                      {t('detail.canCustomize')}
                    </span>
                  </h4>
                  <div className="space-y-2">
                    {filteredOptionalCredentials.map((cred) => (
                      <CredentialCard key={cred.name} credential={cred} variant="optional" />
                    ))}
                  </div>
                </div>
              )}

              {/* Edition-specific hint for self-hosted */}
              {!isCloudSaaS && server.requires_local_access && (
                <p className="text-xs text-gray-500 italic">
                  {t('detail.localConfigNote')}
                </p>
              )}
            </div>
          )}

          {/* ===== TOOLS SECTION (COLLAPSIBLE) ===== */}
          {totalTools > 0 && (
            <div className="py-4 border-y border-gray-200">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                  <WrenchScrewdriverIcon className="h-5 w-5" />
                  {t('detail.availableTools', { count: totalTools })}
                </h3>
                {hasMoreTools && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowAllTools(!showAllTools)}
                    className="text-sm"
                  >
                    {showAllTools ? (
                      <>
                        <ChevronUpIcon className="h-4 w-4 mr-1" />
                        {t('detail.showLess')}
                      </>
                    ) : (
                      <>
                        <ChevronDownIcon className="h-4 w-4 mr-1" />
                        {t('detail.showAllTools', { count: totalTools })}
                      </>
                    )}
                  </Button>
                )}
              </div>

              {/* Full tool details if available */}
              {tools.length > 0 ? (
                <div className="space-y-2">
                  {visibleTools.map((tool) => (
                    <div
                      key={tool.name}
                      className="px-3 py-2 bg-gray-50 rounded-lg border border-gray-100"
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm font-semibold text-gray-900">
                          {tool.name}
                        </span>
                        {tool.is_read_only && (
                          <Badge variant="gray" size="sm">{t('detail.readOnly')}</Badge>
                        )}
                        {tool.is_destructive && (
                          <Badge variant="error" size="sm">{t('detail.destructive')}</Badge>
                        )}
                      </div>
                      {tool.description && (
                        <p className="text-sm text-gray-600 font-sans mt-0.5 line-clamp-2">
                          {tool.description}
                        </p>
                      )}
                    </div>
                  ))}

                  {/* Hidden tools indicator */}
                  {!showAllTools && hasMoreTools && (
                    <p className="text-sm text-gray-500 text-center py-2">
                      {t('server.moreTools', { count: tools.length - TOOLS_PREVIEW_LIMIT })}
                    </p>
                  )}
                </div>
              ) : (
                /* Fallback to preview (just names) */
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {toolsPreview.slice(0, showAllTools ? undefined : TOOLS_PREVIEW_LIMIT).map((toolName) => (
                    <div
                      key={toolName}
                      className="px-2 py-1.5 bg-gray-50 rounded text-xs font-mono text-gray-700 truncate"
                    >
                      {toolName}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Links - inline */}
          {(server.documentation_url || server.repository_url || server.homepage_url) && (
            <div className="flex flex-wrap gap-2">
              {server.documentation_url && (
                <a
                  href={server.documentation_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                >
                  <BookOpenIcon className="h-4 w-4" />
                  {t('detail.docs')}
                </a>
              )}
              {server.repository_url && (
                <a
                  href={server.repository_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                >
                  <CodeBracketIcon className="h-4 w-4" />
                  {t('server.repository')}
                </a>
              )}
              {server.homepage_url && (
                <a
                  href={server.homepage_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                >
                  <LinkIcon className="h-4 w-4" />
                  {t('server.homepage')}
                </a>
              )}
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-between gap-3 pt-4 border-t border-gray-200">
            <Button variant="secondary" onClick={onClose}>
              {t('detail.close')}
            </Button>
            <div className="flex gap-2">
              {/* Configure and Share (Admin only) */}
              {isAdmin && !hasTeamConfig && (
                <Button
                  variant="secondary"
                  onClick={handleShareAsTeamService}
                  className="flex items-center gap-2 border-orange-300 text-orange-700 hover:bg-orange-50"
                >
                  <UserGroupIcon className="w-4 h-4" />
                  {t('detail.configureAndShare')}
                </Button>
              )}
              <Button
                variant={isUnavailableInCloud ? 'secondary' : 'primary'}
                onClick={handleConnect}
                disabled={isConnected || isUnavailableInCloud}
              >
                {isConnected
                  ? t('detail.alreadyConnected')
                  : isUnavailableInCloud
                    ? t('server.selfHostedOnly')
                    : hasTeamConfig && isFullyConfigured
                      ? t('detail.connectWithTeamCredentials')
                      : hasRequiredCredentials
                        ? t('detail.configureAndConnect')
                        : t('detail.connectServer')}
              </Button>
            </div>
          </div>
        </div>
      </Modal>

      {/* Connect Server Modal */}
      {showConnectModal && (
        <ConnectServerModal
          isOpen={showConnectModal}
          onClose={() => setShowConnectModal(false)}
          server={server}
          onComplete={handleConnectionComplete}
        />
      )}

      {/* Team Service Config Modal */}
      {showTeamConfigModal && (
        <TeamServiceConfigModal
          isOpen={showTeamConfigModal}
          onClose={() => setShowTeamConfigModal(false)}
          server={server}
          onSuccess={handleTeamConfigSuccess}
        />
      )}
    </>
  )
}

/**
 * CredentialCard - Displays a single credential field
 */
interface CredentialCardProps {
  credential: CredentialField
  variant: 'required' | 'optional'
}

function CredentialCard({ credential, variant }: CredentialCardProps) {
  const { t } = useTranslation('marketplace')
  const isRequired = variant === 'required'
  const configType = credential.config_type
  const isLocalConfig = configType === 'local'
  const displayName = credential.display_name || credential.name

  return (
    <div
      className={`px-3 py-2.5 rounded-lg border ${
        isRequired
          ? 'bg-amber-50 border-amber-200'
          : 'bg-gray-50 border-gray-200'
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`text-sm font-medium ${
            isRequired ? 'text-amber-800' : 'text-gray-700'
          }`}>
            {displayName}
          </span>
          {isRequired ? (
            <Badge variant="warning" size="sm">{t('credentials.required')}</Badge>
          ) : (
            <Badge variant="gray" size="sm">{t('credentials.optional')}</Badge>
          )}
          {isLocalConfig && (
            <Badge variant="gray" size="sm" className="bg-blue-100 text-blue-700">
              {t('credentials.local')}
            </Badge>
          )}
        </div>
        {credential.documentation_url && (
          <a
            href={credential.documentation_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-orange hover:underline whitespace-nowrap"
          >
            {credential.type === 'secret' ? t('credentials.getApiKey') : t('server.documentation')} →
          </a>
        )}
      </div>
      {/* Show env var name if different from display name */}
      {credential.display_name && credential.display_name !== credential.name && (
        <p className="text-xs text-gray-400 font-mono mt-0.5">
          {credential.name}
        </p>
      )}
      {credential.description && (
        <p className={`text-xs mt-1 ${
          isRequired ? 'text-amber-700' : 'text-gray-600'
        }`}>
          {credential.description}
        </p>
      )}
      {credential.default_value && !isRequired && (
        <p className="text-xs text-gray-500 mt-1">
          {t('credentials.default')} <code className="bg-gray-100 px-1 rounded">{credential.default_value}</code>
        </p>
      )}
      {credential.example && !credential.default_value && (
        <p className="text-xs text-gray-400 mt-1">
          {t('credentials.example')} <code className="bg-gray-100 px-1 rounded">{credential.example}</code>
        </p>
      )}
    </div>
  )
}
