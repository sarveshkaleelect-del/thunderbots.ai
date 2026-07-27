'use client'
import { create } from 'zustand'
import { subscribeWithSelector } from 'zustand/middleware'
import {
  Node, Edge, NodeChange, EdgeChange, Connection,
  applyNodeChanges, applyEdgeChanges, addEdge, Viewport,
} from 'reactflow'
import { v4 as uuidv4 } from 'uuid'

const MAX_UNDO = 50

interface WorkflowStore {
  workflowId: string | null
  workflowName: string
  nodes: Node[]
  edges: Edge[]
  viewport: Viewport
  isDirty: boolean
  isSaving: boolean
  lastSaved: Date | null
  selectedNodeId: string | null
  selectedNodeIds: string[]        // multi-select
  clipboard: Node[]                // copy/paste buffer
  past: Array<{ nodes: Node[]; edges: Edge[] }>
  future: Array<{ nodes: Node[]; edges: Edge[] }>

  setWorkflow: (id: string, name: string, nodes: Node[], edges: Edge[], viewport: Viewport) => void
  setWorkflowName: (name: string) => void
  onNodesChange: (changes: NodeChange[]) => void
  onEdgesChange: (changes: EdgeChange[]) => void
  onConnect: (connection: Connection) => void
  addNode: (node: Node) => void
  updateNodeData: (nodeId: string, data: Record<string, unknown>) => void
  deleteNode: (nodeId: string) => void
  deleteEdge: (edgeId: string) => void
  deleteSelectedNodes: () => void
  setSelectedNode: (id: string | null) => void
  setSelectedNodeIds: (ids: string[]) => void
  setViewport: (v: Viewport) => void
  setIsSaving: (v: boolean) => void
  setLastSaved: (d: Date) => void
  markDirty: () => void
  markClean: () => void

  // Copy / Paste / Duplicate
  copySelected: () => void
  pasteNodes: (offset?: { x: number; y: number }) => void
  duplicateNode: (nodeId: string) => void

  // History
  snapshot: () => void
  undo: () => void
  redo: () => void
  canUndo: () => boolean
  canRedo: () => boolean
}

