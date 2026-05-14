/**
 * Connected-apps API client (N2.4 / Story H).
 *
 * Wraps the user-facing endpoints that show and revoke OAuth grants
 * the user has approved. The corresponding instance-admin view of
 * OAuth clients lives in services/clientControl.ts.
 */

import { apiClient } from './api'

export type ConnectedAppRegistrationMethod =
  | 'dcr_open'
  | 'dcr_approved'
  | 'cimd'
  | 'manual_admin'
  | 'preloaded'

export interface ConnectedApp {
  client_uuid: string
  client_id: string
  name: string
  description: string | null
  cimd_url: string | null
  registration_method: ConnectedAppRegistrationMethod
  session_count: number
  first_authorized_at: string | null
  last_seen_at: string | null
}

export interface ConnectedAppsResponse {
  connected_apps: ConnectedApp[]
}

export async function listConnectedApps(): Promise<ConnectedApp[]> {
  const { data } = await apiClient.get<ConnectedAppsResponse>(
    '/auth/connected-apps',
  )
  return data.connected_apps
}

export async function revokeConnectedApp(clientUuid: string): Promise<void> {
  await apiClient.delete(`/auth/connected-apps/${clientUuid}`)
}
