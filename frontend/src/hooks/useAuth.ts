/**
 * Authentication Hooks
 *
 * Convenience hooks for accessing auth context features.
 */

import { useAuth as useAuthContext } from '../contexts/AuthContext'
import type { SubscriptionTier, FeatureLimits } from '../types/auth'

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
    isCommunity: deploymentConfig.mode === 'self_hosted_community',
    isEnterprise: deploymentConfig.mode === 'self_hosted_enterprise',
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

  return {
    organization,
    hasOrganization: organization !== null,
    organizationId: organization?.id || null,
    organizationName: organization?.name || null,
    organizationSlug: organization?.slug || null,
    supportsOrganizations: deploymentConfig.supports_organizations,
    isTeamOrg,
    isAdmin,
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
