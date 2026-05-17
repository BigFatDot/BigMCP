/**
 * Branding Context
 *
 * Hydrates from GET /api/v1/instance/branding at boot (no auth) so
 * every page — including the login / signup screens — sees the
 * instance's brand. Falls back to BigMCP defaults if the endpoint
 * fails or is unreachable.
 *
 * Side effects on hydration:
 * - sets <title> to "<brand>" (kept in sync if branding updates)
 * - sets favicon if branding.favicon_url provided
 * - sets a CSS variable --brand-primary on :root for theming hooks
 */

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { apiClient } from '@/services/api'

export interface Branding {
  instance_name: string
  instance_tagline: string
  logo_url: string | null
  favicon_url: string | null
  primary_color: string
  support_email: string | null
  instance_url: string | null
  legal_entity: string | null
  setup_completed: boolean
  customized: boolean
}

const DEFAULT_BRANDING: Branding = {
  instance_name: 'BigMCP',
  instance_tagline: 'Unified MCP Gateway for AI Agents',
  logo_url: null,
  favicon_url: null,
  primary_color: '#D97757',
  support_email: null,
  instance_url: null,
  legal_entity: null,
  setup_completed: true,
  customized: false,
}

interface BrandingContextValue {
  branding: Branding
  isLoading: boolean
  refresh: () => Promise<void>
}

const BrandingContext = createContext<BrandingContextValue | undefined>(undefined)

function applyBrandingSideEffects(b: Branding) {
  if (typeof document === 'undefined') return
  // Title: "Brand" if customized, keep the legacy long title otherwise so
  // existing OG/SEO stays intact for bigmcp.cloud.
  if (b.customized) {
    document.title = b.instance_name
  }
  // Favicon swap when an explicit one is provided.
  if (b.favicon_url) {
    let link = document.querySelector("link[rel~='icon']") as HTMLLinkElement | null
    if (!link) {
      link = document.createElement('link')
      link.rel = 'icon'
      document.head.appendChild(link)
    }
    link.href = b.favicon_url
  }
  // CSS variable so any component can pick up the custom hue without
  // round-tripping through React state.
  document.documentElement.style.setProperty('--brand-primary', b.primary_color)
}

export function BrandingProvider({ children }: { children: React.ReactNode }) {
  const [branding, setBranding] = useState<Branding>(DEFAULT_BRANDING)
  const [isLoading, setIsLoading] = useState(true)

  const refresh = useCallback(async () => {
    setIsLoading(true)
    try {
      const { data } = await apiClient.get<Branding>('/instance/branding')
      setBranding(data)
      applyBrandingSideEffects(data)
    } catch (err) {
      // Network or 5xx — keep defaults, log once. Don't block the app.
      console.warn('Branding fetch failed, using defaults', err)
      setBranding(DEFAULT_BRANDING)
      applyBrandingSideEffects(DEFAULT_BRANDING)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const value = useMemo<BrandingContextValue>(
    () => ({ branding, isLoading, refresh }),
    [branding, isLoading, refresh]
  )

  return <BrandingContext.Provider value={value}>{children}</BrandingContext.Provider>
}

export function useBranding(): BrandingContextValue {
  const ctx = useContext(BrandingContext)
  if (ctx === undefined) {
    throw new Error('useBranding must be used within a BrandingProvider')
  }
  return ctx
}
