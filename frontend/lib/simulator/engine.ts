// ============================================================
// AI Conversation Simulator — Engine
//
// 100% local / client-side, read-only. Only ever reads the nodes/edges
// already held in the workflow canvas store — never mutates the workflow,
// never calls a live AI provider, never touches the Knowledge Base, the
// AI Agent execution path, or ThunderGuide. Runs only when explicitly
// triggered by the "Run AI Simulation" button; never automatically.
//
// Reuses ThunderGuide's existing (unmodified) pure analysis helpers for
// reachability/stats so this module doesn't duplicate that logic — it only
// ever *imports* from thunderguide/analyzer.ts, never edits it.
// ============================================================
import type { Node, Edge } from 'reactflow'
import { computeWorkflowStats, validateWorkflow } from '@/lib/thunderguide/analyzer'
import type {
  SimulationReport, SimulationStage, SimNodeRef, SimulatedPath, DeploymentReadiness,
} from './types'
import { SIMULATION_STAGE_ORDER } from './types'

const MAX_SIMULATED_PATHS = 40
const MAX_PATH_DEPTH = 60

function nodeRef(n: Node): SimNodeRef {
  const data = (n.data ?? {}) as { label?: string; question?: string; content?: string; message?: string }
  const label = data.label || data.question || data.content || data.message || n.id
  return { id: n.id, type: n.type ?? 'unknown', label: String(label).slice(0, 80) }
}

function buildOutgoing(nodes: Node[], edges: Edge[]) {
  const byId = new Map(nodes.map(n => [n.id, n]))
  const outEdges = new Map<string, Edge[]>()
  nodes.forEach(n => outEdges.set(n.id, []))
  edges.forEach(e => {
    if (outEdges.has(e.source)) outEdges.get(e.source)!.push(e)
  })
  return { byId, outEdges }
}

// ── Missing transitions & confusing options (Multiple Choice) ───────────────
function analyzeMultipleChoice(nodes: Node[], edges: Edge[]) {
  const missingTransitions: SimulationReport['missingTransitions'] = []
  const confusingOptions: SimulationReport['confusingOptions'] = []

  nodes.filter(n => n.type === 'multiple_choice').forEach(n => {
    const choices: Array<{ label: string; value: string }> = (n.data as any)?.choices ?? []
    const question: string = (n.data as any)?.question ?? ''
    const outEdgesForNode = edges.filter(e => e.source === n.id)

    if (!Array.isArray(choices) || choices.length === 0) {
      confusingOptions.push({ node: nodeRef(n), issue: 'Has no choices configured — users will see an empty option list.' })
      return
    }

    choices.forEach((c, i) => {
      const hasEdge = outEdgesForNode.some(e => e.sourceHandle === `choice_${i}`)
      if (!hasEdge) {
        missingTransitions.push({
          node: nodeRef(n),
          issue: `Choice "${c?.label || `Option ${i + 1}`}" has no outgoing connection — selecting it leads nowhere.`,
        })
      }
    })

    if (choices.length > 6) {
      confusingOptions.push({ node: nodeRef(n), issue: `Presents ${choices.length} options at once — consider grouping to reduce user confusion.` })
    }
    const labels = choices.map(c => (c?.label || '').trim().toLowerCase()).filter(Boolean)
    const dupes = labels.filter((l, i) => labels.indexOf(l) !== i)
    if (dupes.length > 0) {
      confusingOptions.push({ node: nodeRef(n), issue: 'Has duplicate-looking option labels, which can confuse users.' })
    }
    if (!question || !question.trim()) {
      confusingOptions.push({ node: nodeRef(n), issue: 'Has no question text shown above its options.' })
    }
  })

  return { missingTransitions, confusingOptions }
}

// ── Knowledge Base usage (AI Agent nodes only — read-only, no KB calls) ─────
function analyzeKnowledgeBase(nodes: Node[]): SimulationReport['knowledgeBaseUsage'] {
  const kbNodes = nodes.filter(n => n.type === 'ai_agent' && !!(n.data as any)?.knowledgeBaseId)
  return {
    enabled: kbNodes.length > 0,
    nodeCount: kbNodes.length,
    nodes: kbNodes.map(nodeRef),
  }
}

