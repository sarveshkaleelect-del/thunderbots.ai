// ============================================================
// ThunderGuide — Free Analysis Engine
// 100% local / client-side. No network calls, no API keys.
// Operates purely on the current nodes/edges already held in
// the workflow canvas store — never touches the backend.
// ============================================================
import type { Node, Edge } from 'reactflow'
import type {
  WorkflowIssue, ValidationResult, WorkflowStats,
  HealthScoreResult, OptimizationSuggestion,
} from './types'

function buildAdjacency(nodes: Node[], edges: Edge[]) {
  const outMap = new Map<string, string[]>()
  const inMap = new Map<string, string[]>()
  const nodeIds = new Set(nodes.map(n => n.id))

  nodes.forEach(n => { outMap.set(n.id, []); inMap.set(n.id, []) })

  edges.forEach(e => {
    if (outMap.has(e.source)) outMap.get(e.source)!.push(e.target)
    if (inMap.has(e.target)) inMap.get(e.target)!.push(e.source)
  })

  return { outMap, inMap, nodeIds }
}

function findStartNodes(nodes: Node[]): Node[] {
  return nodes.filter(n => n.type === 'start')
}

function findEndNodes(nodes: Node[]): Node[] {
  return nodes.filter(n => n.type === 'end')
}

/** BFS reachability from all start nodes. */
function reachableFromStart(nodes: Node[], edges: Edge[]): Set<string> {
  const { outMap } = buildAdjacency(nodes, edges)
  const starts = findStartNodes(nodes)
  const visited = new Set<string>()
  const queue = [...starts.map(s => s.id)]
  while (queue.length) {
    const cur = queue.shift()!
    if (visited.has(cur)) continue
    visited.add(cur)
    for (const next of outMap.get(cur) ?? []) {
      if (!visited.has(next)) queue.push(next)
    }
  }
  return visited
}

// ── 1. Detect Broken Connections ──────────────────────────────
export function detectBrokenConnections(nodes: Node[], edges: Edge[]): WorkflowIssue[] {
  const { nodeIds } = buildAdjacency(nodes, edges)
  const issues: WorkflowIssue[] = []
  edges.forEach(e => {
    const missingSource = !nodeIds.has(e.source)
    const missingTarget = !nodeIds.has(e.target)
    if (missingSource || missingTarget) {
      issues.push({
        id: `broken-${e.id}`,
        severity: 'critical',
        title: 'Broken connection',
        description: `Connection "${e.id}" references a ${missingSource ? 'source' : 'target'} node that no longer exists.`,
        edgeIds: [e.id],
      })
    }
  })
  return issues
}

// ── 2. Detect Missing End Nodes ───────────────────────────────
export function detectMissingEndNodes(nodes: Node[], edges: Edge[]): WorkflowIssue[] {
  const issues: WorkflowIssue[] = []
  const endNodes = findEndNodes(nodes)

  if (endNodes.length === 0) {
    issues.push({
      id: 'no-end-node',
      severity: 'critical',
      title: 'No End node in workflow',
      description: 'This workflow has no End node. Conversations may never terminate cleanly.',
    })
    return issues
  }

  const reachable = reachableFromStart(nodes, edges)
  const unreachableEnds = endNodes.filter(n => !reachable.has(n.id))
  if (unreachableEnds.length > 0) {
    issues.push({
      id: 'unreachable-end-node',
      severity: 'warning',
      title: 'End node unreachable from Start',
      description: `${unreachableEnds.length} End node${unreachableEnds.length > 1 ? 's are' : ' is'} not reachable from any Start node.`,
      nodeIds: unreachableEnds.map(n => n.id),
    })
  }

  // Leaf nodes (no outgoing edges) that aren't End nodes are dead ends
  const { outMap } = buildAdjacency(nodes, edges)
  const deadEnds = nodes.filter(n =>
    n.type !== 'end' && (outMap.get(n.id) ?? []).length === 0 && reachable.has(n.id)
  )
  if (deadEnds.length > 0) {
    issues.push({
      id: 'dead-end-nodes',
      severity: 'warning',
      title: 'Dead-end nodes detected',
      description: `${deadEnds.length} reachable node${deadEnds.length > 1 ? 's have' : ' has'} no outgoing connection and isn't an End node, which will trap the conversation.`,
      nodeIds: deadEnds.map(n => n.id),
    })
  }

  return issues
}

