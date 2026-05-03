/**
 * Shared types for the Services workspace (catalog, pool, toolboxes).
 */

import type { ToolCardData } from './ToolCard'

export type DragOrigin = 'catalog' | 'pool' | 'toolbox'

export interface DragPayload {
  tool: ToolCardData
  origin: DragOrigin
  toolboxId?: string
}

export interface ToolboxSummary {
  id: string
  name: string
  description?: string | null
  color?: string | null
  visibility?: 'private' | 'organization'
  itemCount: number
  toolIds: Set<string>
}

export interface PoolState {
  poolSize: number
  compositionCount: number
}

export interface CatalogTool extends ToolCardData {
  serverId?: string | null
  inPool: boolean
}
