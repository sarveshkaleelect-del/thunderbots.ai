// ============================================================
// ThunderGuide — Local Auto-Repair
//
// Purely local, deterministic fixes applied to a freshly-generated workflow
// BEFORE it's validated. This does not replace the existing "regenerate via
// the model with the failure reasons" retry in aiActions.ts — it runs first,
// on every attempt, so a candidate the model got 95% right (e.g. one missing
// End node, or one Multiple Choice option missing its edge) can be fixed for
// free instead of burning an entire extra model call, and so a workflow that
// still has issues after every retry has the best possible chance of being
// clean by the time the final fallback decision is made.
//
// Every fix here is strictly additive/corrective — it only adds missing
// structure (an End node, a missing edge) or removes clearly-invalid data
// (edges pointing at indices that don't exist). It never removes or rewrites
// a node the model intentionally produced, so it can't silently change the
// meaning of the generated conversation.
// ============================================================
import type { GeneratedWorkflow, GeneratedNode, GeneratedEdge } from './types'

function isMultipleChoice(n: GeneratedNode | undefined): boolean {
  return !!n && n.type === 'multiple_choice'
}

function choicesOf(n: GeneratedNode): Array<{ label?: string; value?: string }> {
  const c = (n.data as { choices?: Array<{ label?: string; value?: string }> })?.choices
  return Array.isArray(c) ? c : []
}

/**
 * Applies local structural fixes to a generated workflow:
 * 1. Drops edges referencing out-of-range node indices (can't be repaired,
 *    only safely discarded).
 * 2. Ensures at least one End node exists, adding a generic one if not.
 * 3. Connects every reachable dead-end node (no outgoing edge, not itself
 *    an End node) to a fallback End node.
 * 4. Connects every Multiple Choice option that has no outgoing edge for
 *    its choiceIndex to a fallback End node, so no option ever dead-ends.
 *
 * Returns a new GeneratedWorkflow; the input is not mutated.
 */
export function autoRepairWorkflow(gw: GeneratedWorkflow): GeneratedWorkflow {
  if (!gw || !Array.isArray(gw.nodes) || gw.nodes.length === 0) return gw

  const nodes: GeneratedNode[] = gw.nodes.map(n => ({ ...n, data: { ...n.data } }))
  let edges: GeneratedEdge[] = (gw.edges ?? []).filter(
    e => typeof e?.from === 'number' && typeof e?.to === 'number' &&
      e.from >= 0 && e.from < nodes.length && e.to >= 0 && e.to < nodes.length
  )

  // 2. Ensure at least one End node exists.
  let endIndex = nodes.findIndex(n => n.type === 'end')
  if (endIndex === -1) {
    nodes.push({
      type: 'end',
      label: 'End Conversation',
      data: { message: "Thanks for reaching out — we're all set!" },
    })
    endIndex = nodes.length - 1
  }

  // 3. Connect dead-end, non-End nodes to the fallback End node.
  const outCount = new Map<number, number>()
  edges.forEach(e => outCount.set(e.from, (outCount.get(e.from) ?? 0) + 1))
  nodes.forEach((n, i) => {
    if (n.type === 'end') return
    if ((outCount.get(i) ?? 0) === 0 && i !== endIndex) {
      edges.push({ from: i, to: endIndex })
      outCount.set(i, 1)
    }
  })

  // 4. Fill in missing Multiple Choice option edges.
  const coveredChoiceIndexes = new Map<number, Set<number>>()
  edges.forEach(e => {
    if (typeof e.choiceIndex !== 'number') return
    if (!coveredChoiceIndexes.has(e.from)) coveredChoiceIndexes.set(e.from, new Set())
    coveredChoiceIndexes.get(e.from)!.add(e.choiceIndex)
  })
  nodes.forEach((n, i) => {
    if (!isMultipleChoice(n)) return
    const choices = choicesOf(n)
    const covered = coveredChoiceIndexes.get(i) ?? new Set<number>()
    choices.forEach((_c, choiceIndex) => {
      if (!covered.has(choiceIndex)) {
        edges.push({ from: i, to: endIndex, choiceIndex })
      }
    })
  })

  // Dedupe any edges this pass may have doubled up on.
  const seen = new Set<string>()
  edges = edges.filter(e => {
    const key = `${e.from}->${e.to}:${e.choiceIndex ?? ''}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })

  return { nodes, edges }
}
