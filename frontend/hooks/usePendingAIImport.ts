'use client'
// ============================================================
// AI Chatbot by Prompt — pending import
//
// When a chatbot is generated via /create-with-ai, a brand new
// (empty) workflow is created on the backend and the generated
// graph is stashed in sessionStorage keyed by that workflow's id.
// This hook runs once the Builder has loaded that workflow and
// applies the generated nodes/edges into the canvas, then marks
// the workflow dirty so the existing autosave hook persists it.
//
// This is purely additive: it does nothing unless a pending
// import exists for the current workflow id, so it never affects
// normal Builder loading, existing nodes, or the AI Agent runtime.
// ============================================================
import { useEffect, useRef } from 'react'
import { v4 as uuidv4 } from 'uuid'
import { useWorkflowStore } from '@/store/workflowStore'
import { createNode } from '@/lib/utils/nodeFactory'
import { takePendingImport } from '@/lib/ai-create/storage'
import { isValidGeneratedWorkflow } from '@/lib/thunderguide/aiActions'
import type { GeneratedWorkflow } from '@/lib/thunderguide/aiActions'
import type { Node as RFNode, Edge as RFEdge } from 'reactflow'
import { useToast } from '@/components/ui/Toast'

const NODE_W = 260
const ROW_H = 170

function computeLayeredPositions(
  nodeCount: number,
  edges: GeneratedWorkflow['edges'],
  startIndices: number[]
): { x: number; y: number }[] {
  const outBy = new Map<number, number[]>()
  for (let i = 0; i < nodeCount; i++) outBy.set(i, [])
  edges.forEach(e => {
    if (outBy.has(e.from)) outBy.get(e.from)!.push(e.to)
  })

  const depth = new Array<number>(nodeCount).fill(-1)
  const queue: number[] = []
  const roots = startIndices.length ? startIndices : [0]
  roots.forEach(r => { if (depth[r] === -1) { depth[r] = 0; queue.push(r) } })

  while (queue.length) {
    const cur = queue.shift()!
    for (const next of outBy.get(cur) ?? []) {
      if (depth[next] === -1) {
        depth[next] = depth[cur] + 1
        queue.push(next)
      }
    }
  }
  const maxKnownDepth = Math.max(0, ...depth.filter(d => d !== -1))
  for (let i = 0; i < nodeCount; i++) {
    if (depth[i] === -1) depth[i] = maxKnownDepth + 1
  }

  const rows = new Map<number, number[]>()
  for (let i = 0; i < nodeCount; i++) {
    const d = depth[i]
    if (!rows.has(d)) rows.set(d, [])
    rows.get(d)!.push(i)
  }

  const positions = new Array<{ x: number; y: number }>(nodeCount)
  rows.forEach((indices, d) => {
    const rowWidth = (indices.length - 1) * NODE_W
    const startX = 500 - rowWidth / 2
    indices.forEach((nodeIdx, col) => {
      positions[nodeIdx] = { x: startX + col * NODE_W, y: d * ROW_H }
    })
  })
  return positions
}

function applyGeneratedWorkflow(gw: GeneratedWorkflow) {
  const startIndices = gw.nodes.reduce<number[]>((acc, n, i) => (n.type === 'start' ? [...acc, i] : acc), [])
  const layout = computeLayeredPositions(gw.nodes.length, gw.edges, startIndices)

  const idByIndex: string[] = []
  const newNodes: RFNode[] = gw.nodes.map((n, i) => {
    const pos = layout[i] ?? { x: 400, y: 0 }
    const node = createNode(n.type, pos, { label: n.label, ...(n.data as Record<string, unknown>) })
    idByIndex[i] = node.id
    return node as unknown as RFNode
  })

  const newEdges: RFEdge[] = gw.edges
    .filter(e => idByIndex[e.from] && idByIndex[e.to])
    .map(e => {
      const fromNode = gw.nodes[e.from]
      const sourceHandle = fromNode?.type === 'multiple_choice' && typeof e.choiceIndex === 'number'
        ? `choice_${e.choiceIndex}`
        : undefined
      return {
        id: `ai_edge_${uuidv4().replace(/-/g, '').slice(0, 8)}`,
        source: idByIndex[e.from],
        target: idByIndex[e.to],
        ...(sourceHandle ? { sourceHandle } : {}),
        type: 'thunder',
        data: {},
      } as unknown as RFEdge
    })

  useWorkflowStore.setState(s => ({
    nodes: [...s.nodes, ...newNodes],
    edges: [...s.edges, ...newEdges],
    isDirty: true,
  }))
}

/**
 * Call once inside the Builder page, AFTER the hook/effect that loads the
 * fetched workflow into the store (`setWorkflow`). `ready` should only
 * become true once that load has happened, so this never races with (and
 * gets overwritten by) the initial `setWorkflow` reset.
 */
export function usePendingAIImport(workflowId: string | null | undefined, ready: boolean) {
  const applied = useRef<string | null>(null)
  const { toast } = useToast()

  useEffect(() => {
    if (!ready || !workflowId) return
    if (applied.current === workflowId) return
    const gw = takePendingImport<GeneratedWorkflow>(workflowId)
    if (!gw) return
    applied.current = workflowId

    // ROOT CAUSE FIX (Builder crash: "Cannot read properties of undefined
    // (reading 'reduce')"): takePendingImport() does `JSON.parse(raw) as T`
    // — a compile-time-only cast with no runtime guarantee. Anything that
    // made it into sessionStorage under this key but isn't shaped like a
    // real GeneratedWorkflow (stale data from an older schema, a value
    // edited by hand, or any future bug upstream) used to be handed
    // straight to applyGeneratedWorkflow(), which calls gw.nodes.reduce(...)
    // with no guard at all. Validate the shape here, at the actual import
    // boundary, before it ever touches .reduce/.forEach — this is the one
    // place that MUST hold regardless of what bugs may exist upstream.
    if (!isValidGeneratedWorkflow(gw)) {
      console.error('Discarded invalid pending AI-generated workflow (failed shape validation):', gw)
      toast('error', 'The AI-generated workflow could not be imported. Please try generating it again from Create with AI.')
      return
    }
    applyGeneratedWorkflow(gw)
  }, [workflowId, ready, toast])
}
