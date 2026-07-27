'use client'
import { memo } from 'react'
import {
  Play, MessageSquare, List, Bot, GitBranch, Square, Zap,
  GitFork, Link2, Star, MapPin, Video, X,
} from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import { NODE_LIBRARY } from '@/lib/utils/nodeFactory'
import type { NodeType } from '@/types'

const ICONS: Record<string, React.ComponentType<any>> = {
  Play, MessageSquare, List, Bot, GitBranch, Square,
  GitFork, Link2, Star, MapPin, Video,
}

// Memoized — this panel has no reactive props/state of its own, so without
// memoization it was re-rendering (re-running NODE_LIBRARY.map, recreating
// every drag handler) whenever its parent (the canvas) re-rendered on
// unrelated node/edge store updates, e.g. every frame of a node drag.
const DraggableNode = memo(function DraggableNode({
  type, label, description, icon, color, index = 0,
}: { type: NodeType; label: string; description: string; icon: string; color: string; index?: number }) {
  const Icon = ICONS[icon] || Zap
  const onDragStart = (e: React.DragEvent) => {
    e.dataTransfer.setData('application/thunderbots-node', type)
    e.dataTransfer.effectAllowed = 'move'
  }

  return (
    <div
      draggable
      onDragStart={onDragStart}
      data-tutorial={index === 0 ? 'builder-drag-node' : undefined}
      className="tb-lib-item tb-lib-item-glass group flex items-start gap-3 p-3 rounded-xl cursor-grab active:cursor-grabbing tb-anim-fade-up"
      style={{ animationDelay: `${index * 35}ms`, ['--tb-lib-glow' as any]: `${color}55` }}
    >
      <div
        className="tb-lib-icon flex-shrink-0 w-7 h-7 rounded-lg flex items-center justify-center mt-0.5"
        style={{ background: `${color}1c`, border: `1px solid ${color}30` }}
      >
        <Icon size={13} style={{ color }} />
      </div>
      <div className="min-w-0">
        <p className="text-xs font-semibold text-white/80 group-hover:text-white transition-colors">{label}</p>
        <p className="text-[10px] text-white/35 leading-relaxed mt-0.5">{description}</p>
      </div>
    </div>
  )
})

function NodeLibraryPanelImpl({
  mobileOpen = false,
  onMobileClose,
}: {
  /** Controls visibility below the `lg` breakpoint only; ignored at lg+
   *  where the panel is always visible in-flow exactly as before. */
  mobileOpen?: boolean
  onMobileClose?: () => void
}) {
  return (
    <div
      className={cn(
        'tb-lib-panel-glass w-[220px] max-w-[80vw] flex-shrink-0 flex flex-col relative',
        // Below lg: fixed off-canvas drawer, slid in/out with a transform.
        // At lg+: back to the original static, always-visible panel.
        'fixed inset-y-0 left-0 z-40 transition-transform duration-200 ease-out',
        'lg:static lg:z-auto lg:translate-x-0',
        mobileOpen ? 'translate-x-0' : '-translate-x-full'
      )}
    >
      {/* Header */}
      <div className="px-4 py-3 border-b border-white/8 relative z-10 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap size={13} className="text-[#a78bfa]" />
          <span className="text-xs font-semibold text-white/60 uppercase tracking-widest">Nodes</span>
        </div>
        <button
          type="button"
          aria-label="Close node library"
          onClick={onMobileClose}
          className="lg:hidden w-9 h-9 -mr-1 flex items-center justify-center rounded-lg text-white/40 hover:text-white/80 hover:bg-white/[0.06]"
        >
          <X size={15} />
        </button>
      </div>

      {/* Node list */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2 relative z-10">
        <p className="text-[10px] text-white/25 px-1 mb-3">Drag to canvas</p>
        {NODE_LIBRARY.map((n, i) => (
          <DraggableNode key={n.type} {...n} index={i} />
        ))}
      </div>
    </div>
  )
}

export const NodeLibraryPanel = memo(NodeLibraryPanelImpl)
