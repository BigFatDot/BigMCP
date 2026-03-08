/**
 * MarketplaceBrowser - Browse and search MCP servers
 *
 * Includes an Admin mode for instance admins to manage marketplace sources
 * and server visibility using the same visual layout as the marketplace.
 */

import { useState, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  MagnifyingGlassIcon,
  Cog6ToothIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  PlusIcon,
  EyeIcon,
  EyeSlashIcon,
  ServerStackIcon,
  FolderIcon,
  Bars3Icon,
  UserGroupIcon,
} from '@heroicons/react/24/outline'
import { Input, CenteredSpinner, Alert, Card, Button } from '@/components/ui'
import { ServerCard } from './ServerCard'
import { ServerDetailModal } from './ServerDetailModal'
import { LocalRegistryManager } from './LocalRegistryManager'
import { marketplaceApi, adminRegistryApi } from '@/services/marketplace'
import type { SourceInfo, AdminServerInfo } from '@/services/marketplace'
import { useInstanceAdmin } from '@/hooks/useInstanceAdmin'
import { useAuth } from '@/hooks/useAuth'
import type { MCPServer, MarketplaceFilters } from '@/types/marketplace'

export function MarketplaceBrowser() {
  const { t } = useTranslation('marketplace')
  const { isInstanceAdmin, isLoading: adminLoading } = useInstanceAdmin()
  const { isEnterprise, isCloudSaaS, editionLoading } = useAuth()
  const queryClient = useQueryClient()

  // Team services only available for Enterprise and Cloud SaaS editions
  const supportsTeamServices = isEnterprise || isCloudSaaS

  const [filters, setFilters] = useState<MarketplaceFilters>({
    search: '',
    category: 'all',
    sort_by: 'popularity',
    sort_order: 'desc',
    limit: 200,
    offset: 0,
  })
  const [selectedServer, setSelectedServer] = useState<MCPServer | null>(null)
  const [adminMode, setAdminMode] = useState(false)
  const [adminSection, setAdminSection] = useState<'servers' | 'sources' | 'local'>('servers')

  // Fetch admin servers data at parent level (only when admin mode is active)
  // This prevents duplicate fetches in AdminNavigation and AdminPanel
  const { data: adminServers, refetch: refetchAdminServers, isLoading: adminServersLoading } = useQuery({
    queryKey: ['admin-all-servers', adminMode],
    queryFn: () => adminRegistryApi.listAllServers({ limit: 1000 }),
    staleTime: 60 * 1000, // 1 minute cache
    enabled: adminMode && isInstanceAdmin, // Only fetch when admin mode is active
  })

  // Fetch categories dynamically from backend
  const { data: apiCategories = [] } = useQuery({
    queryKey: ['marketplace-categories'],
    queryFn: () => marketplaceApi.listCategories(),
    staleTime: 5 * 60 * 1000,
  })

  // Map category IDs to translation keys
  const getCategoryLabel = useCallback((categoryId: string, defaultName: string): string => {
    const categoryMap: Record<string, string> = {
      'all': t('categories.all'),
      'ai': t('categories.ai'),
      'data': t('categories.data'),
      'dev': t('categories.dev'),
      'development': t('categories.development'),
      'productivity': t('categories.productivity'),
      'communication': t('categories.communication'),
      'storage': t('categories.storage'),
      'cloud': t('categories.cloud'),
      'search': t('categories.search'),
      'automation': t('categories.automation'),
      'security': t('categories.security'),
      'media': t('categories.media'),
      'documents': t('categories.documents'),
      'finance': t('categories.finance'),
      'payment': t('categories.payment'),
      'other': t('categories.other'),
    }
    return categoryMap[categoryId.toLowerCase()] || defaultName
  }, [t])

  // Build category list with "All Servers" at the start
  const categories = useMemo(() => {
    return [
      { id: 'all', name: t('filters.all'), count: 0 },
      ...apiCategories.map(cat => ({
        ...cat,
        name: getCategoryLabel(cat.id, cat.name),
      })),
    ]
  }, [apiCategories, t, getCategoryLabel])

  // Fetch team servers
  const {
    data: teamServers = [],
    isLoading: teamServersLoading,
    error: teamServersError,
  } = useQuery({
    queryKey: ['team-servers'],
    queryFn: () => marketplaceApi.listTeamServers(),
    enabled: filters.category === 'team',
    staleTime: 30 * 1000,
  })

  // Fetch servers (for regular marketplace view)
  const {
    data: servers = [],
    isLoading,
    error,
  } = useQuery({
    queryKey: ['marketplace-servers', filters],
    queryFn: () => {
      const apiFilters = { ...filters }
      if (apiFilters.category === 'all') {
        delete apiFilters.category
      }
      return marketplaceApi.listServers(apiFilters)
    },
    enabled: filters.category !== 'team',
  })

  // Determine which data to display
  const displayServers = filters.category === 'team'
    ? teamServers.map(ts => ({
        ...ts.marketplace_server,
        _teamConfig: ts.org_credential,
        _isFullyConfigured: ts.is_fully_configured,
      }))
    : servers
  const displayLoading = filters.category === 'team' ? teamServersLoading : isLoading
  const displayError = filters.category === 'team' ? teamServersError : error

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFilters((prev) => ({ ...prev, search: e.target.value }))
  }

  const handleCategoryChange = (category: string) => {
    setFilters((prev) => ({ ...prev, category }))
  }

  const isConnected = (serverId: string) => false

  const handleConnect = (server: MCPServer) => {
    setSelectedServer(server)
  }

  const handleViewDetails = (server: MCPServer) => {
    setSelectedServer(server)
  }

  const toggleAdminMode = () => {
    setAdminMode(!adminMode)
    if (!adminMode) {
      setAdminSection('servers')
    }
  }

  return (
    <div className="container py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-gray-900 mb-2">
          {t('title')}
        </h1>
        <p className="text-lg text-gray-600 font-serif">
          {t('subtitle')}
        </p>
      </div>

      {/* Search Bar */}
      <div className="mb-6 space-y-4">
        <div className="flex-1">
          <Input
            placeholder={t('search.placeholder')}
            value={filters.search}
            onChange={handleSearch}
            leftIcon={<MagnifyingGlassIcon className="h-5 w-5" />}
          />
        </div>

        {/* Row 1: Main Navigation */}
        <div className="flex flex-wrap gap-2 items-center">
          {/* Admin Button */}
          {!adminLoading && isInstanceAdmin && (
            <button
              onClick={toggleAdminMode}
              className={`px-4 py-2 rounded-full text-sm font-medium transition-all flex items-center gap-1.5 ${
                adminMode
                  ? 'bg-orange text-white'
                  : 'bg-orange-50 text-orange-700 hover:bg-orange-100 border border-orange-200'
              }`}
            >
              <Cog6ToothIcon className="w-4 h-4" />
              {t('admin.admin')}
            </button>
          )}

          {/* Admin section pills with counts */}
          {adminMode && isInstanceAdmin ? (
            <AdminNavigation
              activeSection={adminSection}
              onSectionChange={setAdminSection}
              onCategoryChange={handleCategoryChange}
              adminServers={adminServers || []}
            />
          ) : (
            /* Normal mode: All Servers + Team Services buttons (Team only for Enterprise/SaaS) */
            <>
              <button
                onClick={() => handleCategoryChange('all')}
                className={`px-4 py-2 rounded-full text-sm font-medium transition-all flex items-center gap-1.5 ${
                  filters.category === 'all'
                    ? 'bg-orange text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                <ServerStackIcon className="w-4 h-4" />
                {t('filters.all')}
              </button>
              {supportsTeamServices && (
                <button
                  onClick={() => handleCategoryChange('team')}
                  className={`px-4 py-2 rounded-full text-sm font-medium transition-all flex items-center gap-1.5 ${
                    filters.category === 'team'
                      ? 'bg-orange text-white'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                >
                  <UserGroupIcon className="w-4 h-4" />
                  {t('filters.team')}
                  {teamServers.length > 0 && filters.category !== 'team' && (
                    <span className="ml-1 text-xs opacity-75">({teamServers.length})</span>
                  )}
                </button>
              )}
            </>
          )}
        </div>

        {/* Row 2: Categories (always visible, filters marketplace or admin servers) */}
        <div className="flex flex-wrap gap-2">
          {categories.slice(1).map((category) => (
            <button
              key={category.id}
              onClick={() => {
                handleCategoryChange(category.id)
                // In admin mode, stay in admin but filter by category
                if (adminMode && adminSection !== 'servers') {
                  setAdminSection('servers')
                }
              }}
              className={`px-4 py-2 rounded-full text-sm font-medium transition-all ${
                filters.category === category.id
                  ? 'bg-orange text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {category.name}
              {category.count > 0 && (
                <span className="ml-1.5 text-xs opacity-75">({category.count})</span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Admin Panel Content */}
      {adminMode && isInstanceAdmin && (
        <AdminPanel
          activeSection={adminSection}
          categoryFilter={filters.category}
          searchFilter={filters.search}
          onViewDetails={handleViewDetails}
          adminServers={adminServers || []}
          adminServersLoading={adminServersLoading}
          refetchAdminServers={refetchAdminServers}
          invalidateMarketplace={() => {
            queryClient.invalidateQueries({ queryKey: ['marketplace-servers'] })
            queryClient.invalidateQueries({ queryKey: ['marketplace-categories'] })
          }}
        />
      )}

      {/* Regular Marketplace Content */}
      {!adminMode && (
        <>
          {displayLoading && <CenteredSpinner />}

          {displayError && (
            <Alert variant="error" title={t('admin.errorLoading')}>
              {displayError instanceof Error ? displayError.message : t('admin.failedToLoad')}
            </Alert>
          )}

          {!displayLoading && !displayError && displayServers.length === 0 && (
            <div className="text-center py-12">
              <p className="text-gray-600 font-serif text-lg">
                {filters.category === 'team'
                  ? t('admin.noTeamServices')
                  : t('admin.noMatchingServers')}
              </p>
            </div>
          )}

          {!displayLoading && !displayError && displayServers.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {displayServers.map((server) => (
                <ServerCard
                  key={server.id}
                  server={server}
                  isConnected={isConnected(server.id)}
                  onConnect={handleConnect}
                  onViewDetails={handleViewDetails}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Server Detail Modal */}
      {selectedServer && (
        <ServerDetailModal
          isOpen={!!selectedServer}
          onClose={() => setSelectedServer(null)}
          server={selectedServer}
          isConnected={isConnected(selectedServer.id)}
        />
      )}
    </div>
  )
}

/**
 * Admin Navigation Pills with counts
 */
interface AdminNavigationProps {
  activeSection: 'servers' | 'sources' | 'local'
  onSectionChange: (section: 'servers' | 'sources' | 'local') => void
  onCategoryChange: (category: string) => void
  adminServers: AdminServerInfo[]
}

function AdminNavigation({ activeSection, onSectionChange, onCategoryChange, adminServers }: AdminNavigationProps) {
  const { t } = useTranslation('marketplace')
  const { data: sources } = useQuery({
    queryKey: ['admin-sources'],
    queryFn: () => adminRegistryApi.listSources(),
    staleTime: 30 * 1000,
  })

  const { data: localServers } = useQuery({
    queryKey: ['admin-local-servers'],
    queryFn: () => adminRegistryApi.listLocalServers(),
    staleTime: 30 * 1000,
  })

  const enabledSourcesCount = sources?.filter(s => s.enabled).length || 0
  const totalSourcesCount = sources?.length || 0

  return (
    <>
      {/* All Servers */}
      <button
        onClick={() => {
          onSectionChange('servers')
          onCategoryChange('all')
        }}
        className={`px-4 py-2 rounded-full text-sm font-medium transition-all flex items-center gap-1.5 ${
          activeSection === 'servers'
            ? 'bg-orange text-white'
            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
        }`}
      >
        <ServerStackIcon className="w-4 h-4" />
        {t('filters.all')}
        <span className="ml-1 text-xs opacity-75">({adminServers.length})</span>
      </button>

      {/* Sources */}
      <button
        onClick={() => onSectionChange('sources')}
        className={`px-4 py-2 rounded-full text-sm font-medium transition-all flex items-center gap-1.5 ${
          activeSection === 'sources'
            ? 'bg-orange text-white'
            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
        }`}
      >
        <FolderIcon className="w-4 h-4" />
        {t('admin.sources')}
        <span className="ml-1 text-xs opacity-75">({enabledSourcesCount}/{totalSourcesCount})</span>
      </button>

      {/* Local Registry */}
      <button
        onClick={() => onSectionChange('local')}
        className={`px-4 py-2 rounded-full text-sm font-medium transition-all flex items-center gap-1.5 ${
          activeSection === 'local'
            ? 'bg-orange text-white'
            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
        }`}
      >
        <PlusIcon className="w-4 h-4" />
        {t('admin.localRegistry')}
        <span className="ml-1 text-xs opacity-75">({localServers?.length || 0})</span>
      </button>
    </>
  )
}

/**
 * Admin Panel Component - Uses ServerCard layout for servers
 */
interface AdminPanelProps {
  activeSection: 'servers' | 'sources' | 'local'
  categoryFilter: string
  searchFilter: string
  onViewDetails: (server: MCPServer) => void
  adminServers: AdminServerInfo[]
  adminServersLoading: boolean
  refetchAdminServers: () => void
  invalidateMarketplace: () => void
}

function AdminPanel({ activeSection, categoryFilter, searchFilter, onViewDetails, adminServers, adminServersLoading, refetchAdminServers, invalidateMarketplace }: AdminPanelProps) {
  const { t } = useTranslation('marketplace')
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [draggedSource, setDraggedSource] = useState<string | null>(null)
  const [orderedSources, setOrderedSources] = useState<SourceInfo[]>([])
  const [selectedServers, setSelectedServers] = useState<Set<string>>(new Set())
  const [isSyncing, setIsSyncing] = useState(false)

  // Fetch sources
  const { data: sources, refetch: refetchSources } = useQuery({
    queryKey: ['admin-sources'],
    queryFn: () => adminRegistryApi.listSources(),
    staleTime: 30 * 1000,
  })

  // Fetch local registry servers
  const { data: localServers, refetch: refetchLocalServers } = useQuery({
    queryKey: ['admin-local-servers'],
    queryFn: () => adminRegistryApi.listLocalServers(),
    staleTime: 30 * 1000,
  })

  // Sync orderedSources with fetched sources
  useMemo(() => {
    if (sources && sources.length > 0) {
      setOrderedSources([...sources].sort((a, b) => a.priority - b.priority))
    }
  }, [sources])

  // Filter servers by search and category
  const filteredServers = useMemo(() => {
    if (!adminServers) return []
    let result = adminServers

    // Filter by category
    if (categoryFilter && categoryFilter !== 'all') {
      result = result.filter(s => s.category === categoryFilter)
    }

    // Filter by search
    if (searchFilter) {
      const search = searchFilter.toLowerCase()
      result = result.filter(s =>
        s.id.toLowerCase().includes(search) ||
        s.name.toLowerCase().includes(search) ||
        s.category?.toLowerCase().includes(search)
      )
    }

    return result
  }, [adminServers, categoryFilter, searchFilter])

  // Handle source toggle
  const handleToggleSource = async (sourceId: string, enabled: boolean) => {
    try {
      await adminRegistryApi.toggleSource(sourceId, enabled)
      setMessage({ type: 'success', text: t('admin.sourceToggled', { id: sourceId, state: enabled ? t('admin.enabled') : t('admin.disabled') }) })
      refetchSources()
      refetchAdminServers()
    } catch (err: any) {
      setMessage({ type: 'error', text: err.response?.data?.detail || t('admin.failedToLoad') })
    }
  }

  // Drag & drop handlers for sources
  const handleDragStart = useCallback((e: React.DragEvent, sourceId: string) => {
    setDraggedSource(sourceId)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', sourceId)
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const handleDrop = useCallback(async (e: React.DragEvent, targetSourceId: string) => {
    e.preventDefault()
    if (!draggedSource || draggedSource === targetSourceId) {
      setDraggedSource(null)
      return
    }

    const newOrder = [...orderedSources]
    const draggedIndex = newOrder.findIndex(s => s.id === draggedSource)
    const targetIndex = newOrder.findIndex(s => s.id === targetSourceId)

    if (draggedIndex !== -1 && targetIndex !== -1) {
      const [removed] = newOrder.splice(draggedIndex, 1)
      newOrder.splice(targetIndex, 0, removed)
      setOrderedSources(newOrder)

      const priorities: Record<string, number> = {}
      newOrder.forEach((source, index) => {
        priorities[source.id] = index
      })

      try {
        await adminRegistryApi.updateSourcePriorities(priorities)
        setMessage({ type: 'success', text: t('admin.prioritiesUpdated') })
        refetchSources()
      } catch (err: any) {
        setMessage({ type: 'error', text: err.response?.data?.detail || t('admin.failedToLoad') })
        refetchSources()
      }
    }

    setDraggedSource(null)
  }, [draggedSource, orderedSources, refetchSources])

  const handleDragEnd = useCallback(() => {
    setDraggedSource(null)
  }, [])

  // Handle server visibility toggle
  const handleToggleVisibility = async (serverId: string, visible: boolean) => {
    try {
      await adminRegistryApi.toggleServerVisibility(serverId, visible)
      refetchAdminServers()
      invalidateMarketplace()
    } catch (err: any) {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to update visibility' })
    }
  }

  // Handle bulk visibility
  const handleBulkVisibility = async (visible: boolean) => {
    if (selectedServers.size === 0) return
    try {
      await adminRegistryApi.bulkToggleVisibility(Array.from(selectedServers), visible)
      setSelectedServers(new Set())
      refetchAdminServers()
      invalidateMarketplace()
    } catch (err: any) {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to update visibility' })
    }
  }

  // Toggle server selection
  const toggleServerSelection = (serverId: string) => {
    setSelectedServers(prev => {
      const next = new Set(prev)
      if (next.has(serverId)) {
        next.delete(serverId)
      } else {
        next.add(serverId)
      }
      return next
    })
  }

  // Convert AdminServerInfo to MCPServer format for ServerCard
  const toMCPServer = (server: AdminServerInfo): MCPServer => ({
    id: server.id,
    name: server.name,
    description: server.description || '',
    author: server.author || 'Community',
    source: server.source,
    category: server.category || 'other',
    tags: server.tags || [],
    tools_preview: server.tools_preview || [],
    tools_count: server.tools_count || 0,
    install_type: server.install_type || 'npm',
    is_official: server.is_official || false,
    is_verified: server.verified || false,
    requires_local_access: server.requires_local_access || false,
    requires_credentials: server.credentials_count > 0,
    icon_url: server.icon_url,
    icon_urls: server.icon_urls,
  } as MCPServer)

  return (
    <div className="space-y-4">
      {/* Message */}
      {message && (
        <div className={`p-3 rounded-lg text-sm flex items-center gap-2 ${
          message.type === 'success'
            ? 'bg-green-50 border border-green-200 text-green-700'
            : 'bg-red-50 border border-red-200 text-red-700'
        }`}>
          {message.type === 'success' && <CheckCircleIcon className="w-4 h-4" />}
          {message.text}
          <button onClick={() => setMessage(null)} className="ml-auto text-xs underline">{t('admin.dismiss')}</button>
        </div>
      )}

      {/* Bulk actions bar */}
      {activeSection === 'servers' && selectedServers.size > 0 && (
        <div className="flex items-center gap-3 p-3 bg-orange-50 border border-orange-200 rounded-lg">
          <span className="text-sm font-medium text-orange-700">
            {t('admin.selected', { count: selectedServers.size })}
          </span>
          <Button
            size="sm"
            variant="outline"
            onClick={() => handleBulkVisibility(true)}
            className="text-green-600 border-green-300 hover:bg-green-50"
          >
            <EyeIcon className="w-4 h-4 mr-1" />
            {t('admin.showAll')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => handleBulkVisibility(false)}
            className="text-orange-600 border-orange-300 hover:bg-orange-50"
          >
            <EyeSlashIcon className="w-4 h-4 mr-1" />
            {t('admin.hideAll')}
          </Button>
          <button
            onClick={() => setSelectedServers(new Set())}
            className="ml-auto text-sm text-gray-500 hover:text-gray-700"
          >
            {t('admin.clearSelection')}
          </button>
        </div>
      )}

      {/* Sources Section */}
      {activeSection === 'sources' && (
        <Card padding="lg">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-semibold text-gray-900">{t('admin.marketplaceSources')}</h3>
              <p className="text-sm text-gray-600">
                {t('admin.sourcesDescription')}
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                setIsSyncing(true)
                setMessage(null)
                try {
                  // Force sync to reload custom servers from mcp_servers.json
                  const result = await marketplaceApi.syncAndPersist(true)
                  setMessage({ type: 'success', text: t('admin.syncedServers', { count: result.sync.total_servers }) })
                  refetchAdminServers()
                  refetchSources()
                } catch (err: any) {
                  setMessage({ type: 'error', text: err.message || t('admin.failedToLoad') })
                } finally {
                  setIsSyncing(false)
                }
              }}
              disabled={isSyncing}
              className="flex items-center gap-2"
            >
              <ArrowPathIcon className={`w-4 h-4 ${isSyncing ? 'animate-spin' : ''}`} />
              {isSyncing ? t('admin.syncing') : t('admin.syncAll')}
            </Button>
          </div>

          <div className="space-y-2">
            {orderedSources.map((source, index) => (
              <div
                key={source.id}
                draggable
                onDragStart={(e) => handleDragStart(e, source.id)}
                onDragOver={handleDragOver}
                onDrop={(e) => handleDrop(e, source.id)}
                onDragEnd={handleDragEnd}
                className={`p-4 rounded-lg border transition-all cursor-move ${
                  draggedSource === source.id
                    ? 'border-orange-400 bg-orange-50 opacity-50 scale-[0.98]'
                    : source.enabled
                    ? 'border-green-200 bg-green-50 hover:border-green-300'
                    : 'border-gray-200 bg-gray-50 hover:border-gray-300'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className="flex-shrink-0 text-gray-400 hover:text-gray-600 cursor-grab active:cursor-grabbing">
                    <Bars3Icon className="w-5 h-5" />
                  </div>

                  <div className="flex-shrink-0 w-6 h-6 rounded-full bg-orange-100 text-orange-700 text-xs font-bold flex items-center justify-center">
                    {index + 1}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900">{source.name}</span>
                    </div>
                    <p className="text-sm text-gray-600 truncate">{source.description}</p>
                  </div>

                  <label className="relative inline-flex items-center cursor-pointer flex-shrink-0">
                    <input
                      type="checkbox"
                      checked={source.enabled}
                      onChange={(e) => {
                        e.stopPropagation()
                        handleToggleSource(source.id, e.target.checked)
                      }}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-300 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-orange-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-orange"></div>
                  </label>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Servers Section - Grid layout like marketplace */}
      {activeSection === 'servers' && (
        <>
          {adminServersLoading ? (
            <CenteredSpinner />
          ) : filteredServers.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-600 font-serif text-lg">{t('admin.noServersFound')}</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {filteredServers.map((server) => (
                <ServerCard
                  key={server.id}
                  server={toMCPServer(server)}
                  adminMode={true}
                  isSelected={selectedServers.has(server.id)}
                  isHidden={!server.visible_in_marketplace}
                  onToggleSelect={() => toggleServerSelection(server.id)}
                  onToggleVisibility={() => handleToggleVisibility(server.id, !server.visible_in_marketplace)}
                  onViewDetails={onViewDetails}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Local Registry Section */}
      {activeSection === 'local' && (
        <LocalRegistryManager
          servers={localServers || []}
          onAddServer={async (serverId, config, metadata) => {
            await adminRegistryApi.createServerFromConfig(serverId, config, metadata)
            setMessage({ type: 'success', text: `Server ${serverId} added` })
            refetchLocalServers()
            refetchAdminServers()
            invalidateMarketplace()
          }}
          onUpdateServer={async (serverId, config) => {
            await adminRegistryApi.updateServerConfig(serverId, config)
            setMessage({ type: 'success', text: `Server ${serverId} updated` })
            refetchLocalServers()
            refetchAdminServers()
            invalidateMarketplace()
          }}
          onRenameServer={async (oldServerId, newServerId, config) => {
            // Rename = create new + delete old
            const metadata = config._metadata ? {
              name: config._metadata.name,
              description: config._metadata.description,
              category: config._metadata.category,
              icon_url: config._metadata.iconUrl,
            } : undefined
            await adminRegistryApi.createServerFromConfig(newServerId, config, metadata)
            await adminRegistryApi.deleteLocalServer(oldServerId)
            setMessage({ type: 'success', text: `Server renamed from ${oldServerId} to ${newServerId}` })
            refetchLocalServers()
            refetchAdminServers()
            invalidateMarketplace()
          }}
          onUpdateMetadata={async (serverId, metadata) => {
            await adminRegistryApi.updateLocalServer(serverId, metadata)
            setMessage({ type: 'success', text: `Server ${serverId} metadata updated` })
            refetchLocalServers()
            refetchAdminServers()
            invalidateMarketplace()
          }}
          onDeleteServer={async (serverId) => {
            if (!confirm(`Delete server "${serverId}" from local registry?`)) return
            await adminRegistryApi.deleteLocalServer(serverId)
            setMessage({ type: 'success', text: `Server ${serverId} deleted` })
            refetchLocalServers()
            refetchAdminServers()
            invalidateMarketplace()
          }}
          onToggleVisibility={async (serverId, visible) => {
            await handleToggleVisibility(serverId, visible)
            refetchLocalServers()
            invalidateMarketplace()
          }}
        />
      )}
    </div>
  )
}

