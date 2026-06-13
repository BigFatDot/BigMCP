/**
 * usePageMeta - Sets document title and meta tags for SEO
 *
 * Lightweight hook using DOM API directly (no dependency).
 * Updates title, description, and Open Graph tags per page.
 */

import { useEffect } from 'react'

interface PageMeta {
  title?: string
  description?: string
}

function setMetaTag(property: string, content: string) {
  // Try property attribute first (og:*), then name attribute (description)
  let element = document.querySelector(`meta[property="${property}"]`)
    || document.querySelector(`meta[name="${property}"]`)

  if (element) {
    element.setAttribute('content', content)
  } else {
    element = document.createElement('meta')
    if (property.startsWith('og:') || property.startsWith('twitter:')) {
      element.setAttribute('property', property)
    } else {
      element.setAttribute('name', property)
    }
    element.setAttribute('content', content)
    document.head.appendChild(element)
  }
}

const DEFAULT_TITLE = 'BigMCP — One endpoint for all your MCP servers'
const DEFAULT_DESCRIPTION =
  'Self-host an autonomous MCP gateway. Bring your own LLM, run fully offline, keep every byte on your infrastructure. AGPLv3, no vendor lock-in.'

/**
 * Returns the final title string. If the title already contains "BigMCP",
 * we use it as-is to avoid "BigMCP — … | BigMCP" duplication. Otherwise
 * we append a discrete " | BigMCP" suffix for brand consistency.
 */
function formatTitle(title: string): string {
  return /bigmcp/i.test(title) ? title : `${title} | BigMCP`
}

export function usePageMeta({ title, description }: PageMeta) {
  useEffect(() => {
    if (title) {
      const formatted = formatTitle(title)
      document.title = formatted
      setMetaTag('og:title', formatted)
      setMetaTag('twitter:title', formatted)
    }

    if (description) {
      setMetaTag('description', description)
      setMetaTag('og:description', description)
      setMetaTag('twitter:description', description)
    }

    // Cleanup: restore defaults on unmount
    return () => {
      document.title = DEFAULT_TITLE
      setMetaTag('description', DEFAULT_DESCRIPTION)
      setMetaTag('og:title', DEFAULT_TITLE)
      setMetaTag('og:description', DEFAULT_DESCRIPTION)
    }
  }, [title, description])
}
