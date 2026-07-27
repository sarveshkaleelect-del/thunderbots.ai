export interface MarketplaceTemplate {
  id: string
  name: string
  description: string
  category: string
  industry: string
  difficulty: 'Beginner' | 'Intermediate' | 'Advanced'
  setup_time: string
  features: string[]
  icon: string
  featured: boolean
  added_at: string
}

export interface MarketplaceTemplateDetail extends MarketplaceTemplate {
  preview_nodes: unknown[]
  preview_edges: unknown[]
}

export interface ImportedWorkflow {
  id: string
  name: string
  description?: string
  status: string
  nodes: unknown[]
  edges: unknown[]
  canvas_state: { x: number; y: number; zoom: number }
  settings: Record<string, unknown>
  knowledge_base_id?: string | null
  created_at: string
  updated_at: string
}
