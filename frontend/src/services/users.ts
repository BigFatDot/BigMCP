/**
 * Admin users API client.
 *
 * Surfaces the lifecycle endpoints behind /api/v1/admin/users for the
 * UsersAdminPage. All calls require instance-admin privileges; the
 * backend returns 403 to non-admins which the page renders gracefully.
 */

import { apiClient } from './api'

export type UserStatus = 'active' | 'suspended' | 'deleted'

export interface AdminUser {
  id: string
  email: string
  name: string | null
  status: UserStatus
  status_changed_at: string | null
  status_reason: string | null
  deleted_at: string | null
  email_verified: boolean
  last_login_at: string | null
  tokens_revoked_at: string | null
  is_instance_admin: boolean
  created_at: string
}

export interface AdminUserListResponse {
  items: AdminUser[]
  total: number
  limit: number
  offset: number
}

export interface AdminUserListFilters {
  status?: UserStatus | ''
  search?: string
  limit?: number
  offset?: number
}

export async function listAdminUsers(
  filters: AdminUserListFilters = {},
): Promise<AdminUserListResponse> {
  const params = Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined && v !== ''),
  )
  const { data } = await apiClient.get<AdminUserListResponse>('/admin/users', { params })
  return data
}

export interface UserLifecycleResult {
  id: string
  email: string
  status: UserStatus
  status_changed_at: string | null
  status_reason: string | null
  deleted_at: string | null
}

async function lifecycleAction(
  id: string,
  action: 'suspend' | 'reactivate' | 'soft-delete',
  reason?: string,
): Promise<UserLifecycleResult> {
  const { data } = await apiClient.post<UserLifecycleResult>(
    `/admin/users/${id}/${action}`,
    { reason: reason || null },
  )
  return data
}

export const suspendUser = (id: string, reason?: string) =>
  lifecycleAction(id, 'suspend', reason)
export const reactivateUser = (id: string, reason?: string) =>
  lifecycleAction(id, 'reactivate', reason)
export const softDeleteUser = (id: string, reason?: string) =>
  lifecycleAction(id, 'soft-delete', reason)

export interface RevokeAllResult {
  user_id: string
  tokens_revoked_at: string
  api_keys_revoked: number
  refresh_tokens_revoked: number
}

export async function revokeAllSessions(
  id: string,
  reason?: string,
): Promise<RevokeAllResult> {
  const { data } = await apiClient.post<RevokeAllResult>(
    `/admin/users/${id}/revoke-all`,
    { reason: reason || null },
  )
  return data
}
