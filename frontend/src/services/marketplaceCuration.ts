/**
 * Org-scoped marketplace curation API client (Phase 2).
 *
 * Wraps the instance-admin endpoints under /admin/org/marketplace-curation
 * for managing which marketplace servers are approved/featured/hidden in
 * the caller's org.
 */

import { apiClient } from './api'

export type CurationStatus = 'approved' | 'featured' | 'hidden'

export interface CurationRule {
  server_id: string
  status: CurationStatus
  featured_order: number | null
  notes: string | null
  curated_by_user_id: string | null
  updated_at: string
}

export interface CurationListResponse {
  organization_id: string
  rules: CurationRule[]
  counts: {
    approved: number
    featured: number
    hidden: number
  }
}

export interface CurationUpdateItem {
  server_id: string
  // null removes any existing rule (back to default = visible)
  status: CurationStatus | null
  featured_order?: number | null
  notes?: string | null
}

export async function listCurationRules(): Promise<CurationListResponse> {
  const { data } = await apiClient.get<CurationListResponse>(
    '/admin/org/marketplace-curation',
  )
  return data
}

export async function batchUpsertCuration(
  items: CurationUpdateItem[],
): Promise<CurationListResponse> {
  const { data } = await apiClient.put<CurationListResponse>(
    '/admin/org/marketplace-curation',
    { items },
  )
  return data
}