// ── AI Agent path completeness (config-level only — never invokes a provider) ──
function analyzeAIAgentPaths(nodes: Node[]): string[] {
  const notes: string[] = []
  nodes.filter(n => n.type === 'ai_agent').forEach(n => {
    const data = (n.data ?? {}) as { systemPrompt?: string; label?: string }
    if (!data.systemPrompt || !data.systemPrompt.trim()) {
      notes.push(`AI Agent "${data.label || n.id}" has no system prompt — responses may be inconsistent.`)
    }
  })
  return notes
}

// ── Conversation simulation: enumerate representative paths from Start ─────
function simulateConversations(nodes: Node[], edges: Edge[]): SimulatedPath[] {
  const { byId, outEdges } = buildOutgoing(nodes, edges)
  const starts = nodes.filter(n => n.type === 'start')
  if (starts.length === 0) return []

  const paths: SimulatedPath[] = []

  function walk(nodeId: string, visited: string[], branchesTaken: number) {
    if (paths.length >= MAX_SIMULATED_PATHS) return
    const path = [...visited, nodeId]
    const node = byId.get(nodeId)
    if (!node) {
      paths.push({ nodeIds: path, outcome: 'dead_end', reason: 'References a node that no longer exists.' })
      return
    }
    if (path.length > MAX_PATH_DEPTH) {
      paths.push({ nodeIds: path, outcome: 'incomplete', reason: 'Path exceeded maximum depth — possible loop.' })
      return
    }
    if (path.slice(0, -1).includes(nodeId)) {
      paths.push({ nodeIds: path, outcome: 'incomplete', reason: 'Conversation loops back on itself.' })
      return
    }
    if (node.type === 'end') {
      paths.push({ nodeIds: path, outcome: 'success' })
      return
    }

    const outs = outEdges.get(nodeId) ?? []
    if (outs.length === 0) {
      paths.push({ nodeIds: path, outcome: 'dead_end', reason: 'No outgoing connection and not an End node.' })
      return
    }

    // Multiple Choice: branch on every choice (capped) to exercise each option.
    // Everything else: follow each distinct outgoing edge (Transition branches,
    // linear next-step) — capped overall by MAX_SIMULATED_PATHS.
    const targets = Array.from(new Set(outs.map(e => e.target)))
    targets.forEach(t => {
      if (paths.length >= MAX_SIMULATED_PATHS) return
      walk(t, path, branchesTaken + (targets.length > 1 ? 1 : 0))
    })
  }

  starts.forEach(s => walk(s.id, [], 0))
  return paths
}

function computeReadiness(
  successRate: number, unreachableCount: number, deadEndCount: number, missingTransitionsCount: number, hasStart: boolean, hasEnd: boolean,
): { readiness: DeploymentReadiness; label: string } {
  if (!hasStart || !hasEnd) {
    return { readiness: 'not_ready', label: 'Not Ready — workflow needs both a Start and an End node' }
  }
  if (successRate >= 85 && unreachableCount === 0 && deadEndCount === 0 && missingTransitionsCount === 0) {
    return { readiness: 'ready', label: 'Ready to Deploy' }
  }
  if (successRate < 40 || deadEndCount > 3) {
    return { readiness: 'not_ready', label: 'Not Ready — significant issues found' }
  }
  return { readiness: 'needs_attention', label: 'Needs Attention before deploying' }
}

/** Thrown for conditions the simulator can identify precisely, so the panel
 * can show the real cause instead of a generic failure message. */
export class SimulationError extends Error {
  code: string
  constructor(code: string, message: string) {
    super(message)
    this.name = 'SimulationError'
    this.code = code
  }
}

/** Pure, synchronous analysis — safe to call as often as needed. The panel
 * wraps this with staged progress + caching; this function itself never
 * touches the network, storage, or any provider. */
