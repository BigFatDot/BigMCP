/**
 * Tools Dashboard - Unified Tool Management Interface
 *
 * Combines:
 * - Connected servers with their tools
 * - Tool groups for customized access control
 *
 * Single cohesive page for optimal user experience.
 * Supports organization/team context for multi-tenant access.
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircleIcon,
  XCircleIcon,
  XMarkIcon,
  TrashIcon,
  ArrowPathIcon,
  PlayIcon,
  StopIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  EyeIcon,
  WrenchScrewdriverIcon,
  PlusIcon,
  BoltIcon,
  ArchiveBoxIcon,
  BuildingOffice2Icon,
  KeyIcon,
  UsersIcon,
  UserIcon,
  InformationCircleIcon,
} from '@heroicons/react/24/outline'
import {
  Card,
  CardContent,
  Button,
  Badge,
  Alert,
  CenteredSpinner,
} from '@/components/ui'
import { cn } from '@/utils/cn'
import { credentialsApi, serverControlApi, toolGroupsApi, orgCredentialsApi } from '@/services/marketplace'
import type { UserCredential, ToolInfo, ToolGroup, OrganizationCredential } from '@/types/marketplace'
import { useOrganization, useFeatureAccess } from '@/hooks/useAuth'

// Helper to clean display names (remove "Credentials" suffix)
const getDisplayName = (name: string | undefined) => {
  if (!name) return 'Unnamed Server'
  return name.replace(/ Credentials$/i, '').trim()
}

// Color options for toolboxes
const GROUP_COLORS = [
  { id: 'orange', bg: 'bg-orange-100', text: 'text-orange', ring: 'ring-orange' },
  { id: 'blue', bg: 'bg-blue-100', text: 'text-blue-600', ring: 'ring-blue-500' },
  { id: 'green', bg: 'bg-green-100', text: 'text-green-600', ring: 'ring-green-500' },
  { id: 'purple', bg: 'bg-purple-100', text: 'text-purple-600', ring: 'ring-purple-500' },
  { id: 'pink', bg: 'bg-pink-100', text: 'text-pink-600', ring: 'ring-pink-500' },
]

type ViewMode = 'servers' | 'groups'

interface CreateGroupModalProps {
  isOpen: boolean
  onClose: () => void
  availableTools: ToolInfo[]
  canShareWithOrg: boolean
}

function CreateGroupModal({ isOpen, onClose, availableTools, canShareWithOrg }: CreateGroupModalProps) {
  const { t } = useTranslation('dashboard')
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selectedColor, setSelectedColor] = useState('orange')
  const [selectedTools, setSelectedTools] = useState<string[]>([])
  const [visibility, setVisibility] = useState<'private' | 'organization'>('private')
  const [step, setStep] = useState<'info' | 'tools'>('info')

  const createMutation = useMutation({
    mutationFn: async () => {
      const group = await toolGroupsApi.create({
        name,
        description: description || undefined,
        color: selectedColor,
        visibility: canShareWithOrg ? visibility : 'private',
      })

      // Add each selected tool to the group
      for (const toolId of selectedTools) {
        await toolGroupsApi.addTool(group.id, toolId)
      }

      return group
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tool-groups'] })
      handleClose()
    },
    onError: (error) => {
      alert(`Failed to create group: ${error instanceof Error ? error.message : 'Unknown error'}`)
    },
  })

  const handleClose = () => {
    setName('')
    setDescription('')
    setSelectedColor('orange')
    setSelectedTools([])
    setVisibility('private')
    setStep('info')
    onClose()
  }

  const toggleTool = (toolId: string) => {
    setSelectedTools((prev) =>
      prev.includes(toolId) ? prev.filter((id) => id !== toolId) : [...prev, toolId]
    )
  }

  // Group tools by server
  const toolsByServer = availableTools.reduce((acc, tool) => {
    const serverName = tool.server_name || 'Unknown Server'
    if (!acc[serverName]) acc[serverName] = []
    acc[serverName].push(tool)
    return acc
  }, {} as Record<string, ToolInfo[]>)

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-hidden flex flex-col">
        <div className="p-6 border-b border-gray-200">
          <h2 className="text-xl font-bold text-gray-900">{t('tools.createModal.title')}</h2>
          <p className="text-sm text-gray-600 mt-1">
            {step === 'info' ? t('tools.createModal.stepInfo') : t('tools.createModal.stepTools')}
          </p>
          <div className="flex items-center gap-2 mt-4">
            <div className={cn(
              'w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold',
              step === 'info' ? 'bg-orange text-white' : 'bg-green-500 text-white'
            )}>
              {step === 'tools' ? <CheckCircleIcon className="w-4 h-4" /> : '1'}
            </div>
            <div className="flex-1 h-1 bg-gray-200 rounded">
              <div className={cn('h-full rounded transition-all bg-orange', step === 'tools' ? 'w-full' : 'w-0')} />
            </div>
            <div className={cn(
              'w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold',
              step === 'tools' ? 'bg-orange text-white' : 'bg-gray-200 text-gray-500'
            )}>
              2
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {step === 'info' ? (
            <div className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">{t('tools.createModal.groupName')}</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t('tools.createModal.groupNamePlaceholder')}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">{t('tools.groups.description')}</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder={t('tools.createModal.descriptionPlaceholder')}
                  rows={2}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">{t('tools.createModal.color')}</label>
                <div className="flex gap-3">
                  {GROUP_COLORS.map((color) => (
                    <button
                      key={color.id}
                      onClick={() => setSelectedColor(color.id)}
                      className={cn(
                        'w-10 h-10 rounded-lg border-2 transition-all',
                        color.bg,
                        selectedColor === color.id
                          ? `border-gray-400 ring-2 ring-offset-2 ${color.ring}`
                          : 'border-transparent hover:scale-110'
                      )}
                    >
                      {selectedColor === color.id && <CheckCircleIcon className={cn('w-5 h-5 mx-auto', color.text)} />}
                    </button>
                  ))}
                </div>
              </div>

              {/* Visibility - Only for Team plans */}
              {canShareWithOrg && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">{t('tools.createModal.visibility')}</label>
                  <div className="flex gap-3">
                    <button
                      onClick={() => setVisibility('private')}
                      className={cn(
                        'flex-1 px-4 py-3 rounded-lg border-2 text-left transition-all',
                        visibility === 'private'
                          ? 'border-orange bg-orange-50'
                          : 'border-gray-200 hover:border-gray-300'
                      )}
                    >
                      <p className="font-medium text-gray-900">{t('tools.createModal.visibilityPrivate')}</p>
                      <p className="text-xs text-gray-500">{t('tools.createModal.visibilityPrivateDesc')}</p>
                    </button>
                    <button
                      onClick={() => setVisibility('organization')}
                      className={cn(
                        'flex-1 px-4 py-3 rounded-lg border-2 text-left transition-all',
                        visibility === 'organization'
                          ? 'border-orange bg-orange-50'
                          : 'border-gray-200 hover:border-gray-300'
                      )}
                    >
                      <p className="font-medium text-gray-900">{t('tools.createModal.visibilityOrganization')}</p>
                      <p className="text-xs text-gray-500">{t('tools.createModal.visibilityOrganizationDesc')}</p>
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between bg-gray-50 p-3 rounded-lg">
                <span className="text-sm text-gray-600">
                  {t('tools.createModal.toolsSelected', { count: selectedTools.length })}
                </span>
                {selectedTools.length > 0 && (
                  <button onClick={() => setSelectedTools([])} className="text-sm text-orange hover:underline">
                    {t('tools.createModal.clearAll')}
                  </button>
                )}
              </div>

              {Object.entries(toolsByServer).map(([serverName, tools]) => (
                <div key={serverName} className="border border-gray-200 rounded-lg overflow-hidden">
                  <div className="bg-gray-50 px-4 py-2 flex items-center justify-between">
                    <span className="font-medium text-gray-900">{serverName}</span>
                    <button
                      onClick={() => {
                        const serverToolIds = tools.map((t) => t.id)
                        const allSelected = serverToolIds.every((id) => selectedTools.includes(id))
                        if (allSelected) {
                          setSelectedTools((prev) => prev.filter((id) => !serverToolIds.includes(id)))
                        } else {
                          setSelectedTools((prev) => [...new Set([...prev, ...serverToolIds])])
                        }
                      }}
                      className="text-xs text-orange hover:underline"
                    >
                      {tools.every((tool) => selectedTools.includes(tool.id)) ? t('tools.createModal.deselectAll') : t('tools.createModal.selectAll')}
                    </button>
                  </div>
                  <div className="divide-y divide-gray-100">
                    {tools.map((tool) => (
                      <label
                        key={tool.id}
                        className={cn(
                          'flex items-start gap-3 p-3 cursor-pointer transition-colors',
                          selectedTools.includes(tool.id) ? 'bg-orange-50' : 'hover:bg-gray-50'
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={selectedTools.includes(tool.id)}
                          onChange={() => toggleTool(tool.id)}
                          className="mt-0.5 rounded border-gray-300 text-orange focus:ring-orange"
                        />
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-gray-900 text-sm">{tool.display_name || tool.tool_name}</p>
                          {tool.description && <p className="text-xs text-gray-500 line-clamp-1">{tool.description}</p>}
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              ))}

              {Object.keys(toolsByServer).length === 0 && (
                <div className="text-center py-8 text-gray-500">
                  <WrenchScrewdriverIcon className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                  <p>{t('tools.createModal.noToolsAvailable')}</p>
                  <p className="text-sm">{t('tools.createModal.connectServersFirst')}</p>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="p-6 border-t border-gray-200 flex justify-between">
          {step === 'tools' && (
            <Button variant="ghost" onClick={() => setStep('info')}>{t('tools.createModal.back')}</Button>
          )}
          <div className="flex gap-3 ml-auto">
            <Button variant="secondary" onClick={handleClose}>{t('tools.createModal.cancel')}</Button>
            {step === 'info' ? (
              <Button variant="primary" onClick={() => setStep('tools')} disabled={!name.trim()}>
                {t('tools.createModal.nextSelectTools')}
              </Button>
            ) : (
              <Button
                variant="primary"
                onClick={() => createMutation.mutate()}
                disabled={createMutation.isPending}
              >
                {createMutation.isPending ? t('tools.createModal.creating') : t('tools.createModal.createGroup', { count: selectedTools.length })}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

type ServerTabType = 'personal' | 'team'

export function ToolsDashboard() {
  const { t } = useTranslation('dashboard')
  const queryClient = useQueryClient()
  const { organizationName, hasOrganization, isTeamOrg } = useOrganization()
  const { features, isTeam, isEnterprise } = useFeatureAccess()
  const [viewMode, setViewMode] = useState<ViewMode>('servers')
  const [serverTab, setServerTab] = useState<ServerTabType>('personal')
  const [expandedServers, setExpandedServers] = useState<Set<string>>(new Set())
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())
  const [showCreateGroupModal, setShowCreateGroupModal] = useState(false)
  const [showInfoBanner, setShowInfoBanner] = useState(() => {
    return localStorage.getItem('services-info-banner-dismissed') !== 'true'
  })

  // Can share with organization if user has Team/Enterprise plan and organizations feature
  const canShareWithOrg = (isTeam || isEnterprise) && features.organizations && hasOrganization

  // Fetch credentials (servers)
  const { data: credentials = [], isLoading: isLoadingCredentials, error: credentialsError } = useQuery({
    queryKey: ['user-credentials'],
    queryFn: () => credentialsApi.listUserCredentials(),
  })

  // Connection status is derived from credentials (is_active flag)
  // No separate API call needed - credentials already have all the info

  // Fetch available tools
  const { data: availableTools = [], isLoading: isLoadingTools, error: toolsError } = useQuery({
    queryKey: ['available-tools'],
    queryFn: () => toolGroupsApi.listAvailableTools(),
    retry: 1,
  })

  // Fetch tool groups
  const { data: groupsData } = useQuery({
    queryKey: ['tool-groups'],
    queryFn: () => toolGroupsApi.list(),
  })

  // Fetch organization credentials (for Team Servers tab)
  const { data: orgCredentials = [] } = useQuery({
    queryKey: ['org-credentials'],
    queryFn: () => orgCredentialsApi.listOrgCredentials(),
    enabled: isTeamOrg, // Only fetch for team organizations
  })

  // Mutations
  const deleteCredentialMutation = useMutation({
    mutationFn: (credentialId: string) => credentialsApi.deleteUserCredential(credentialId),
    onMutate: async (credentialId) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['user-credentials'] })
      // Snapshot the previous value
      const previousCredentials = queryClient.getQueryData<UserCredential[]>(['user-credentials'])
      // Optimistically remove from the list
      queryClient.setQueryData<UserCredential[]>(['user-credentials'], (old) =>
        old?.filter((cred) => cred.id !== credentialId)
      )
      return { previousCredentials }
    },
    onError: (_err, _credentialId, context) => {
      // Rollback on error
      if (context?.previousCredentials) {
        queryClient.setQueryData(['user-credentials'], context.previousCredentials)
      }
    },
    onSettled: async () => {
      // Always refetch after success or error to sync with server
      await queryClient.refetchQueries({ queryKey: ['user-credentials'] })
      await queryClient.refetchQueries({ queryKey: ['available-tools'] })
    },
  })

  const startServerMutation = useMutation({
    mutationFn: (serverId: string) => serverControlApi.startServer(serverId),
    onMutate: async (serverId) => {
      await queryClient.cancelQueries({ queryKey: ['user-credentials'] })
      const previousCredentials = queryClient.getQueryData<UserCredential[]>(['user-credentials'])
      queryClient.setQueryData<UserCredential[]>(['user-credentials'], (old) =>
        old?.map((cred) =>
          cred.server_id === serverId ? { ...cred, server_status: 'starting' } : cred
        )
      )
      return { previousCredentials }
    },
    onError: (_err, _vars, context) => {
      if (context?.previousCredentials) {
        queryClient.setQueryData(['user-credentials'], context.previousCredentials)
      }
    },
    onSettled: async () => {
      await queryClient.refetchQueries({ queryKey: ['user-credentials'] })
      await queryClient.refetchQueries({ queryKey: ['available-tools'] })
    },
  })

  const stopServerMutation = useMutation({
    mutationFn: (serverId: string) => serverControlApi.stopServer(serverId),
    onMutate: async (serverId) => {
      await queryClient.cancelQueries({ queryKey: ['user-credentials'] })
      const previousCredentials = queryClient.getQueryData<UserCredential[]>(['user-credentials'])
      queryClient.setQueryData<UserCredential[]>(['user-credentials'], (old) =>
        old?.map((cred) =>
          cred.server_id === serverId ? { ...cred, server_status: 'stopped' } : cred
        )
      )
      return { previousCredentials }
    },
    onError: (_err, _vars, context) => {
      if (context?.previousCredentials) {
        queryClient.setQueryData(['user-credentials'], context.previousCredentials)
      }
    },
    onSettled: async () => {
      await queryClient.refetchQueries({ queryKey: ['user-credentials'] })
      await queryClient.refetchQueries({ queryKey: ['available-tools'] })
    },
  })

  const restartServerMutation = useMutation({
    mutationFn: (serverId: string) => serverControlApi.restartServer(serverId),
    onMutate: async (serverId) => {
      await queryClient.cancelQueries({ queryKey: ['user-credentials'] })
      const previousCredentials = queryClient.getQueryData<UserCredential[]>(['user-credentials'])
      queryClient.setQueryData<UserCredential[]>(['user-credentials'], (old) =>
        old?.map((cred) =>
          cred.server_id === serverId ? { ...cred, server_status: 'starting' } : cred
        )
      )
      return { previousCredentials }
    },
    onError: (_err, _vars, context) => {
      if (context?.previousCredentials) {
        queryClient.setQueryData(['user-credentials'], context.previousCredentials)
      }
    },
    onSettled: async () => {
      await queryClient.refetchQueries({ queryKey: ['user-credentials'] })
      await queryClient.refetchQueries({ queryKey: ['available-tools'] })
    },
  })

  const toggleServerMutation = useMutation({
    mutationFn: ({ serverId, enabled }: { serverId: string; enabled: boolean }) =>
      serverControlApi.toggleServer(serverId, enabled),
    onMutate: async ({ serverId, enabled }) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['user-credentials'] })

      // Snapshot previous value
      const previousCredentials = queryClient.getQueryData<UserCredential[]>(['user-credentials'])

      // Optimistically update the cache (is_visible_to_oauth_clients)
      queryClient.setQueryData<UserCredential[]>(['user-credentials'], (old) =>
        old?.map((cred) =>
          cred.server_id === serverId ? { ...cred, is_visible_to_oauth_clients: enabled } : cred
        )
      )

      return { previousCredentials }
    },
    onError: (_err, _vars, context) => {
      // Rollback on error
      if (context?.previousCredentials) {
        queryClient.setQueryData(['user-credentials'], context.previousCredentials)
      }
    },
    onSettled: async () => {
      // Always refetch after success or error to sync with server
      await queryClient.refetchQueries({ queryKey: ['user-credentials'] })
      await queryClient.refetchQueries({ queryKey: ['available-tools'] })
    },
  })

  const deleteGroupMutation = useMutation({
    mutationFn: (groupId: string) => toolGroupsApi.delete(groupId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tool-groups'] }),
  })

  const toggleGroupActiveMutation = useMutation({
    mutationFn: ({ groupId, isActive }: { groupId: string; isActive: boolean }) =>
      toolGroupsApi.update(groupId, { is_active: !isActive }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tool-groups'] }),
  })

  // Toggle group visibility mutation
  const toggleGroupVisibilityMutation = useMutation({
    mutationFn: ({ groupId, currentVisibility }: { groupId: string; currentVisibility: string }) =>
      toolGroupsApi.update(groupId, {
        visibility: currentVisibility === 'private' ? 'organization' : 'private'
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tool-groups'] }),
  })

  // Helpers
  // Combined server state for UI display
  type ServerState = 'active' | 'api_only' | 'standby' | 'disabled' | 'error'

  const getServerState = (credential: UserCredential): ServerState => {
    // Determine combined state from server_status and server_enabled
    const isRunning = credential.server_status === 'running'
    const isEnabled = credential.server_enabled ?? false
    const isError = credential.server_status === 'error'

    if (isError) return 'error'
    if (isRunning && isEnabled) return 'active'       // Running + Visible to Claude
    if (isRunning && !isEnabled) return 'api_only'    // Running but hidden from Claude (API/Toolboxes only)
    if (!isRunning && isEnabled) return 'standby'     // Stopped but will be visible when started
    return 'disabled'                                  // Stopped + Hidden
  }

  const getServerTools = (serverId: string): ToolInfo[] => {
    if (!Array.isArray(availableTools)) return []
    return availableTools.filter((t) => t.server_id === serverId)
  }

  const toggleServerExpanded = (serverId: string) => {
    const newExpanded = new Set(expandedServers)
    if (newExpanded.has(serverId)) newExpanded.delete(serverId)
    else newExpanded.add(serverId)
    setExpandedServers(newExpanded)
  }

  const toggleGroupExpanded = (groupId: string) => {
    const newExpanded = new Set(expandedGroups)
    if (newExpanded.has(groupId)) newExpanded.delete(groupId)
    else newExpanded.add(groupId)
    setExpandedGroups(newExpanded)
  }

  // State badge helper
  const getStateBadge = (state: ServerState) => {
    switch (state) {
      case 'active':
        return { variant: 'success' as const, icon: CheckCircleIcon, label: 'Active' }
      case 'api_only':
        return { variant: 'warning' as const, icon: KeyIcon, label: 'API Only' }
      case 'standby':
        return { variant: 'gray' as const, icon: StopIcon, label: 'Standby' }
      case 'disabled':
        return { variant: 'gray' as const, icon: XCircleIcon, label: 'Disabled' }
      case 'error':
        return { variant: 'error' as const, icon: XCircleIcon, label: 'Error' }
    }
  }

  // Stats
  const groups: ToolGroup[] = groupsData || []
  const activeServers = credentials.filter((c) => getServerState(c) === 'active').length
  const totalTools = availableTools.length
  const totalGroups = groups.length
  const teamServersCount = orgCredentials.length

  // Loading
  if (isLoadingCredentials) return <CenteredSpinner />

  // Error
  if (credentialsError) {
    return (
      <div className="container py-8">
        <Alert variant="error" title="Error loading data">
          {credentialsError instanceof Error ? credentialsError.message : 'Failed to load'}
        </Alert>
      </div>
    )
  }

  return (
    <div className="container py-8">
      {/* Header with Organization Context */}
      <div className="mb-8">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <h1 className="text-4xl font-bold text-gray-900 mb-2">{t('tools.title')}</h1>
            <p className="text-lg text-gray-600 font-serif">
              {t('tools.subtitle')}
            </p>
          </div>
        </div>
      </div>

      {/* View Toggle */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
        <div className="flex bg-gray-100 rounded-lg p-1 w-full sm:w-auto">
          <button
            onClick={() => setViewMode('servers')}
            className={cn(
              'flex-1 sm:flex-none px-4 py-2 rounded-md text-sm font-medium transition-colors text-center',
              viewMode === 'servers'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            )}
          >
            <BoltIcon className="w-4 h-4 inline mr-2" />
            {t('tools.viewToggle.servers')} ({credentials.length})
          </button>
          <button
            onClick={() => setViewMode('groups')}
            className={cn(
              'flex-1 sm:flex-none px-4 py-2 rounded-md text-sm font-medium transition-colors text-center',
              viewMode === 'groups'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            )}
          >
            <ArchiveBoxIcon className="w-4 h-4 inline mr-2" />
            {t('tools.viewToggle.toolboxes')} ({totalGroups})
          </button>
        </div>

        {viewMode === 'groups' && (
          <Button variant="primary" onClick={() => setShowCreateGroupModal(true)} className="w-full sm:w-auto justify-center">
            <PlusIcon className="w-5 h-5 mr-2" />
            {t('tools.groups.create')}
          </Button>
        )}
      </div>

      {/* Info Banner - Contextual explanation (dismissable) */}
      {showInfoBanner && (
        <div className="mb-6 p-4 rounded-lg border bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200">
          <div className="flex items-start gap-3">
            <InformationCircleIcon className="w-6 h-6 text-blue-600 mt-0.5 flex-shrink-0" />
            <div className="flex-1">
              {viewMode === 'servers' ? (
                <>
                  <p className="text-sm font-semibold text-blue-900 mb-1">
                    <BoltIcon className="w-4 h-4 inline mr-1" />
                    {t('tools.infoBanner.serversTitle')}
                  </p>
                  <p className="text-sm text-blue-700 mb-2">
                    {t('tools.infoBanner.serversDescription')}
                  </p>
                  <div className="flex items-center gap-4 text-xs">
                    <span className="flex items-center gap-1 text-green-700">
                      <EyeIcon className="w-3 h-3" /> {t('tools.infoBanner.visibleLabel')}
                    </span>
                    <span className="flex items-center gap-1 text-gray-500">
                      {t('tools.infoBanner.hiddenLabel')}
                    </span>
                  </div>
                </>
              ) : (
                <>
                  <p className="text-sm font-semibold text-blue-900 mb-1">
                    <ArchiveBoxIcon className="w-4 h-4 inline mr-1" />
                    {t('tools.infoBanner.toolboxesTitle')}
                  </p>
                  <p className="text-sm text-blue-700 mb-2">
                    {t('tools.infoBanner.toolboxesDescription')}
                  </p>
                  <div className="flex items-center gap-4 text-xs flex-wrap">
                    <span className="flex items-center gap-1 text-purple-700">
                      <KeyIcon className="w-3 h-3" /> {t('tools.infoBanner.forExternalIntegrations')}
                    </span>
                    <Link to="/app/api-keys" className="flex items-center gap-1 text-orange hover:underline">
                      <KeyIcon className="w-3 h-3" /> {t('tools.infoBanner.manageConnections')}
                    </Link>
                  </div>
                </>
              )}
            </div>
            <button
              onClick={() => {
                localStorage.setItem('services-info-banner-dismissed', 'true')
                setShowInfoBanner(false)
              }}
              className="p-1 hover:bg-blue-100 rounded transition-colors flex-shrink-0"
              title="Dismiss this message"
            >
              <XMarkIcon className="w-5 h-5 text-blue-400 hover:text-blue-600" />
            </button>
          </div>
        </div>
      )}

      {/* SERVERS VIEW */}
      {viewMode === 'servers' && (
        <>
          {/* Tabs for Team Organizations */}
          {isTeamOrg && (
            <div className="mb-4 sm:mb-6 border-b border-gray-200">
              <nav className="flex gap-4 sm:gap-8" aria-label="Server tabs">
                <button
                  onClick={() => setServerTab('personal')}
                  className={cn(
                    'flex items-center gap-2 py-3 px-1 border-b-2 font-medium text-sm transition-colors',
                    serverTab === 'personal'
                      ? 'border-orange text-orange'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  )}
                >
                  <UserIcon className="w-4 h-4" />
                  <span>{t('myServers.tabs.personal')}</span>
                  <Badge variant="gray" size="sm">{credentials.length}</Badge>
                </button>
                <button
                  onClick={() => setServerTab('team')}
                  className={cn(
                    'flex items-center gap-2 py-3 px-1 border-b-2 font-medium text-sm transition-colors',
                    serverTab === 'team'
                      ? 'border-orange text-orange'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  )}
                >
                  <BuildingOffice2Icon className="w-4 h-4" />
                  <span>{t('myServers.tabs.team')}</span>
                  <Badge variant="gray" size="sm">{teamServersCount}</Badge>
                </button>
              </nav>
            </div>
          )}

          {/* Personal Servers Tab Content */}
          {serverTab === 'personal' && (
            credentials.length === 0 ? (
              <Card>
                <CardContent className="py-12 text-center">
                  <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-100 flex items-center justify-center">
                    <BoltIcon className="w-8 h-8 text-gray-400" />
                  </div>
                  <h3 className="text-xl font-bold text-gray-900 mb-2">No services connected</h3>
                  <p className="text-gray-600 font-serif mb-6">
                    Get started by connecting your first MCP server from the marketplace.
                  </p>
                  <Button variant="primary" onClick={() => (window.location.href = '/app/marketplace')}>
                    Browse Marketplace
                  </Button>
                </CardContent>
              </Card>
            ) : (
            <div className="space-y-4">
              {credentials.map((credential) => {
                const serverState = getServerState(credential)
                const stateBadge = getStateBadge(serverState)
                const StateBadgeIcon = stateBadge.icon
                const isRunning = credential.server_status === 'running'
                const isVisible = credential.is_visible_to_oauth_clients ?? true
                const isExpanded = expandedServers.has(credential.server_id)
                const serverTools = getServerTools(credential.server_id)
                const toolCount = serverTools.length

                return (
                  <Card key={credential.id} hover={false} className="overflow-hidden">
                    <CardContent>
                      {/* Desktop Layout - Single Row */}
                      <div className="hidden sm:flex items-center justify-between">
                        <div className="flex items-center gap-4 flex-1">
                          <button
                            onClick={() => toggleServerExpanded(credential.server_id)}
                            className="p-1 hover:bg-gray-100 rounded transition-colors"
                          >
                            {isExpanded ? (
                              <ChevronDownIcon className="w-5 h-5 text-gray-500" />
                            ) : (
                              <ChevronRightIcon className="w-5 h-5 text-gray-500" />
                            )}
                          </button>

                          <div className="w-10 h-10 rounded-lg bg-gradient-orange flex items-center justify-center text-white font-bold text-lg flex-shrink-0">
                            {getDisplayName(credential.name).charAt(0)}
                          </div>

                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <h3 className="text-lg font-bold text-gray-900 truncate">
                                {getDisplayName(credential.name)}
                              </h3>
                              <Badge variant={stateBadge.variant} size="sm">
                                <StateBadgeIcon className="w-3 h-3 mr-1 inline" />
                                {stateBadge.label}
                              </Badge>
                              {toolCount > 0 && (
                                <Badge variant="info" size="sm">
                                  <WrenchScrewdriverIcon className="w-3 h-3 mr-1 inline" />
                                  {toolCount} tool{toolCount > 1 ? 's' : ''}
                                </Badge>
                              )}
                            </div>
                            {credential.description && (
                              <p className="text-sm text-gray-500 truncate">{credential.description}</p>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-3 ml-4">
                          {/* Visibility Toggle (OAuth visibility) */}
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-gray-500">
                              {isVisible ? 'Visible' : 'Hidden'}
                            </span>
                            <button
                              onClick={() => toggleServerMutation.mutate({ serverId: credential.server_id, enabled: !isVisible })}
                              disabled={toggleServerMutation.isPending}
                              className={cn(
                                'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
                                isVisible ? 'bg-orange' : 'bg-gray-300',
                                toggleServerMutation.isPending && 'opacity-50 cursor-wait'
                              )}
                            >
                              <span className={cn(
                                'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
                                isVisible ? 'translate-x-6' : 'translate-x-1'
                              )} />
                            </button>
                          </div>

                          <div className="w-px h-6 bg-gray-200" />

                          {/* Server Control */}
                          {isRunning ? (
                            <>
                              <Button
                                variant="ghost" size="sm"
                                onClick={() => { if (confirm('Stop server?')) stopServerMutation.mutate(credential.server_id) }}
                                isLoading={stopServerMutation.isPending}
                                className="text-orange hover:bg-orange-50"
                              >
                                <StopIcon className="w-4 h-4" />
                              </Button>
                              <Button
                                variant="ghost" size="sm"
                                onClick={() => restartServerMutation.mutate(credential.server_id)}
                                isLoading={restartServerMutation.isPending}
                              >
                                <ArrowPathIcon className="w-4 h-4" />
                              </Button>
                            </>
                          ) : (
                            <Button
                              variant="ghost" size="sm"
                              onClick={() => startServerMutation.mutate(credential.server_id)}
                              isLoading={startServerMutation.isPending}
                              className="text-green-600 hover:bg-green-50"
                            >
                              <PlayIcon className="w-4 h-4" />
                            </Button>
                          )}

                          <div className="w-px h-6 bg-gray-200" />

                          <Button
                            variant="ghost" size="sm"
                            onClick={() => {
                              if (confirm('Delete this server and its credentials?')) {
                                deleteCredentialMutation.mutate(credential.id)
                              }
                            }}
                            className="text-error hover:bg-red-50"
                          >
                            <TrashIcon className="w-4 h-4" />
                          </Button>
                        </div>
                      </div>

                      {/* Mobile Layout - Stacked */}
                      <div className="sm:hidden">
                        {/* Row 1: Server Info + Toggle */}
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => toggleServerExpanded(credential.server_id)}
                            className="p-1 hover:bg-gray-100 rounded transition-colors flex-shrink-0"
                          >
                            {isExpanded ? (
                              <ChevronDownIcon className="w-4 h-4 text-gray-500" />
                            ) : (
                              <ChevronRightIcon className="w-4 h-4 text-gray-500" />
                            )}
                          </button>

                          <div className="w-8 h-8 rounded-lg bg-gradient-orange flex items-center justify-center text-white font-bold text-sm flex-shrink-0">
                            {getDisplayName(credential.name).charAt(0)}
                          </div>

                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5">
                              <h3 className="text-sm font-bold text-gray-900 truncate">
                                {getDisplayName(credential.name)}
                              </h3>
                              {/* Colored dot based on state */}
                              <span
                                className={cn(
                                  'w-2 h-2 rounded-full flex-shrink-0',
                                  serverState === 'active' && 'bg-green-500',
                                  serverState === 'api_only' && 'bg-yellow-500',
                                  serverState === 'standby' && 'bg-gray-400',
                                  serverState === 'disabled' && 'bg-gray-300',
                                  serverState === 'error' && 'bg-red-500'
                                )}
                                title={stateBadge.label}
                              />
                            </div>
                            {toolCount > 0 && (
                              <p className="text-xs text-gray-500">{toolCount} tools</p>
                            )}
                          </div>

                          {/* Visibility Toggle (mobile) */}
                          <button
                            onClick={() => toggleServerMutation.mutate({ serverId: credential.server_id, enabled: !isVisible })}
                            disabled={toggleServerMutation.isPending}
                            className={cn(
                              'relative inline-flex h-5 w-9 items-center rounded-full transition-colors flex-shrink-0',
                              isVisible ? 'bg-orange' : 'bg-gray-300',
                              toggleServerMutation.isPending && 'opacity-50 cursor-wait'
                            )}
                          >
                            <span className={cn(
                              'inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform',
                              isVisible ? 'translate-x-4' : 'translate-x-1'
                            )} />
                          </button>
                        </div>

                        {/* Row 2: Action Buttons */}
                        <div className="flex items-center justify-between mt-2 pt-2 border-t border-gray-100">
                          {/* Server Control */}
                          <div className="flex items-center gap-1">
                            {isRunning ? (
                              <>
                                <Button
                                  variant="ghost" size="sm"
                                  onClick={() => { if (confirm('Stop server?')) stopServerMutation.mutate(credential.server_id) }}
                                  isLoading={stopServerMutation.isPending}
                                  className="text-orange hover:bg-orange-50 px-2 py-1 text-xs"
                                >
                                  <StopIcon className="w-3.5 h-3.5 mr-1" />
                                  Stop
                                </Button>
                                <Button
                                  variant="ghost" size="sm"
                                  onClick={() => restartServerMutation.mutate(credential.server_id)}
                                  isLoading={restartServerMutation.isPending}
                                  className="px-2 py-1 text-xs"
                                >
                                  <ArrowPathIcon className="w-3.5 h-3.5 mr-1" />
                                  Restart
                                </Button>
                              </>
                            ) : (
                              <Button
                                variant="ghost" size="sm"
                                onClick={() => startServerMutation.mutate(credential.server_id)}
                                isLoading={startServerMutation.isPending}
                                className="text-green-600 hover:bg-green-50 px-2 py-1 text-xs"
                              >
                                <PlayIcon className="w-3.5 h-3.5 mr-1" />
                                Start
                              </Button>
                            )}
                          </div>

                          {/* Delete */}
                          <Button
                            variant="ghost" size="sm"
                            onClick={() => {
                              if (confirm('Delete this server and its credentials?')) {
                                deleteCredentialMutation.mutate(credential.id)
                              }
                            }}
                            className="text-error hover:bg-red-50 px-2 py-1"
                          >
                            <TrashIcon className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      </div>

                      {/* Expanded Tools */}
                      {isExpanded && (
                        <div className="mt-4 pt-4 border-t border-gray-100">
                          {serverState === 'error' && (
                            <Alert variant="error" className="mb-4">Server encountered an error</Alert>
                          )}

                          {serverTools.length > 0 ? (
                            <div>
                              <div className="flex items-center gap-2 mb-3">
                                <WrenchScrewdriverIcon className="w-4 h-4 text-gray-500" />
                                <span className="text-sm font-medium text-gray-700">
                                  Available Tools ({serverTools.length})
                                </span>
                                {isVisible && (
                                  <Badge variant="success" size="sm">
                                    <EyeIcon className="w-3 h-3 mr-1 inline" />Visible to Claude
                                  </Badge>
                                )}
                              </div>
                              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                                {serverTools.map((tool) => (
                                  <div key={tool.id} className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                    <div className="flex items-start gap-2">
                                      <div className="w-6 h-6 rounded bg-purple-100 flex items-center justify-center flex-shrink-0">
                                        <WrenchScrewdriverIcon className="w-3 h-3 text-purple-600" />
                                      </div>
                                      <div className="min-w-0 flex-1">
                                        <p className="text-sm font-medium text-gray-900 truncate">
                                          {tool.display_name || tool.tool_name}
                                        </p>
                                        {tool.description && (
                                          <p className="text-xs text-gray-500 line-clamp-2">{tool.description}</p>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ) : isRunning ? (
                            <div className="text-center py-6 text-gray-500">
                              <WrenchScrewdriverIcon className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                              <p className="text-sm">Discovering tools...</p>
                            </div>
                          ) : (
                            <div className="text-center py-6 text-gray-500">
                              <WrenchScrewdriverIcon className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                              <p className="text-sm">Start server to discover tools</p>
                            </div>
                          )}

                          <div className="mt-4 pt-4 border-t border-gray-100 flex items-center gap-4 text-xs text-gray-500">
                            <span>Created: {new Date(credential.created_at).toLocaleDateString()}</span>
                            {credential.last_used_at && (
                              <span>Last used: {new Date(credential.last_used_at).toLocaleDateString()}</span>
                            )}
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )
              })}
            </div>
            )
          )}

          {/* Team Servers Tab Content */}
          {serverTab === 'team' && isTeamOrg && (
            orgCredentials.length === 0 ? (
              <Card>
                <CardContent className="py-12 text-center">
                  <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-purple-100 flex items-center justify-center">
                    <BuildingOffice2Icon className="w-8 h-8 text-purple-600" />
                  </div>
                  <h3 className="text-xl font-bold text-gray-900 mb-2">No team servers yet</h3>
                  <p className="text-gray-600 font-serif mb-4">
                    Team servers are shared with all organization members. Only admins can add them.
                  </p>
                  <p className="text-sm text-gray-500 mb-6">
                    Go to Team Settings to manage shared credentials.
                  </p>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-4">
                {/* Team Info Banner */}
                <div className="p-3 sm:p-4 bg-purple-50 border border-purple-200 rounded-lg">
                  <div className="flex items-start gap-2 sm:gap-3">
                    <BuildingOffice2Icon className="w-4 h-4 sm:w-5 sm:h-5 text-purple-600 mt-0.5 flex-shrink-0" />
                    <div>
                      <p className="text-xs sm:text-sm font-medium text-purple-900">Team Services</p>
                      <p className="text-xs sm:text-sm text-purple-700">
                        These servers are shared with all organization members. Credentials are managed by admins.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Team Servers List */}
                {orgCredentials.map((orgCred: OrganizationCredential) => {
                  const isExpanded = expandedServers.has(orgCred.server_id)
                  const serverTools = getServerTools(orgCred.server_id)
                  const toolCount = serverTools.length

                  return (
                    <Card key={orgCred.id} hover={false} className="overflow-hidden border-purple-100">
                      <CardContent>
                        <div className="flex items-center justify-between gap-2">
                          {/* Left: Expand + Server Info */}
                          <div className="flex items-center gap-4 flex-1 min-w-0">
                            {/* Expand Button */}
                            <button
                              onClick={() => toggleServerExpanded(orgCred.server_id)}
                              className="p-1 hover:bg-gray-100 rounded transition-colors flex-shrink-0"
                            >
                              {isExpanded ? (
                                <ChevronDownIcon className="w-5 h-5 text-gray-500" />
                              ) : (
                                <ChevronRightIcon className="w-5 h-5 text-gray-500" />
                              )}
                            </button>

                            {/* Server Icon with Team Badge */}
                            <div className="relative">
                              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-purple-500 to-purple-600 flex items-center justify-center text-white font-bold text-lg flex-shrink-0">
                                {getDisplayName(orgCred.name).charAt(0)}
                              </div>
                              <div className="absolute -bottom-1 -right-1 w-4 h-4 bg-purple-100 rounded-full flex items-center justify-center">
                                <BuildingOffice2Icon className="w-2.5 h-2.5 text-purple-600" />
                              </div>
                            </div>

                            {/* Server Details */}
                            <div className="flex-1 min-w-0 overflow-hidden">
                              <div className="flex items-center gap-2 flex-wrap">
                                <h3 className="text-lg font-bold text-gray-900 truncate">
                                  {getDisplayName(orgCred.name)}
                                </h3>
                                <Badge variant="info" size="sm" className="text-xs bg-purple-100 text-purple-700">
                                  <BuildingOffice2Icon className="w-3 h-3 mr-1 inline" />
                                  Team
                                </Badge>
                                {toolCount > 0 && (
                                  <Badge variant="info" size="sm" className="text-xs">
                                    <WrenchScrewdriverIcon className="w-3 h-3 mr-1 inline" />
                                    {toolCount} tool{toolCount > 1 ? 's' : ''}
                                  </Badge>
                                )}
                              </div>
                              {orgCred.visible_to_users && (
                                <p className="text-xs text-purple-600 mt-1">
                                  <EyeIcon className="w-3 h-3 inline mr-1" />
                                  Visible to all members
                                </p>
                              )}
                            </div>
                          </div>

                          {/* Right: Server Controls */}
                          <div className="flex items-center gap-3 ml-4 flex-shrink-0">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => restartServerMutation.mutate(orgCred.server_id)}
                              isLoading={restartServerMutation.isPending}
                              title="Restart server"
                              className="p-2"
                            >
                              <ArrowPathIcon className="w-4 h-4" />
                            </Button>
                          </div>
                        </div>

                        {/* Expanded Tools Section */}
                        {isExpanded && (
                          <div className="mt-4 pt-4 border-t border-gray-100">
                            {serverTools.length > 0 ? (
                              <div>
                                <div className="flex items-center gap-2 mb-3">
                                  <WrenchScrewdriverIcon className="w-4 h-4 text-gray-500" />
                                  <span className="text-sm font-medium text-gray-700">
                                    Available Tools ({serverTools.length})
                                  </span>
                                </div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                                  {serverTools.map((tool) => (
                                    <div
                                      key={tool.id}
                                      className="p-3 bg-gray-50 rounded-lg border border-gray-100"
                                    >
                                      <div className="flex items-start gap-2">
                                        <div className="w-6 h-6 rounded bg-purple-100 flex items-center justify-center flex-shrink-0">
                                          <WrenchScrewdriverIcon className="w-3 h-3 text-purple-600" />
                                        </div>
                                        <div className="min-w-0 flex-1">
                                          <p className="text-sm font-medium text-gray-900 truncate">
                                            {tool.display_name || tool.tool_name}
                                          </p>
                                          {tool.description && (
                                            <p className="text-xs text-gray-500 line-clamp-2">
                                              {tool.description}
                                            </p>
                                          )}
                                        </div>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            ) : (
                              <div className="text-center py-6 text-gray-500">
                                <WrenchScrewdriverIcon className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                                <p className="text-sm">No tools discovered yet</p>
                                <p className="text-xs">Tools will appear after server initialization</p>
                              </div>
                            )}
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            )
          )}
        </>
      )}

      {/* TOOL GROUPS VIEW */}
      {viewMode === 'groups' && (
        <>
          {groups.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center">
                <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-100 flex items-center justify-center">
                  <ArchiveBoxIcon className="w-8 h-8 text-gray-400" />
                </div>
                <h3 className="text-xl font-bold text-gray-900 mb-2">{t('tools.groups.empty')}</h3>
                <p className="text-gray-600 font-serif mb-6">
                  {t('tools.groups.emptyDescription')}
                </p>
                <Button variant="primary" onClick={() => setShowCreateGroupModal(true)} className="w-full sm:w-auto justify-center">
                  <PlusIcon className="w-5 h-5 mr-2" />
                  {t('tools.groups.createFirst')}
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {groups.map((group) => {
                const colorConfig = GROUP_COLORS.find((c) => c.id === group.color) || GROUP_COLORS[0]
                const isExpanded = expandedGroups.has(group.id)
                const toolCount = group.items?.length || 0

                return (
                  <Card key={group.id} hover={false} className="overflow-hidden">
                    <CardContent className="py-4 px-6">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4 flex-1">
                          <button
                            onClick={() => toggleGroupExpanded(group.id)}
                            className="p-1 hover:bg-gray-100 rounded transition-colors"
                          >
                            {isExpanded ? (
                              <ChevronDownIcon className="w-5 h-5 text-gray-500" />
                            ) : (
                              <ChevronRightIcon className="w-5 h-5 text-gray-500" />
                            )}
                          </button>

                          <div className={cn('w-10 h-10 rounded-lg flex items-center justify-center', colorConfig.bg)}>
                            <ArchiveBoxIcon className={cn('w-5 h-5', colorConfig.text)} />
                          </div>

                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <h3 className="text-lg font-bold text-gray-900">{group.name}</h3>
                              <Badge variant={group.is_active ? 'success' : 'gray'} size="sm">
                                {group.is_active ? 'Active' : 'Inactive'}
                              </Badge>
                              <Badge variant="info" size="sm">
                                <WrenchScrewdriverIcon className="w-3 h-3 mr-1 inline" />
                                {toolCount} tool{toolCount !== 1 ? 's' : ''}
                              </Badge>
                              {/* Show visibility toggle for Team/Enterprise users */}
                              {canShareWithOrg && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    toggleGroupVisibilityMutation.mutate({
                                      groupId: group.id,
                                      currentVisibility: group.visibility
                                    })
                                  }}
                                  disabled={toggleGroupVisibilityMutation.isPending}
                                  className={cn(
                                    'flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors',
                                    group.visibility === 'organization'
                                      ? 'bg-purple-100 text-purple-700 hover:bg-purple-200'
                                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200',
                                    toggleGroupVisibilityMutation.isPending && 'opacity-50 cursor-wait'
                                  )}
                                  title={group.visibility === 'organization' ? 'Click to make private' : 'Click to share with team'}
                                >
                                  {group.visibility === 'organization' ? (
                                    <>
                                      <UsersIcon className="w-3 h-3" />
                                      <span className="hidden sm:inline">Shared</span>
                                    </>
                                  ) : (
                                    <>
                                      <EyeIcon className="w-3 h-3" />
                                      <span className="hidden sm:inline">Private</span>
                                    </>
                                  )}
                                </button>
                              )}
                            </div>
                            {group.description && (
                              <p className="text-sm text-gray-500 truncate">{group.description}</p>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-3 ml-4">
                          <button
                            onClick={() => toggleGroupActiveMutation.mutate({ groupId: group.id, isActive: group.is_active })}
                            className={cn(
                              'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
                              group.is_active ? 'bg-orange' : 'bg-gray-300'
                            )}
                          >
                            <span className={cn(
                              'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
                              group.is_active ? 'translate-x-6' : 'translate-x-1'
                            )} />
                          </button>

                          <div className="w-px h-6 bg-gray-200" />

                          <Button
                            variant="ghost" size="sm"
                            onClick={() => {
                              if (confirm(`Delete "${group.name}"? API keys using this group will lose their restrictions.`)) {
                                deleteGroupMutation.mutate(group.id)
                              }
                            }}
                            className="text-error hover:bg-red-50"
                          >
                            <TrashIcon className="w-4 h-4" />
                          </Button>
                        </div>
                      </div>

                      {isExpanded && (
                        <div className="mt-4 pt-4 border-t border-gray-100">
                          {toolCount > 0 ? (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                              {group.items?.map((item) => (
                                <div key={item.id} className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                  <div className="flex items-start gap-2">
                                    <div className="w-6 h-6 rounded bg-purple-100 flex items-center justify-center flex-shrink-0">
                                      <WrenchScrewdriverIcon className="w-3 h-3 text-purple-600" />
                                    </div>
                                    <div className="min-w-0 flex-1">
                                      <p className="text-sm font-medium text-gray-900 truncate">
                                        {item.tool_name || 'Unknown Tool'}
                                      </p>
                                      {item.server_name && (
                                        <p className="text-xs text-gray-500">{item.server_name}</p>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="text-center py-6 text-gray-500">
                              <WrenchScrewdriverIcon className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                              <p className="text-sm">No tools in this group</p>
                            </div>
                          )}

                          <div className="mt-4 pt-4 border-t border-gray-100 flex items-center gap-4 text-xs text-gray-500">
                            <span>Created: {new Date(group.created_at).toLocaleDateString()}</span>
                            {group.usage_count > 0 && (
                              <span>Used {group.usage_count} time{group.usage_count !== 1 ? 's' : ''}</span>
                            )}
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )
              })}
            </div>
          )}
        </>
      )}

      {/* Create Group Modal */}
      <CreateGroupModal
        isOpen={showCreateGroupModal}
        onClose={() => setShowCreateGroupModal(false)}
        availableTools={availableTools}
        canShareWithOrg={canShareWithOrg}
      />
    </div>
  )
}