export const useWorkflowStore = create<WorkflowStore>()(
  subscribeWithSelector((set, get) => ({
    workflowId: null,
    workflowName: 'Untitled Workflow',
    nodes: [],
    edges: [],
    viewport: { x: 0, y: 0, zoom: 1 },
    isDirty: false,
    isSaving: false,
    lastSaved: null,
    selectedNodeId: null,
    selectedNodeIds: [],
    clipboard: [],
    past: [],
    future: [],

    setWorkflow: (id, name, nodes, edges, viewport) =>
      set({
        workflowId: id, workflowName: name,
        nodes: nodes ?? [], edges: edges ?? [],
        viewport: viewport ?? { x: 0, y: 0, zoom: 1 },
        isDirty: false, past: [], future: [],
        selectedNodeId: null, selectedNodeIds: [],
      }),

    setWorkflowName: (name) => set({ workflowName: name }),

    onNodesChange: (changes) => {
      const isPositionFinal = changes.some(c => c.type === 'position' && c.dragging === false)
      if (isPositionFinal) get().snapshot()

      // Track multi-select from ReactFlow selection events
      const selectionChanges = changes.filter(c => c.type === 'select')
      if (selectionChanges.length > 0) {
        const currentNodes = applyNodeChanges(changes, get().nodes)
        const selectedIds = currentNodes.filter(n => n.selected).map(n => n.id)
        set(s => ({
          nodes: applyNodeChanges(changes, s.nodes),
          isDirty: !selectionChanges.every(c => c.type === 'select'), // don't dirty on selection only
          selectedNodeIds: selectedIds,
          selectedNodeId: selectedIds.length === 1 ? selectedIds[0] : (selectedIds.length === 0 ? null : s.selectedNodeId),
        }))
        return
      }

      set(s => ({ nodes: applyNodeChanges(changes, s.nodes), isDirty: true }))
    },

    onEdgesChange: (changes) => {
      set(s => ({ edges: applyEdgeChanges(changes, s.edges), isDirty: true }))
    },

    onConnect: (connection) => {
      get().snapshot()
      set(s => ({
        edges: addEdge({ ...connection, type: 'thunder', data: {} }, s.edges),
        isDirty: true,
      }))
    },

    addNode: (node) => {
      get().snapshot()
      set(s => ({ nodes: [...s.nodes, node], isDirty: true }))
    },

    updateNodeData: (nodeId, data) => {
      set(s => ({
        nodes: s.nodes.map(n => n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n),
        isDirty: true,
      }))
    },

    deleteNode: (nodeId) => {
      get().snapshot()
      set(s => ({
        nodes: s.nodes.filter(n => n.id !== nodeId),
        edges: s.edges.filter(e => e.source !== nodeId && e.target !== nodeId),
        selectedNodeId: s.selectedNodeId === nodeId ? null : s.selectedNodeId,
        selectedNodeIds: s.selectedNodeIds.filter(id => id !== nodeId),
        isDirty: true,
      }))
    },

    deleteEdge: (edgeId) => {
      get().snapshot()
      set(s => ({ edges: s.edges.filter(e => e.id !== edgeId), isDirty: true }))
    },

    deleteSelectedNodes: () => {
      const { selectedNodeIds, nodes, edges } = get()
      if (!selectedNodeIds.length) return
      get().snapshot()
      set({
        nodes: nodes.filter(n => !selectedNodeIds.includes(n.id)),
        edges: edges.filter(e => !selectedNodeIds.includes(e.source) && !selectedNodeIds.includes(e.target)),
        selectedNodeId: null,
        selectedNodeIds: [],
        isDirty: true,
      })
    },

    setSelectedNode: (id) => set({ selectedNodeId: id }),
    setSelectedNodeIds: (ids) => set({ selectedNodeIds: ids }),
    setViewport: (viewport) => set({ viewport }),
    setIsSaving: (isSaving) => set({ isSaving }),
    setLastSaved: (lastSaved) => set({ lastSaved }),
    markDirty: () => set({ isDirty: true }),
    markClean: () => set({ isDirty: false }),

    // ── Copy / Paste ──────────────────────────────────────────
    copySelected: () => {
      const { nodes, selectedNodeIds, selectedNodeId } = get()
      const ids = selectedNodeIds.length > 0 ? selectedNodeIds : (selectedNodeId ? [selectedNodeId] : [])
      const clipboard = nodes.filter(n => ids.includes(n.id))
      if (clipboard.length) set({ clipboard })
    },

    pasteNodes: (offset = { x: 40, y: 40 }) => {
      const { clipboard } = get()
      if (!clipboard.length) return
      get().snapshot()
      const idMap: Record<string, string> = {}
      const newNodes = clipboard.map(n => {
        const newId = `${n.type}_${uuidv4().replace(/-/g, '').slice(0, 8)}`
        idMap[n.id] = newId
        return {
          ...n,
          id: newId,
          position: { x: n.position.x + offset.x, y: n.position.y + offset.y },
          selected: true,
          data: { ...n.data },
        }
      })
      set(s => ({
        nodes: [...s.nodes.map(n => ({ ...n, selected: false })), ...newNodes],
        selectedNodeIds: newNodes.map(n => n.id),
        selectedNodeId: newNodes.length === 1 ? newNodes[0].id : null,
        isDirty: true,
      }))
    },

    duplicateNode: (nodeId) => {
      const { nodes } = get()
      const node = nodes.find(n => n.id === nodeId)
      if (!node) return
      get().snapshot()
      const newId = `${node.type}_${uuidv4().replace(/-/g, '').slice(0, 8)}`
      const newNode: Node = {
        ...node,
        id: newId,
        position: { x: node.position.x + 40, y: node.position.y + 40 },
        selected: false,
        data: { ...node.data },
      }
      set(s => ({ nodes: [...s.nodes, newNode], isDirty: true }))
    },

    // ── History ───────────────────────────────────────────────
    snapshot: () => {
      const { nodes, edges, past } = get()
      set({
        past: [...past.slice(-(MAX_UNDO - 1)), { nodes: [...nodes], edges: [...edges] }],
        future: [],
      })
    },

    undo: () => {
      const { past, nodes, edges, future } = get()
      if (!past.length) return
      const prev = past[past.length - 1]
      set({ nodes: prev.nodes, edges: prev.edges, past: past.slice(0, -1), future: [{ nodes, edges }, ...future], isDirty: true })
    },

    redo: () => {
      const { future, nodes, edges, past } = get()
      if (!future.length) return
      const next = future[0]
      set({ nodes: next.nodes, edges: next.edges, future: future.slice(1), past: [...past, { nodes, edges }], isDirty: true })
    },

    canUndo: () => get().past.length > 0,
    canRedo: () => get().future.length > 0,
  }))
)