// ── 3. Detect Infinite Loops ──────────────────────────────────
export function detectInfiniteLoops(nodes: Node[], edges: Edge[]): WorkflowIssue[] {
  const { outMap } = buildAdjacency(nodes, edges)
  const issues: WorkflowIssue[] = []

  const WHITE = 0, GRAY = 1, BLACK = 2
  const color = new Map<string, number>()
  nodes.forEach(n => color.set(n.id, WHITE))
  const cyclesFound: string[][] = []

  function dfs(nodeId: string, stack: string[]) {
    color.set(nodeId, GRAY)
    stack.push(nodeId)
    for (const next of outMap.get(nodeId) ?? []) {
      const c = color.get(next)
      if (c === GRAY) {
        // found a cycle — slice the stack from where `next` first appeared
        const idx = stack.indexOf(next)
        cyclesFound.push(stack.slice(idx >= 0 ? idx : 0).concat(next))
      } else if (c === WHITE) {
        dfs(next, stack)
      }
    }
    stack.pop()
    color.set(nodeId, BLACK)
  }

  nodes.forEach(n => {
    if (color.get(n.id) === WHITE) dfs(n.id, [])
  })

  // A cycle is only truly "infinite" risk if none of the nodes in it are a
  // Transition node (which can carry a condition that eventually exits) —
  // still flag it, but severity differs.
  cyclesFound.forEach((cycle, i) => {
    const hasTransition = cycle.some(id => nodes.find(n => n.id === id)?.type === 'transition')
    issues.push({
      id: `loop-${i}`,
      severity: hasTransition ? 'warning' : 'critical',
      title: hasTransition ? 'Potential loop with no guaranteed exit' : 'Infinite loop detected',
      description: hasTransition
        ? 'A cycle exists between these nodes. Make sure at least one Transition condition can break out of the loop.'
        : 'These nodes form a closed cycle with no Transition or End node to break out — the conversation can loop forever.',
      nodeIds: Array.from(new Set(cycle)),
    })
  })

  return issues
}

// ── 4. Detect Unused Nodes ────────────────────────────────────
export function detectUnusedNodes(nodes: Node[], edges: Edge[]): WorkflowIssue[] {
  const reachable = reachableFromStart(nodes, edges)
  const { inMap, outMap } = buildAdjacency(nodes, edges)
  const issues: WorkflowIssue[] = []

  const unused = nodes.filter(n => {
    if (n.type === 'start') return false
    const noIncoming = (inMap.get(n.id) ?? []).length === 0
    const noOutgoing = (outMap.get(n.id) ?? []).length === 0
    const isUnreachable = !reachable.has(n.id)
    // Fully isolated (no edges at all) or unreachable from any Start
    return (noIncoming && noOutgoing) || isUnreachable
  })

  if (unused.length > 0) {
    issues.push({
      id: 'unused-nodes',
      severity: 'info',
      title: 'Unused nodes found',
      description: `${unused.length} node${unused.length > 1 ? 's are' : ' is'} disconnected or unreachable from Start and will never run.`,
      nodeIds: unused.map(n => n.id),
    })
  }

  return issues
}

// ── Master validator — combines all free checks ───────────────
export function validateWorkflow(nodes: Node[], edges: Edge[]): ValidationResult {
  const issues: WorkflowIssue[] = []

  if (nodes.length === 0) {
    return {
      valid: false,
      issues: [{
        id: 'empty-workflow',
        severity: 'critical',
        title: 'Workflow is empty',
        description: 'Add a Start node to begin building your workflow.',
      }],
    }
  }

  const starts = findStartNodes(nodes)
  if (starts.length === 0) {
    issues.push({
      id: 'no-start-node',
      severity: 'critical',
      title: 'No Start node',
      description: 'Every workflow needs exactly one Start node as its entry point.',
    })
  } else if (starts.length > 1) {
    issues.push({
      id: 'multiple-start-nodes',
      severity: 'warning',
      title: 'Multiple Start nodes',
      description: `Found ${starts.length} Start nodes. Only one entry point is recommended to avoid ambiguous behavior.`,
      nodeIds: starts.map(n => n.id),
    })
  }

  issues.push(...detectBrokenConnections(nodes, edges))
  issues.push(...detectMissingEndNodes(nodes, edges))
  issues.push(...detectInfiniteLoops(nodes, edges))
  issues.push(...detectUnusedNodes(nodes, edges))

  // Node-level data sanity checks (still free / local)
  nodes.forEach(n => {
    if (n.type === 'multiple_choice') {
      const choices = (n.data as { choices?: unknown[] })?.choices ?? []
      if (!Array.isArray(choices) || choices.length === 0) {
        issues.push({
          id: `empty-choices-${n.id}`,
          severity: 'warning',
          title: 'Multiple Choice node has no options',
          description: 'This node presents no choices for the user to select.',
          nodeIds: [n.id],
        })
      }
    }
    if (n.type === 'ai_agent') {
      const sp = (n.data as { systemPrompt?: string })?.systemPrompt
      if (!sp || !sp.trim()) {
        issues.push({
          id: `empty-prompt-${n.id}`,
          severity: 'info',
          title: 'AI Agent node has no system prompt',
          description: 'This AI Agent will fall back to generic behavior without a system prompt.',
          nodeIds: [n.id],
        })
      }
    }
    if (n.type === 'transition') {
      const conditions = (n.data as { conditions?: unknown[] })?.conditions ?? []
      if (!Array.isArray(conditions) || conditions.length === 0) {
        issues.push({
          id: `empty-conditions-${n.id}`,
          severity: 'warning',
          title: 'Transition node has no conditions',
          description: 'This Transition node will never route anywhere without at least one condition.',
          nodeIds: [n.id],
        })
      }
    }
  })

  const criticalCount = issues.filter(i => i.severity === 'critical').length
  return { valid: criticalCount === 0, issues }
}

