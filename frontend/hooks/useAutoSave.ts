'use client'
import { useEffect, useRef, useCallback } from 'react'
import { useReactFlow } from 'reactflow'
import { useWorkflowStore } from '@/store/workflowStore'
import { workflowsApi } from '@/lib/api/workflows'

const DELAY = 1500

export function useAutoSave() {
  const timer = useRef<ReturnType<typeof setTimeout>>()
  const { getViewport } = useReactFlow()

  // FIX: Use separate selectors for each primitive to avoid reference-equality
  // churn. Previously [nodes, edges] in the effect dependency array caused the
  // effect to re-run (and reset the debounce timer) on every Zustand state
  // update even when isDirty=false, because array references always differ.
  const workflowId  = useWorkflowStore(s => s.workflowId)
  const isDirty     = useWorkflowStore(s => s.isDirty)
  const setIsSaving = useWorkflowStore(s => s.setIsSaving)
  const setLastSaved = useWorkflowStore(s => s.setLastSaved)
  const markClean   = useWorkflowStore(s => s.markClean)

  const save = useCallback(async () => {
    // Read nodes/edges at call-time, not at closure-creation-time.
    // This avoids stale closure capturing an old snapshot.
    const { nodes, edges } = useWorkflowStore.getState()
    const wid = useWorkflowStore.getState().workflowId
    if (!wid || !useWorkflowStore.getState().isDirty) return

    setIsSaving(true)
    try {
      const viewport = getViewport()
      await workflowsApi.save(wid, nodes, edges, viewport)
      setLastSaved(new Date())
      markClean()
    } catch (err) {
      console.error('Auto-save failed:', err)
      // Don't markClean — keep isDirty so user can retry
    } finally {
      setIsSaving(false)
    }
  }, [getViewport, setIsSaving, setLastSaved, markClean])

  // FIX: Only depend on isDirty (a boolean) and workflowId (a string).
  // Nodes and edges are read from the store at save-time via getState().
  // This means the effect only reruns when isDirty actually flips,
  // not on every array reference change.
  useEffect(() => {
    if (!isDirty || !workflowId) return
    clearTimeout(timer.current)
    timer.current = setTimeout(save, DELAY)
    return () => clearTimeout(timer.current)
  }, [isDirty, workflowId, save])

  return { save }
}
