/**
 * Documentation Content
 *
 * All documentation content stored as markdown strings.
 * Organized by language > section > slug for easy lookup.
 * Falls back to English if translation not available.
 */

// Import English content (default/fallback)
import { gettingStartedContent as enGettingStarted } from './en/getting-started'
import { conceptsContent as enConcepts } from './en/concepts'
import { guidesContent as enGuides } from './en/guides'
import { apiContent as enApi } from './en/api'
import { selfHostingContent as enSelfHosting } from './en/self-hosting'
import { integrationsContent as enIntegrations } from './en/integrations'

// Import French content
import { gettingStartedContent as frGettingStarted } from './fr/getting-started'
import { conceptsContent as frConcepts } from './fr/concepts'
import { guidesContent as frGuides } from './fr/guides'
import { apiContent as frApi } from './fr/api'
import { selfHostingContent as frSelfHosting } from './fr/self-hosting'
import { integrationsContent as frIntegrations } from './fr/integrations'

type DocsContentType = Record<string, Record<string, string>>

// English content (fallback)
const enContent: DocsContentType = {
  'getting-started': enGettingStarted,
  'concepts': enConcepts,
  'guides': enGuides,
  'api': enApi,
  'self-hosting': enSelfHosting,
  'integrations': enIntegrations,
}

// French content
const frContent: DocsContentType = {
  'getting-started': frGettingStarted,
  'concepts': frConcepts,
  'guides': frGuides,
  'api': frApi,
  'self-hosting': frSelfHosting,
  'integrations': frIntegrations,
}

// All content organized by language
export const docsContentByLang: Record<string, DocsContentType> = {
  en: enContent,
  fr: frContent,
}

/**
 * Get documentation content for a specific language with fallback to English
 */
export function getDocsContent(language: string): DocsContentType {
  // Try to get content for the requested language
  const content = docsContentByLang[language]
  if (content) {
    return content
  }
  // Fallback to English
  return enContent
}

/**
 * Get a specific doc page content with language fallback
 */
export function getDocPageContent(
  language: string,
  section: string,
  slug: string
): string | null {
  // Try requested language first
  const langContent = docsContentByLang[language]
  if (langContent?.[section]?.[slug]) {
    return langContent[section][slug]
  }
  // Fallback to English
  return enContent[section]?.[slug] || null
}

// Legacy export for backward compatibility
export const docsContent = enContent
