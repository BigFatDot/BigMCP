/**
 * DocPage - Renders individual documentation pages
 *
 * Features:
 * - Markdown rendering with syntax highlighting
 * - Table of contents generation
 * - Copy button on code blocks
 * - SEO metadata
 * - Breadcrumbs
 */

import { useMemo, useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSlug from 'rehype-slug'
import rehypeAutolinkHeadings from 'rehype-autolink-headings'
import {
  ChevronRightIcon,
  ClipboardIcon,
  CheckIcon,
  ArrowLeftIcon,
  ArrowRightIcon,
} from '@heroicons/react/24/outline'
import { cn } from '@/utils/cn'
import { usePageMeta } from '@/hooks/usePageMeta'
import { docsNavigation, findDocBySlug, getAllDocItems } from './navigation'
import { getDocPageContent } from './content'
import { MermaidDiagram } from '@/components/docs/MermaidDiagram'

// Code block with copy button
function CodeBlock({ children, className }: { children: string; className?: string }) {
  const [copied, setCopied] = useState(false)
  const language = className?.replace('language-', '') || 'text'

  const handleCopy = async () => {
    await navigator.clipboard.writeText(children)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="relative group">
      <div className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={handleCopy}
          className="p-1.5 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 hover:text-white transition-colors"
          title="Copy code"
        >
          {copied ? (
            <CheckIcon className="w-4 h-4 text-green-400" />
          ) : (
            <ClipboardIcon className="w-4 h-4" />
          )}
        </button>
      </div>
      <div className="text-xs text-gray-400 absolute right-2 bottom-2">
        {language}
      </div>
      <pre className={cn('overflow-x-auto p-4 rounded-lg bg-gray-900 text-gray-100', className)}>
        <code>{children}</code>
      </pre>
    </div>
  )
}

// Custom markdown components
const markdownComponents = {
  h1: ({ children, id }: any) => (
    <h1 id={id} className="text-3xl font-bold text-gray-900 mb-4 scroll-mt-20">
      {children}
    </h1>
  ),
  h2: ({ children, id }: any) => (
    <h2 id={id} className="text-2xl font-bold text-gray-900 mt-10 mb-4 scroll-mt-20 group">
      <a href={`#${id}`} className="hover:text-orange">
        {children}
      </a>
    </h2>
  ),
  h3: ({ children, id }: any) => (
    <h3 id={id} className="text-xl font-semibold text-gray-900 mt-8 mb-3 scroll-mt-20">
      {children}
    </h3>
  ),
  p: ({ children }: any) => (
    <p className="text-gray-700 leading-relaxed mb-4">{children}</p>
  ),
  ul: ({ children }: any) => (
    <ul className="list-disc list-inside space-y-2 mb-4 text-gray-700">{children}</ul>
  ),
  ol: ({ children }: any) => (
    <ol className="list-decimal list-inside space-y-2 mb-4 text-gray-700">{children}</ol>
  ),
  li: ({ children }: any) => <li className="ml-2">{children}</li>,
  a: ({ href, children }: any) => (
    <a
      href={href}
      className="text-orange hover:text-orange-dark underline"
      target={href?.startsWith('http') ? '_blank' : undefined}
      rel={href?.startsWith('http') ? 'noopener noreferrer' : undefined}
    >
      {children}
    </a>
  ),
  code: ({ children, className }: any) => {
    const content = String(children).replace(/\n$/, '')

    // Inline code: no className (no language) and single line without newlines
    const isInline = !className && !content.includes('\n')

    if (isInline) {
      return (
        <code className="px-1.5 py-0.5 bg-gray-100 text-orange rounded text-sm font-mono">
          {children}
        </code>
      )
    }

    // Check if this is a mermaid diagram
    const language = className?.replace('language-', '') || ''

    if (language === 'mermaid') {
      return <MermaidDiagram chart={content} />
    }

    return <CodeBlock className={className}>{content}</CodeBlock>
  },
  pre: ({ children }: any) => <div className="mb-4">{children}</div>,
  blockquote: ({ children }: any) => (
    <blockquote className="border-l-4 border-orange pl-4 py-2 mb-4 bg-orange-50 rounded-r-lg italic text-gray-700">
      {children}
    </blockquote>
  ),
  table: ({ children }: any) => (
    <div className="overflow-x-auto mb-4">
      <table className="min-w-full divide-y divide-gray-200 border border-gray-200 rounded-lg">
        {children}
      </table>
    </div>
  ),
  th: ({ children }: any) => (
    <th className="px-4 py-2 bg-gray-50 text-left text-sm font-semibold text-gray-900">
      {children}
    </th>
  ),
  td: ({ children }: any) => (
    <td className="px-4 py-2 text-sm text-gray-700 border-t border-gray-200">{children}</td>
  ),
  hr: () => <hr className="my-8 border-gray-200" />,
}

export function DocPage() {
  const { t } = useTranslation('docs')
  const { section, slug } = useParams()

  // Map section IDs to translation keys
  const getSectionTitle = useCallback((sectionId: string): string => {
    const sectionKeyMap: Record<string, string> = {
      'getting-started': 'sections.gettingStarted.title',
      'guides': 'sections.guides.title',
      'integrations': 'sections.integrations.title',
      'concepts': 'sections.concepts.title',
      'api': 'sections.api.title',
      'self-hosting': 'sections.selfHosting.title',
    }
    return t(sectionKeyMap[sectionId] || sectionId)
  }, [t])

  // Map item slugs to translation keys
  const getItemTitle = useCallback((sectionId: string, itemSlug: string): string => {
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
  }, [t])

  // Get item description
  const getItemDescription = useCallback((sectionId: string, itemSlug: string): string => {
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
    return t(`sections.${sectionKey}.${itemKey}.description`)
  }, [t])

  // Get current doc info
  const docInfo = useMemo(() => {
    if (!section || !slug) return null
    return findDocBySlug(section, slug)
  }, [section, slug])

  // Get current language from i18next
  const { i18n } = useTranslation()
  const currentLang = i18n.language?.split('-')[0] || 'en' // Handle 'fr-FR' -> 'fr'

  // Get content based on current language
  const content = useMemo(() => {
    if (!section || !slug) return null
    return getDocPageContent(currentLang, section, slug)
  }, [section, slug, currentLang])

  // Get navigation items for prev/next
  const allDocs = useMemo(() => getAllDocItems(), [])
  const currentIndex = useMemo(() => {
    return allDocs.findIndex((d) => d.section === section && d.slug === slug)
  }, [allDocs, section, slug])

  const prevDoc = currentIndex > 0 ? allDocs[currentIndex - 1] : null
  const nextDoc = currentIndex < allDocs.length - 1 ? allDocs[currentIndex + 1] : null

  // Get section info
  const sectionInfo = useMemo(() => {
    return docsNavigation.find((s) => s.id === section)
  }, [section])

  // Update document title and meta tags
  const translatedTitle = section && slug ? getItemTitle(section, slug) : docInfo?.title
  const translatedDescription = section && slug ? getItemDescription(section, slug) : docInfo?.description
  usePageMeta({
    title: translatedTitle ? `${translatedTitle} - Docs` : undefined,
    description: translatedDescription || undefined,
  })

  // Scroll to top when navigating to a new page
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [section, slug])

  if (!content) {
    return (
      <div className="text-center py-12">
        <h1 className="text-2xl font-bold text-gray-900 mb-4">{t('page.notFoundTitle')}</h1>
        <p className="text-gray-600 mb-6">{t('page.notFoundDescription')}</p>
        <Link to="/docs" className="text-orange hover:text-orange-dark underline">
          {t('page.goToHome')}
        </Link>
      </div>
    )
  }

  return (
    <article className="prose prose-gray max-w-none">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-2 text-sm text-gray-500 mb-6 not-prose">
        <Link to="/docs" className="hover:text-gray-700">
          {t('page.breadcrumbDocs')}
        </Link>
        <ChevronRightIcon className="w-4 h-4" />
        <Link to={`/docs/${section}`} className="hover:text-gray-700">
          {section && getSectionTitle(section)}
        </Link>
        <ChevronRightIcon className="w-4 h-4" />
        <span className="text-gray-900 font-medium">{section && slug && getItemTitle(section, slug)}</span>
      </nav>

      {/* Title & Description */}
      <header className="mb-8 not-prose">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">{section && slug && getItemTitle(section, slug)}</h1>
        {section && slug && (
          <p className="text-lg text-gray-600">{getItemDescription(section, slug)}</p>
        )}
      </header>

      {/* Content */}
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSlug, [rehypeAutolinkHeadings, { behavior: 'wrap' }]]}
        components={markdownComponents}
      >
        {content}
      </ReactMarkdown>

      {/* Prev/Next navigation */}
      <nav className="flex items-center justify-between mt-12 pt-6 border-t border-gray-200 not-prose">
        {prevDoc ? (
          <Link
            to={prevDoc.path}
            className="flex items-center gap-2 text-gray-600 hover:text-orange transition-colors"
          >
            <ArrowLeftIcon className="w-4 h-4" />
            <div className="text-left">
              <p className="text-xs text-gray-400">{t('page.previous')}</p>
              <p className="font-medium">{getItemTitle(prevDoc.section, prevDoc.slug)}</p>
            </div>
          </Link>
        ) : (
          <div />
        )}
        {nextDoc ? (
          <Link
            to={nextDoc.path}
            className="flex items-center gap-2 text-gray-600 hover:text-orange transition-colors text-right"
          >
            <div>
              <p className="text-xs text-gray-400">{t('page.next')}</p>
              <p className="font-medium">{getItemTitle(nextDoc.section, nextDoc.slug)}</p>
            </div>
            <ArrowRightIcon className="w-4 h-4" />
          </Link>
        ) : (
          <div />
        )}
      </nav>
    </article>
  )
}
