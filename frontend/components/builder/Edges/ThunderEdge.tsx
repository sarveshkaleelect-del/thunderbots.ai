'use client'
import { memo, useState, useCallback, useMemo } from 'react'
import {
  EdgeProps, getBezierPath, EdgeLabelRenderer,
  BaseEdge, useReactFlow,
} from 'reactflow'
import { X } from 'lucide-react'
import { useWorkflowStore } from '@/store/workflowStore'

export const ThunderEdge = memo(({
  id, sourceX, sourceY, targetX, targetY,
  sourcePosition, targetPosition, data, selected, markerEnd,
}: EdgeProps) => {
  const [hovered, setHovered] = useState(false)
  const deleteEdge = useWorkflowStore(s => s.deleteEdge)

  // A slightly deeper curvature than the ReactFlow default gives the
  // connection a more graceful, organic "S" — the signature ThunderBots
  // bezier — without changing anchor points or connection logic.
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX, sourceY, sourcePosition,
    targetX, targetY, targetPosition,
    curvature: 0.32,
  })

  const onDelete = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    deleteEdge(id)
  }, [id, deleteEdge])

  const isVisible = selected || hovered
  const gradientId = useMemo(() => `tb-edge-grad-${id}`, [id])

  return (
    <>
      <defs>
        {/* Subtle electric gradient along the line — brighter toward the
            middle, giving the current a sense of directional travel
            instead of a flat single-tone stroke. */}
        <linearGradient id={gradientId} gradientUnits="userSpaceOnUse"
          x1={sourceX} y1={sourceY} x2={targetX} y2={targetY}>
          <stop offset="0%" stopColor={selected ? '#818cf8' : '#4f52cc'} stopOpacity="0.35" />
          <stop offset="50%" stopColor={selected ? '#c4b5fd' : '#6366f1'} stopOpacity="1" />
          <stop offset="100%" stopColor={selected ? '#818cf8' : '#4f52cc'} stopOpacity="0.35" />
        </linearGradient>
      </defs>

      {/* Wide invisible hit area */}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={20}
        className="cursor-pointer"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      />

      {/* Visible edge */}
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: selected ? '#818cf8' : hovered ? '#5457d1' : '#2e2e34',
          strokeWidth: isVisible ? 2.25 : 1.5,
          strokeLinecap: 'round',
          transition: 'stroke 0.14s ease, stroke-width 0.14s ease, filter 0.18s ease',
          filter: selected
            ? 'drop-shadow(0 0 7px rgba(129,140,248,0.65)) drop-shadow(0 0 2px rgba(129,140,248,0.5))'
            : hovered
              ? 'drop-shadow(0 0 4px rgba(99,102,241,0.35))'
              : 'none',
        }}
      />

      {/* ThunderBots signature current — a slow traveling pulse layered
          over the base line, distinct from a plain dashed connector.
          Rendered with the electric gradient for a subtle flow effect. */}
      <path
        d={edgePath}
        fill="none"
        stroke={`url(#${gradientId})`}
        strokeWidth={isVisible ? 1.6 : 1.1}
        strokeDasharray="1 9"
        strokeLinecap="round"
        className="tb-edge-current"
        style={{
          opacity: isVisible ? 1 : 0.4,
          transition: 'opacity 0.18s ease, stroke-width 0.18s ease',
          pointerEvents: 'none',
        }}
      />

      {/* Delete button + optional label — shown on hover/select */}
      <EdgeLabelRenderer>
        <div
          className="absolute pointer-events-none"
          style={{ transform: `translate(-50%,-50%) translate(${labelX}px,${labelY}px)` }}
        >
          {/* Edge label */}
          {data?.label && (
            <div className="text-[10px] px-1.5 py-0.5 rounded bg-[#1a1a1a] border border-[#2a2a2a] text-white/40 whitespace-nowrap mb-1 text-center">
              {data.label}
            </div>
          )}

          {/* Delete button */}
          {isVisible && (
            <button
              onClick={onDelete}
              onMouseEnter={() => setHovered(true)}
              onMouseLeave={() => setHovered(false)}
              className="pointer-events-auto w-5 h-5 rounded-full bg-[#1a1a1a] border border-[#3a3a3a]
                         hover:bg-red-500/20 hover:border-red-500/50 flex items-center justify-center
                         transition-all duration-100 mx-auto shadow-[0_2px_8px_rgba(0,0,0,0.5)]"
              title="Delete connection"
            >
              <X size={9} className="text-white/40 hover:text-red-400" />
            </button>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  )
})

ThunderEdge.displayName = 'ThunderEdge'

export const edgeTypes = { thunder: ThunderEdge }