// ── 5. Workflow Statistics ────────────────────────────────────
export function computeWorkflowStats(nodes: Node[], edges: Edge[]): WorkflowStats {
  const { outMap } = buildAdjacency(nodes, edges)
  const nodesByType: Record<string, number> = {}
  nodes.forEach(n => {
    const t = n.type ?? 'unknown'
    nodesByType[t] = (nodesByType[t] ?? 0) + 1
  })

  const outDegrees = nodes.map(n => (outMap.get(n.id) ?? []).length)
  const avgOutDegree = nodes.length ? outDegrees.reduce((a, b) => a + b, 0) / nodes.length : 0
  const branchingNodes = nodes.filter(n => (outMap.get(n.id) ?? []).length > 1).length

  const reachable = reachableFromStart(nodes, edges)
  const isolatedNodes = nodes.filter(n => {
    const { inMap } = buildAdjacency(nodes, edges)
    return (inMap.get(n.id) ?? []).length === 0 && (outMap.get(n.id) ?? []).length === 0
  }).length

  // Longest path (max depth) via memoized DFS — guards against cycles
  const memo = new Map<string, number>()
  const visiting = new Set<string>()
  function depth(id: string): number {
    if (memo.has(id)) return memo.get(id)!
    if (visiting.has(id)) return 0 // cycle guard
    visiting.add(id)
    const children = outMap.get(id) ?? []
    const d = children.length === 0 ? 1 : 1 + Math.max(...children.map(depth))
    visiting.delete(id)
    memo.set(id, d)
    return d
  }
  const maxDepth = nodes.length ? Math.max(...nodes.map(n => depth(n.id))) : 0

  return {
    totalNodes: nodes.length,
    totalEdges: edges.length,
    nodesByType,
    startNodes: nodesByType['start'] ?? 0,
    endNodes: nodesByType['end'] ?? 0,
    aiAgentNodes: nodesByType['ai_agent'] ?? 0,
    branchingNodes,
    avgOutDegree: Math.round(avgOutDegree * 100) / 100,
    maxDepth,
    isolatedNodes,
    reachableNodes: reachable.size,
    unreachableNodes: Math.max(0, nodes.length - reachable.size),
  }
}

