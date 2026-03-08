/**
 * Authentication Context
 *
 * Manages user authentication state, JWT tokens, subscription, and deployment mode.
 * Supports both Cloud SaaS (JWT) and Self-hosted (API keys via marketplace).
 */

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import type {
  User,
  Subscription,
  Organization,
  DeploymentConfig,
  AuthTokens,
  FeatureLimits,
  SubscriptionTier,
  EditionInfo,
  MFAChallengeResponse,
} from '../types/auth'
import type { DeploymentType } from '../types/marketplace'
import { editionApi } from '../services/marketplace'
import { queryClient } from '../lib/queryClient'

// ============================================================================
// Types
// ============================================================================

interface AuthContextValue {
  // Authentication state
  user: User | null
  subscription: Subscription | null
  organization: Organization | null
  isAuthenticated: boolean
  isLoading: boolean

  // Deployment configuration
  deploymentConfig: DeploymentConfig

  // Edition information (from backend /edition/status)
  edition: EditionInfo | null
  editionLoading: boolean
  isCloudSaaS: boolean
  isEnterprise: boolean
  isCommunity: boolean

  // Authentication actions
  login: (email: string, password: string) => Promise<MFAChallengeResponse | void>
  signup: (email: string, password: string, fullName: string) => Promise<void>
  logout: () => void
  refreshToken: () => Promise<void>
  refreshUser: () => Promise<void>

  // Feature access
  hasFeature: (feature: keyof FeatureLimits) => boolean
  canAddUser: () => boolean
  isInTrial: () => boolean
  daysUntilTrialEnd: () => number | null
}

// ============================================================================
// Context
// ============================================================================

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

// ============================================================================
// Local Storage Keys
// ============================================================================

const STORAGE_KEYS = {
  ACCESS_TOKEN: 'bigmcp_access_token',
  REFRESH_TOKEN: 'bigmcp_refresh_token',
  USER: 'bigmcp_user',
  SUBSCRIPTION: 'bigmcp_subscription',
  ORGANIZATION: 'bigmcp_organization',
  DEPLOYMENT_MODE: 'bigmcp_deployment_mode',
} as const

// ============================================================================
// Deployment Mode Detection
// ============================================================================

/**
 * Detect deployment mode based on environment and hostname.
 * - Cloud: app.bigmcp.cloud, *.bigmcp.cloud, localhost (dev)
 * - Self-hosted: Everything else
 */
function detectDeploymentMode(): DeploymentType {
  // Check environment variable first (set during build)
  const envMode = import.meta.env.VITE_DEPLOYMENT_MODE as DeploymentType | undefined
  if (envMode) {
    return envMode
  }

  // Detect from hostname
  const hostname = window.location.hostname

  // Localhost and 127.0.0.1 are considered Cloud mode for development
  if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname.includes('bigmcp.cloud')) {
    return 'cloud'
  }

  // Check localStorage for self-hosted configuration
  const storedMode = localStorage.getItem(STORAGE_KEYS.DEPLOYMENT_MODE) as DeploymentType | null
  if (storedMode === 'self_hosted_enterprise') {
    return 'self_hosted_enterprise'
  }

  // Default to self-hosted community
  return 'self_hosted_community'
}

/**
 * Get deployment configuration based on mode
 *
 * API routing:
 * - Frontend ALWAYS calls /api/v1 (local backend)
 * - Backend handles routing to cloud marketplace API if needed
 * - Self-hosted backends use MARKETPLACE_API_URL env var for marketplace proxying
 */
function getDeploymentConfig(mode: DeploymentType): DeploymentConfig {
  const isCloud = mode === 'cloud'

  // API base URL - configurable via env or defaults to /api/v1
  // This ensures self-hosted deployments use their local backend
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'

  return {
    mode,
    is_cloud: isCloud,
    requires_subscription: isCloud,
    supports_organizations: mode === 'cloud' || mode === 'self_hosted_enterprise',
    // Always use local backend - it handles marketplace proxy to cloud if needed
    marketplace_api_url: apiBaseUrl,
  }
}

