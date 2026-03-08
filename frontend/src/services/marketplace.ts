/**
 * Marketplace API Service
 *
 * Handles all marketplace-related API calls.
 */

import axios from 'axios'
import type {
  MCPServer,
  MarketplaceFilters,
  UserCredential,
  OrganizationCredential,
  CredentialSetupToken,
  MarketplaceAPIKey,
  ServerConnectionStatus,
} from '@/types/marketplace'

// Re-export types for convenience
export type { OrganizationCredential } from '@/types/marketplace'

const API_BASE = '/api/v1'

// ============================================================================
// Marketplace Admin Types
// ============================================================================

export interface SyncResult {
  status: string
  total_servers: number
  sources: Record<string, number>
  from_cache: boolean
  cache_age_seconds?: number
}

export interface SyncAndPersistResult {
  sync: SyncResult
  persistence: {
    servers_written: number
    path: string
  }
}

export interface CurationStatus {
  total_servers: number
  curated_servers: number
  pending_curation: number
  needs_icon_refresh: number
  llm_configured: boolean
  cache_path?: string
}

export interface CurationResult {
  status: string
  total_curated: number
  new_curated: number
  remaining?: number
  errors?: string[]
}

export interface FullCurationResult extends CurationResult {
  cache_cleared?: number
  deduplication?: {
    duplicates_found: number
    servers_merged: number
  }
}

export interface SemanticDeduplicationResult {
  status: string
  duplicates_found: number
  servers_merged: number
  clusters?: Array<{
    canonical: string
    duplicates: string[]
  }>
}

export interface SyncStatus {
  servers_count: number
  last_sync: string | null
  cache_expires: string | null
  cache_valid: boolean
  sources_enabled: Record<string, boolean>
  sources_active: string[]
}

// ============================================================================
// Admin Registry Types
// ============================================================================

export interface SourceInfo {
  id: string
  name: string
  description: string
  enabled: boolean
  priority: number
  server_count: number
}

export interface CredentialDefinition {
  name: string
  description: string
  required: boolean
  type: string
  default?: string
  example?: string
  documentationUrl?: string
  allow_localhost?: boolean
  allow_private_ip?: boolean
}

export interface InstallDefinition {
  type: 'npm' | 'pip' | 'github' | 'docker' | 'local' | 'remote'
  package?: string
  url?: string
  binary_path?: string
}

export interface LocalServerCreate {
  id: string
  name: string
  description: string
  author?: string
  repository?: string
  category?: string
  tags?: string[]
  install: InstallDefinition
  command?: string
  args?: string[]
  env?: Record<string, string>
  credentials?: CredentialDefinition[]
  toolsPreview?: string[]
  popularity?: number
  verified?: boolean
  visible_in_marketplace?: boolean
  saas_compatible?: boolean
  icon_url?: string
}

export interface LocalServerResponse {
  id: string
  name: string
  description: string
  author?: string
  repository?: string
  category: string
  tags: string[]
  install: InstallDefinition
  command?: string
  args: string[]
  env?: Record<string, string>
  credentials: CredentialDefinition[]
  toolsPreview: string[]
  popularity: number
  verified: boolean
  visible_in_marketplace: boolean
  saas_compatible: boolean
  icon_url?: string
}

export interface CurationPreviewResponse {
  server_id: string
  name: string
  description: string
  service_id?: string
  service_display_name?: string
  author?: string
  category: string
  tags: string[]
  icon_url?: string
  icon_hint?: string
  credentials: CredentialDefinition[]
  tools_preview: string[]
  summary?: string
  use_cases: string[]
  quality_score: number
  install: InstallDefinition
  curated: boolean
  curation_source: string
}

export interface AdminServerInfo {
  id: string
  name: string
  source: string
  category?: string
  visible_in_marketplace: boolean
  verified: boolean
  popularity: number
  credentials_count: number
  saas_compatible: boolean
  // Additional fields for full ServerCard display
  description?: string
  author?: string
  tags?: string[]
  tools_preview?: string[]
  tools_count?: number
  install_type?: string
  is_official?: boolean
  requires_local_access?: boolean
  icon_url?: string
  icon_urls?: string[]
}

// Create axios instance with default config
const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Storage keys (must match AuthContext)
const STORAGE_KEYS = {
  ACCESS_TOKEN: 'bigmcp_access_token',
  REFRESH_TOKEN: 'bigmcp_refresh_token',
  USER: 'bigmcp_user',
  SUBSCRIPTION: 'bigmcp_subscription',
  ORGANIZATION: 'bigmcp_organization',
}

/**
 * Clear all auth data and redirect to login page.
 * Used by the 401 response interceptor.
 */