// ── 6. Workflow Health Score ──────────────────────────────────
export function computeHealthScore(nodes: Node[], edges: Edge[]): HealthScoreResult {
  const validation = validateWorkflow(nodes, edges)
  const stats = computeWorkflowStats(nodes, edges)
  const breakdown: HealthScoreResult['breakdown'] = []

  // Structure (30 pts): has exactly one start, at least one end
  let structurePts = 0
  if (stats.startNodes === 1) structurePts += 15
  else if (stats.startNodes > 1) structurePts += 5
  if (stats.endNodes >= 1) structurePts += 15
  breakdown.push({ label: 'Structure (Start/End)', points: structurePts, max: 30 })

  // Connectivity (25 pts): reachability ratio
  const connRatio = stats.totalNodes ? stats.reachableNodes / stats.totalNodes : 0
  const connPts = Math.round(connRatio * 25)
  breakdown.push({ label: 'Connectivity', points: connPts, max: 25 })

  // No broken connections (15 pts)
  const brokenCount = validation.issues.filter(i => i.id.startsWith('broken-')).length
  const brokenPts = brokenCount === 0 ? 15 : Math.max(0, 15 - brokenCount * 5)
  breakdown.push({ label: 'No broken connections', points: brokenPts, max: 15 })

  // No unsafe loops (15 pts)
  const loopIssues = validation.issues.filter(i => i.id.startsWith('loop-'))
  const criticalLoops = loopIssues.filter(i => i.severity === 'critical').length
  const loopPts = criticalLoops === 0 ? 15 : Math.max(0, 15 - criticalLoops * 7)
  breakdown.push({ label: 'No unsafe loops', points: loopPts, max: 15 })

  // No unused nodes (10 pts)
  const unusedIssue = validation.issues.find(i => i.id === 'unused-nodes')
  const unusedPts = unusedIssue ? Math.max(0, 10 - (unusedIssue.nodeIds?.length ?? 0) * 2) : 10
  breakdown.push({ label: 'No unused nodes', points: unusedPts, max: 10 })

  // Config completeness (5 pts)
  const configIssues = validation.issues.filter(i =>
    i.id.startsWith('empty-choices-') || i.id.startsWith('empty-conditions-')
  ).length
  const configPts = configIssues === 0 ? 5 : Math.max(0, 5 - configIssues)
  breakdown.push({ label: 'Node configuration', points: configPts, max: 5 })

  const score = breakdown.reduce((a, b) => a + b.points, 0)
  const grade: HealthScoreResult['grade'] =
    score >= 90 ? 'A' : score >= 75 ? 'B' : score >= 60 ? 'C' : score >= 40 ? 'D' : 'F'

  return { score, grade, breakdown }
}

// ── 7. Basic Workflow Optimization (rule-based, no AI) ────────
export function basicOptimize(nodes: Node[], edges: Edge[]): OptimizationSuggestion[] {
  const suggestions: OptimizationSuggestion[] = []
  const { outMap, inMap } = buildAdjacency(nodes, edges)

  // Consecutive text_card chains that could be merged
  nodes.forEach(n => {
    if (n.type !== 'text_card') return
    const outs = outMap.get(n.id) ?? []
    if (outs.length === 1) {
      const next = nodes.find(m => m.id === outs[0])
      if (next?.type === 'text_card' && (inMap.get(next.id) ?? []).length === 1) {
        suggestions.push({
          id: `merge-text-${n.id}-${next.id}`,
          title: 'Merge consecutive Text Card nodes',
          detail: `"${(n.data as { label?: string })?.label ?? n.id}" flows directly into another Text Card. Consider merging them into one message to reduce round-trips.`,
          impact: 'low',
        })
      }
    }
  })

  // Long linear chains without branching
  const linearRun = nodes.filter(n => (outMap.get(n.id) ?? []).length === 1 && (inMap.get(n.id) ?? []).length <= 1)
  if (linearRun.length >= 6) {
    suggestions.push({
      id: 'long-linear-chain',
      title: 'Long linear chain detected',
      detail: `${linearRun.length} nodes form an unbranched sequence. Consider adding a Multiple Choice or Transition node to give users more control.`,
      impact: 'medium',
    })
  }

  // Multiple choice with a single option (should probably be a text card)
  nodes.forEach(n => {
    if (n.type === 'multiple_choice') {
      const choices = (n.data as { choices?: unknown[] })?.choices ?? []
      if (Array.isArray(choices) && choices.length === 1) {
        suggestions.push({
          id: `single-choice-${n.id}`,
          title: 'Multiple Choice with only one option',
          detail: `"${(n.data as { label?: string })?.label ?? n.id}" only offers one option — a Text Card node may be simpler here.`,
          impact: 'low',
        })
      }
    }
  })

  // AI Agent nodes with very high maxTokens (cost/perf)
  nodes.forEach(n => {
    if (n.type === 'ai_agent') {
      const maxTokens = (n.data as { maxTokens?: number })?.maxTokens
      if (typeof maxTokens === 'number' && maxTokens > 4000) {
        suggestions.push({
          id: `high-tokens-${n.id}`,
          title: 'AI Agent has a very high max token limit',
          detail: `"${(n.data as { label?: string })?.label ?? n.id}" is set to ${maxTokens} max tokens. Lowering this can reduce latency and cost.`,
          impact: 'medium',
        })
      }
    }
  })

  // Nodes with excessive fan-out (potential UX confusion)
  nodes.forEach(n => {
    const outs = (outMap.get(n.id) ?? []).length
    if (outs >= 6) {
      suggestions.push({
        id: `high-fanout-${n.id}`,
        title: 'Node has many outgoing paths',
        detail: `"${(n.data as { label?: string })?.label ?? n.id}" branches into ${outs} paths. Consider grouping options or adding an intermediate node.`,
        impact: 'medium',
      })
    }
  })

  return suggestions
}
