/**
 * Audit logs API client.
 *
 * Read-only client for the immutable audit trail. Only callable by
 * users flagged as instance admins; the backend enforces this with
 * require_instance_admin on /api/v1/admin/audit-logs.
 */

import { apiClient } from './api'

export interface AuditLog {
  id: string
  timestamp: string
  actor_id: string | null
  organization_id: string | null
  action: string
  resource_type: string
  resource_id: string | null
  ip_address: string | null
  user_agent: string | null
  details: Record<string, unknown> | null
  // Resolved labels enriched server-side by the list endpoint
  // (saves the UI a second round-trip).
  actor_email: string | null
  resource_label: string | null
}

export interface AuditLogListResponse {
  items: AuditLog[]
  total: number
  limit: number
  offset: number
}

export interface AuditLogFilters {
  actor_id?: string
  organization_id?: string
  action?: string
  resource_type?: string
  resource_id?: string
  ip_address?: string
  since?: string
  until?: string
  limit?: number
  offset?: number
}

export async function listAuditLogs(
  filters: AuditLogFilters = {},
): Promise<AuditLogListResponse> {
  const params = Object.fromEntries(
    Object.entries(filters).filter(([, value]) => value !== undefined && value !== ''),
  )
  const { data } = await apiClient.get<AuditLogListResponse>(
    '/admin/audit-logs',
    { params },
  )
  return data
}

export async function getAuditLog(id: string): Promise<AuditLog> {
  const { data } = await apiClient.get<AuditLog>(`/admin/audit-logs/${id}`)
  return data
}
