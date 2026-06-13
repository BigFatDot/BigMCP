/**
 * Authentication Hooks
 *
 * Convenience hooks for accessing auth context features.
 */

import { useAuth as useAuthContext } from '../contexts/AuthContext'
import type { SubscriptionTier, FeatureLimits, OrganizationMembership } from '../types/auth'

// Re-export main useAuth hook
export { useAuth } from '../contexts/AuthContext'

/**
 * Hook for accessing subscription information
 */
export function useSubscription() {
  const { subscription, isInTrial, daysUntilTrialEnd, canAddUser } = useAuthContext()

  return {
    subscription,
    tier: subscription?.tier as SubscriptionTier | null,
    status: subscription?.status || null,
    isActive: subscription?.is_active || false,
    isInTrial: isInTrial(),
    daysUntilTrialEnd: daysUntilTrialEnd(),
    canAddUser: canAddUser(),
    maxUsers: subscription?.max_users ?? 1,
    currentPeriodEnd: subscription?.current_period_end || null,
    cancelAtPeriodEnd: subscription?.cancel_at_period_end || false,
  }
}

/**
 * Hook for checking feature access
 */
export function useFeatureAccess() {
  const { hasFeature, deploymentConfig, subscription } = useAuthContext()

  // Helper function to check multiple features at once
  const hasAllFeatures = (features: Array<keyof FeatureLimits>): boolean => {
    return features.every((feature) => hasFeature(feature))
  }

  const hasAnyFeature = (features: Array<keyof FeatureLimits>): boolean => {
    return features.some((feature) => hasFeature(feature))
  }

  // Pre-computed common feature checks
  const features = {
    // Basic features (available to all)
    marketplace: hasFeature('marketplace_access'),
    aiFeatures: hasFeature('unlimited_ai_features'),
    semanticSearch: hasFeature('unlimited_semantic_search'),
    compositions: hasFeature('unlimited_compositions'),

    // Team features (Team tier only)
    organizations: hasFeature('organizations'),
    rbac: hasFeature('rbac'),
    oauth: hasFeature('oauth'),
    teamCredentials: hasFeature('team_credentials'),
  }

  return {
    // Individual feature checks
    hasFeature,
    hasAllFeatures,
    hasAnyFeature,

    // Pre-computed features
    features,

    // Deployment info
    deploymentMode: deploymentConfig.mode,
    isCloud: deploymentConfig.is_cloud,
    requiresSubscription: deploymentConfig.requires_subscription,
    supportsOrganizations: deploymentConfig.supports_organizations,

    // Tier info
    tier: subscription?.tier || null,
    isIndividual: subscription?.tier === 'individual',
    isTeam: subscription?.tier === 'team',
  }
}

/**
 * Hook for accessing organization information
 */
export function useOrganization() {
  const { user, organization, deploymentConfig, subscription } = useAuthContext()

  // Team org: has organization AND is on team tier
  const isTeamOrg = organization !== null && subscription?.tier === 'team'

  // Determine if user is an admin (ADMIN or OWNER role) for the current organization
  const currentMembership = organization?.id
    ? user?.organization_memberships?.find(m => m.organization_id === organization.id)
    : user?.organization_memberships?.[0]
  const isAdmin = currentMembership?.role === 'admin' ||
                  currentMembership?.role === 'owner'

  // Memberships exposed for OrgSwitcher and other multi-tenant UIs.
  // Sourced from /auth/me payload (already loaded into AuthContext on mount).
  const memberships: OrganizationMembership[] = user?.organization_memberships ?? []

  /**
   * Switch the current active organization by calling /auth/switch-organization,
   * persisting the new tokens, and triggering a full reload so every context
   * picks up the new identity. Factorised from TeamPage:187-222 so the navbar
   * OrgSwitcher and the settings page share a single code path.
   *
   * Throws on failure — callers are expected to surface the error message
   * (e.g. via toast.error) and manage their own `isSwitching` UI state.
   */
  const switchOrganization = async (organizationId: string): Promise<void> => {
    const token = localStorage.getItem('bigmcp_access_token')
    const response = await fetch(
      `/api/v1/auth/switch-organization?organization_id=${encodeURIComponent(organizationId)}`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      },
    )

    if (!response.ok) {
      let detail = `HTTP ${response.status}`
      try {
        const data = await response.json()
        if (data?.detail && typeof data.detail === 'string') {
          detail = data.detail
        }
      } catch {
        // ignore JSON parse error, keep status fallback
      }
      throw new Error(detail)
    }

    const data = await response.json()
    if (data?.access_token) {
      localStorage.setItem('bigmcp_access_token', data.access_token)
    }
    if (data?.refresh_token) {
      localStorage.setItem('bigmcp_refresh_token', data.refresh_token)
    }

    // Pattern hérité de TeamPage : un reload garantit que AuthContext et
    // tout le reste de l'app rechargent l'identité avec le nouveau JWT.
    window.location.reload()
  }

  return {
    organization,
    hasOrganization: organization !== null,
    organizationId: organization?.id || null,
    organizationName: organization?.name || null,
    organizationSlug: organization?.slug || null,
    supportsOrganizations: deploymentConfig.supports_organizations,
    isTeamOrg,
    isAdmin,
    memberships,
    switchOrganization,
  }
}

/**
 * Hook for accessing edition information from backend.
 *
 * Use this hook when you need to conditionally render based on edition:
 * - isCloudSaaS: Full billing UI, subscription management
 * - isEnterprise: License display, enterprise features
 * - isCommunity: Upgrade CTA, limited features
 */
export function useEdition() {
  const {
    edition,
    editionLoading,
    isCloudSaaS,
    isEnterprise,
    isCommunity,
  } = useAuthContext()

  return {
    // Raw edition data
    edition,
    editionLoading,

    // Edition type flags
    isCloudSaaS,
    isEnterprise,
    isCommunity,

    // License info (Enterprise only)
    licenseOrg: edition?.license?.organization || null,
    licenseFeatures: edition?.license?.features || [],

    // SaaS info (Cloud only)
    billingEnabled: edition?.saas?.billing_enabled || false,
    marketplaceEnabled: edition?.saas?.marketplace_enabled || true,

    // Limits
    maxUsers: edition?.limits?.max_users || 1,
    maxOrganizations: edition?.limits?.max_organizations || 1,
  }
}
