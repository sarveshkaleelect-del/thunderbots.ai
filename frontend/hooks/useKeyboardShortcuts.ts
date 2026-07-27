'use client'
import { useEffect } from 'react'
import { useWorkflowStore } from '@/store/workflowStore'

export function useKeyboardShortcuts(onSave?: () => void) {
  // Granular selectors — the previous whole-store subscription re-rendered
  // whatever component calls this hook (the canvas) on every single node/
  // edge/history change, i.e. every drag frame.
  const undo = useWorkflowStore(s => s.undo)
  const redo = useWorkflowStore(s => s.redo)
  const deleteNode = useWorkflowStore(s => s.deleteNode)
  const deleteSelectedNodes = useWorkflowStore(s => s.deleteSelectedNodes)
  const selectedNodeId = useWorkflowStore(s => s.selectedNodeId)
  const selectedNodeIds = useWorkflowStore(s => s.selectedNodeIds)
  const copySelected = useWorkflowStore(s => s.copySelected)
  const pasteNodes = useWorkflowStore(s => s.pasteNodes)
  const duplicateNode = useWorkflowStore(s => s.duplicateNode)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const ctrl = e.ctrlKey || e.metaKey
      const tag  = (e.target as HTMLElement).tagName
      const isInput = tag === 'INPUT' || tag === 'TEXTAREA' || (e.target as HTMLElement).isContentEditable

      // Undo / Redo
      if (ctrl && e.key === 'z' && !e.shiftKey) { e.preventDefault(); undo(); return }
      if (ctrl && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) { e.preventDefault(); redo(); return }

      // Save
      if (ctrl && e.key === 's') { e.preventDefault(); onSave?.(); return }

      // Copy / Paste / Duplicate — only when not in an input
      if (!isInput) {
        if (ctrl && e.key === 'c') { e.preventDefault(); copySelected(); return }
        if (ctrl && e.key === 'v') { e.preventDefault(); pasteNodes(); return }
        if (ctrl && e.key === 'd') {
          e.preventDefault()
          if (selectedNodeId) duplicateNode(selectedNodeId)
          return
        }

        // Delete selected node(s)
        if (e.key === 'Delete' || e.key === 'Backspace') {
          e.preventDefault()
          if (selectedNodeIds.length > 1) {
            deleteSelectedNodes()
          } else if (selectedNodeId) {
            deleteNode(selectedNodeId)
          }
          return
        }

        // Deselect
        if (e.key === 'Escape') {
          useWorkflowStore.getState().setSelectedNode(null)
          useWorkflowStore.getState().setSelectedNodeIds([])
        }
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [undo, redo, deleteNode, deleteSelectedNodes, selectedNodeId, selectedNodeIds,
      copySelected, pasteNodes, duplicateNode, onSave])
}
