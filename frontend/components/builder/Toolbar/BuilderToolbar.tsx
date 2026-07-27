'use client'
import { memo } from 'react'
import Link from 'next/link'
import {
  Undo2, Redo2, Save, MessageSquare, Settings,
  History, ChevronLeft, Zap, Database, Check,
  Loader2, Copy, Clipboard, GitBranch, Rocket, Compass, Sparkles,
  PanelLeft, PanelRight,
} from 'lucide-react'
import { useWorkflowStore } from '@/store/workflowStore'
import { useUIStore } from '@/store/uiStore'
import { cn } from '@/lib/utils/cn'

interface Props {
  onSave: () => void
  /** Mobile-only (< lg) drawer toggles for the node library / right panel.
   *  Both are purely presentational — they never touch workflow state. */
  onToggleLibrary?: () => void
  onOpenRightPanel?: () => void
}

// Granular selectors below: each component subscribes only to the exact
// primitives it renders. Previously this file called useWorkflowStore()
// with no selector, which subscribes to the ENTIRE store — meaning the
// whole toolbar (and its child buttons) re-rendered on every single node
// position update while dragging a node on the canvas. Splitting into
// individual selectors means the toolbar now only re-renders when a
// value it actually displays changes.

const SaveStatus = memo(function SaveStatus() {
  const isDirty = useWorkflowStore(s => s.isDirty)
  const isSaving = useWorkflowStore(s => s.isSaving)
  const lastSaved = useWorkflowStore(s => s.lastSaved)

  if (isSaving) return (
    <span className="flex items-center gap-1.5 text-[11px] text-white/35">
      <Loader2 size={10} className="animate-spin" /> Saving…
    </span>
  )
  if (!isDirty && lastSaved) return (
    <span className="flex items-center gap-1.5 text-[11px] text-white/30">
      <Check size={10} className="text-emerald-400" />
      {lastSaved.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
    </span>
  )
  if (isDirty) return <span className="text-[11px] text-amber-400/60">Unsaved</span>
  return null
})

const PANELS = [
  { id: 'chat',        icon: MessageSquare, label: 'Chat Tester' },
  { id: 'config',      icon: Settings,      label: 'Node Config' },
  { id: 'history',     icon: History,       label: 'History' },
  { id: 'knowledge',   icon: Database,      label: 'Knowledge' },
  { id: 'simulator',   icon: Sparkles,      label: 'AI Simulation' },
  { id: 'deploy',      icon: Rocket,        label: 'Deploy' },
  { id: 'thunderguide', icon: Compass,      label: 'ThunderGuide' },
] as const

function BuilderToolbarImpl({ onSave, onToggleLibrary, onOpenRightPanel }: Props) {
  const workflowName = useWorkflowStore(s => s.workflowName)
  const undo = useWorkflowStore(s => s.undo)
  const redo = useWorkflowStore(s => s.redo)
  // Subscribing to the lengths (primitives) instead of calling canUndo()/
  // canRedo() off a whole-store subscription — this only re-renders the
  // toolbar when the undo/redo availability actually flips, not on every
  // unrelated node/edge change.
  const canUndo = useWorkflowStore(s => s.past.length > 0)
  const canRedo = useWorkflowStore(s => s.future.length > 0)
  const copySelected = useWorkflowStore(s => s.copySelected)
  const pasteNodes = useWorkflowStore(s => s.pasteNodes)
  const selectedNodeId = useWorkflowStore(s => s.selectedNodeId)
  const hasClipboard = useWorkflowStore(s => s.clipboard.length > 0)
  const rightPanel = useUIStore(s => s.rightPanel)
  const setRightPanel = useUIStore(s => s.setRightPanel)

  return (
    <div className="flex items-center justify-between h-12 px-2 sm:px-4 border-b border-[#1e1e1e] bg-[#0d0d0d] flex-shrink-0 gap-2 sm:gap-3 overflow-x-auto tb-scroll-x">

      {/* Left — back + workflow name */}
      <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-shrink-0">
        {onToggleLibrary && (
          <button
            type="button"
            aria-label="Toggle node library"
            onClick={onToggleLibrary}
            data-tutorial="builder-node-library"
            className="lg:hidden w-9 h-9 flex items-center justify-center rounded-lg text-white/40 hover:text-white/80 hover:bg-white/5 flex-shrink-0"
          >
            <PanelLeft size={15} />
          </button>
        )}
        <Link href="/dashboard" className="text-white/25 hover:text-white/60 transition flex-shrink-0">
          <ChevronLeft size={16} />
        </Link>
        <div className="flex items-center gap-1.5 min-w-0">
          <Zap size={12} className="text-[#6366f1] flex-shrink-0" />
          <span className="text-sm font-semibold text-white/80 truncate max-w-[100px] sm:max-w-[160px]">
            {workflowName}
          </span>
        </div>
        <SaveStatus />
      </div>

      {/* Center — edit controls */}
      <div className="flex items-center gap-0.5 flex-shrink-0">
        <ToolBtn onClick={undo} disabled={!canUndo} title="Undo (⌘Z)">
          <Undo2 size={14} />
        </ToolBtn>
        <ToolBtn onClick={redo} disabled={!canRedo} title="Redo (⌘Y)">
          <Redo2 size={14} />
        </ToolBtn>

        <div className="w-px h-4 bg-[#2a2a2a] mx-1" />

        <ToolBtn onClick={copySelected} disabled={!selectedNodeId} title="Copy (⌘C)">
          <Copy size={14} />
        </ToolBtn>
        <ToolBtn onClick={() => pasteNodes()} disabled={!hasClipboard} title="Paste (⌘V)">
          <Clipboard size={14} />
        </ToolBtn>

        <div className="w-px h-4 bg-[#2a2a2a] mx-1" />

        <button
          onClick={onSave}
          data-tutorial="builder-save"
          className="tb-savebtn flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 rounded-lg
                     bg-[#1a1a1a] hover:bg-[#222] border border-[#2a2a2a]
                     text-white/50 hover:text-white/90 transition"
        >
          <Save size={11} /> Save
        </button>
      </div>

      {/* Right — panel switcher */}
      <div className="flex items-center gap-0.5 bg-[#111] rounded-lg p-0.5 border border-[#1e1e1e] flex-shrink-0" data-tutorial="builder-panel-switcher">
        {PANELS.map(({ id, icon: Icon, label }) => (
          <button
            key={id}
            onClick={() => { setRightPanel(id); onOpenRightPanel?.() }}
            title={label}
            className={cn(
              'tb-toolbtn p-1.5 rounded-md transition-all duration-100 min-w-[36px] min-h-[36px] flex items-center justify-center',
              rightPanel === id
                ? 'bg-[#6366f1]/20 text-[#818cf8]'
                : 'text-white/25 hover:text-white/60 hover:bg-white/5'
            )}
          >
            <Icon size={14} />
          </button>
        ))}
        {onOpenRightPanel && (
          <button
            type="button"
            aria-label="Open panel"
            onClick={onOpenRightPanel}
            className="lg:hidden w-9 h-9 flex items-center justify-center rounded-md text-white/40 hover:text-white/80 hover:bg-white/5"
          >
            <PanelRight size={15} />
          </button>
        )}
      </div>
    </div>
  )
}

const ToolBtn = memo(function ToolBtn({ onClick, disabled, title, children }: {
  onClick: () => void; disabled?: boolean; title?: string; children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="tb-toolbtn p-1.5 rounded text-white/35 hover:text-white/80 disabled:opacity-20
                 disabled:cursor-not-allowed hover:bg-white/5 transition-all duration-100"
    >
      {children}
    </button>
  )
})

// Memoized: onSave is a stable useCallback reference from useAutoSave, so
// with the granular selectors above this component now only re-renders
// when a value it actually displays changes — not on every canvas
// interaction — eliminating a full toolbar re-render on every drag frame.
export const BuilderToolbar = memo(BuilderToolbarImpl)
