/**
 * ServerCard - Displays an MCP server in the marketplace
 *
 * Supports admin mode for visibility management with same visual style.
 */

import { useTranslation } from 'react-i18next'
import { CheckBadgeIcon, ShieldCheckIcon, ComputerDesktopIcon, WrenchScrewdriverIcon, KeyIcon, Cog6ToothIcon, EyeIcon, EyeSlashIcon } from '@heroicons/react/24/solid'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter, Badge, Button } from '@/components/ui'
import { ServerIcon } from './ServerIcon'
import { useAuth } from '@/hooks/useAuth'
import type { MCPServer } from '@/types/marketplace'

export interface ServerCardProps {
  server: MCPServer
  isConnected?: boolean
  onConnect?: (server: MCPServer) => void
  onViewDetails?: (server: MCPServer) => void
  // Admin mode props
  adminMode?: boolean
  isSelected?: boolean
  isHidden?: boolean
  onToggleSelect?: () => void
  onToggleVisibility?: () => void
}

export function ServerCard({
  server,
  isConnected = false,
  onConnect,
  onViewDetails,
  adminMode = false,
  isSelected = false,
  isHidden = false,
  onToggleSelect,
  onToggleVisibility,
}: ServerCardProps) {
  const { t } = useTranslation('marketplace')
  const { isCloudSaaS } = useAuth()

  const handleConnect = (e: React.MouseEvent) => {
    e.stopPropagation()
    onConnect?.(server)
  }

  const handleViewDetails = () => {
    onViewDetails?.(server)
  }

  // Check if server is available for this edition
  const isUnavailableInCloud = isCloudSaaS && server.requires_local_access

  // Get tools count from tools array or tools_count field
  const toolsCount = (server as any).tools_count || server.tools?.length || server.tools_preview?.length || 0

  // For team services, use the custom name from team config
  const teamConfig = (server as any)._teamConfig
  const displayName = teamConfig?.name || server.name

  return (
    <Card
      hover
      onClick={handleViewDetails}
      className={`cursor-pointer relative ${adminMode && isSelected ? 'ring-2 ring-orange ring-opacity-50' : ''} ${adminMode && isHidden ? 'opacity-60' : ''}`}
    >
      {/* Admin mode: Selection checkbox */}
      {adminMode && (
        <div className="absolute top-3 left-3 z-10">
          <input
            type="checkbox"
            checked={isSelected}
            onChange={(e) => {
              e.stopPropagation()
              onToggleSelect?.()
            }}
            onClick={(e) => e.stopPropagation()}
            className="w-4 h-4 text-orange border-gray-300 rounded focus:ring-orange cursor-pointer"
          />
        </div>
      )}

      {/* Admin mode: Hidden badge */}
      {adminMode && isHidden && (
        <div className="absolute top-3 right-3 z-10">
          <Badge variant="warning" size="sm" className="flex items-center gap-1">
            <EyeSlashIcon className="w-3 h-3" />
            {t('server.hidden')}
          </Badge>
        </div>
      )}

      <CardHeader className={adminMode ? 'pl-10' : ''}>
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            {/* Server Icon with fallback chain */}
            <ServerIcon
              name={server.name}
              iconUrl={server.icon_url}
              iconUrls={(server as any).icon_urls}
            />

            <div>
              <div className="flex items-center gap-2">
                <CardTitle className="text-lg">{displayName}</CardTitle>
                {server.is_official && (
                  <CheckBadgeIcon
                    className="h-5 w-5 text-orange"
                    title={t('server.officialMCP')}
                  />
                )}
                {server.is_verified && (
                  <ShieldCheckIcon
                    className="h-5 w-5 text-success"
                    title={t('server.verifiedByBigMCP')}
                  />
                )}
              </div>
              <p className="text-xs text-gray-500 font-sans">{t('server.by')} {server.author || 'Community'}</p>
            </div>
          </div>

          {/* Connection Status or Tools Count */}
          {isConnected ? (
            <Badge variant="success" size="sm">
              {t('server.connected')}
            </Badge>
          ) : toolsCount > 0 && (
            <Badge variant="gray" size="sm" className="flex items-center gap-1">
              <WrenchScrewdriverIcon className="h-3 w-3" />
              {toolsCount}
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent>
        <CardDescription className="line-clamp-2 mb-3">
          {server.description}
        </CardDescription>

        {/* Tags */}
        {server.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {server.tags.slice(0, 3).map((tag) => (
              <Badge key={tag} variant="gray" size="sm">
                {tag}
              </Badge>
            ))}
            {server.tags.length > 3 && (
              <Badge variant="gray" size="sm">
                {t('server.more', { count: server.tags.length - 3 })}
              </Badge>
            )}
          </div>
        )}

        {/* Tools Preview */}
        {toolsCount > 0 && (
          <div className="text-sm text-gray-600 font-sans">
            <span className="font-medium text-gray-900">{t('server.toolsLabel', { count: toolsCount })}</span>
            <span className="ml-2">
              {(server.tools_preview || []).slice(0, 3).join(', ')}
              {toolsCount > 3 && ` ${t('server.more', { count: toolsCount - 3 })}`}
            </span>
          </div>
        )}
      </CardContent>

      <CardFooter>
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center gap-2 flex-wrap">
            {/* Local access indicator - different messaging for SaaS vs self-hosted */}
            {server.requires_local_access && (
              <Badge
                variant={isUnavailableInCloud ? 'error' : 'gray'}
                size="sm"
                className="flex items-center gap-1"
              >
                <ComputerDesktopIcon className="h-3 w-3" />
                {isUnavailableInCloud ? t('server.selfHostedOnly') : t('server.localAccess')}
              </Badge>
            )}
            {/* Required credentials (API keys that must be provided) */}
            {server.requires_credentials && (
              <Badge variant="warning" size="sm" className="flex items-center gap-1">
                <KeyIcon className="h-3 w-3" />
                {t('server.apiKeyRequired')}
              </Badge>
            )}
            {/* Optional credentials (configuration available but not required) */}
            {!server.requires_credentials && (server as any).has_optional_credentials && (
              <Badge variant="gray" size="sm" className="flex items-center gap-1">
                <Cog6ToothIcon className="h-3 w-3" />
                {t('server.configAvailable')}
              </Badge>
            )}
            {server.license && (
              <span className="text-xs text-gray-500 font-sans">{server.license}</span>
            )}
            {/* Admin mode: Install type badge */}
            {adminMode && server.install_type && (
              <Badge variant="gray" size="sm" className="font-mono">
                {server.install_type}
              </Badge>
            )}
            {/* Admin mode: Visibility status text */}
            {adminMode && (
              <span className="text-xs text-gray-500 font-sans">
                {isHidden ? t('server.hiddenFromMarketplace') : t('server.visibleInMarketplace')}
              </span>
            )}
          </div>

          {/* Admin mode: Visibility toggle button */}
          {adminMode ? (
            <button
              onClick={(e) => {
                e.stopPropagation()
                onToggleVisibility?.()
              }}
              className={`p-2 rounded-lg transition-colors ${
                isHidden
                  ? 'text-orange-600 hover:bg-orange-100'
                  : 'text-green-600 hover:bg-green-100'
              }`}
              title={isHidden ? t('server.showInMarketplace') : t('server.hideFromMarketplace')}
            >
              {isHidden ? (
                <EyeIcon className="w-5 h-5" />
              ) : (
                <EyeSlashIcon className="w-5 h-5" />
              )}
            </button>
          ) : (
            <Button
              variant={isConnected ? 'secondary' : (isUnavailableInCloud ? 'secondary' : 'primary')}
              size="sm"
              onClick={handleConnect}
              disabled={isUnavailableInCloud}
              title={isUnavailableInCloud ? t('server.cloudUnavailable') : undefined}
            >
              {isConnected ? t('server.manage') : (isUnavailableInCloud ? t('server.unavailable') : t('server.connect'))}
            </Button>
          )}
        </div>
      </CardFooter>
    </Card>
  )
}
