/**
 * LocalRegistryManager - Manage local MCP servers via JSON config
 *
 * Displays each server with its MCP JSON config, allows inline editing,
 * and provides a card to add new servers by pasting config.
 */

import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
  TrashIcon,
  EyeIcon,
  EyeSlashIcon,
  CheckIcon,
  XMarkIcon,
  PlusIcon,
  ExclamationTriangleIcon,
  CommandLineIcon,
  GlobeAltIcon,
  CubeIcon,
  KeyIcon,
  SparklesIcon,
  ArrowPathIcon,
  TagIcon,
  PencilIcon,
  ClipboardDocumentIcon,
  ClipboardDocumentCheckIcon,
} from '@heroicons/react/24/outline'
import { Card, Badge, Button } from '@/components/ui'
import type { LocalServerResponse, CurationPreviewResponse } from '@/services/marketplace'
import { adminRegistryApi } from '@/services/marketplace'

// ============================================================================
// Types
// ============================================================================

interface MCPServerConfig {
  command?: string
  args?: string[]
  env?: Record<string, string>
  url?: string  // For remote SSE servers
  _metadata?: {
    name?: string
    description?: string
    category?: string
    iconUrl?: string
    credentials?: Array<{name: string; description?: string; required?: boolean}>
    visible_in_marketplace?: boolean
    saas_compatible?: boolean
  }
}

interface ParsedConfig {
  serverId: string
  config: MCPServerConfig
  detectedType: 'npm' | 'pip' | 'docker' | 'local' | 'remote' | 'unknown'
  detectedPackage?: string
  detectedCredentials: string[]
  isValid: boolean
  error?: string
}

interface ServerMetadata {
  name?: string
  description?: string
  category?: string
  icon_url?: string
}

interface LocalRegistryManagerProps {
  servers: LocalServerResponse[]
  onAddServer: (serverId: string, config: MCPServerConfig, metadata?: ServerMetadata) => Promise<void>
  onUpdateServer: (serverId: string, config: MCPServerConfig) => Promise<void>
  onRenameServer?: (oldServerId: string, newServerId: string, config: MCPServerConfig) => Promise<void>
  onUpdateMetadata: (serverId: string, metadata: ServerMetadata) => Promise<void>
  onDeleteServer: (serverId: string) => Promise<void>
  onToggleVisibility: (serverId: string, visible: boolean) => Promise<void>
}

// ============================================================================
// MCP Config Parser
// ============================================================================

function parseMCPConfig(jsonString: string): ParsedConfig | { error: string } {
  try {
    const parsed = JSON.parse(jsonString)

    // Handle different input formats
    let serverId: string
    let config: MCPServerConfig

    // Format 1: { "mcpServers": { "server-id": { ... } } }
    if (parsed.mcpServers && typeof parsed.mcpServers === 'object') {
      const keys = Object.keys(parsed.mcpServers)
      if (keys.length === 0) {
        return { error: 'No servers found in mcpServers object' }
      }
      serverId = keys[0]
      config = parsed.mcpServers[serverId]
    }
    // Format 2: { "server-id": { "command": "...", ... } }
    else if (!parsed.command && !parsed.url) {
      const keys = Object.keys(parsed)
      if (keys.length === 0) {
        return { error: 'Empty config object' }
      }
      serverId = keys[0]
      config = parsed[serverId]
    }
    // Format 3: Direct config { "command": "...", ... } - need server ID separately
    else {
      return { error: 'Please wrap your config in { "server-id": { ... } }' }
    }

    // Validate config structure
    if (!config || typeof config !== 'object') {
      return { error: 'Invalid server config structure' }
    }

    // Detect server type
    let detectedType: ParsedConfig['detectedType'] = 'unknown'
    let detectedPackage: string | undefined

    if (config.url) {
      detectedType = 'remote'
    } else if (config.command) {
      const cmd = config.command.toLowerCase()
      const args = config.args || []

      if (cmd === 'npx' || cmd === 'npm') {
        detectedType = 'npm'
        // Extract package from args
        const pkgArg = args.find(a => a.startsWith('@') || a.startsWith('mcp-server-') || a.includes('/'))
        if (pkgArg) {
          detectedPackage = pkgArg.replace('-y', '').trim()
        }
      } else if (cmd === 'uvx' || cmd === 'pip' || cmd === 'python' || cmd === 'python3') {
        detectedType = 'pip'
        const pkgArg = args.find(a => a.startsWith('mcp-') || a.includes('mcp'))
        if (pkgArg) detectedPackage = pkgArg
      } else if (cmd === 'docker') {
        detectedType = 'docker'
        const imgArg = args.find((a, i) => args[i-1] === 'run' || !a.startsWith('-'))
        if (imgArg) detectedPackage = imgArg
      } else {
        detectedType = 'local'
      }
    }

    // Detect credentials from env variables with ${VAR} pattern
    const detectedCredentials: string[] = []
    if (config.env) {
      Object.entries(config.env).forEach(([key, value]) => {
        if (typeof value === 'string') {
          // Match ${VAR_NAME} pattern
          const matches = value.match(/\$\{([^}]+)\}/g)
          if (matches) {
            matches.forEach(m => {
              const varName = m.replace('${', '').replace('}', '')
              if (!detectedCredentials.includes(varName)) {
                detectedCredentials.push(varName)
              }
            })
          }
          // Also check if the value itself is a placeholder
          if (value.startsWith('${') || value === '') {
            if (!detectedCredentials.includes(key)) {
              detectedCredentials.push(key)
            }
          }
        }
      })
    }

    return {
      serverId,
      config,
      detectedType,
      detectedPackage,
      detectedCredentials,
      isValid: true,
    }
  } catch (e) {
    return { error: `Invalid JSON: ${(e as Error).message}` }
  }
}

