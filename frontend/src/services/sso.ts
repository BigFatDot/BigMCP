/**
 * SSO admin API client (Story I.2).
 *
 * Wraps the instance-admin endpoints under /admin/sso for managing
 * OIDC providers, group mappings, and the force-SSO-only toggle.
 * Public surface (the LoginPage) uses /auth/sso-providers, see
 * services/connectedApps.ts neighbour for the user-side analog.
 */

import { apiClient } from './api'

// ============================================================================
// Presets
// ============================================================================

export interface OIDCPreset {
  id: string
  label: string
  default_name: string
  default_display_label: string
  issuer_url_template: string
  issuer_url_placeholder: string
  scopes: string[]
  groups_claim_path: string
  email_claim_path: string
  name_claim_path: string
  require_email_verified: boolean
  notes: string
  docs_url: string
}

export async function listPresets(): Promise<OIDCPreset[]> {
  const { data } = await apiClient.get<{ presets: OIDCPreset[] }>(
    '/admin/sso/presets',
  )
  return data.presets
}

// ============================================================================
// Providers
// ============================================================================

export interface OIDCProvider {
  id: string
  name: string
  display_label: string
  issuer_url: string
  client_id: string
  scopes: string[]
  groups_claim_path: string | null
  email_claim_path: string
  name_claim_path: string
  auto_link_by_verified_email: boolean
  require_email_verified: boolean
  reject_unmapped_users: boolean
  fallback_organization_id: string | null
  fallback_role: string
  is_active: boolean
  manual_endpoints_json: Record<string, unknown> | null
  created_at: string
  updated_at: string
  mapping_count: number
}

export interface OIDCProviderCreatePayload {
  name: string
  display_label: string
  issuer_url: string
  client_id: string
  client_secret: string
  scopes?: string[]
  groups_claim_path?: string | null
  email_claim_path?: string
  name_claim_path?: string
  auto_link_by_verified_email?: boolean
  require_email_verified?: boolean
  reject_unmapped_users?: boolean
  fallback_organization_id?: string | null
  fallback_role?: string
  is_active?: boolean
  manual_endpoints_json?: Record<string, unknown> | null
}

export type OIDCProviderUpdatePayload = Partial<OIDCProviderCreatePayload>

export async function listProviders(): Promise<OIDCProvider[]> {
  const { data } = await apiClient.get<OIDCProvider[]>('/admin/sso/providers')
  return data
}

export async function createProvider(
  payload: OIDCProviderCreatePayload,
): Promise<OIDCProvider> {
  const { data } = await apiClient.post<OIDCProvider>(
    '/admin/sso/providers',
    payload,
  )
  return data
}

export async function updateProvider(
  id: string,
  payload: OIDCProviderUpdatePayload,
): Promise<OIDCProvider> {
  const { data } = await apiClient.put<OIDCProvider>(
    `/admin/sso/providers/${id}`,
    payload,
  )
  return data
}

export async function deleteProvider(id: string): Promise<void> {
  await apiClient.delete(`/admin/sso/providers/${id}`)
}

// ============================================================================
// Group mappings
// ============================================================================

export interface OIDCGroupMapping {
  id: string
  provider_id: string
  idp_group_name: string
  organization_id: string | null
  role: string | null
  grants_instance_admin: boolean
}

export async function listMappings(
  providerId: string,
): Promise<OIDCGroupMapping[]> {
  const { data } = await apiClient.get<OIDCGroupMapping[]>(
    `/admin/sso/providers/${providerId}/mappings`,
  )
  return data
}

export async function createMapping(
  providerId: string,
  payload: {
    idp_group_name: string
    organization_id?: string | null
    role?: string | null
    grants_instance_admin?: boolean
  },
): Promise<OIDCGroupMapping> {
  const { data } = await apiClient.post<OIDCGroupMapping>(
    `/admin/sso/providers/${providerId}/mappings`,
    payload,
  )
  return data
}

export async function deleteMapping(
  providerId: string,
  mappingId: string,
): Promise<void> {
  await apiClient.delete(
    `/admin/sso/providers/${providerId}/mappings/${mappingId}`,
  )
}

// ============================================================================
// Force-SSO-only toggle
// ============================================================================

export async function getForceSsoOnly(): Promise<boolean> {
  const { data } = await apiClient.get<{ enabled: boolean }>(
    '/admin/sso/force-sso-only',
  )
  return data.enabled
}

export async function setForceSsoOnly(enabled: boolean): Promise<boolean> {
  const { data } = await apiClient.put<{ enabled: boolean }>(
    '/admin/sso/force-sso-only',
    { enabled },
  )
  return data.enabled
}
