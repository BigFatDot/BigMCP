/**
 * SSO buttons row for the LoginPage.
 *
 * Calls the public ``GET /api/v1/auth/sso-providers`` endpoint and
 * renders one button per active OIDC provider. Clicking a button
 * navigates to ``GET /api/v1/auth/oidc/{id}/login`` which performs the
 * full-page redirect to the IdP.
 *
 * Renders nothing when no providers are configured — the LoginPage
 * keeps its classic password form unchanged.
 */

import { useEffect, useState } from 'react'
import { ArrowRightOnRectangleIcon } from '@heroicons/react/24/outline'

interface SSOProvider {
  id: string
  name: string
  display_label: string
}

export function SsoButtons() {
  const [providers, setProviders] = useState<SSOProvider[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/v1/auth/sso-providers')
      .then((r) => (r.ok ? r.json() : { providers: [] }))
      .then((data) => setProviders(data.providers || []))
      .catch(() => setProviders([]))
      .finally(() => setLoading(false))
  }, [])

  if (loading || providers.length === 0) return null

  return (
    <div className="space-y-3 mb-6">
      {providers.map((p) => (
        <a
          key={p.id}
          href={`/api/v1/auth/oidc/${p.id}/login`}
          className="w-full flex items-center justify-center gap-3 px-4 py-3 border border-gray-300 rounded-lg bg-white hover:bg-gray-50 text-gray-800 font-medium transition-colors"
        >
          <ArrowRightOnRectangleIcon className="h-5 w-5 text-gray-500" />
          {p.display_label}
        </a>
      ))}
      <div className="relative my-4">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-gray-200" />
        </div>
        <div className="relative flex justify-center text-xs">
          <span className="bg-white px-2 text-gray-500">or</span>
        </div>
      </div>
    </div>
  )
}