// ============================================================================
// Provider Component
// ============================================================================

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [subscription, setSubscription] = useState<Subscription | null>(null)
  const [organization, setOrganization] = useState<Organization | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [deploymentConfig] = useState<DeploymentConfig>(() => {
    const mode = detectDeploymentMode()
    return getDeploymentConfig(mode)
  })

  // Edition state (fetched from backend /edition/status)
  const [edition, setEdition] = useState<EditionInfo | null>(null)
  const [editionLoading, setEditionLoading] = useState(true)

  // Computed edition flags
  const isCloudSaaS = edition?.edition === 'cloud_saas'
  const isEnterprise = edition?.edition === 'enterprise'
  const isCommunity = edition?.edition === 'community' || (!editionLoading && edition === null)

  // ============================================================================
  // Token Management
  // ============================================================================

  const saveTokens = useCallback((tokens: AuthTokens) => {
    localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, tokens.access_token)
    localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, tokens.refresh_token)
  }, [])

  const clearTokens = useCallback(() => {
    localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN)
    localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN)
    localStorage.removeItem(STORAGE_KEYS.USER)
    localStorage.removeItem(STORAGE_KEYS.SUBSCRIPTION)
    localStorage.removeItem(STORAGE_KEYS.ORGANIZATION)
  }, [])

  const getAccessToken = useCallback((): string | null => {
    return localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN)
  }, [])

  const getRefreshToken = useCallback((): string | null => {
    return localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN)
  }, [])

  // ============================================================================
  // API Client
  // ============================================================================

  const apiClient = useCallback(
    async (endpoint: string, options: RequestInit = {}) => {
      const url = `${deploymentConfig.marketplace_api_url}${endpoint}`
      const token = getAccessToken()

      const headers: HeadersInit = {
        'Content-Type': 'application/json',
        ...options.headers,
      }

      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      const response = await fetch(url, {
        ...options,
        headers,
      })

      if (!response.ok) {
        // If 401 and we have a refresh token, try to refresh
        if (response.status === 401 && getRefreshToken()) {
          try {
            await refreshToken()
            // Retry the original request with new token
            const newToken = getAccessToken()
            if (newToken) {
              headers['Authorization'] = `Bearer ${newToken}`
              const retryResponse = await fetch(url, { ...options, headers })
              if (retryResponse.ok) {
                return retryResponse
              }
            }
          } catch (error) {
            // Refresh failed, logout user
            logout()
            throw new Error('Session expired. Please login again.')
          }
        }

        const errorData = await response.json().catch(() => ({ detail: response.statusText }))
        throw new Error(errorData.detail || `HTTP ${response.status}`)
      }

      return response
    },
    [deploymentConfig.marketplace_api_url, getAccessToken, getRefreshToken]
  )

  // ============================================================================
  // Authentication Actions
  // ============================================================================

  const login = useCallback(
    async (email: string, password: string): Promise<MFAChallengeResponse | void> => {
      // Direct fetch to handle specific error codes (403 for email not verified)
      const response = await fetch(`${deploymentConfig.marketplace_api_url}/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password }),
      })

      const data = await response.json()

      // Handle email not verified error (403)
      if (response.status === 403 && data.detail?.error === 'email_not_verified') {
        const error = new Error(data.detail.message || 'Please verify your email address before logging in.')
        ;(error as any).emailNotVerified = true
        ;(error as any).email = data.detail.email || email
        throw error
      }

      // Handle other errors
      if (!response.ok) {
        throw new Error(data.detail || `HTTP ${response.status}`)
      }

      // Handle MFA required response
      if (data.mfa_required) {
        return {
          mfa_required: true,
          mfa_token: data.mfa_token,
          message: data.message || 'MFA verification required',
        }
      }

      // Backend returns TokenResponse with access_token, refresh_token
      const tokens = {
        access_token: data.access_token,
        refresh_token: data.refresh_token,
        token_type: data.token_type,
      }
      saveTokens(tokens)

      // Fetch current user data after login
      const userResponse = await apiClient('/auth/me')
      const userData = await userResponse.json()

      setUser(userData.user || userData)
      setSubscription(userData.subscription || null)
      setOrganization(userData.organization || null)

      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(userData.user || userData))
      if (userData.subscription) {
        localStorage.setItem(STORAGE_KEYS.SUBSCRIPTION, JSON.stringify(userData.subscription))
      }
      if (userData.organization) {
        localStorage.setItem(STORAGE_KEYS.ORGANIZATION, JSON.stringify(userData.organization))
      }
    },
    [apiClient, deploymentConfig.marketplace_api_url, saveTokens]
  )

  const signup = useCallback(
    async (email: string, password: string, fullName: string) => {
      // Direct fetch to handle different status codes (202 for verification required)
      const response = await fetch(`${deploymentConfig.marketplace_api_url}/auth/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email,
          password,
          name: fullName,
        }),
      })

      const data = await response.json()

      // SaaS mode: 202 Accepted means verification required
      if (response.status === 202 && data.requires_verification) {
        // Throw a special error that SignupPage can handle
        const error = new Error(data.message || 'Email verification required')
        ;(error as any).requiresVerification = true
        ;(error as any).email = data.email
        throw error
      }

      // Handle other errors
      if (!response.ok) {
        throw new Error(data.detail || `HTTP ${response.status}`)
      }

      // Non-SaaS mode: Auto-login with tokens
      const tokens = {
        access_token: data.access_token,
        refresh_token: data.refresh_token,
        token_type: data.token_type,
      }
      saveTokens(tokens)

      // User data is included in registration response
      const userData = data.user

      setUser(userData)
      setSubscription(null) // New users don't have subscription yet
      setOrganization(userData.organization || null)

      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(userData))
      if (userData.organization) {
        localStorage.setItem(STORAGE_KEYS.ORGANIZATION, JSON.stringify(userData.organization))
      }
    },
    [deploymentConfig.marketplace_api_url, saveTokens]
  )

  const logout = useCallback(() => {
    // Clear all cached data to prevent data leakage between accounts
    queryClient.clear()
    clearTokens()
    setUser(null)
    setSubscription(null)
    setOrganization(null)
  }, [clearTokens])

  const refreshToken = useCallback(async () => {
    const refreshTokenValue = getRefreshToken()
    if (!refreshTokenValue) {
      throw new Error('No refresh token available')
    }

    const response = await fetch(`${deploymentConfig.marketplace_api_url}/auth/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ refresh_token: refreshTokenValue }),
    })

    if (!response.ok) {
      throw new Error('Token refresh failed')
    }

    const data = await response.json()
    saveTokens(data.tokens)
  }, [deploymentConfig.marketplace_api_url, getRefreshToken, saveTokens])

  const refreshUser = useCallback(async () => {
    const token = getAccessToken()
    if (!token) {
      return
    }

    try {
      const response = await apiClient('/auth/me')
      const userData = await response.json()

      const newUser = userData.user || userData
      setUser(newUser)
      setSubscription(userData.subscription || null)
      setOrganization(userData.organization || null)

      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(newUser))
      if (userData.subscription) {
        localStorage.setItem(STORAGE_KEYS.SUBSCRIPTION, JSON.stringify(userData.subscription))
      }
      if (userData.organization) {
        localStorage.setItem(STORAGE_KEYS.ORGANIZATION, JSON.stringify(userData.organization))
      }
    } catch (error) {
      console.error('Failed to refresh user:', error)
    }
  }, [apiClient, getAccessToken])

  // ============================================================================
  // Feature Access
  // ============================================================================

  const hasFeature = useCallback(
    (feature: keyof FeatureLimits): boolean => {
      // Self-hosted community: limited features
      if (deploymentConfig.mode === 'self_hosted_community') {
        const communityFeatures: Array<keyof FeatureLimits> = [
          'marketplace_access',
          'unlimited_ai_features',
          'unlimited_semantic_search',
          'unlimited_compositions',
        ]
        return communityFeatures.includes(feature)
      }

      // Self-hosted enterprise: all features
      if (deploymentConfig.mode === 'self_hosted_enterprise') {
        return true
      }

      // Cloud: check subscription tier
      if (!subscription) {
        // Trial or no subscription - basic features only
        const trialFeatures: Array<keyof FeatureLimits> = [
          'marketplace_access',
          'unlimited_ai_features',
          'unlimited_semantic_search',
          'unlimited_compositions',
        ]
        return trialFeatures.includes(feature)
      }

      // Check tier-specific features
      if (feature === 'organizations' || feature === 'rbac' || feature === 'oauth' || feature === 'team_credentials') {
        return subscription.tier === 'team'
      }

      // All other features are available to all paid tiers
      return true
    },
    [deploymentConfig.mode, subscription]
  )

  const canAddUser = useCallback((): boolean => {
    if (!subscription) {
      return false
    }

    // This would need to be checked against actual user count from API
    // For now, just check if we're under the limit
    return true // Placeholder - implement with actual user count
  }, [subscription])

  const isInTrial = useCallback((): boolean => {
    if (!subscription) {
      return false
    }

    return subscription.is_trial
  }, [subscription])

  const daysUntilTrialEnd = useCallback((): number | null => {
    if (!subscription || !subscription.trial_ends_at) {
      return null
    }

    const trialEnd = new Date(subscription.trial_ends_at)
    const now = new Date()
    const diffTime = trialEnd.getTime() - now.getTime()
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))

    return diffDays > 0 ? diffDays : 0
  }, [subscription])

  // ============================================================================
  // Initialization
  // ============================================================================

  useEffect(() => {
    const initializeAuth = async () => {
      // Restore session from localStorage for immediate UI
      const storedUser = localStorage.getItem(STORAGE_KEYS.USER)
      const storedSubscription = localStorage.getItem(STORAGE_KEYS.SUBSCRIPTION)
      const storedOrganization = localStorage.getItem(STORAGE_KEYS.ORGANIZATION)
      const accessToken = getAccessToken()

      if (accessToken) {
        // Set initial state from localStorage for fast UI render (if available)
        if (storedUser) {
          setUser(JSON.parse(storedUser))
          if (storedSubscription) {
            setSubscription(JSON.parse(storedSubscription))
          }
          if (storedOrganization) {
            setOrganization(JSON.parse(storedOrganization))
          }
        }

        // Refresh from server to get latest data (subscription, org, etc.)
        // This ensures we have the most up-to-date data even if localStorage is stale
        // Also handles MFA login where tokens are stored but user data isn't
        try {
          const response = await fetch(`${deploymentConfig.marketplace_api_url}/auth/me`, {
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${accessToken}`,
            },
          })

          if (response.ok) {
            const userData = await response.json()
            const newUser = userData.user || userData
            setUser(newUser)
            setSubscription(userData.subscription || null)
            setOrganization(userData.organization || null)

            // Update localStorage with fresh data
            localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(newUser))
            if (userData.subscription) {
              localStorage.setItem(STORAGE_KEYS.SUBSCRIPTION, JSON.stringify(userData.subscription))
            }
            if (userData.organization) {
              localStorage.setItem(STORAGE_KEYS.ORGANIZATION, JSON.stringify(userData.organization))
            }
          } else if (response.status === 401) {
            // Token is invalid, clear auth state
            clearTokens()
          }
        } catch (error) {
          console.error('Failed to refresh user data on init:', error)
          // Keep using localStorage data if refresh fails (and we had stored data)
        }
      }

      setIsLoading(false)
    }

    initializeAuth()
  }, [getAccessToken, deploymentConfig.marketplace_api_url])

  // ============================================================================
  // Edition Fetching
  // ============================================================================

  useEffect(() => {
    const fetchEdition = async () => {
      try {
        const editionInfo = await editionApi.getStatus()
        setEdition(editionInfo)
      } catch (error) {
        console.error('Failed to fetch edition status:', error)
        // Fallback to community if backend unreachable
        setEdition({
          edition: 'community',
          limits: { max_users: 1, max_organizations: 1 },
          features: { billing: false, sso: false, unlimited_users: false, organizations: false },
        })
      } finally {
        setEditionLoading(false)
      }
    }

    fetchEdition()
  }, [])

  // ============================================================================
  // Context Value
  // ============================================================================

  const value: AuthContextValue = {
    user,
    subscription,
    organization,
    isAuthenticated: user !== null,
    isLoading,
    deploymentConfig,
    // Edition information
    edition,
    editionLoading,
    isCloudSaaS,
    isEnterprise,
    isCommunity,
    // Actions
    login,
    signup,
    logout,
    refreshToken,
    refreshUser,
    hasFeature,
    canAddUser,
    isInTrial,
    daysUntilTrialEnd,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// ============================================================================
// Hook
// ============================================================================

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
