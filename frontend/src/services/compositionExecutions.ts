/**
 * Composition Executions API client (B-0 chunk 11).
 *
 * Backed by the FastAPI router at /api/v1/compositions/executions
 * (B-0 chunk 10). All endpoints are JWT-protected and per-user
 * scoped on the server side; the UI does no extra auth.
 */

import axios, { type AxiosInstance } from 'axios'

const API_BASE = '/api/v1'

const STORAGE_KEYS = {
  ACCESS_TOKEN: 'bigmcp_access_token',
}

const api: AxiosInstance = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN)
  if (token) {
    config.headers = config.headers || {}
    ;(config.headers as Record<string, string>).Authorization = `Bearer ${token}`
  }
  return config
})

export type ExecutionStatus =
  | 'queued'
  | 'running'
  | 'suspended'
  | 'completed'
  | 'failed'
  | 'expired'
  | 'cancelled'

export const NON_TERMINAL_STATUSES: ExecutionStatus[] = [
  'queued',
  'running',
  'suspended',
]

export interface ExecutionSummary {
  id: string
  composition_id: string
  user_id: string
  organization_id: string
  parent_execution_id: string | null
  status: ExecutionStatus
  trigger: string
  cancel_requested: boolean
  started_at: string
  updated_at: string
  expires_at: string | null
  error: string | null
  current_step_id: string | null
  suspension_reason: string | null
}

export interface ExecutionStepEvent {
  id: string
  execution_id: string
  step_id: string
  event_type: string
  payload: Record<string, unknown> | null
  timestamp: string
}

export interface ExecutionDetail extends ExecutionSummary {
  state: Record<string, unknown>
  client_capabilities: Record<string, unknown> | null
  mcp_session_id: string | null
  result: Record<string, unknown> | null
  events: ExecutionStepEvent[]
}

export interface ExecutionListResponse {
  items: ExecutionSummary[]
  total: number
  limit: number
  offset: number
}

export interface ListParams {
  status?: ExecutionStatus[]
  includeTerminal?: boolean
  limit?: number
  offset?: number
}

export const executionsApi = {
  async list(params: ListParams = {}): Promise<ExecutionListResponse> {
    const query: Record<string, string> = {}
    if (params.status && params.status.length > 0) {
      query.status = params.status.join(',')
    }
    if (params.includeTerminal) query.include_terminal = 'true'
    if (params.limit !== undefined) query.limit = String(params.limit)
    if (params.offset !== undefined) query.offset = String(params.offset)
    const resp = await api.get<ExecutionListResponse>(
      '/compositions/executions',
      { params: query },
    )
    return resp.data
  },

  async get(executionId: string): Promise<ExecutionDetail> {
    const resp = await api.get<ExecutionDetail>(
      `/compositions/executions/${executionId}`,
    )
    return resp.data
  },

  async cancel(executionId: string): Promise<{
    execution_id: string
    cancel_requested: boolean
    detail: string
  }> {
    const resp = await api.post(
      `/compositions/executions/${executionId}/cancel`,
    )
    return resp.data
  },

  async resume(
    executionId: string,
    response: unknown,
  ): Promise<{ execution_id: string; status: ExecutionStatus }> {
    const resp = await api.post(
      `/compositions/executions/${executionId}/resume`,
      { response },
    )
    return resp.data
  },
}