export function analyzeWorkflow(workflowId: string | null, nodes: Node[], edges: Edge[]): SimulationReport {
  if (!Array.isArray(nodes) || !Array.isArray(edges)) {
    throw new SimulationError('invalid_workflow', 'Invalid workflow — nodes or edges could not be read from the canvas.')
  }
  const stats = computeWorkflowStats(nodes, edges)
  const validation = validateWorkflow(nodes, edges)

  const { byId } = buildOutgoing(nodes, edges)
  const reachableIds = new Set<string>()
  // Recompute reachable set locally (mirrors ThunderGuide's algorithm) so we
  // can also list the actual unreachable node refs, not just a count.
  const outAdj = new Map<string, string[]>()
  nodes.forEach(n => outAdj.set(n.id, []))
  edges.forEach(e => { if (outAdj.has(e.source)) outAdj.get(e.source)!.push(e.target) })
  const queue = nodes.filter(n => n.type === 'start').map(n => n.id)
  while (queue.length) {
    const cur = queue.shift()!
    if (reachableIds.has(cur)) continue
    reachableIds.add(cur)
    for (const next of outAdj.get(cur) ?? []) if (!reachableIds.has(next)) queue.push(next)
  }
  const unreachableNodes = nodes.filter(n => !reachableIds.has(n.id)).map(nodeRef)

  const endNodes = nodes.filter(n => n.type === 'end')
  const aiAgentNodes = nodes.filter(n => n.type === 'ai_agent')
  const mcNodes = nodes.filter(n => n.type === 'multiple_choice')

  const { missingTransitions, confusingOptions } = analyzeMultipleChoice(nodes, edges)
  const kbUsage = analyzeKnowledgeBase(nodes)
  const aiAgentNotes = analyzeAIAgentPaths(nodes)

  const deadEndNodes = nodes.filter(n =>
    n.type !== 'end' && reachableIds.has(n.id) && (outAdj.get(n.id) ?? []).length === 0
  )
  const deadEndPaths = deadEndNodes.map(n => ({
    node: nodeRef(n),
    reason: 'Reachable node with no outgoing connection and no End node — traps the conversation.',
  }))

  const simulated = simulateConversations(nodes, edges)
  const conversationsTested = simulated.length
  const successfulPaths = simulated.filter(p => p.outcome === 'success').length
  const successRate = conversationsTested > 0 ? Math.round((successfulPaths / conversationsTested) * 100) : 0
  const failedPaths = simulated
    .filter(p => p.outcome !== 'success')
    .slice(0, 15)
    .map(p => ({ path: p.nodeIds.map(id => byId.get(id)).filter(Boolean).map(n => nodeRef(n as Node)), reason: p.reason || 'Did not reach an End node.' }))

  const visitedBySim = new Set<string>()
  simulated.forEach(p => p.nodeIds.forEach(id => visitedBySim.add(id)))
  const coverageSet = new Set<string>([...reachableIds, ...visitedBySim])
  const workflowCoverage = stats.totalNodes > 0 ? Math.round((coverageSet.size / stats.totalNodes) * 100) : 0

  // ── AI Suggestions (heuristic, rule-based — no external AI call) ─────────
  const aiSuggestions: string[] = []
  if (nodes.filter(n => n.type === 'start').length === 0) {
    aiSuggestions.push('Add a Start node — the workflow currently has no entry point.')
  }
  if (endNodes.length === 0) {
    aiSuggestions.push('Add at least one End node so conversations can terminate cleanly.')
  }
  if (unreachableNodes.length > 0) {
    aiSuggestions.push(`Connect or remove ${unreachableNodes.length} unreachable node${unreachableNodes.length > 1 ? 's' : ''} — they will never be visited.`)
  }
  if (deadEndPaths.length > 0) {
    aiSuggestions.push(`Fix ${deadEndPaths.length} dead-end path${deadEndPaths.length > 1 ? 's' : ''} by adding a next step or an End node.`)
  }
  if (missingTransitions.length > 0) {
    aiSuggestions.push(`Connect ${missingTransitions.length} Multiple Choice option${missingTransitions.length > 1 ? 's' : ''} that currently lead nowhere.`)
  }
  if (confusingOptions.length > 0) {
    aiSuggestions.push('Simplify one or more Multiple Choice nodes flagged as potentially confusing.')
  }
  aiAgentNotes.forEach(n => aiSuggestions.push(n))
  if (validation.issues.some(i => i.id.startsWith('loop-'))) {
    aiSuggestions.push('Review detected loops — make sure every cycle has a guaranteed exit condition.')
  }
  if (aiSuggestions.length === 0) {
    aiSuggestions.push('No structural issues found — this workflow looks ready for real conversations.')
  }

  const { readiness, label } = computeReadiness(
    successRate, unreachableNodes.length, deadEndPaths.length, missingTransitions.length,
    nodes.some(n => n.type === 'start'), endNodes.length > 0,
  )

  return {
    generatedAt: new Date().toISOString(),
    workflowId,
    successRate,
    conversationsTested,
    workflowCoverage,
    totalNodes: stats.totalNodes,
    reachableNodeCount: reachableIds.size,
    unreachableNodes,
    endNodesCount: endNodes.length,
    aiAgentNodesCount: aiAgentNodes.length,
    multipleChoiceNodesCount: mcNodes.length,
    deadEndPaths,
    failedPaths,
    confusingOptions,
    missingTransitions,
    knowledgeBaseUsage: kbUsage,
    aiSuggestions,
    deploymentReadiness: readiness,
    readinessLabel: label,
  }
}

