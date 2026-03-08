/**
 * DocsLayout - Documentation page layout with sidebar navigation
 *
 * Features:
 * - Collapsible sidebar with section groups
 * - Responsive design (mobile drawer)
 * - Active page highlighting
 * - Keyboard navigation support
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Outlet, useParams } from 'react-router-dom'
import {
  Bars3Icon,
  XMarkIcon,
  ChevronRightIcon,
  MagnifyingGlassIcon,
} from '@heroicons/react/24/outline'
import { BigMCPLogoWithText } from '@/components/brand/BigMCPLogo'
import { cn } from '@/utils/cn'
import { docsNavigation, getDefaultDoc } from './navigation'

export function DocsLayout() {
  const { t } = useTranslation('docs')
  const { section, slug } = useParams()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(docsNavigation.map((s) => s.id))
  )

  // Determine current page
  const currentSection = section || getDefaultDoc().section
  const currentSlug = slug || getDefaultDoc().slug

  const toggleSection = (sectionId: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev)
      if (next.has(sectionId)) {
        next.delete(sectionId)
      } else {
        next.add(sectionId)
      }
      return next
    })
  }

  const isActive = (sectionId: string, itemSlug: string) => {
    return currentSection === sectionId && currentSlug === itemSlug
  }

  // Map section IDs to translation keys
  const getSectionTitle = (sectionId: string): string => {
    const sectionKeyMap: Record<string, string> = {
      'getting-started': 'sections.gettingStarted.title',
      'guides': 'sections.guides.title',
      'integrations': 'sections.integrations.title',
      'concepts': 'sections.concepts.title',
      'api': 'sections.api.title',
      'self-hosting': 'sections.selfHosting.title',
    }
    return t(sectionKeyMap[sectionId] || sectionId)
  }

  // Map item slugs to translation keys
  const getItemTitle = (sectionId: string, itemSlug: string): string => {
    const sectionKeyMap: Record<string, string> = {
      'getting-started': 'gettingStarted',
      'guides': 'guides',
      'integrations': 'integrations',
      'concepts': 'concepts',
      'api': 'api',
      'self-hosting': 'selfHosting',
    }
    const itemKeyMap: Record<string, string> = {
      'introduction': 'introduction',
      'quickstart': 'quickstart',
      'first-server': 'firstServer',
      'marketplace': 'marketplace',
      'credentials': 'credentials',
      'tool-groups': 'toolGroups',
      'api-keys': 'apiKeys',
      'compositions': 'compositions',
      'team-services': 'teamServices',
      'claude-desktop': 'claudeDesktop',
      'mistral-lechat': 'mistralLechat',
      'n8n': 'n8n',
      'custom-clients': 'customClients',
      'mcp-overview': 'mcpOverview',
      'servers': 'servers',
      'tools': 'tools',
      'security': 'security',
      'api-overview': 'apiOverview',
      'api-marketplace': 'apiMarketplace',
      'api-credentials': 'apiCredentials',
      'api-mcp': 'apiMcp',
      'api-tools': 'apiTools',
      'self-host-overview': 'selfHostOverview',
      'docker-setup': 'dockerSetup',
      'configuration': 'configuration',
      'llm-providers': 'llmProviders',
      'custom-servers': 'customServers',
    }
    const sectionKey = sectionKeyMap[sectionId] || sectionId
    const itemKey = itemKeyMap[itemSlug] || itemSlug
    return t(`sections.${sectionKey}.${itemKey}.title`)
  }

  const Sidebar = () => (
    <nav className="flex-1 overflow-y-auto py-6 px-4" aria-label="Documentation">
      {/* Search - placeholder for now */}
      <div className="mb-6">
        <div className="relative">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder={t('layout.searchPlaceholder')}
            className="w-full pl-10 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange focus:border-transparent"
          />
        </div>
      </div>

      {/* Navigation sections */}
      <div className="space-y-4">
        {docsNavigation.map((navSection) => {
          const Icon = navSection.icon
          const isExpanded = expandedSections.has(navSection.id)

          return (
            <div key={navSection.id}>
              {/* Section header */}
              <button
                onClick={() => toggleSection(navSection.id)}
                className="flex items-center gap-2 w-full px-2 py-1.5 text-left text-sm font-semibold text-gray-900 hover:bg-gray-50 rounded-lg transition-colors"
              >
                <Icon className="w-4 h-4 text-gray-500" />
                <span className="flex-1">{getSectionTitle(navSection.id)}</span>
                <ChevronRightIcon
                  className={cn(
                    'w-4 h-4 text-gray-400 transition-transform',
                    isExpanded && 'rotate-90'
                  )}
                />
              </button>

              {/* Section items */}
              {isExpanded && (
                <ul className="mt-1 ml-6 space-y-0.5">
                  {navSection.items.map((item) => {
                    const active = isActive(navSection.id, item.slug)
                    return (
                      <li key={item.slug}>
                        <Link
                          to={`/docs/${navSection.id}/${item.slug}`}
                          onClick={() => setSidebarOpen(false)}
                          className={cn(
                            'block px-3 py-1.5 text-sm rounded-lg transition-colors',
                            active
                              ? 'bg-orange-50 text-orange font-medium border-l-2 border-orange -ml-0.5 pl-3.5'
                              : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                          )}
                        >
                          {getItemTitle(navSection.id, item.slug)}
                        </Link>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          )
        })}
      </div>

      {/* Version info */}
      <div className="mt-8 pt-6 border-t border-gray-200">
        <p className="text-xs text-gray-500 px-2">{t('layout.version')}</p>
        <div className="mt-2 flex gap-2 px-2">
          <a
            href="https://github.com/bigmcp/bigmcp"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-gray-500 hover:text-gray-700"
          >
            {t('layout.github')}
          </a>
          <span className="text-gray-300">|</span>
          <a
            href="/api/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-gray-500 hover:text-gray-700"
          >
            {t('layout.apiDocs')}
          </a>
        </div>
      </div>
    </nav>
  )

  return (
    <div className="min-h-screen bg-white">
      {/* Mobile header */}
      <header className="lg:hidden fixed top-0 left-0 right-0 z-40 bg-white border-b border-gray-200">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center">
            <BigMCPLogoWithText size="sm" textSize="md" />
          </Link>
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 text-gray-600 hover:bg-gray-100 rounded-lg"
          >
            <Bars3Icon className="w-6 h-6" />
          </button>
        </div>
      </header>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="lg:hidden fixed inset-0 z-50">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setSidebarOpen(false)}
          />
          <div className="absolute left-0 top-0 bottom-0 w-72 bg-white shadow-xl">
            <div className="flex items-center justify-between px-4 h-16 border-b border-gray-200">
              <Link to="/" className="flex items-center">
                <BigMCPLogoWithText size="sm" textSize="md" />
              </Link>
              <button
                onClick={() => setSidebarOpen(false)}
                className="p-2 text-gray-600 hover:bg-gray-100 rounded-lg"
              >
                <XMarkIcon className="w-6 h-6" />
              </button>
            </div>
            <Sidebar />
          </div>
        </div>
      )}

      {/* Desktop sidebar */}
      <aside className="hidden lg:flex lg:flex-col lg:fixed lg:inset-y-0 lg:left-0 lg:w-72 lg:border-r lg:border-gray-200 lg:bg-gray-50">
        {/* Logo */}
        <div className="flex items-center px-6 h-16 border-b border-gray-200 bg-white">
          <Link to="/" className="flex items-center">
            <BigMCPLogoWithText size="sm" textSize="md" />
          </Link>
          <span className="ml-3 px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-600 rounded">
            {t('layout.badge')}
          </span>
        </div>
        <Sidebar />
      </aside>

      {/* Main content */}
      <main className="lg:pl-72 pt-16 lg:pt-0">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 lg:py-12">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
