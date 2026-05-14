/**
 * SSO bridge route — picks up the token pair from the URL fragment
 * (which the backend's OIDC callback redirected to) and persists it
 * in localStorage under the same keys AuthContext uses, then bounces
 * to /app.
 *
 * Tokens travel via fragment (#access_token=...&refresh_token=...)
 * so they never hit the server logs.
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

const STORAGE_ACCESS = 'bigmcp_access_token'
const STORAGE_REFRESH = 'bigmcp_refresh_token'

export function SsoCallbackPage() {
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fragment = window.location.hash.startsWith('#')
      ? window.location.hash.slice(1)
      : window.location.hash
    const params = new URLSearchParams(fragment)

    const access = params.get('access_token')
    const refresh = params.get('refresh_token')

    if (!access || !refresh) {
      setError('Missing tokens in SSO callback. Please retry.')
      return
    }

    try {
      localStorage.setItem(STORAGE_ACCESS, access)
      localStorage.setItem(STORAGE_REFRESH, refresh)
    } catch {
      setError('Could not persist session locally.')
      return
    }

    // Clear fragment from URL bar (cosmetic + paranoia)
    history.replaceState(null, '', '/auth/sso-callback')

    // Hard navigation so AuthContext re-bootstraps with the new token
    window.location.assign('/app')
  }, [navigate])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center">
        {error ? (
          <>
            <p className="text-red-600 font-medium mb-3">{error}</p>
            <a
              href="/login"
              className="text-orange hover:text-orange-dark font-medium"
            >
              Back to login
            </a>
          </>
        ) : (
          <>
            <div className="animate-spin rounded-full h-12 w-12 border-2 border-gray-300 border-t-orange mx-auto mb-4" />
            <p className="text-gray-600">Finalizing SSO sign-in…</p>
          </>
        )}
      </div>
    </div>
  )
}
