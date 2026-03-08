/**
 * Documentation Navigation Structure
 *
 * Defines the sidebar hierarchy and page metadata.
 * Used for navigation, breadcrumbs, and SEO.
 */

import {
  BookOpenIcon,
  RocketLaunchIcon,
  CubeIcon,
  CommandLineIcon,
  ServerStackIcon,
  CodeBracketIcon,
} from '@heroicons/react/24/outline'

export interface DocItem {
  slug: string
  title: string
  description?: string
  keywords?: string[]
}

export interface DocSection {
  id: string
  title: string
  icon: React.ComponentType<{ className?: string }>
  items: DocItem[]
}

export const docsNavigation: DocSection[] = [
  // ============================================================================
  // 1. GETTING STARTED - First contact, learn the basics
  // ============================================================================
  {
    id: 'getting-started',
    title: 'Getting Started',
    icon: RocketLaunchIcon,
    items: [
      {
        slug: 'introduction',
        title: 'Introduction',
        description: 'What is BigMCP and why use it',
        keywords: ['mcp', 'introduction', 'overview', 'what is'],
      },
      {
        slug: 'quickstart',
        title: 'Quick Start',
        description: 'Get up and running in 5 minutes',
        keywords: ['quickstart', 'setup', 'install', 'first steps'],
      },
      {
        slug: 'first-server',
        title: 'Connect Your First Server',
        description: 'Add an MCP server to your account',
        keywords: ['connect', 'server', 'add', 'configure'],
      },
    ],
  },
  // ============================================================================
  // 2. GUIDES - Practice immediately after getting started
  // ============================================================================
  {
    id: 'guides',
    title: 'Guides',
    icon: CommandLineIcon,
    items: [
      {
        slug: 'marketplace',
        title: 'Discover Servers',
        description: 'Browse and install MCP servers from the marketplace',
        keywords: ['marketplace', 'discover', 'install', 'browse', 'servers'],
      },
      {
        slug: 'credentials',
        title: 'Manage Services',
        description: 'Control your connected servers and their tools',
        keywords: ['services', 'servers', 'tools', 'visibility', 'manage'],
      },
      {
        slug: 'tool-groups',
        title: 'Organize with Toolboxes',
        description: 'Bundle tools for different use cases and access control',
        keywords: ['toolboxes', 'organize', 'bundle', 'access control', 'context'],
      },
      {
        slug: 'api-keys',
        title: 'Create API Keys',
        description: 'Generate keys for external integrations and automation',
        keywords: ['api', 'keys', 'integration', 'external', 'automation'],
      },
      {
        slug: 'compositions',
        title: 'Build Compositions',
        description: 'Chain tools together for complex workflows',
        keywords: ['compositions', 'workflows', 'automation', 'orchestration', 'chain'],
      },
      {
        slug: 'team-services',
        title: 'Team Services',
        description: 'Manage shared services for your team (Team plan)',
        keywords: ['team', 'services', 'shared', 'organization', 'admin'],
      },
    ],
  },
  // ============================================================================
  // 3. INTEGRATIONS - Connect with your existing tools
  // ============================================================================
  {
    id: 'integrations',
    title: 'Integrations',
    icon: CubeIcon,
    items: [
      {
        slug: 'claude-desktop',
        title: 'Claude Desktop',
        description: 'Connect BigMCP to Claude Desktop via OAuth',
        keywords: ['claude', 'desktop', 'anthropic', 'connect', 'oauth'],
      },
      {
        slug: 'mistral-lechat',
        title: 'Mistral Le Chat',
        description: 'Use BigMCP tools in Mistral Le Chat',
        keywords: ['mistral', 'le chat', 'connect', 'oauth'],
      },
      {
        slug: 'n8n',
        title: 'n8n Automation',
        description: 'Use BigMCP tools in n8n workflows',
        keywords: ['n8n', 'automation', 'workflow', 'node'],
      },
      {
        slug: 'custom-clients',
        title: 'Custom Clients',
        description: 'Build your own MCP client with the SDK',
        keywords: ['client', 'sdk', 'build', 'custom', 'developer'],
      },
    ],
  },
  // ============================================================================
  // 4. CORE CONCEPTS - Deep understanding after practical experience
  // ============================================================================
  {
    id: 'concepts',
    title: 'Core Concepts',
    icon: BookOpenIcon,
    items: [
      {
        slug: 'mcp-overview',
        title: 'MCP Protocol',
        description: 'Understanding the Model Context Protocol standard',
        keywords: ['mcp', 'protocol', 'model context', 'standard', 'specification'],
      },
      {
        slug: 'servers',
        title: 'MCP Servers',
        description: 'How servers expose tools, resources, and prompts',
        keywords: ['servers', 'tools', 'resources', 'prompts', 'capabilities'],
      },
      {
        slug: 'tools',
        title: 'Tools & Execution',
        description: 'How tools work and are executed by AI agents',
        keywords: ['tools', 'functions', 'actions', 'execution', 'agents'],
      },
      {
        slug: 'security',
        title: 'Security Model',
        description: 'Encryption, authentication, and access control',
        keywords: ['security', 'encryption', 'auth', 'access control', 'aes'],
      },
    ],
  },
  // ============================================================================
  // 5. API REFERENCE - For developers building integrations
  // ============================================================================
  {
    id: 'api',
    title: 'API Reference',
    icon: CodeBracketIcon,
    items: [
      {
        slug: 'api-overview',
        title: 'API Overview',
        description: 'REST API introduction and authentication',
        keywords: ['api', 'rest', 'authentication', 'endpoints'],
      },
      {
        slug: 'api-marketplace',
        title: 'Marketplace API',
        description: 'Endpoints for server discovery',
        keywords: ['marketplace', 'api', 'servers', 'search'],
      },
      {
        slug: 'api-credentials',
        title: 'Credentials API',
        description: 'Manage user credentials programmatically',
        keywords: ['credentials', 'api', 'manage', 'create'],
      },
      {
        slug: 'api-mcp',
        title: 'MCP Gateway API',
        description: 'Connect to tools via the gateway',
        keywords: ['mcp', 'gateway', 'sse', 'tools', 'execute'],
      },
      {
        slug: 'api-tools',
        title: 'Tools & Execution API',
        description: 'Execute tools, bindings, and compositions',
        keywords: ['tools', 'execute', 'bindings', 'compositions', 'orchestrate'],
      },
    ],
  },
  // ============================================================================
  // 6. SELF-HOSTING - For admins deploying on-premise
  // ============================================================================
  {
    id: 'self-hosting',
    title: 'Self-Hosting',
    icon: ServerStackIcon,
    items: [
      {
        slug: 'self-host-overview',
        title: 'Overview',
        description: 'Self-hosting options and requirements',
        keywords: ['self-host', 'docker', 'requirements', 'install'],
      },
      {
        slug: 'docker-setup',
        title: 'Docker Setup',
        description: 'Deploy with Docker Compose',
        keywords: ['docker', 'compose', 'deploy', 'container'],
      },
      {
        slug: 'configuration',
        title: 'Configuration',
        description: 'Environment variables and settings',
        keywords: ['config', 'environment', 'settings', 'variables'],
      },
      {
        slug: 'llm-providers',
        title: 'LLM Providers',
        description: 'Configure your AI backend',
        keywords: ['llm', 'openai', 'anthropic', 'local', 'ollama'],
      },
      {
        slug: 'custom-servers',
        title: 'Custom MCP Servers',
        description: 'Add your own MCP servers to Enterprise instances',
        keywords: ['custom', 'servers', 'enterprise', 'install', 'private', 'internal'],
      },
      {
        slug: 'scaling',
        title: 'Scaling & Performance',
        description: 'Optimize performance and scale your BigMCP instance',
        keywords: ['scaling', 'performance', 'memory', 'tuning', 'capacity', 'enterprise', 'production'],
      },
      {
        slug: 'monitoring',
        title: 'Monitoring',
        description: 'Set up Prometheus metrics and observability',
        keywords: ['monitoring', 'prometheus', 'metrics', 'observability', 'grafana', 'alerting'],
      },
      {
        slug: 'backup',
        title: 'Backup & Restore',
        description: 'Database backup and disaster recovery procedures',
        keywords: ['backup', 'restore', 'disaster recovery', 'postgresql', 'database', 'security'],
      },
    ],
  },
]

/**
 * Get a flat list of all doc items with their full paths
 */
export function getAllDocItems(): Array<DocItem & { section: string; path: string }> {
  return docsNavigation.flatMap((section) =>
    section.items.map((item) => ({
      ...item,
      section: section.id,
      path: `/docs/${section.id}/${item.slug}`,
    }))
  )
}

/**
 * Find a doc item by its slug
 */
export function findDocBySlug(sectionId: string, slug: string): DocItem | undefined {
  const section = docsNavigation.find((s) => s.id === sectionId)
  return section?.items.find((item) => item.slug === slug)
}

/**
 * Get the default doc (first item in first section)
 */
export function getDefaultDoc(): { section: string; slug: string } {
  const firstSection = docsNavigation[0]
  const firstItem = firstSection.items[0]
  return { section: firstSection.id, slug: firstItem.slug }
}