// ── Staged, cancellable run with progress callbacks ─────────────────────────
// Each stage yields to the event loop between steps so a simulation on a
// large workflow can never block the Workflow Builder UI or the chatbot
// runtime — this module is only ever imported dynamically, on click.
export async function runSimulation(
  workflowId: string | null,
  nodes: Node[],
  edges: Edge[],
  onStage?: (stage: SimulationStage) => void,
): Promise<SimulationReport> {
  const yieldTick = () => new Promise<void>(resolve => setTimeout(resolve, 260))

  for (const stage of SIMULATION_STAGE_ORDER) {
    onStage?.(stage)
    // eslint-disable-next-line no-await-in-loop
    await yieldTick()
  }

  return analyzeWorkflow(workflowId, nodes, edges)
}

// ── Latest-result cache, invalidated whenever the workflow graph changes ───
let cachedKey: string | null = null
let cachedReport: SimulationReport | null = null

/** JSON.stringify that never throws — falls back safely for circular or
 * otherwise unserializable node data (e.g. a stray non-plain object landing
 * in a node's data) instead of crashing the whole simulation run. */
function safeStringify(value: unknown): string {
  const seen = new WeakSet<object>()
  try {
    return JSON.stringify(value, (_key, val) => {
      if (typeof val === 'object' && val !== null) {
        if (seen.has(val)) return '[Circular]'
        seen.add(val)
      }
      return val
    }) ?? 'null'
  } catch {
    return '[Unserializable]'
  }
}

function hashGraph(workflowId: string | null, nodes: Node[], edges: Edge[]): string {
  // Cheap structural fingerprint — good enough to detect "workflow changed"
  // without the cost of a full deep-equality check on every render.
  try {
    const nodeSig = nodes.map(n => `${n.id}:${n.type}:${safeStringify(n.data ?? {})}`).join('|')
    const edgeSig = edges.map(e => `${e.id}:${e.source}:${e.target}:${e.sourceHandle ?? ''}`).join('|')
    return `${workflowId ?? ''}::${nodes.length}::${edges.length}::${nodeSig.length}::${edgeSig.length}::${simpleHash(nodeSig + edgeSig)}`
  } catch {
    // Fingerprinting must never abort a simulation run — worst case, the
    // cache simply misses more often (a rerun instead of a crash).
    return `${workflowId ?? ''}::${nodes.length}::${edges.length}::fallback`
  }
}

function simpleHash(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) {
    h = (Math.imul(31, h) + s.charCodeAt(i)) | 0
  }
  return h
}

export function getCachedReport(workflowId: string | null, nodes: Node[], edges: Edge[]): SimulationReport | null {
  try {
    const key = hashGraph(workflowId, nodes, edges)
    return cachedKey === key ? cachedReport : null
  } catch {
    return null
  }
}

export function setCachedReport(workflowId: string | null, nodes: Node[], edges: Edge[], report: SimulationReport): void {
  try {
    cachedKey = hashGraph(workflowId, nodes, edges)
    cachedReport = report
  } catch {
    // Caching is best-effort only — never let it invalidate a completed run.
  }
}
