/**
 * Shared axios instance for the BigMCP API.
 *
 * Centralises:
 * - Base URL (/api/v1)
 * - JWT injection from localStorage (same key as AuthContext)
 * - 401 → trigger logout on the AuthContext side
 *
 * Existing services like marketplace.ts use plain axios calls; new
 * services should prefer this shared instance to keep auth handling
 * consistent. This file is intentionally minimal — no auto-refresh
 * yet (AuthContext handles that on cold reload) so we don't fight
 * the existing flow.
 */

import axios, { AxiosError, type AxiosRequestConfig } from 'axios'

const STORAGE_KEY_ACCESS_TOKEN = 'bigmcp_access_token'

export const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
})

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(STORAGE_KEY_ACCESS_TOKEN)
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    // 401 from the API means our local JWT is gone / expired. Surface
    // the error to the caller — AuthContext owns the logout flow.
    return Promise.reject(error)
  },
)

/**
 * Convenience helper for callers that just want the parsed body.
 * Throws the original AxiosError so React-Query / error boundaries
 * can react idiomatically.
 */
export async function apiGet<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const { data } = await apiClient.get<T>(url, config)
  return data
}

/**
 * Re-export the canonical error parser.
 *
 * `extractApiError` lives in services/marketplace.ts (which is older
 * and has the most callers). We re-export it from the shared HTTP
 * module so that future services / contexts can import it from one
 * stable place without dragging in the whole marketplace barrel.
 *
 * Canonical implementation: services/marketplace.ts
 */
export { extractApiError } from './marketplace'