function serverToMCPConfig(server: LocalServerResponse): MCPServerConfig {
  // Only include MCP config fields (command, args, env, url)
  // Metadata is edited via the separate form (pencil icon)
  const config: MCPServerConfig = {}

  if (server.install?.type === 'remote' && server.install?.url) {
    config.url = server.install.url
  } else {
    if (server.command) config.command = server.command
    if (server.args && server.args.length > 0) config.args = server.args
  }

  if (server.env && Object.keys(server.env).length > 0) {
    config.env = server.env
  }

  return config
}

function formatJSON(obj: any): string {
  return JSON.stringify(obj, null, 2)
}

// ============================================================================
// ServerConfigCard Component
// ============================================================================

interface ServerConfigCardProps {
  server: LocalServerResponse
  onUpdate: (config: MCPServerConfig) => Promise<void>
  onRename?: (newServerId: string, config: MCPServerConfig) => Promise<void>
  onUpdateMetadata: (metadata: ServerMetadata) => Promise<void>
  onDelete: () => Promise<void>
  onToggleVisibility: (visible: boolean) => Promise<void>
}

function ServerConfigCard({ server, onUpdate, onRename, onUpdateMetadata, onDelete, onToggleVisibility }: ServerConfigCardProps) {
  const { t } = useTranslation('marketplace')
  const [isEditingConfig, setIsEditingConfig] = useState(false)
  const [isEditingMetadata, setIsEditingMetadata] = useState(false)
  const [configText, setConfigText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [copied, setCopied] = useState(false)

  // Metadata edit state
  const [editableMeta, setEditableMeta] = useState({
    name: server.name || '',
    description: server.description || '',
    category: server.category || 'custom',
    icon_url: server.icon_url || '',
  })

  const mcpConfig = serverToMCPConfig(server)
  const displayConfig = { [server.id]: mcpConfig }

  useEffect(() => {
    setConfigText(formatJSON(displayConfig))
  }, [server])

  useEffect(() => {
    setEditableMeta({
      name: server.name || '',
      description: server.description || '',
      category: server.category || 'custom',
      icon_url: server.icon_url || '',
    })
  }, [server])

  const handleCopyConfig = async () => {
    try {
      await navigator.clipboard.writeText(configText)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (e) {
      console.error('Failed to copy:', e)
    }
  }

  const handleSaveConfig = async () => {
    const result = parseMCPConfig(configText)
    if ('error' in result && !('isValid' in result)) {
      setError(result.error)
      return
    }

    setError(null)
    setIsSaving(true)
    try {
      // Detect if the server ID was changed in the JSON
      const newServerId = result.serverId
      const isIdChanged = newServerId !== server.id

      if (isIdChanged && onRename) {
        // Server ID changed - use rename operation
        await onRename(newServerId, result.config)
      } else if (isIdChanged && !onRename) {
        // ID change requested but rename not supported
        setError(`Cannot change server ID from "${server.id}" to "${newServerId}". Delete and recreate the server instead.`)
        return
      } else {
        // Normal update - same ID
        await onUpdate(result.config)
      }
      setIsEditingConfig(false)
    } catch (e: any) {
      setError(e.message || 'Failed to save')
    } finally {
      setIsSaving(false)
    }
  }

  const handleCancelConfig = () => {
    setConfigText(formatJSON(displayConfig))
    setError(null)
    setIsEditingConfig(false)
  }

  const handleSaveMetadata = async () => {
    setIsSaving(true)
    try {
      await onUpdateMetadata(editableMeta)
      setIsEditingMetadata(false)
    } catch (e: any) {
      setError(e.message || 'Failed to save metadata')
    } finally {
      setIsSaving(false)
    }
  }

  const handleCancelMetadata = () => {
    setEditableMeta({
      name: server.name || '',
      description: server.description || '',
      category: server.category || 'custom',
      icon_url: server.icon_url || '',
    })
    setError(null)
    setIsEditingMetadata(false)
  }

  // Detect info from current config
  const installType = server.install?.type || 'local'
  const isRemote = installType === 'remote'
  const credentialsCount = server.credentials?.length || 0

  return (
    <Card className="overflow-hidden">
      {/* Main content - 50/50 split layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-gray-100">
        {/* Left side - Server presentation */}
        <div className="p-4">
          {/* Header with icon and actions */}
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-3">
              {/* Server Icon */}
              {server.icon_url ? (
                <img
                  src={server.icon_url}
                  alt={server.name}
                  className="w-12 h-12 rounded-lg border border-gray-200 object-contain bg-white"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none'
                    const fallback = (e.target as HTMLImageElement).nextElementSibling as HTMLElement
                    if (fallback) fallback.style.display = 'flex'
                  }}
                />
              ) : null}
              <div
                className={`w-12 h-12 rounded-lg bg-orange-100 items-center justify-center ${server.icon_url ? 'hidden' : 'flex'}`}
              >
                {isRemote ? (
                  <GlobeAltIcon className="w-6 h-6 text-orange-600" />
                ) : (
                  <CommandLineIcon className="w-6 h-6 text-orange-600" />
                )}
              </div>
              <div>
                <h3 className="font-semibold text-gray-900 text-lg">{server.name || server.id}</h3>
                <p className="text-xs text-gray-500 font-mono">{server.id}</p>
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-1">
              <button
                onClick={() => setIsEditingMetadata(!isEditingMetadata)}
                className={`p-1.5 rounded-lg transition-colors ${
                  isEditingMetadata
                    ? 'text-orange-600 bg-orange-100'
                    : 'text-gray-500 hover:bg-gray-100'
                }`}
                title={t('localRegistry.editMetadata')}
              >
                <PencilIcon className="w-4 h-4" />
              </button>
              <button
                onClick={() => onToggleVisibility(!server.visible_in_marketplace)}
                className={`p-1.5 rounded-lg transition-colors ${
                  server.visible_in_marketplace
                    ? 'text-green-600 hover:bg-green-100'
                    : 'text-orange-600 hover:bg-orange-100'
                }`}
                title={server.visible_in_marketplace ? t('server.hideFromMarketplace') : t('server.showInMarketplace')}
              >
                {server.visible_in_marketplace ? (
                  <EyeIcon className="w-4 h-4" />
                ) : (
                  <EyeSlashIcon className="w-4 h-4" />
                )}
              </button>
              <button
                onClick={onDelete}
                className="p-1.5 rounded-lg text-red-600 hover:bg-red-100 transition-colors"
                title={t('localRegistry.deleteServer')}
              >
                <TrashIcon className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Description */}
          <p className="text-sm text-gray-600 mb-3 line-clamp-3">
            {server.description || t('localRegistry.noDescription')}
          </p>

          {/* Info badges */}
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="gray" size="sm" className="flex items-center gap-1">
              <CubeIcon className="w-3 h-3" />
              {installType}
            </Badge>

            {server.category && (
              <Badge variant="gray" size="sm">
                {server.category}
              </Badge>
            )}

            {credentialsCount > 0 && (
              <Badge variant="warning" size="sm" className="flex items-center gap-1">
                <KeyIcon className="w-3 h-3" />
                {credentialsCount} credential{credentialsCount > 1 ? 's' : ''}
              </Badge>
            )}

            {!server.visible_in_marketplace && (
              <Badge variant="warning" size="sm">
                {t('server.hidden')}
              </Badge>
            )}
          </div>

          {/* Metadata Editor (collapsible) */}
          {isEditingMetadata && (
            <div className="mt-4 pt-4 border-t border-gray-100">
              <div className="space-y-3">
                {/* Name and Category */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">{t('localRegistry.name')}</label>
                    <input
                      type="text"
                      value={editableMeta.name}
                      onChange={(e) => setEditableMeta({ ...editableMeta, name: e.target.value })}
                      className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-200"
                      placeholder={t('localRegistry.namePlaceholder')}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">{t('localRegistry.category')}</label>
                    <select
                      value={editableMeta.category}
                      onChange={(e) => setEditableMeta({ ...editableMeta, category: e.target.value })}
                      className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-200"
                    >
                      <option value="custom">{t('localRegistry.categories.custom')}</option>
                      <option value="productivity">{t('localRegistry.categories.productivity')}</option>
                      <option value="development">{t('localRegistry.categories.development')}</option>
                      <option value="data">{t('localRegistry.categories.data')}</option>
                      <option value="communication">{t('localRegistry.categories.communication')}</option>
                      <option value="ai">{t('localRegistry.categories.ai')}</option>
                      <option value="file-system">{t('localRegistry.categories.fileSystem')}</option>
                      <option value="database">{t('localRegistry.categories.database')}</option>
                      <option value="cloud">{t('localRegistry.categories.cloud')}</option>
                      <option value="search">{t('localRegistry.categories.search')}</option>
                    </select>
                  </div>
                </div>

                {/* Description */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">{t('localRegistry.description')}</label>
                  <textarea
                    value={editableMeta.description}
                    onChange={(e) => setEditableMeta({ ...editableMeta, description: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-200 resize-none"
                    rows={2}
                    placeholder={t('localRegistry.descriptionPlaceholder')}
                  />
                </div>

                {/* Icon URL */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">{t('localRegistry.iconUrl')}</label>
                  <div className="flex items-center gap-2">
                    {editableMeta.icon_url ? (
                      <img
                        src={editableMeta.icon_url}
                        alt="Icon preview"
                        className="w-8 h-8 rounded border border-gray-200 object-contain bg-white"
                        onError={(e) => {
                          (e.target as HTMLImageElement).src = ''
                          (e.target as HTMLImageElement).className = 'w-8 h-8 rounded border border-gray-200 bg-gray-100'
                        }}
                      />
                    ) : (
                      <div className="w-8 h-8 rounded border border-gray-200 bg-gray-100 flex items-center justify-center">
                        <CubeIcon className="w-4 h-4 text-gray-400" />
                      </div>
                    )}
                    <input
                      type="text"
                      value={editableMeta.icon_url}
                      onChange={(e) => setEditableMeta({ ...editableMeta, icon_url: e.target.value })}
                      className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-200"
                      placeholder={t('localRegistry.iconUrlPlaceholder')}
                    />
                  </div>
                </div>

                {/* Save/Cancel metadata */}
                <div className="flex justify-end gap-2 pt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCancelMetadata}
                    disabled={isSaving}
                  >
                    {t('localRegistry.cancel')}
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleSaveMetadata}
                    disabled={isSaving}
                  >
                    {isSaving ? t('localRegistry.saving') : t('localRegistry.save')}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right side - JSON Config Editor */}
        <div className="p-4 bg-gray-50/50">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">{t('localRegistry.mcpConfig')}</span>
            <button
              onClick={handleCopyConfig}
              className={`flex items-center gap-1 px-2 py-1 text-xs rounded transition-colors ${
                copied
                  ? 'text-green-600 bg-green-100'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-gray-200'
              }`}
              title={t('localRegistry.copy')}
            >
              {copied ? (
                <>
                  <ClipboardDocumentCheckIcon className="w-3.5 h-3.5" />
                  {t('localRegistry.copied')}
                </>
              ) : (
                <>
                  <ClipboardDocumentIcon className="w-3.5 h-3.5" />
                  {t('localRegistry.copy')}
                </>
              )}
            </button>
          </div>

          <div className="relative">
            <textarea
              value={configText}
              onChange={(e) => {
                setConfigText(e.target.value)
                if (!isEditingConfig) setIsEditingConfig(true)
                setError(null)
              }}
              className={`w-full h-48 font-mono text-xs p-3 rounded-lg border resize-none focus:outline-none focus:ring-2 ${
                error
                  ? 'border-red-300 focus:ring-red-200 bg-red-50'
                  : 'border-gray-200 focus:ring-orange-200 bg-white'
              }`}
              spellCheck={false}
            />

            {error && (
              <div className="absolute bottom-2 left-2 right-2 bg-red-100 text-red-700 text-xs p-2 rounded flex items-center gap-1">
                <ExclamationTriangleIcon className="w-4 h-4 flex-shrink-0" />
                <span className="truncate">{error}</span>
              </div>
            )}
          </div>

          {/* Save/Cancel buttons (when editing config) */}
          {isEditingConfig && (
            <div className="flex justify-end gap-2 mt-3">
              <Button
                variant="outline"
                size="sm"
                onClick={handleCancelConfig}
                disabled={isSaving}
              >
                {t('localRegistry.cancel')}
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleSaveConfig}
                disabled={isSaving}
              >
                {isSaving ? t('localRegistry.saving') : t('localRegistry.saveConfig')}
              </Button>
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}

// ============================================================================
// AddServerCard Component with Curation Step
// ============================================================================

type AddServerStep = 'input' | 'curating' | 'review'

interface EditableCuration {
  name: string
  description: string
  category: string
  tags: string[]
  author: string
  iconUrl: string
}

interface AddServerCardProps {
  onAdd: (serverId: string, config: MCPServerConfig, metadata?: ServerMetadata) => Promise<void>
}

function AddServerCard({ onAdd }: AddServerCardProps) {
  const { t } = useTranslation('marketplace')
  const [configText, setConfigText] = useState('')
  const [parsedInfo, setParsedInfo] = useState<ParsedConfig | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isAdding, setIsAdding] = useState(false)

  // Curation state
  const [step, setStep] = useState<AddServerStep>('input')
  const [curationResult, setCurationResult] = useState<CurationPreviewResponse | null>(null)
  const [editableCuration, setEditableCuration] = useState<EditableCuration>({
    name: '',
    description: '',
    category: 'custom',
    tags: [],
    author: '',
    iconUrl: '',
  })
  const [newTag, setNewTag] = useState('')

  const handleAnalyze = () => {
    if (!configText.trim()) {
      setError('Please paste your MCP config JSON')
      setParsedInfo(null)
      return
    }

    const result = parseMCPConfig(configText)
    if ('error' in result && !('isValid' in result)) {
      setError(result.error)
      setParsedInfo(null)
    } else if ('isValid' in result) {
      setError(null)
      setParsedInfo(result)
    }
  }

  const handleCurate = async () => {
    if (!parsedInfo) return

    setStep('curating')
    setError(null)

    try {
      // Call curation preview API
      const result = await adminRegistryApi.curateServerPreview(
        parsedInfo.serverId,
        parsedInfo.config,
        { name: parsedInfo.serverId, description: '' }
      )

      setCurationResult(result)

      // Initialize editable curation with results
      setEditableCuration({
        name: result.name || parsedInfo.serverId,
        description: result.description || result.summary || '',
        category: result.category || 'custom',
        tags: result.tags || [],
        author: result.author || '',
        iconUrl: result.icon_url || '',
      })

      setStep('review')
    } catch (e: any) {
      setError(e.message || 'Curation failed')
      setStep('input')
    }
  }

  const handleAdd = async () => {
    if (!parsedInfo) return

    setIsAdding(true)
    try {
      await onAdd(parsedInfo.serverId, parsedInfo.config, {
        name: editableCuration.name,
        description: editableCuration.description,
        category: editableCuration.category,
        icon_url: editableCuration.iconUrl || undefined,
      })
      // Reset form
      setConfigText('')
      setParsedInfo(null)
      setCurationResult(null)
      setEditableCuration({
        name: '',
        description: '',
        category: 'custom',
        tags: [],
        author: '',
        iconUrl: '',
      })
      setStep('input')
    } catch (e: any) {
      setError(e.message || 'Failed to add server')
    } finally {
      setIsAdding(false)
    }
  }

  const handleAddTag = () => {
    if (newTag.trim() && !editableCuration.tags.includes(newTag.trim())) {
      setEditableCuration({
        ...editableCuration,
        tags: [...editableCuration.tags, newTag.trim()],
      })
      setNewTag('')
    }
  }

  const handleRemoveTag = (tag: string) => {
    setEditableCuration({
      ...editableCuration,
      tags: editableCuration.tags.filter((t) => t !== tag),
    })
  }

  const handleReset = () => {
    setStep('input')
    setParsedInfo(null)
    setCurationResult(null)
    setEditableCuration({
      name: '',
      description: '',
      category: 'custom',
      tags: [],
      author: '',
      iconUrl: '',
    })
    setError(null)
  }

  const placeholder = `{
  "my-server": {
    "command": "npx",
    "args": ["-y", "@org/mcp-server"],
    "env": {
      "API_KEY": "\${API_KEY}"
    }
  }
}`

  // Categories for selection
  const categories = [
    'productivity', 'development', 'data', 'communication', 'cloud',
    'ai', 'automation', 'security', 'media', 'custom', 'other'
  ]

  return (
    <Card className="border-dashed border-2 border-gray-300 bg-gray-50/50">
      <div className="p-4">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-8 h-8 rounded-lg bg-orange-100 flex items-center justify-center">
            {step === 'curating' ? (
              <ArrowPathIcon className="w-5 h-5 text-orange-600 animate-spin" />
            ) : step === 'review' ? (
              <SparklesIcon className="w-5 h-5 text-orange-600" />
            ) : (
              <PlusIcon className="w-5 h-5 text-orange-600" />
            )}
          </div>
          <h3 className="font-semibold text-gray-900">
            {step === 'curating' ? t('localRegistry.curatingServer') :
             step === 'review' ? t('localRegistry.reviewMetadata') :
             t('localRegistry.addServer')}
          </h3>
        </div>

        {/* Step 1: Input Config */}
        {step === 'input' && (
          <>
            <p className="text-sm text-gray-600 mb-3">
              {t('localRegistry.pasteConfig')}
            </p>

            <textarea
              value={configText}
              onChange={(e) => {
                setConfigText(e.target.value)
                setError(null)
                setParsedInfo(null)
              }}
              placeholder={placeholder}
              className={`w-full h-48 font-mono text-sm p-3 rounded-lg border resize-none focus:outline-none focus:ring-2 ${
                error
                  ? 'border-red-300 focus:ring-red-200 bg-red-50'
                  : 'border-gray-200 focus:ring-orange-200 bg-white'
              }`}
              spellCheck={false}
            />

            {error && (
              <div className="mt-2 bg-red-100 text-red-700 text-sm p-2 rounded flex items-center gap-1">
                <ExclamationTriangleIcon className="w-4 h-4" />
                {error}
              </div>
            )}

            {/* Parsed info display */}
            {parsedInfo && (
              <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded-lg">
                <p className="text-sm font-medium text-green-800 mb-2">
                  ✓ {t('localRegistry.configParsed')}
                </p>

                <div className="space-y-2 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="text-gray-600">{t('localRegistry.serverId')}</span>
                    <code className="bg-green-100 px-2 py-0.5 rounded text-green-800">
                      {parsedInfo.serverId}
                    </code>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-gray-600">{t('localRegistry.type')}</span>
                    <Badge variant="gray" size="sm">{parsedInfo.detectedType}</Badge>
                    {parsedInfo.detectedPackage && (
                      <code className="bg-gray-100 px-2 py-0.5 rounded text-gray-700">
                        {parsedInfo.detectedPackage}
                      </code>
                    )}
                  </div>

                  {parsedInfo.detectedCredentials.length > 0 && (
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-gray-600">{t('localRegistry.credentialsLabel')}</span>
                      {parsedInfo.detectedCredentials.map(cred => (
                        <Badge key={cred} variant="warning" size="sm" className="flex items-center gap-1">
                          <KeyIcon className="w-3 h-3" />
                          {cred}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Action buttons */}
            <div className="flex justify-end gap-2 mt-3">
              {!parsedInfo ? (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleAnalyze}
                  disabled={!configText.trim()}
                >
                  {t('localRegistry.analyzeConfig')}
                </Button>
              ) : (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setParsedInfo(null)}
                  >
                    {t('localRegistry.back')}
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleCurate}
                  >
                    <SparklesIcon className="w-4 h-4 mr-1" />
                    {t('localRegistry.curateWithAI')}
                  </Button>
                </>
              )}
            </div>
          </>
        )}

        {/* Step 2: Curating (loading state) */}
        {step === 'curating' && (
          <div className="flex flex-col items-center justify-center py-8">
            <ArrowPathIcon className="w-12 h-12 text-orange-500 animate-spin mb-4" />
            <p className="text-gray-600">{t('localRegistry.analyzingWithAI')}</p>
            <p className="text-sm text-gray-500 mt-1">{t('localRegistry.analyzingNote')}</p>
          </div>
        )}

        {/* Step 3: Review Curation Results */}
        {step === 'review' && curationResult && (
          <>
            <div className="space-y-4">
              {/* Curation source badge */}
              <div className="flex items-center gap-2">
                <Badge
                  variant={curationResult.curated ? 'success' : 'warning'}
                  size="sm"
                  className="flex items-center gap-1"
                >
                  <SparklesIcon className="w-3 h-3" />
                  {curationResult.curation_source === 'llm+static' ? t('localRegistry.aiAnalysis') :
                   curationResult.curation_source === 'static' ? t('localRegistry.staticAnalysis') :
                   curationResult.curation_source}
                </Badge>
                {curationResult.quality_score > 0 && (
                  <Badge variant="gray" size="sm">
                    {t('localRegistry.quality', { score: curationResult.quality_score })}
                  </Badge>
                )}
              </div>

              {/* Editable fields */}
              <div className="space-y-3">
                {/* Icon with editable URL */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{t('localRegistry.icon')}</label>
                  <div className="flex items-center gap-3">
                    {editableCuration.iconUrl ? (
                      <img
                        src={editableCuration.iconUrl}
                        alt="Icon"
                        className="w-12 h-12 rounded-lg border border-gray-200 object-contain bg-white"
                        onError={(e) => {
                          (e.target as HTMLImageElement).src = ''
                          (e.target as HTMLImageElement).className = 'w-12 h-12 rounded-lg border border-gray-200 bg-gray-100'
                        }}
                      />
                    ) : (
                      <div className="w-12 h-12 rounded-lg border border-gray-200 bg-gray-100 flex items-center justify-center">
                        <CubeIcon className="w-6 h-6 text-gray-400" />
                      </div>
                    )}
                    <input
                      type="text"
                      value={editableCuration.iconUrl}
                      onChange={(e) => setEditableCuration({ ...editableCuration, iconUrl: e.target.value })}
                      placeholder="https://cdn.simpleicons.org/... or paste icon URL"
                      className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-orange-200"
                    />
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Paste icon URL or use SimpleIcons CDN: https://cdn.simpleicons.org/[slug]
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{t('localRegistry.name')}</label>
                  <input
                    type="text"
                    value={editableCuration.name}
                    onChange={(e) => setEditableCuration({ ...editableCuration, name: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-200"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{t('localRegistry.description')}</label>
                  <textarea
                    value={editableCuration.description}
                    onChange={(e) => setEditableCuration({ ...editableCuration, description: e.target.value })}
                    rows={3}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-200 resize-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{t('localRegistry.category')}</label>
                  <select
                    value={editableCuration.category}
                    onChange={(e) => setEditableCuration({ ...editableCuration, category: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-200"
                  >
                    {categories.map((cat) => (
                      <option key={cat} value={cat}>{cat.charAt(0).toUpperCase() + cat.slice(1)}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{t('localRegistry.author')}</label>
                  <input
                    type="text"
                    value={editableCuration.author}
                    onChange={(e) => setEditableCuration({ ...editableCuration, author: e.target.value })}
                    placeholder={t('localRegistry.authorPlaceholder')}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-200"
                  />
                </div>

                {/* Tags */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{t('localRegistry.tags')}</label>
                  <div className="flex flex-wrap gap-2 mb-2">
                    {editableCuration.tags.map((tag) => (
                      <Badge
                        key={tag}
                        variant="gray"
                        size="sm"
                        className="flex items-center gap-1"
                      >
                        <TagIcon className="w-3 h-3" />
                        {tag}
                        <button
                          onClick={() => handleRemoveTag(tag)}
                          className="ml-1 hover:text-red-600"
                        >
                          <XMarkIcon className="w-3 h-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newTag}
                      onChange={(e) => setNewTag(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddTag())}
                      placeholder={t('localRegistry.addTagPlaceholder')}
                      className="flex-1 px-3 py-1 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-orange-200"
                    />
                    <Button variant="outline" size="sm" onClick={handleAddTag}>
                      {t('localRegistry.add')}
                    </Button>
                  </div>
                </div>

                {/* Use cases from curation */}
                {curationResult.use_cases && curationResult.use_cases.length > 0 && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">{t('localRegistry.suggestedUseCases')}</label>
                    <ul className="text-sm text-gray-600 list-disc list-inside space-y-1">
                      {curationResult.use_cases.map((uc, i) => (
                        <li key={i}>{uc}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Credentials detected */}
                {curationResult.credentials && curationResult.credentials.length > 0 && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">{t('localRegistry.credentialsDetected')}</label>
                    <div className="flex flex-wrap gap-2">
                      {curationResult.credentials.map((cred) => (
                        <Badge key={cred.name} variant="warning" size="sm" className="flex items-center gap-1">
                          <KeyIcon className="w-3 h-3" />
                          {cred.name}
                          {cred.required && <span className="text-red-600">*</span>}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {error && (
                <div className="bg-red-100 text-red-700 text-sm p-2 rounded flex items-center gap-1">
                  <ExclamationTriangleIcon className="w-4 h-4" />
                  {error}
                </div>
              )}
            </div>

            {/* Action buttons */}
            <div className="flex justify-end gap-2 mt-4 pt-4 border-t border-gray-200">
              <Button
                variant="outline"
                size="sm"
                onClick={handleReset}
              >
                {t('localRegistry.startOver')}
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleAdd}
                disabled={isAdding || !editableCuration.name}
              >
                <CheckIcon className="w-4 h-4 mr-1" />
                {isAdding ? t('localRegistry.adding') : t('localRegistry.addToRegistry')}
              </Button>
            </div>
          </>
        )}
      </div>
    </Card>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function LocalRegistryManager({
  servers,
  onAddServer,
  onUpdateServer,
  onRenameServer,
  onUpdateMetadata,
  onDeleteServer,
  onToggleVisibility,
}: LocalRegistryManagerProps) {
  const { t } = useTranslation('marketplace')
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-2">
        <div>
          <h3 className="font-semibold text-gray-900">{t('localRegistry.title')}</h3>
          <p className="text-sm text-gray-600">
            {t('localRegistry.subtitle')}
          </p>
        </div>
        <Badge variant="gray" size="sm">
          {t('localRegistry.serverCount', { count: servers.length })}
        </Badge>
      </div>

      {/* Existing servers */}
      {servers.map(server => (
        <ServerConfigCard
          key={server.id}
          server={server}
          onUpdate={(config) => onUpdateServer(server.id, config)}
          onRename={onRenameServer ? (newId, config) => onRenameServer(server.id, newId, config) : undefined}
          onUpdateMetadata={(metadata) => onUpdateMetadata(server.id, metadata)}
          onDelete={() => onDeleteServer(server.id)}
          onToggleVisibility={(visible) => onToggleVisibility(server.id, visible)}
        />
      ))}

      {/* Add new server card */}
      <AddServerCard onAdd={onAddServer} />
    </div>
  )
}

export default LocalRegistryManager
