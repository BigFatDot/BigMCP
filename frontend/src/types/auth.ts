/**
 * Authentication and User Type Definitions
 */

import { DeploymentType } from './marketplace'

export type SubscriptionTier = 'individual' | 'team'

export type SubscriptionStatus = 'trialing' | 'active' | 'past_due' | 'cancelled' | 'expired'

export type UserRole = 'owner' | 'admin' | 'member' | 'viewer'

export interface OrganizationMembership {
  id: string
  organization_id: string
  user_id: string
  role: UserRole
  created_at: string
  updated_at: string
}

export interface User {
  id: string
  email: string
  full_name: string
  is_active: boolean
  is_verified: boolean
  is_superuser: boolean
  organization_id?: string
  organization_memberships?: OrganizationMembership[]
  created_at: string
  updated_at: string
}

export interface Organization {
  id: string
  name: string
  slug: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Subscription {
  id: string
  tier: SubscriptionTier
  status: SubscriptionStatus
  organization_id?: string
  max_users: number
  current_period_start: string
  current_period_end: string
  trial_ends_at?: string
  cancel_at_period_end: boolean
  cancelled_at?: string
  is_active: boolean
  is_trial: boolean
}

export interface FeatureLimits {
  tier: SubscriptionTier
  max_users: number
  unlimited_ai_features: boolean
  unlimited_semantic_search: boolean
  unlimited_compositions: boolean
  marketplace_access: boolean
  organizations: boolean
  rbac: boolean
  oauth: boolean
  team_credentials: boolean
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface LoginRequest {
  email: string
  password: string
  mfa_code?: string
}

export interface SignupRequest {
  email: string
  password: string
  full_name: string
}

export interface AuthResponse {
  user: User
  tokens: AuthTokens
  subscription?: Subscription
  organization?: Organization
}

// ============================================================================
// MFA (Two-Factor Authentication) Types
// ============================================================================

export interface MFAStatus {
  enabled: boolean
  enrolled_at: string | null
  backup_codes_remaining: number | null
}

export interface MFASetupResponse {
  provisioning_uri: string
  backup_codes: string[]
  message: string
}

export interface MFAChallengeResponse {
  mfa_required: boolean
  mfa_token: string
  message: string
}

export interface MFALoginRequest {
  mfa_token: string
  mfa_code: string
}

export interface DeploymentConfig {
  mode: DeploymentType
  is_cloud: boolean
  requires_subscription: boolean
  supports_organizations: boolean
  marketplace_api_url: string
}

// ============================================================================
// Enterprise License Types
// ============================================================================

export type LicenseEdition = 'community' | 'professional' | 'enterprise'
export type LicenseStatus = 'trial' | 'active' | 'expired' | 'suspended' | 'revoked'

export interface License {
  id: string
  license_key: string
  admin_token?: string  // For self-hosted admin setup
  edition: LicenseEdition
  status: LicenseStatus
  company_name?: string
  issued_at: string
  expires_at?: string | null
  features: string[]
  order_id?: string
}

export interface LicensesListResponse {
  licenses: License[]
  count: number
}

export interface EnterpriseCheckoutRequest {
  organization_name: string
}

export interface EnterpriseCheckoutResponse {
  checkout_url: string
  is_public_sector: boolean
}

export interface PublicSectorEligibility {
  is_eligible: boolean
  domain?: string
  organization_name?: string
  category?: string
}

// ============================================================================
// Edition Types (from /edition/status endpoint)
// ============================================================================

/**
 * Backend edition type.
 * - community: Free self-hosted, 1 user limit
 * - enterprise: Licensed self-hosted, unlimited users
 * - cloud_saas: BigMCP Cloud (bigmcp.cloud)
 */
export type EditionType = 'community' | 'enterprise' | 'cloud_saas'

export interface EditionLimits {
  max_users: number
  max_organizations: number
}

export interface EditionFeatures {
  billing: boolean
  sso: boolean
  unlimited_users: boolean
  organizations: boolean
}

export interface EditionLicenseInfo {
  organization: string
  features: string[]
}

export interface EditionSaaSInfo {
  billing_enabled: boolean
  marketplace_enabled: boolean
}

/**
 * Response from /edition/status endpoint.
 * Used to determine which edition is running and adapt UI accordingly.
 */
export interface EditionInfo {
  edition: EditionType
  limits: EditionLimits
  features: EditionFeatures
  license?: EditionLicenseInfo    // Enterprise edition only
  saas?: EditionSaaSInfo          // Cloud SaaS edition only
}
