'use client'
import { useCallback, useRef, useState } from 'react'
import dynamic from 'next/dynamic'
import ReactFlow, {
  Background, BackgroundVariant, Controls, MiniMap,
  ReactFlowProvider, useReactFlow, SelectionMode,
  type Node, type Viewport,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { X } from 'lucide-react'

import { useWorkflowStore } from '@/store/workflowStore'
import { useAutoSave } from '@/hooks/useAutoSave'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { cn } from '@/lib/utils/cn'
import { nodeTypes } from '../Nodes'
import { edgeTypes } from '../Edges/ThunderEdge'
import { NodeLibraryPanel } from '../Panels/NodeLibraryPanel'
import { PageLoader } from '@/components/ui/States'
import { BuilderToolbar } from '../Toolbar/BuilderToolbar'
import { AIPromptReminder } from '../Overlays/AIPromptReminder'
import { useUIStore } from '@/store/uiStore'
import { createNode } from '@/lib/utils/nodeFactory'
import type { NodeType } from '@/types'

// PERF FIX (v107): these 7 right-hand builder panels total ~3,700 lines
// combined, but the switch statement in RightPanel() below only ever
// renders ONE of them at a time. Statically importing all 7 meant every
// visitor to /builder downloaded and parsed all of them up front, even
// though 6 out of 7 are typically never opened in a given session. Each
// is now a separate on-demand chunk fetched only the first time its tab is
// selected — subsequent switches are served from the browser's normal
// chunk cache, so this costs nothing on repeat visits within a session.
// ssr: false is safe here — these are 'use client' panels that read from
// client-only stores (useUIStore/useWorkflowStore) and are only ever
// rendered inside the already-'use client' builder canvas.
const ChatTesterPanel = dynamic(
  () => import('../Panels/ChatTesterPanel').then(m => m.ChatTesterPanel),
  { loading: () => <PageLoader label="Loading chat tester…" />, ssr: false },
)
const HistoryPanel = dynamic(
  () => import('../Panels/HistoryPanel').then(m => m.HistoryPanel),
  { loading: () => <PageLoader label="Loading history…" />, ssr: false },
)
const KnowledgePanel = dynamic(
  () => import('../Panels/KnowledgePanel').then(m => m.KnowledgePanel),
  { loading: () => <PageLoader label="Loading knowledge base…" />, ssr: false },
)
const DeployPanel = dynamic(
  () => import('../Panels/DeployPanel').then(m => m.DeployPanel),
  { loading: () => <PageLoader label="Loading deploy panel…" />, ssr: false },
)
const ThunderGuidePanel = dynamic(
  () => import('../Panels/ThunderGuidePanel').then(m => m.ThunderGuidePanel),
  { loading: () => <PageLoader label="Loading ThunderGuide…" />, ssr: false },
)
const SimulatorPanel = dynamic(
  () => import('../Panels/SimulatorPanel').then(m => m.SimulatorPanel),
  { loading: () => <PageLoader label="Loading simulator…" />, ssr: false },
)
// NodeConfigPanel is the DEFAULT panel (shown the instant the builder
// loads, with no tab click required), so it stays eagerly imported —
// lazily loading the default view would just move the same download to
// first paint instead of removing it.
import { NodeConfigPanel } from '../Panels/NodeConfigPanel'

const MINIMAP_COLORS: Record<string, string> = {
  start: '#22c55e', text_card: '#3b82f6',
  multiple_choice: '#f59e0b', ai_agent: '#818cf8',
  transition: '#ec4899', end: '#ef4444',
}
// Stable reference — declared once, module scope, so it never triggers a
// prop-identity change on MiniMap between renders.
const getMinimapNodeColor = (n: Node) => MINIMAP_COLORS[n.type || ''] || '#2a2a2a'

// Stable style/option objects for ReactFlow. These were previously inline
// object/array literals re-created on every render, which defeats
// ReactFlow's internal prop-identity checks and forces extra internal
// effect re-runs on every keystroke/store update.
const CONNECTION_LINE_STYLE = { stroke: '#818cf8', strokeWidth: 2, strokeDasharray: '5 4' }
const DEFAULT_EDGE_OPTIONS = { type: 'thunder', data: {} }
const FIT_VIEW_OPTIONS = { padding: 0.2 }
const PRO_OPTIONS = { hideAttribution: true }
const SNAP_GRID: [number, number] = [16, 16]

function RightPanel() {
  const rightPanel = useUIStore(s => s.rightPanel)
  let panel: React.ReactNode
  switch (rightPanel) {
    case 'chat':      panel = <ChatTesterPanel />; break
    case 'history':   panel = <HistoryPanel />; break
    case 'knowledge': panel = <KnowledgePanel />; break
    case 'deploy':    panel = <DeployPanel />; break
    case 'thunderguide': panel = <ThunderGuidePanel />; break
    case 'simulator': panel = <SimulatorPanel />; break
    default:          panel = <NodeConfigPanel />
  }
  // key forces a clean remount per panel switch so the reveal animation replays
  return <div key={rightPanel} className="h-full tb-anim-slide-in">{panel}</div>
}

function CanvasInner() {
  // Granular selectors — each subscribes only to the slice it needs, so
  // this component doesn't re-render (and cascade re-renders down into
  // the toolbar/library panel) on every unrelated store update such as
  // undo-history snapshots or selection changes.
  const nodes = useWorkflowStore(s => s.nodes)
  const edges = useWorkflowStore(s => s.edges)
  const onNodesChange = useWorkflowStore(s => s.onNodesChange)
  const onEdgesChange = useWorkflowStore(s => s.onEdgesChange)
  const onConnect = useWorkflowStore(s => s.onConnect)
  const addNode = useWorkflowStore(s => s.addNode)
  const setViewport = useWorkflowStore(s => s.setViewport)
  const deleteEdge = useWorkflowStore(s => s.deleteEdge)
  const setSelectedNode = useWorkflowStore(s => s.setSelectedNode)
  const setSelectedNodeIds = useWorkflowStore(s => s.setSelectedNodeIds)

  const { screenToFlowPosition } = useReactFlow()
  const { save } = useAutoSave()
  useKeyboardShortcuts(save)

  const reactFlowWrapper = useRef<HTMLDivElement>(null)

  // Mobile/tablet (< lg) drawer visibility for the two side panels, which
  // are always-visible fixed-width columns at lg+. Purely a presentational
  // concern — never read by or written to workflow/business state.
  const [mobileLibraryOpen, setMobileLibraryOpen] = useState(false)
  const [mobileRightOpen, setMobileRightOpen] = useState(false)

  // Pauses decorative, continuously-running CSS animations (the electric
  // edge current, the aurora drift, the selected-node pulse) for the
  // duration of a pan/zoom/drag gesture. Toggled directly on the DOM via
  // a ref — never through React state — so it adds zero extra renders
  // while making the interaction itself butter-smooth on lower-end GPUs.
  const setInteracting = useCallback((on: boolean) => {
    reactFlowWrapper.current?.classList.toggle('tb-interacting', on)
  }, [])
  const onMoveStart = useCallback(() => setInteracting(true), [setInteracting])
  const onMoveEnd = useCallback((_: unknown, vp: Viewport) => {
    setInteracting(false)
    setViewport(vp)
  }, [setInteracting, setViewport])
  const onNodeDragStart = useCallback(() => setInteracting(true), [setInteracting])
  const onNodeDragStop = useCallback(() => setInteracting(false), [setInteracting])
  const onSelectionDragStart = useCallback(() => setInteracting(true), [setInteracting])
  const onSelectionDragStop = useCallback(() => setInteracting(false), [setInteracting])

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const type = e.dataTransfer.getData('application/thunderbots-node') as NodeType
    if (!type) return
    const position = screenToFlowPosition({ x: e.clientX, y: e.clientY })
    addNode(createNode(type, position))
  }, [screenToFlowPosition, addNode])

  // Right-click on edge → delete
  const onEdgeContextMenu = useCallback((e: React.MouseEvent, edge: { id: string }) => {
    e.preventDefault()
    if (window.confirm('Delete this connection?')) deleteEdge(edge.id)
  }, [deleteEdge])

  // Click on pane → deselect
  const onPaneClick = useCallback(() => {
    setSelectedNode(null)
    setSelectedNodeIds([])
  }, [setSelectedNode, setSelectedNodeIds])

  return (
    <div className="flex h-screen w-screen bg-[#0a0912] overflow-hidden">
      {/* Backdrop for mobile/tablet drawers — click to dismiss. Never
          rendered at lg+ where both panels sit statically in-flow. */}
      {(mobileLibraryOpen || mobileRightOpen) && (
        <div
          className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={() => { setMobileLibraryOpen(false); setMobileRightOpen(false) }}
        />
      )}

      {/* Left: Node Library */}
      <NodeLibraryPanel
        mobileOpen={mobileLibraryOpen}
        onMobileClose={() => setMobileLibraryOpen(false)}
      />

      {/* Center: Canvas */}
      <div className="flex-1 flex flex-col min-w-0">
        <BuilderToolbar
          onSave={save}
          onToggleLibrary={() => setMobileLibraryOpen(o => !o)}
          onOpenRightPanel={() => setMobileRightOpen(true)}
        />
        <div className="flex-1 relative tb-canvas-aurora" ref={reactFlowWrapper} onDragOver={onDragOver} onDrop={onDrop} data-tutorial="builder-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onMoveStart={onMoveStart}
            onMoveEnd={onMoveEnd}
            onNodeDragStart={onNodeDragStart}
            onNodeDragStop={onNodeDragStop}
            onSelectionDragStart={onSelectionDragStart}
            onSelectionDragStop={onSelectionDragStop}
            onEdgeContextMenu={onEdgeContextMenu}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            defaultEdgeOptions={DEFAULT_EDGE_OPTIONS}
            connectionLineStyle={CONNECTION_LINE_STYLE}
            selectionMode={SelectionMode.Partial}
            multiSelectionKeyCode="Shift"
            selectionKeyCode="Shift"
            snapToGrid
            snapGrid={SNAP_GRID}
            minZoom={0.05}
            maxZoom={4}
            fitView
            fitViewOptions={FIT_VIEW_OPTIONS}
            deleteKeyCode={null}       // handled by our own keyboard hook
            proOptions={PRO_OPTIONS}
          >
            <Background
              variant={BackgroundVariant.Dots}
              gap={24}
              size={1.1}
              color="rgba(168,139,250,0.22)"
            />
            <Controls showInteractive={false} className="tb-flow-controls" />
            <MiniMap
              nodeColor={getMinimapNodeColor}
              nodeStrokeWidth={0}
              maskColor="rgba(10,9,14,0.72)"
              position="bottom-right"
              className="hidden sm:block"
            />
          </ReactFlow>
          <AIPromptReminder />
        </div>
      </div>

      {/* Right: Panels — fixed drawer below lg, static column at lg+ */}
      <div
        className={cn(
          'w-[340px] max-w-[88vw] flex-shrink-0 border-l border-[#1e1e1e] flex flex-col overflow-hidden bg-[#0a0912]',
          'fixed inset-y-0 right-0 z-40 transition-transform duration-200 ease-out',
          'lg:static lg:z-auto lg:translate-x-0',
          mobileRightOpen ? 'translate-x-0' : 'translate-x-full'
        )}
      >
        <button
          type="button"
          aria-label="Close panel"
          onClick={() => setMobileRightOpen(false)}
          className="lg:hidden absolute top-2 right-2 z-10 w-9 h-9 flex items-center justify-center rounded-lg text-white/40 hover:text-white/80 hover:bg-white/[0.06]"
        >
          <X size={15} />
        </button>
        <RightPanel />
      </div>
    </div>
  )
}

export function WorkflowCanvas() {
  return (
    <ReactFlowProvider>
      <CanvasInner />
    </ReactFlowProvider>
  )
}
