'use client'
import { useEffect, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { WorkflowCanvas } from '@/components/builder/Canvas/WorkflowCanvas'
import { ApiKeyReminder } from '@/components/ui/ApiKeyReminder'
import { useWorkflowStore } from '@/store/workflowStore'
import { workflowsApi } from '@/lib/api/workflows'
import { usePendingAIImport } from '@/hooks/usePendingAIImport'
import { Loader2, AlertCircle } from 'lucide-react'
import type { Node, Edge } from 'reactflow'
import type { Workflow } from '@/types'

/**
 * FIX: Normalize nodes and edges from the API response before passing to
 * React Flow. The JSONB column stores plain JSON objects; React Flow requires
 * each node to have at minimum: { id, type, position: {x,y}, data: {} }.
 * Missing or malformed fields caused silent canvas crashes.
 */
function normalizeNode(n: Record<string, unknown>): Node {
  return {
    id:       String(n.id ?? ''),
    type:     String(n.type ?? 'text_card'),
    position: {
      x: Number((n.position as Record<string, number>)?.x ?? 0),
      y: Number((n.position as Record<string, number>)?.y ?? 0),
    },
    data:     (n.data as Record<string, unknown>) ?? {},
    selected: false,
    dragging: false,
  }
}

function normalizeEdge(e: Record<string, unknown>): Edge {
  return {
    id:           String(e.id ?? ''),
    source:       String(e.source ?? ''),
    target:       String(e.target ?? ''),
    sourceHandle: e.sourceHandle ? String(e.sourceHandle) : undefined,
    targetHandle: e.targetHandle ? String(e.targetHandle) : undefined,
    type:         String(e.type ?? 'thunder'),
    data:         (e.data as Record<string, unknown>) ?? {},
  }
}

export default function BuilderPage() {
  const params = useParams()
  const workflowId = params?.workflowId as string
  const router = useRouter()
  const setWorkflow = useWorkflowStore(s => s.setWorkflow)

  const { data: workflow, isLoading, error } = useQuery<Workflow>({
    queryKey: ['workflow', workflowId],
    queryFn:  () => workflowsApi.get(workflowId),
    enabled:  !!workflowId,
    retry: 1,
    staleTime: 0,   // always fresh on builder load
  })

  // FIX: Normalize shapes before handing to React Flow store
  const loadWorkflow = useCallback((wf: Workflow) => {
    const nodes = (wf.nodes as unknown as Record<string, unknown>[]).map(normalizeNode)
    const edges = (wf.edges as unknown as Record<string, unknown>[]).map(normalizeEdge)
    const viewport = wf.canvas_state ?? { x: 0, y: 0, zoom: 1 }
    setWorkflow(wf.id, wf.name, nodes, edges, viewport)
  }, [setWorkflow])

  useEffect(() => {
    if (workflow) loadWorkflow(workflow)
  }, [workflow, loadWorkflow])

  // Applies a freshly AI-generated workflow (from /create-with-ai) into the
  // canvas exactly once, only after the fetched workflow above has finished
  // loading into the store — never races with or overwrites normal loads.
  usePendingAIImport(workflowId, !!workflow)

  if (isLoading) return (
    <div className="h-screen flex items-center justify-center bg-[#080808]">
      <Loader2 size={22} className="text-[#6366f1] animate-spin" />
    </div>
  )

  if (error) return (
    <div className="h-screen flex flex-col items-center justify-center bg-[#080808] gap-3">
      <AlertCircle size={22} className="text-red-400" />
      <p className="text-white/40 text-sm">Failed to load workflow</p>
      <p className="text-white/20 text-xs">
        {(error as Error)?.message || 'Unknown error'}
      </p>
      <button
        onClick={() => router.push('/dashboard')}
        className="text-xs text-[#6366f1] hover:underline mt-1"
      >
        ← Back to dashboard
      </button>
    </div>
  )

  if (!workflow) return null

  return (
    <>
      <WorkflowCanvas />
      <ApiKeyReminder />
    </>
  )
}
