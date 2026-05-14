/**
 * Persistent pool API client (Phase 3).
 *
 * Two surfaces:
 *
 * - /admin/org/default-pool — instance admin manages the org's default
 *   pool. Inherited by every user at MCP-connect time, so first-time
 *   agents see a populated catalog instead of an empty pool.
 *
 * - /pool/pin — any authenticated user manages their personal pinned
 *   entries. Pins survive across sessions on top of the org defaults.
 */

import { apiClient } from './api'

export interface OrgDefaultPoolEntry {
  id: string
  tool_id: string | null
  composition_id: string | null
  position: number
  added_by_user_id: string | null
  updated_at: string
}

export interface OrgDefaultPoolListResponse {
  organization_id: string
  entries: OrgDefaultPoolEntry[]
}

export interface UserPin {
  id: string
  tool_id: string | null
  composition_id: string | null
  last_used_at: string | null
  created_at: string
}

export interface UserPinListResponse {
  user_id: string
  pins: UserPin[]
}

export interface PoolEntryRef {
  tool_id?: string
  composition_id?: string
}

export const orgDefaultPoolApi = {
  async list(): Promise<OrgDefaultPoolListResponse> {
    const { data } = await apiClient.get<OrgDefaultPoolListResponse>(
      '/admin/org/default-pool',
    )
    return data
  },
  async add(
    ref: PoolEntryRef & { position?: number },
  ): Promise<OrgDefaultPoolEntry> {
    const { data } = await apiClient.post<OrgDefaultPoolEntry>(
      '/admin/org/default-pool',
      ref,
    )
    return data
  },
  async remove(entryId: string): Promise<void> {
    await apiClient.delete(`/admin/org/default-pool/${entryId}`)
  },
}

export const userPinApi = {
  async list(): Promise<UserPinListResponse> {
    const { data } = await apiClient.get<UserPinListResponse>('/pool/pin')
    return data
  },
  async pin(ref: PoolEntryRef): Promise<UserPin> {
    const { data } = await apiClient.post<UserPin>('/pool/pin', ref)
    return data
  },
  async unpin(pinId: string): Promise<void> {
    await apiClient.delete(`/pool/pin/${pinId}`)
  },
}
