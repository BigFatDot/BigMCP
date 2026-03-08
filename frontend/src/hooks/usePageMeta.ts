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

export function usePageMeta({ title, description }: PageMeta) {
  useEffect(() => {
    if (title) {
      document.title = `${title} | BigMCP`
      setMetaTag('og:title', `${title} | BigMCP`)
      setMetaTag('twitter:title', `${title} | BigMCP`)
    }

    if (description) {
      setMetaTag('description', description)
      setMetaTag('og:description', description)
      setMetaTag('twitter:description', description)
    }

    // Cleanup: restore defaults on unmount
    return () => {
      document.title = 'BigMCP - Unified MCP Server Gateway'
      setMetaTag('description', 'Connect, manage, and orchestrate all your MCP servers in one place.')
      setMetaTag('og:title', 'BigMCP - Unified MCP Server Gateway')
      setMetaTag('og:description', 'Connect, manage, and orchestrate all your MCP servers in one place.')
    }
  }, [title, description])
}
