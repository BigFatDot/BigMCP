/**
 * Client-control admin API client (N2.2).
 *
 * Wraps the instance-admin endpoints that manage:
 * - the global client-control policy (DCR mode, CIMD requirements,
 *   trusted CIMD URLs, allowed redirect domains, …)
 * - the OAuth-clients lifecycle (list / approve / reject / revoke)
 *
 * All calls require instance-admin privileges. The backend gates with
 * 403 / 401 — the pages render those inline.
 */

import { apiClient } from './api'

// ============================================================================
// Policy
// ============================================================================

export type DcrPolicy = 'open' | 'admin_approval' | 'denied'

export interface ClientControlPolicy {
  enabled: boolean
  dcr_policy: DcrPolicy
  require_cimd: boolean
  trusted_cimd_urls: string[]
  allowed_redirect_domains: string[]
  auto_approve_cimd: boolean
  notify_admins_on_new_client: boolean
}

export const DEFAULT_POLICY: ClientControlPolicy = {
  enabled: false,
  dcr_policy: 'open',
  require_cimd: false,
  trusted_cimd_urls: [],
  allowed_redirect_domains: [],
  auto_approve_cimd: true,
  notify_admins_on_new_client: true,
}

export async function getClientPolicy(): Promise<ClientControlPolicy> {
  const { data } = await apiClient.get<ClientControlPolicy>('/admin/client-policy')
  return data
}

export async function updateClientPolicy(
  policy: ClientControlPolicy,
): Promise<ClientControlPolicy> {
  const { data } = await apiClient.put<ClientControlPolicy>(
    '/admin/client-policy',
    policy,
  )
  return data
}

// ============================================================================
// OAuth clients
// ============================================================================

export type RegistrationMethod =
  | 'dcr_open'
  | 'dcr_approved'
  | 'cimd'
  | 'manual_admin'
  | 'preloaded'

export type ApprovalStatus =
  | 'auto_approved'
  | 'pending'
  | 'approved'
  | 'rejected'

export interface OAuthClientAdminItem {
  id: string
  client_id: string
  name: string
  description: string | null
  organization_id: string | null
  registration_method: RegistrationMethod
  approval_status: ApprovalStatus
  is_active: boolean
  is_trusted: boolean
  cimd_url: string | null
  redirect_uris: string[]
  created_at: string
  approved_by_user_id: string | null
  approved_at: string | null
}

export interface OAuthClientListResponse {
  items: OAuthClientAdminItem[]
  total: number
  limit: number
  offset: number
}

export interface OAuthClientFilters {
  approval_status?: ApprovalStatus | ''
  registration_method?: RegistrationMethod | ''
  organization_id?: string
  search?: string
  limit?: number
  offset?: number
}

export async function listOAuthClients(
  filters: OAuthClientFilters = {},
): Promise<OAuthClientListResponse> {
  const params = Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined && v !== ''),
  )
  const { data } = await apiClient.get<OAuthClientListResponse>(
    '/admin/oauth-clients',
    { params },
  )
  return data
}

export async function approveOAuthClient(id: string, reason?: string) {
  const { data } = await apiClient.post(`/admin/oauth-clients/${id}/approve`, {
    reason: reason || null,
  })
  return data
}

export async function rejectOAuthClient(id: string, reason?: string) {
  const { data } = await apiClient.post(`/admin/oauth-clients/${id}/reject`, {
    reason: reason || null,
  })
  return data
}

export async function revokeOAuthClient(id: string): Promise<void> {
  await apiClient.delete(`/admin/oauth-clients/${id}`)
}
