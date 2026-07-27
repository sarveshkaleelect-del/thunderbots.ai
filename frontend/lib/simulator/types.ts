// ============================================================
// AI Conversation Simulator — shared types
// Independent, optional, read-only module: it only ever reads
// nodes/edges already in the canvas store and never mutates the
// workflow, calls the AI Agent, or touches the Knowledge Base.
// ============================================================

export type SimulationStage =
  | 'understanding'
  | 'simulating'
  | 'testing_ai'
  | 'validating'
  | 'generating_report'

export const SIMULATION_STAGE_ORDER: SimulationStage[] = [
  'understanding', 'simulating', 'testing_ai', 'validating', 'generating_report',
]

export const SIMULATION_STAGE_LABELS: Record<SimulationStage, string> = {
  understanding: 'Understanding Workflow...',
  simulating: 'Simulating Conversations...',
  testing_ai: 'Testing AI Responses...',
  validating: 'Validating Workflow...',
  generating_report: 'Generating Report...',
}

export interface SimNodeRef {
  id: string
  type: string
  label: string
}

export interface SimulatedPath {
  nodeIds: string[]
  outcome: 'success' | 'dead_end' | 'incomplete'
  reason?: string
}

export type DeploymentReadiness = 'ready' | 'needs_attention' | 'not_ready'

export interface SimulationReport {
  generatedAt: string
  workflowId: string | null

  // Headline metrics
  successRate: number            // 0-100
  conversationsTested: number
  workflowCoverage: number       // 0-100, % of nodes reached by simulation/reachability

  // Structural analysis
  totalNodes: number
  reachableNodeCount: number
  unreachableNodes: SimNodeRef[]
  endNodesCount: number
  aiAgentNodesCount: number
  multipleChoiceNodesCount: number

  // Path analysis
  deadEndPaths: { node: SimNodeRef; reason: string }[]
  failedPaths: { path: SimNodeRef[]; reason: string }[]
  confusingOptions: { node: SimNodeRef; issue: string }[]
  missingTransitions: { node: SimNodeRef; issue: string }[]

  // Knowledge Base
  knowledgeBaseUsage: {
    enabled: boolean
    nodeCount: number
    nodes: SimNodeRef[]
  }

  aiSuggestions: string[]
  deploymentReadiness: DeploymentReadiness
  readinessLabel: string
}
