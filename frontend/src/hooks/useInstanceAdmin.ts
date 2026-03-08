/**
 * Instance Admin Hook
 *
 * Provides access to instance admin status and actions.
 * Edition-aware behavior:
 * - Community: Auto-admin, no token needed
 * - Enterprise: Token validation, stored in preferences
 * - Cloud SaaS: Platform owner only (no UI exposed)
 */

import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { instanceAdminApi, type AdminStatus } from '../services/marketplace'

interface UseInstanceAdminResult {
  // Status
  isInstanceAdmin: boolean
  isLoading: boolean
  error: string | null

  // Edition info
  edition: string | null
  requiresToken: boolean
  tokenHint: string | null

  // Actions (Enterprise only)
  validateToken: (token: string) => Promise<boolean>
  revokeAdmin: () => Promise<boolean>

  // Refresh
  refreshStatus: () => Promise<void>
}

export function useInstanceAdmin(): UseInstanceAdminResult {
  const { isAuthenticated, isCommunity, isEnterprise, isCloudSaaS } = useAuth()

  const [status, setStatus] = useState<AdminStatus | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Fetch admin status
  const fetchStatus = useCallback(async () => {
    if (!isAuthenticated) {
      setIsLoading(false)
      return
    }

    try {
      setIsLoading(true)
      setError(null)
      const adminStatus = await instanceAdminApi.getStatus()
      setStatus(adminStatus)
    } catch (err: any) {
      console.error('Failed to fetch admin status:', err)
      setError(err.response?.data?.detail || 'Failed to fetch admin status')
    } finally {
      setIsLoading(false)
    }
  }, [isAuthenticated])

  // Fetch on mount and when auth changes
  useEffect(() => {
    fetchStatus()
  }, [fetchStatus])

  // Validate admin token (Enterprise only)
  const validateToken = useCallback(async (token: string): Promise<boolean> => {
    if (!isEnterprise) {
      setError('Token validation is only available for Enterprise edition')
      return false
    }

    try {
      setError(null)
      const result = await instanceAdminApi.validateToken(token)
      if (result.success) {
        // Refresh status after successful validation
        await fetchStatus()
        return true
      }
      return false
    } catch (err: any) {
      console.error('Failed to validate admin token:', err)
      setError(err.response?.data?.detail || 'Invalid admin token')
      return false
    }
  }, [isEnterprise, fetchStatus])

  // Revoke admin privileges (Enterprise only)
  const revokeAdmin = useCallback(async (): Promise<boolean> => {
    if (isCommunity) {
      setError('Cannot revoke admin on Community edition')
      return false
    }

    try {
      setError(null)
      const result = await instanceAdminApi.revokeAdmin()
      if (result.success) {
        await fetchStatus()
        return true
      }
      return false
    } catch (err: any) {
      console.error('Failed to revoke admin:', err)
      setError(err.response?.data?.detail || 'Failed to revoke admin privileges')
      return false
    }
  }, [isCommunity, fetchStatus])

  return {
    // Status
    isInstanceAdmin: status?.is_instance_admin ?? false,
    isLoading,
    error,

    // Edition info
    edition: status?.edition ?? null,
    requiresToken: status?.requires_token ?? false,
    tokenHint: status?.token_hint ?? null,

    // Actions
    validateToken,
    revokeAdmin,

    // Refresh
    refreshStatus: fetchStatus,
  }
}
