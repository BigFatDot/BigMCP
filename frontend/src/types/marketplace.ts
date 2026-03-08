/**
 * Marketplace and MCP Server Type Definitions
 */

export type DeploymentType = 'cloud' | 'self_hosted_community' | 'self_hosted_enterprise'

/**
 * Tool preview from static analysis
 */
export interface MCPToolPreview {
  name: string
  description: string
  is_read_only?: boolean
  is_destructive?: boolean
  is_idempotent?: boolean
}

export interface MCPServer {
  id: string
  name: string
  description: string
  category: string[]
  author: string
  repository_url?: string
  documentation_url?: string
  homepage_url?: string
  license?: string
  version?: string
  icon_url?: string
  is_official: boolean
  is_verified: boolean
  popularity_score: number

  // Installation
  install_type: 'npm' | 'pip' | 'docker' | 'github' | 'local' | 'remote'
  install_command?: string
  install_package?: string  // Package name for npm/pip
  command?: string          // Executable command (e.g., "python", "npx")
  args?: string[]           // Command arguments

  // Capabilities & Tools
  capabilities?: {
    tools?: number
    resources?: number
    prompts?: number
  }
  tools?: MCPToolPreview[]  // Full tool details from static analysis
  tools_preview?: string[]  // Just names for quick display

  // Credentials
  requires_credentials: boolean
  credentials?: CredentialField[]  // Changed from credential_fields to match backend
  has_optional_credentials?: boolean  // True if server has optional config fields

  // SaaS compatibility
  requires_local_access?: boolean  // True if server needs local filesystem/docker access

  // Metadata
  tags: string[]
  created_at: string
  updated_at: string
}

export interface CredentialField {
  name: string
  display_name?: string  // Human-readable name (e.g., "OpenAI API Key")
  type: 'secret' | 'string' | 'url' | 'number' | 'boolean'
  required: boolean
  description: string
  placeholder?: string
  default_value?: string
  validation_regex?: string
  documentation_url?: string
  config_type?: 'remote' | 'local'  // remote = API keys, local = localhost configs
  example?: string  // Example value for user reference
}

export interface UserCredential {
  id: string
  user_id: string
  server_id: string
  organization_id: string
  name?: string
  description?: string
  is_active: boolean
  is_validated: boolean
  last_used_at?: string
  validated_at?: string
  created_at: string
  updated_at: string
  // Server status info (from mcp_servers table)
  server_status?: 'stopped' | 'starting' | 'running' | 'error' | 'disabled'
  server_enabled?: boolean
  // Visibility for OAuth clients (web dashboard) - hidden servers still accessible via API keys
  is_visible_to_oauth_clients?: boolean
}

export interface OrganizationCredential {
  id: string
  organization_id: string
  server_id: string
  name: string
  description?: string
  is_active: boolean
  visible_to_users: boolean
  usage_count: number
  last_used_at?: string
  created_by?: string
  updated_by?: string
  created_at: string
  updated_at: string
}

export interface CredentialSetupToken {
  id: string
  token: string
  setup_url: string
  composition_id?: string
  required_credentials: {
    servers: Array<{
      server_id: string
      server_name: string
      credentials: CredentialField[]
    }>
  }
  is_used: boolean
  is_valid: boolean
  expires_at: string
  created_at: string
  completed_at?: string
}

export interface MarketplaceAPIKey {
  id: string
  user_id: string
  key_name: string
  key_prefix: string
  deployment_type: DeploymentType
  is_active: boolean
  rate_limit_per_minute: number
  request_count: number
  last_used_at?: string
  created_at: string
  updated_at: string
}

export interface MarketplaceFilters {
  search?: string
  category?: string
  tags?: string[]
  requires_credentials?: boolean
  is_official?: boolean
  is_verified?: boolean
  sort_by?: 'popularity' | 'name' | 'created_at' | 'updated_at'
  sort_order?: 'asc' | 'desc'
  limit?: number
  offset?: number
}

export interface ServerConnectionStatus {
  server_id: string
  is_connected: boolean
  has_credentials: boolean
  last_connection_at?: string
  connection_error?: string
}

/**
 * MCP Server instance (user's installed server)
 */
export interface MCPServerInstance {
  id: string
  organization_id: string
  server_id: string
  name: string
  description?: string
  install_type: 'pip' | 'npx' | 'docker' | 'binary'
  install_package: string
  version?: string
  command: string
  args: string[]
  env: Record<string, string>
  status: 'stopped' | 'starting' | 'running' | 'error' | 'stopping'
  enabled: boolean
  is_visible_to_oauth_clients: boolean
  last_connected_at?: string
  error_message?: string
  total_requests: number
  failed_requests: number
  created_at: string
  updated_at: string
  // Tools discovered from server
  tools?: MCPTool[]
}

/**
 * Tool discovered from MCP server
 */
export interface MCPTool {
  id: string
  server_id: string
  tool_name: string
  display_name?: string
  description?: string
  parameters_schema: Record<string, unknown>
  returns_schema?: Record<string, unknown>
  tags?: string[]
  category?: string
}

/**
 * Tool Group - Collection of tools for specialized AI agents
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
  // Enriched fields from backend
  tool_name?: string
  tool_description?: string
  server_id?: string
  server_name?: string
}

export interface CreateToolGroupRequest {
  name: string
  description?: string
  icon?: string
  color?: string
  visibility?: 'private' | 'organization' | 'public'
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
}

/**
 * Server visibility state (3-state model)
 */
export type ServerVisibilityState = 'visible' | 'hidden' | 'disabled'