function clearAuthAndRedirect() {
  localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN)
  localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN)
  localStorage.removeItem(STORAGE_KEYS.USER)
  localStorage.removeItem(STORAGE_KEYS.SUBSCRIPTION)
  localStorage.removeItem(STORAGE_KEYS.ORGANIZATION)

  // Only redirect if not already on login page
  if (!window.location.pathname.includes('/login')) {
    window.location.href = '/login'
  }
}

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Handle 401 errors with automatic token refresh and redirect
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // Only handle 401 errors that haven't been retried yet
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      const refreshToken = localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN)

      // No refresh token → clear and redirect to login
      if (!refreshToken) {
        clearAuthAndRedirect()
        return Promise.reject(error)
      }

      try {
        // Attempt to refresh the token
        const refreshResponse = await fetch(`${API_BASE}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        })

        if (!refreshResponse.ok) {
          // Refresh failed → clear and redirect
          clearAuthAndRedirect()
          return Promise.reject(error)
        }

        const data = await refreshResponse.json()
        const newAccessToken = data.access_token
        const newRefreshToken = data.refresh_token

        // Update stored tokens
        localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, newAccessToken)
        if (newRefreshToken) {
          localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, newRefreshToken)
        }

        // Retry original request with new token
        originalRequest.headers['Authorization'] = `Bearer ${newAccessToken}`
        return api(originalRequest)

      } catch {
        // Refresh failed completely → clear and redirect
        clearAuthAndRedirect()
        return Promise.reject(error)
      }
    }

    return Promise.reject(error)
  }
)

/**
 * Marketplace Server Discovery
 */
export const marketplaceApi = {
  /**
   * List all available MCP servers in the marketplace
   */
  async listServers(filters?: MarketplaceFilters): Promise<MCPServer[]> {
    const { data } = await api.get('/marketplace/servers', { params: filters })
    // Backend returns {servers: [...], total, offset, limit, has_more}
    return data.servers || []
  },

  /**
   * Connect to a server (install + configure credentials in one operation)
   * Supports multi-account: always creates a new server instance
   */
  async connectServer(
    serverId: string,
    organizationId: string,
    credentials: Record<string, string>,
    name?: string,
    autoStart: boolean = false,
    useOrgCredentials: boolean = false,
    additionalCredentials: Record<string, string> = {}
  ): Promise<{
    success: boolean
    message: string
    server_id: string
    server_uuid: string
    credential_id: string
    already_installed: boolean
  }> {
    const { data } = await api.post('/marketplace/connect', {
      server_id: serverId,
      organization_id: organizationId,
      credentials,
      name,
      auto_start: autoStart,
      use_org_credentials: useOrgCredentials,
      additional_credentials: additionalCredentials,
    })
    return data
  },

  /**
   * List marketplace servers that have organization credentials configured
   */
  async listTeamServers(): Promise<Array<{
    marketplace_server: MCPServer
    org_credential: {
      id: string
      server_id: string
      name: string
      description: string | null
      visible_to_users: boolean
      is_active: boolean
      created_at: string | null
      credential_keys: string[]
    }
    is_fully_configured: boolean
  }>> {
    const { data } = await api.get('/marketplace/team-servers')
    return data
  },

  /**
   * Get detailed information about a specific server
   */
  async getServer(serverId: string): Promise<MCPServer> {
    const { data } = await api.get(`/marketplace/servers/${serverId}`)
    return data
  },

  /**
   * Search servers by query
   */
  async searchServers(query: string): Promise<MCPServer[]> {
    const { data } = await api.get('/marketplace/servers/search', {
      params: { q: query },
    })
    return data
  },

  /**
   * Get servers by category
   */
  async getServersByCategory(category: string): Promise<MCPServer[]> {
    const { data } = await api.get(`/marketplace/categories/${category}/servers`)
    return data
  },

  /**
   * Get popular servers
   */
  async getPopularServers(limit: number = 10): Promise<MCPServer[]> {
    const { data } = await api.get('/marketplace/servers/popular', {
      params: { limit },
    })
    return data
  },

  /**
   * Get connection status for user's servers
   */
  async getConnectionStatus(): Promise<ServerConnectionStatus[]> {
    const { data } = await api.get('/marketplace/connection-status')
    return data
  },

  /**
   * List all available categories with server counts
   */
  async listCategories(): Promise<Array<{ id: string; name: string; count: number }>> {
    const { data } = await api.get('/marketplace/categories')
    return data
  },

  /**
   * Sync marketplace from all sources (Instance Admin only)
   */
  async syncMarketplace(force: boolean = false): Promise<SyncResult> {
    const { data } = await api.post('/marketplace/sync', null, { params: { force } })
    return data
  },

  /**
   * Sync marketplace AND persist validated data (Instance Admin only)
   */
  async syncAndPersist(force: boolean = false): Promise<SyncAndPersistResult> {
    const { data } = await api.post('/marketplace/sync-and-persist', null, { params: { force } })
    return data
  },

  /**
   * Persist currently validated server data to local registry (Instance Admin only)
   */
  async persistValidated(): Promise<{ servers_written: number; path: string }> {
    const { data } = await api.post('/marketplace/persist-validated')
    return data
  },

  /**
   * Get LLM curation status (Instance Admin only)
   */
  async getCurationStatus(): Promise<CurationStatus> {
    const { data } = await api.get('/marketplace/curation/status')
    return data
  },

  /**
   * Run LLM curation on new servers (Instance Admin only)
   */
  async runCuration(options?: {
    batch_size?: number
    max_servers?: number
    semantic_dedup?: boolean
  }): Promise<CurationResult> {
    const { data } = await api.post('/marketplace/curation/run', null, { params: options })
    return data
  },

  /**
   * Run LLM curation in background (Instance Admin only)
   */
  async runCurationBackground(options?: {
    batch_size?: number
    max_servers?: number
  }): Promise<{ status: string; message: string }> {
    const { data } = await api.post('/marketplace/curation/run-background', null, { params: options })
    return data
  },

  /**
   * Force full re-curation of ALL servers (Instance Admin only)
   */
  async forceFullCuration(options?: {
    batch_size?: number
    max_servers?: number
  }): Promise<FullCurationResult> {
    const { data } = await api.post('/marketplace/curation/force-full', null, { params: options })
    return data
  },

  /**
   * Refresh icons for servers (Instance Admin only)
   */
  async refreshIcons(): Promise<{ validated: number; failed: number }> {
    const { data } = await api.post('/marketplace/curation/refresh-icons')
    return data
  },

  /**
   * Revalidate icons for servers (Instance Admin only)
   */
  async revalidateIcons(): Promise<{ validated: number; failed: number }> {
    const { data } = await api.post('/marketplace/curation/revalidate-icons')
    return data
  },

  /**
   * Run semantic deduplication (Instance Admin only)
   */
  async semanticDeduplicate(): Promise<SemanticDeduplicationResult> {
    const { data } = await api.post('/marketplace/curation/semantic-deduplicate')
    return data
  },

  /**
   * Get sync status (Instance Admin only)
   */
  async getSyncStatus(): Promise<SyncStatus> {
    const { data } = await api.get('/marketplace/status')
    return data
  },
}

/**
 * Admin Registry Management (Instance Admin only)
 */
export const adminRegistryApi = {
  // ============================================================================
  // Sources
  // ============================================================================

  /**
   * List all marketplace sources
   */
  async listSources(): Promise<SourceInfo[]> {
    const { data } = await api.get('/admin/registry/sources')
    return data
  },

  /**
   * Toggle source enabled/disabled
   */
  async toggleSource(sourceId: string, enabled: boolean): Promise<{ success: boolean; message: string }> {
    const { data } = await api.patch(`/admin/registry/sources/${sourceId}`, { enabled })
    return data
  },

  /**
   * Update source priorities (for drag & drop reordering)
   */
  async updateSourcePriorities(priorities: Record<string, number>): Promise<{ success: boolean; message: string }> {
    const { data } = await api.put('/admin/registry/sources/priorities', { priorities })
    return data
  },

  // ============================================================================
  // Local Registry Servers
  // ============================================================================

  /**
   * List servers in local registry
   */
  async listLocalServers(): Promise<LocalServerResponse[]> {
    const { data } = await api.get('/admin/registry/servers')
    return data
  },

  /**
   * Get a specific server from local registry
   */
  async getLocalServer(serverId: string): Promise<LocalServerResponse> {
    const { data } = await api.get(`/admin/registry/servers/${serverId}`)
    return data
  },

  /**
   * Create a new server in local registry
   */
  async createLocalServer(server: LocalServerCreate): Promise<LocalServerResponse> {
    const { data } = await api.post('/admin/registry/servers', server)
    return data
  },

  /**
   * Update a server in local registry
   */
  async updateLocalServer(serverId: string, update: Partial<LocalServerCreate>): Promise<LocalServerResponse> {
    const { data } = await api.patch(`/admin/registry/servers/${serverId}`, update)
    return data
  },

  /**
   * Delete a server from local registry
   */
  async deleteLocalServer(serverId: string): Promise<{ success: boolean; message: string }> {
    const { data } = await api.delete(`/admin/registry/servers/${serverId}`)
    return data
  },

  /**
   * Create a server from raw MCP config JSON
   */
  async createServerFromConfig(
    serverId: string,
    config: { command?: string; args?: string[]; env?: Record<string, string>; url?: string },
    metadata?: { name?: string; description?: string; category?: string }
  ): Promise<LocalServerResponse> {
    const { data } = await api.post('/admin/registry/servers/from-config', {
      server_id: serverId,
      config,
      metadata,
    })
    return data
  },

  /**
   * Update a server's raw MCP config and optional metadata
   */
  async updateServerConfig(
    serverId: string,
    config: {
      command?: string
      args?: string[]
      env?: Record<string, string>
      url?: string
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
  ): Promise<LocalServerResponse> {
    const { data } = await api.put(`/admin/registry/servers/${serverId}/config`, { config })
    return data
  },

  /**
   * Get curation preview for a server config without saving
   * Runs the config through LLM curation pipeline to generate metadata suggestions
   */
  async curateServerPreview(
    serverId: string,
    config: { command?: string; args?: string[]; env?: Record<string, string>; url?: string },
    metadata?: { name?: string; description?: string }
  ): Promise<CurationPreviewResponse> {
    const { data } = await api.post('/admin/registry/servers/curate-preview', {
      server_id: serverId,
      config,
      metadata,
    })
    return data
  },

  // ============================================================================
  // All Servers (across sources)
  // ============================================================================

  /**
   * List all servers from all sources
   */
  async listAllServers(filters?: {
    source?: string
    category?: string
    search?: string
    visible_only?: boolean
    limit?: number
  }): Promise<AdminServerInfo[]> {
    const { data } = await api.get('/admin/registry/all-servers', { params: filters })
    return data
  },

  /**
   * Toggle server visibility in marketplace
   */
  async toggleServerVisibility(serverId: string, visible: boolean): Promise<{ success: boolean; message: string }> {
    const { data } = await api.patch(`/admin/registry/servers/${serverId}/visibility`, { visible_in_marketplace: visible })
    return data
  },

  /**
   * Bulk toggle visibility for multiple servers
   */
  async bulkToggleVisibility(serverIds: string[], visible: boolean): Promise<{ success: boolean; updated_count: number }> {
    const { data } = await api.post('/admin/registry/servers/bulk-visibility', { server_ids: serverIds, visible })
    return data
  },

  // ============================================================================
  // Categories
  // ============================================================================

  /**
   * List categories in local registry
   */
  async listCategories(): Promise<Record<string, { name: string; description: string; icon: string }>> {
    const { data } = await api.get('/admin/registry/categories')
    return data
  },

  /**
   * Create or update a category
   */
  async saveCategory(categoryId: string, name: string, description: string, icon: string): Promise<{ success: boolean }> {
    const { data } = await api.post(`/admin/registry/categories/${categoryId}`, null, {
      params: { name, description, icon }
    })
    return data
  },
}

/**
 * User Credentials Management
 */
export const credentialsApi = {
  /**
   * List user's credentials
   */
  async listUserCredentials(): Promise<UserCredential[]> {
    const { data } = await api.get('/user-credentials/')
    return data
  },

  /**
   * Create user credential for a server
   */
  async createUserCredential(
    serverId: string,
    credentials: Record<string, string>,
    name?: string
  ): Promise<UserCredential> {
    const { data } = await api.post('/user-credentials/', {
      server_id: serverId,
      credentials,
      name,
    })
    return data
  },

  /**
   * Update user credential
   */
  async updateUserCredential(
    credentialId: string,
    credentials: Record<string, string>
  ): Promise<UserCredential> {
    const { data } = await api.put(`/user-credentials/${credentialId}`, {
      credentials,
    })
    return data
  },

  /**
   * Delete user credential
   */
  async deleteUserCredential(credentialId: string): Promise<void> {
    await api.delete(`/user-credentials/${credentialId}`)
  },

  /**
   * Validate credentials by testing connection
   */
  async validateCredential(credentialId: string): Promise<boolean> {
    const { data } = await api.post(`/user-credentials/${credentialId}/validate`)
    return data.valid
  },
}

/**
 * Organization Credentials Management (Admin only)
 */
export const orgCredentialsApi = {
  /**
   * List organization credentials
   */
  async listOrgCredentials(): Promise<OrganizationCredential[]> {
    const { data } = await api.get('/org-credentials/')
    return data
  },

  /**
   * Create organization credential
   */
  async createOrgCredential(
    marketplaceServerId: string,
    credentials: Record<string, string>,
    name: string,
    visibleToUsers: boolean = false,
    description?: string
  ): Promise<OrganizationCredential> {
    const { data } = await api.post('/org-credentials/', {
      marketplace_server_id: marketplaceServerId,
      credentials,
      name,
      description,
      visible_to_users: visibleToUsers,
    })
    return data
  },

  /**
   * Update organization credential
   */
  async updateOrgCredential(
    serverId: string,
    update: {
      credentials?: Record<string, string>
      name?: string
      description?: string
      visible_to_users?: boolean
      is_active?: boolean
    }
  ): Promise<OrganizationCredential> {
    const { data } = await api.patch(`/org-credentials/${serverId}`, update)
    return data
  },

  /**
   * Delete organization credential
   */
  async deleteOrgCredential(credentialId: string): Promise<void> {
    await api.delete(`/org-credentials/${credentialId}`)
  },
}

/**
 * Credential Setup Tokens (for assisted credential setup)
 */
export const credentialSetupApi = {
  /**
   * Create a credential setup token
   */
  async createSetupToken(
    serverIds: string[],
    compositionId?: string
  ): Promise<CredentialSetupToken> {
    const { data } = await api.post('/credentials/setup-token', {
      server_ids: serverIds,
      composition_id: compositionId,
    })
    return data
  },

  /**
   * Get setup token details
   */
  async getSetupToken(token: string): Promise<CredentialSetupToken> {
    const { data } = await api.get(`/credentials/setup-token/${token}`)
    return data
  },

  /**
   * Complete credential setup via token
   */
  async completeSetup(
    token: string,
    credentials: Record<string, Record<string, string>>
  ): Promise<void> {
    await api.post(`/credentials/setup-token/${token}/complete`, { credentials })
  },
}

/**
 * Marketplace API Keys (for self-hosted installations)
 */
export const apiKeysApi = {
  /**
   * List user's marketplace API keys
   */
  async listAPIKeys(): Promise<MarketplaceAPIKey[]> {
    const { data } = await api.get('/marketplace-keys')
    return data
  },

  /**
   * Create new API key
   */
  async createAPIKey(
    name: string,
    deploymentType: string
  ): Promise<{ key: string; api_key: MarketplaceAPIKey }> {
    const { data } = await api.post('/marketplace-keys', {
      name,
      deployment_type: deploymentType,
    })
    return data
  },

  /**
   * Revoke API key
   */
  async revokeAPIKey(keyId: string): Promise<void> {
    await api.delete(`/marketplace-keys/${keyId}`)
  },
}

/**
 * User API Keys Management (for programmatic access to BigMCP)
 *
 * Different from marketplaceApiKeysApi:
 * - User API Keys: For users to access BigMCP API (Claude Desktop, scripts, automation)
 * - Marketplace API Keys: For self-hosted installations to access the cloud catalog
 */
export interface UserAPIKey {
  id: string
  name: string
  key_prefix: string
  scopes: string[]
  description?: string
  tool_group_id?: string
  is_active: boolean
  expires_at: string | null
  created_at: string
  last_used_at: string | null
  last_used_ip?: string
}

export interface CreateUserAPIKeyRequest {
  name: string
  scopes: string[]
  description?: string
  expires_at?: string
  tool_group_id?: string
}

export interface CreateUserAPIKeyResponse {
  api_key: UserAPIKey
  secret: string
}

export const userApiKeysApi = {
  /**
   * List all API keys for the current user
   */
  async list(organizationId?: string): Promise<UserAPIKey[]> {
    const params = organizationId ? { organization_id: organizationId } : {}
    const { data } = await api.get('/api-keys', { params })
    return data
  },

  /**
   * Create a new API key
   */
  async create(
    request: CreateUserAPIKeyRequest,
    organizationId?: string
  ): Promise<CreateUserAPIKeyResponse> {
    const params = organizationId ? { organization_id: organizationId } : {}
    const { data } = await api.post('/api-keys', request, { params })
    return data
  },

  /**
   * Get a specific API key
   */
  async get(keyId: string): Promise<UserAPIKey> {
    const { data } = await api.get(`/api-keys/${keyId}`)
    return data
  },

  /**
   * Update an API key
   */
  async update(
    keyId: string,
    updates: Partial<Pick<UserAPIKey, 'name' | 'description' | 'scopes' | 'is_active'>>
  ): Promise<UserAPIKey> {
    const { data } = await api.patch(`/api-keys/${keyId}`, updates)
    return data
  },

  /**
   * Revoke (delete) an API key
   */
  async revoke(keyId: string): Promise<void> {
    await api.delete(`/api-keys/${keyId}`)
  },

  /**
   * Reactivate a previously revoked API key
   */
  async activate(keyId: string): Promise<UserAPIKey> {
    const { data } = await api.post(`/api-keys/${keyId}/activate`)
    return data
  },
}

/**
 * Authentication & Account Management
 */
export interface ProfileUpdateRequest {
  name?: string
  avatar_url?: string
}

export interface PasswordChangeRequest {
  old_password: string
  new_password: string
}

export const authApi = {
  /**
   * Update user profile
   */
  async updateProfile(data: ProfileUpdateRequest): Promise<any> {
    const { data: response } = await api.patch('/auth/profile', data)
    return response
  },

  /**
   * Change password
   */
  async changePassword(data: PasswordChangeRequest): Promise<void> {
    await api.post('/auth/change-password', data)
  },

  /**
   * Delete account (irreversible)
   */
  async deleteAccount(): Promise<void> {
    await api.delete('/auth/account')
  },

  /**
   * Get current user info
   */
  async getMe(): Promise<any> {
    const { data } = await api.get('/auth/me')
    return data
  },
}

/**
 * MFA (Two-Factor Authentication) API
 */
import type {
  MFAStatus,
  MFASetupResponse,
  MFAChallengeResponse,
  MFALoginRequest,
} from '@/types/auth'

export const mfaApi = {
  /**
   * Get MFA status for current user
   */
  async getStatus(): Promise<MFAStatus> {
    const { data } = await api.get('/mfa/status')
    return data
  },

  /**
   * Start MFA setup (returns QR code URI and backup codes)
   */
  async setup(): Promise<MFASetupResponse> {
    const { data } = await api.post('/mfa/setup')
    return data
  },

  /**
   * Verify TOTP code to complete MFA setup
   */
  async verify(code: string): Promise<{ message: string }> {
    const { data } = await api.post('/mfa/verify', { code })
    return data
  },

  /**
   * Disable MFA (requires current TOTP code)
   */
  async disable(code: string): Promise<{ message: string }> {
    const { data } = await api.post('/mfa/disable', { code })
    return data
  },

  /**
   * Regenerate backup codes (requires current TOTP code)
   */
  async regenerateBackupCodes(code: string): Promise<{ backup_codes: string[]; message: string }> {
    const { data } = await api.post('/mfa/backup-codes/regenerate', { code })
    return data
  },

  /**
   * Complete login with MFA code (after receiving mfa_token)
   */
  async loginWithMFA(mfa_token: string, mfa_code: string): Promise<{
    access_token: string
    refresh_token: string
    token_type: string
    expires_in: number
  }> {
    const { data } = await api.post('/auth/login/mfa', { mfa_token, mfa_code })
    return data
  },
}

/**
 * OAuth Flow
 */
export const oauthApi = {
  /**
   * Initiate OAuth flow for a service
   */
  async initiateOAuth(
    serverId: string,
    redirectUri: string
  ): Promise<{ authorization_url: string }> {
    const { data } = await api.post('/oauth/authorize', {
      server_id: serverId,
      redirect_uri: redirectUri,
    })
    return data
  },

  /**
   * Complete OAuth flow with authorization code
   */
  async completeOAuth(
    code: string,
    state: string
  ): Promise<UserCredential> {
    const { data } = await api.post('/oauth/callback', { code, state })
    return data
  },
}

/**
 * MCP Server Control
 */
export const serverControlApi = {
  /**
   * Start an MCP server with user credentials
   */
  async startServer(serverId: string): Promise<void> {
    await api.post(`/mcp-servers/${serverId}/start`)
  },

  /**
   * Stop a running MCP server
   */
  async stopServer(serverId: string): Promise<void> {
    await api.post(`/mcp-servers/${serverId}/stop`)
  },

  /**
   * Restart an MCP server
   */
  async restartServer(serverId: string): Promise<void> {
    await api.post(`/mcp-servers/${serverId}/restart`)
  },

  /**
   * Toggle server visibility for OAuth clients (controls exposure to web dashboard)
   * Hidden servers are still accessible via API keys and tool groups
   */
  async toggleServer(serverId: string, isVisibleToOauth: boolean): Promise<void> {
    await api.patch(`/mcp-servers/${serverId}`, { is_visible_to_oauth_clients: isVisibleToOauth })
  },

  /**
   * Update server visibility settings
   */
  async updateServerVisibility(
    serverId: string,
    enabled: boolean,
    isVisibleToOauth: boolean
  ): Promise<void> {
    await api.patch(`/mcp-servers/${serverId}`, {
      enabled,
      is_visible_to_oauth_clients: isVisibleToOauth
    })
  },

  /**
   * Get server status
   */
  async getServerStatus(serverId: string): Promise<{
    status: string
    uptime?: number
    server_info?: any
  }> {
    const { data } = await api.get(`/mcp-servers/${serverId}`)
    return data
  },

  /**
   * List all MCP servers for the organization
   */
  async listServers(): Promise<any[]> {
    const { data } = await api.get('/mcp-servers/')
    return data.servers || []
  },
}

/**
 * Tools Visibility Management API
 *
 * Allows users to control tool visibility for OAuth clients.
 */
export const toolsApi = {
  /**
   * Update tool visibility for OAuth clients
   */
  async updateVisibility(
    toolId: string,
    isVisible: boolean
  ): Promise<{ success: boolean; tool: any }> {
    const { data } = await api.patch(`/tools/${toolId}/visibility`, {
      is_visible_to_oauth_clients: isVisible
    })
    return data
  },

  /**
   * List tools with optional filtering
   */
  async listTools(
    organizationId: string,
    includeHidden: boolean = false
  ): Promise<any[]> {
    const { data } = await api.get('/tools/', {
      params: {
        organization_id: organizationId,
        include_hidden: includeHidden
      }
    })
    return data.tools || []
  }
}

/**
 * Toolboxes Management API
 *
 * Allows users to create specialized toolboxes for AI agents,
 * controlling which tools are exposed to Claude Desktop.
 */
export interface ToolGroup {
  id: string
  user_id: string
  organization_id: string
  name: string
  description?: string
  icon?: string
  color?: string
  visibility: 'private' | 'organization' | 'public'
  is_active: boolean
  usage_count: number
  last_used_at?: string
  items: ToolGroupItem[]
  created_at: string
  updated_at: string
}

export interface ToolGroupItem {
  id: string
  tool_group_id: string
  item_type: 'tool' | 'composition'
  tool_id?: string
  composition_id?: string
  order: number
  config: Record<string, unknown>
  tool_name?: string
  tool_description?: string
  server_id?: string
  server_name?: string
}

export interface ToolInfo {
  id: string
  server_id: string
  server_name: string
  tool_name: string
  display_name?: string
  description?: string
  category?: string
  tags?: string[]
  in_groups: string[]
  is_visible_to_oauth_clients: boolean
}

export interface CreateToolGroupRequest {
  name: string
  description?: string
  icon?: string
  color?: string
  visibility?: 'private' | 'organization' | 'public'
}

export const toolGroupsApi = {
  /**
   * List all tool groups accessible to the user
   */
  async list(includeOrgGroups: boolean = true): Promise<ToolGroup[]> {
    const { data } = await api.get('/tool-groups', {
      params: { include_org_groups: includeOrgGroups }
    })
    return data.groups || []
  },

  /**
   * Create a new tool group
   */
  async create(request: CreateToolGroupRequest): Promise<ToolGroup> {
    const { data } = await api.post('/tool-groups', request)
    return data
  },

  /**
   * Get a specific tool group
   */
  async get(groupId: string): Promise<ToolGroup> {
    const { data } = await api.get(`/tool-groups/${groupId}`)
    return data
  },

  /**
   * Update a tool group
   */
  async update(groupId: string, updates: Partial<CreateToolGroupRequest & { is_active: boolean }>): Promise<ToolGroup> {
    const { data } = await api.patch(`/tool-groups/${groupId}`, updates)
    return data
  },

  /**
   * Delete a tool group
   */
  async delete(groupId: string): Promise<void> {
    await api.delete(`/tool-groups/${groupId}`)
  },

  /**
   * Add a tool to a group
   */
  async addTool(groupId: string, toolId: string, order?: number): Promise<ToolGroupItem> {
    const { data } = await api.post(`/tool-groups/${groupId}/items`, {
      item_type: 'tool',
      tool_id: toolId,
      order: order ?? 0
    })
    return data
  },

  /**
   * Remove an item from a group
   */
  async removeItem(groupId: string, itemId: string): Promise<void> {
    await api.delete(`/tool-groups/${groupId}/items/${itemId}`)
  },

  /**
   * List all available tools that can be added to groups
   */
  async listAvailableTools(): Promise<ToolInfo[]> {
    const { data } = await api.get('/tool-groups/available-tools')
    return data
  }
}

/**
 * Compositions API
 *
 * Manages multi-step workflow compositions with RBAC support.
 */
export type CompositionVisibility = 'private' | 'organization' | 'public'

export interface Composition {
  id: string
  organization_id: string
  created_by: string
  name: string
  description?: string
  visibility: CompositionVisibility
  steps: Array<{
    id: string
    tool: string
    params: Record<string, unknown>
    depends_on: string[]
  }>
  data_mappings: Array<{
    from: string
    to: string
  }>
  input_schema: Record<string, unknown>
  output_schema?: Record<string, unknown>
  server_bindings: Record<string, string>
  allowed_roles: string[]
  force_org_credentials: boolean
  requires_approval: boolean
  status: 'temporary' | 'validated' | 'production'
  ttl?: number
  extra_metadata: Record<string, unknown>
  created_at: string
  updated_at: string
  can_execute?: boolean
  can_edit?: boolean
}

export interface CreateCompositionRequest {
  name: string
  description?: string
  visibility?: CompositionVisibility
  steps?: Array<{
    id: string
    tool: string
    params?: Record<string, unknown>
    depends_on?: string[]
  }>
  data_mappings?: Array<{ from: string; to: string }>
  input_schema?: Record<string, unknown>
  output_schema?: Record<string, unknown>
  server_bindings?: Record<string, string>
  allowed_roles?: string[]
  force_org_credentials?: boolean
  status?: string
  ttl?: number
  extra_metadata?: Record<string, unknown>
}

/**
 * Detailed result of a single composition step execution.
 */
export interface StepResult {
  /** Unique step identifier from composition definition */
  step_id: string
  /** Name of the tool that was executed */
  tool: string
  /** Step execution status */
  status: 'success' | 'failed' | 'skipped'
  /** Step execution duration in milliseconds */
  duration_ms: number
  /** Step output if successful (structure depends on tool) */
  result?: Record<string, unknown>
  /** Error message if step failed */
  error?: string
  /** Number of retry attempts before final status */
  retries?: number
}

/**
 * Response from composition execution.
 */
export interface CompositionExecuteResponse {
  /** ID of the executed composition */
  composition_id: string
  /** Unique execution identifier for tracking */
  execution_id?: string
  /** Overall execution status */
  status: 'success' | 'partial' | 'failed'
  /** Final outputs (result of last successful step) */
  outputs: Record<string, unknown>
  /** Total execution duration in milliseconds */
  duration_ms: number
  /** Detailed results from each step */
  step_results: StepResult[]
  /** Execution start timestamp (ISO format) */
  started_at?: string
  /** Execution completion timestamp (ISO format) */
  completed_at?: string
  /** Global error message if execution failed */
  error?: string
}

/**
 * JSON Schema property definition for composition inputs.
 */
export interface InputSchemaProperty {
  type: 'string' | 'number' | 'integer' | 'boolean' | 'array' | 'object'
  description?: string
  default?: unknown
  enum?: string[]
  items?: InputSchemaProperty
  properties?: Record<string, InputSchemaProperty>
  minLength?: number
  maxLength?: number
  minimum?: number
  maximum?: number
}

/**
 * JSON Schema for composition input parameters.
 */
export interface InputSchema {
  type: 'object'
  required?: string[]
  properties?: Record<string, InputSchemaProperty>
}

export const compositionsApi = {
  /**
   * List all compositions for the current organization
   */
  async list(filters?: {
    status?: string
    created_by?: string
  }): Promise<{ compositions: Composition[]; total: number }> {
    const { data } = await api.get('/compositions', { params: filters })
    return data
  },

  /**
   * Create a new composition
   */
  async create(request: CreateCompositionRequest): Promise<Composition> {
    const { data } = await api.post('/compositions', request)
    return data
  },

  /**
   * Get a specific composition
   */
  async get(compositionId: string): Promise<Composition> {
    const { data } = await api.get(`/compositions/${compositionId}`)
    return data
  },

  /**
   * Update a composition
   */
  async update(
    compositionId: string,
    updates: Partial<CreateCompositionRequest>
  ): Promise<Composition> {
    const { data } = await api.patch(`/compositions/${compositionId}`, updates)
    return data
  },

  /**
   * Delete a composition
   */
  async delete(compositionId: string): Promise<void> {
    await api.delete(`/compositions/${compositionId}`)
  },

  /**
   * Promote composition status (temporary → validated → production)
   */
  async promote(
    compositionId: string,
    status: 'validated' | 'production'
  ): Promise<Composition> {
    const { data } = await api.post(`/compositions/${compositionId}/promote`, {
      status,
    })
    return data
  },

  /**
   * Execute a composition
   */
  async execute(
    compositionId: string,
    inputs: Record<string, unknown> = {}
  ): Promise<CompositionExecuteResponse> {
    const { data } = await api.post(`/compositions/${compositionId}/execute`, {
      inputs,
    })
    return data
  },
}

/**
 * Organization Members API
 *
 * Manages organization members, roles, and invitations.
 */
export type MemberRole = 'owner' | 'admin' | 'member' | 'viewer'

export interface OrganizationMember {
  id: string
  user_id: string
  organization_id: string
  role: MemberRole
  invited_by?: string
  created_at: string
  updated_at: string
  user_email?: string
  user_name?: string
  user_avatar_url?: string
}

export interface Invitation {
  id: string
  organization_id: string
  email: string
  role: MemberRole
  token: string
  invited_by: string
  expires_at: string
  created_at: string
  organization_name?: string
}

export interface PendingInvitation {
  id: string
  organization_name: string
  organization_slug: string
  role: MemberRole
  invited_by_name?: string
  expires_at: string
}

export const organizationMembersApi = {
  /**
   * List all members of an organization
   */
  async listMembers(
    organizationId: string
  ): Promise<{ members: OrganizationMember[]; total: number }> {
    const { data } = await api.get(`/organizations/${organizationId}/members`)
    return data
  },

  /**
   * Update a member's role
   */
  async updateRole(
    organizationId: string,
    userId: string,
    role: MemberRole
  ): Promise<OrganizationMember> {
    const { data } = await api.patch(
      `/organizations/${organizationId}/members/${userId}`,
      { role }
    )
    return data
  },

  /**
   * Remove a member from the organization
   */
  async removeMember(
    organizationId: string,
    userId: string
  ): Promise<{ success: boolean; message: string }> {
    const { data } = await api.delete(
      `/organizations/${organizationId}/members/${userId}`
    )
    return data
  },

  /**
   * Send an invitation to join the organization
   */
  async invite(
    organizationId: string,
    email: string,
    role: MemberRole,
    message?: string
  ): Promise<Invitation> {
    const { data } = await api.post(
      `/organizations/${organizationId}/invitations`,
      { email, role, message }
    )
    return data
  },

  /**
   * List all invitations for an organization
   */
  async listInvitations(
    organizationId: string,
    status?: string
  ): Promise<Invitation[]> {
    const { data } = await api.get(
      `/organizations/${organizationId}/invitations`,
      { params: status ? { status } : {} }
    )
    return data
  },

  /**
   * Revoke a pending invitation
   */
  async revokeInvitation(
    organizationId: string,
    invitationId: string
  ): Promise<{ success: boolean; message: string }> {
    const { data } = await api.delete(
      `/organizations/${organizationId}/invitations/${invitationId}`
    )
    return data
  },

  /**
   * Get pending invitations for the current user
   */
  async getMyPendingInvitations(): Promise<PendingInvitation[]> {
    const { data } = await api.get('/organizations/invitations/pending')
    return data
  },

  /**
   * Accept an invitation
   */
  async acceptInvitation(token: string): Promise<{
    success: boolean
    message: string
    organization: {
      id: string
      name: string
      slug: string
    }
  }> {
    const { data } = await api.post(`/organizations/invitations/${token}/accept`)
    return data
  },

  /**
   * Decline an invitation
   */
  async declineInvitation(
    token: string
  ): Promise<{ success: boolean; message: string }> {
    const { data } = await api.post(`/organizations/invitations/${token}/decline`)
    return data
  },
}

/**
 * Edition API
 *
 * Fetches edition status from backend.
 * Works in ALL editions (Community, Enterprise, Cloud SaaS).
 */
import type {
  EditionInfo,
  License,
  LicensesListResponse,
  EnterpriseCheckoutRequest,
  EnterpriseCheckoutResponse,
  PublicSectorEligibility,
} from '@/types/auth'

export const editionApi = {
  /**
   * Get current edition status from backend.
   * This endpoint is available at root level (not under /api/v1).
   * It's always available regardless of edition or authentication.
   */
  async getStatus(): Promise<EditionInfo> {
    // Call /edition/status directly (not through /api/v1 prefix)
    const response = await fetch('/edition/status')
    if (!response.ok) {
      throw new Error(`Failed to fetch edition status: ${response.status}`)
    }
    return response.json()
  },
}

/**
 * Instance Admin API
 *
 * Manages instance-level admin privileges.
 * - Community: Auto-admin (all users)
 * - Enterprise: Token validated once, stored in user preferences
 * - Cloud SaaS: Platform owner only (no UI exposed)
 */
export interface AdminStatus {
  is_instance_admin: boolean
  edition: string
  requires_token: boolean
  token_hint?: string
}

export interface AdminTokenResponse {
  success: boolean
  message: string
}

export const instanceAdminApi = {
  /**
   * Get current user's admin status
   */
  async getStatus(): Promise<AdminStatus> {
    const { data } = await api.get('/admin/status')
    return data
  },

  /**
   * Validate admin token and grant admin privileges
   * Only used for Enterprise edition
   */
  async validateToken(token: string): Promise<AdminTokenResponse> {
    const { data } = await api.post('/admin/validate-token', { token })
    return data
  },

  /**
   * Revoke own admin privileges
   * Not available on Community edition
   */
  async revokeAdmin(): Promise<{ success: boolean; message: string }> {
    const { data } = await api.post('/admin/revoke')
    return data
  },

  /**
   * Get admin info (admin-only endpoint)
   */
  async getAdminInfo(): Promise<{
    edition: string
    admin_email: string
    features: Record<string, boolean>
    license?: {
      organization: string
      features: string[]
    }
    saas?: {
      marketplace_curation: boolean
      license_generation: boolean
    }
  }> {
    const { data } = await api.get('/admin/info')
    return data
  },
}

/**
 * Enterprise Licenses API
 *
 * Manages Enterprise license retrieval and checkout.
 * Enterprise licenses are for self-hosted deployments.
 * Note: These endpoints are only available in Cloud SaaS edition.
 */
export const licensesApi = {
  /**
   * Get all licenses for the current user
   */
  async getMyLicenses(): Promise<LicensesListResponse> {
    const { data } = await api.get('/licenses/me')
    return data
  },

  /**
   * Get a specific license by ID
   */
  async getLicense(licenseId: string): Promise<License> {
    const { data } = await api.get(`/licenses/${licenseId}`)
    return data
  },

  /**
   * Check Public Sector eligibility for free Enterprise license
   */
  async checkEligibility(): Promise<PublicSectorEligibility> {
    const { data } = await api.get('/enterprise/eligibility')
    return data
  },

  /**
   * Create Enterprise checkout session
   * For Public Sector users, a 100% discount is automatically applied server-side
   */
  async createCheckout(
    request: EnterpriseCheckoutRequest
  ): Promise<EnterpriseCheckoutResponse> {
    const { data } = await api.post('/enterprise/checkout', request)
    return data
  },
}

// Export the api instance for use in other components
export { api as apiClient }
