'use client'
import { memo, ReactNode, useEffect, useState } from 'react'
import { NodeProps } from 'reactflow'
import { cn } from '@/lib/utils/cn'
import { useWorkflowStore } from '@/store/workflowStore'

export type NodeShape =
  | 'rounded'
  | 'octagon'
  | 'hex'
  | 'chamfer'
  | 'octagon-wide'
  | 'octagon-premium'
  | 'diamond-octagon'

interface BaseNodeProps extends NodeProps {
  icon: ReactNode
  label: string
  accentColor: string
  children: ReactNode
  /** Connection handles for this node. Rendered OUTSIDE the clipped card
   *  face (as siblings of it) so a faceted silhouette (hex/octagon/etc)
   *  never crops or misaligns a connector dot sitting on its edge. */
  handles?: ReactNode
  className?: string
  /** Signature ThunderBots silhouette for this node type. Defaults to the
   *  original rounded-rectangle card if omitted. */
  shape?: NodeShape
  /** Adds a faint inner facet ring for "premium" node types. */
  premium?: boolean
  /** Two-stop vibrant gradient unique to this node type. Falls back to a
   *  flat accentColor-derived gradient if omitted. */
  gradient?: [string, string]
  /** Stacked header layout — title on top, icon centered below it, then
   *  the description underneath the icon. Used by the Start node. */
  stacked?: boolean
}

const SHAPE_CLASS: Record<NodeShape, string> = {
  rounded: 'rounded-2xl',
  octagon: 'tb-shape-octagon',
  hex: 'tb-shape-hex',
  chamfer: 'tb-shape-chamfer',
  'octagon-wide': 'tb-shape-octagon-wide',
  'octagon-premium': 'tb-shape-octagon-premium',
  'diamond-octagon': 'tb-shape-diamond-octagon',
}

export const BaseNode = memo(function BaseNode({
  id, selected, icon, label, accentColor, children, handles, className,
  shape = 'rounded', premium, gradient, stacked,
}: BaseNodeProps) {
  const setSelectedNode = useWorkflowStore(s => s.setSelectedNode)

  // Plays the entrance animation once on mount (new node drop / initial
  // canvas load) without ever re-triggering on re-render or selection.
  const [entered, setEntered] = useState(false)
  useEffect(() => {
    const frame = requestAnimationFrame(() => setEntered(true))
    return () => cancelAnimationFrame(frame)
  }, [])

  const [gFrom, gTo] = gradient ?? [accentColor, accentColor]

  const glow = `${gTo}80`
  const glowSoft = `${gFrom}40`
  const shapeClass = SHAPE_CLASS[shape]

  // The "outline" layer is a vibrant gradient fill (or the selection
  // highlight color), clipped to the exact same silhouette as the card.
  // The card itself sits inset by a hair-line margin on top of it. This
  // reproduces a crisp, anti-aliased border along diagonal/faceted edges
  // — a plain CSS `border` on a `clip-path` box renders jagged and
  // inconsistent per-side, which was the source of the "broken polygon"
  // look.
  const outlineBackground = selected
    ? 'linear-gradient(135deg, #a5b4fc, #6366f1)'
    : `linear-gradient(135deg, ${gFrom}cc, ${gTo}cc)`

  return (
    <div
      onClick={() => setSelectedNode(id)}
      className={cn('tb-node-shell', selected && 'tb-node-selected-shell', entered && 'tb-node-enter')}
      style={{
        opacity: entered ? undefined : 0,
        ['--tb-glow' as any]: glow,
        ['--tb-glow-soft' as any]: glowSoft,
        ['--tb-accent' as any]: accentColor,
        ['--tb-grad-from' as any]: gFrom,
        ['--tb-grad-to' as any]: gTo,
      }}
    >
      <div
        className={cn('min-w-[240px] max-w-[300px] tb-node-outline', shapeClass)}
        style={{ background: outlineBackground }}
      >
        <div
          className={cn('bg-[#141414] select-none tb-node-card tb-node-inner-glow', premium && 'tb-node-premium-ring', shapeClass, className)}
          style={{ margin: 1.5 }}
        >
          {/* Premium corner glow — soft accent bloom in the top-left
              facet, purely decorative, sits below the content layer. */}
          <div
            className="tb-node-corner-glow"
            style={{ background: `radial-gradient(130px circle at 12% 8%, ${gFrom}38, transparent 60%)` }}
          />

          {stacked ? (
            <>
              {/* Header — title only, centered on top */}
              <div
                className="relative z-10 flex items-center justify-center px-3.5 pt-3 pb-2 tb-node-header"
                style={{
                  background: `linear-gradient(90deg, ${gFrom}22, ${gTo}22)`,
                  borderBottom: `1px solid ${gFrom}30`,
                }}
              >
                <span className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-white/70">
                  {label}
                </span>
              </div>

              {/* Body — icon centered below title, description below icon */}
              <div className="relative z-10 flex flex-col items-center gap-2 px-3.5 py-3.5 text-center">
                <span
                  className="tb-node-icon flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center"
                  style={{
                    color: gTo,
                    background: `linear-gradient(135deg, ${gFrom}33, ${gTo}33)`,
                    border: `1px solid ${gFrom}55`,
                  }}
                >
                  {icon}
                </span>
                <div className="space-y-1">{children}</div>
              </div>
            </>
          ) : (
            <>
              {/* Header */}
              <div
                className="relative z-10 flex items-center gap-2.5 px-3.5 py-2.5 tb-node-header"
                style={{
                  background: `linear-gradient(90deg, ${gFrom}22, ${gTo}22)`,
                  borderBottom: `1px solid ${gFrom}30`,
                }}
              >
                <span style={{ color: gTo }} className="flex-shrink-0 tb-node-icon">{icon}</span>
                <span className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-white/55">
                  {label}
                </span>
              </div>

              {/* Body */}
              <div className="relative z-10 p-3.5 space-y-2">{children}</div>
            </>
          )}
        </div>
      </div>

      {/* Connection handles — unclipped, positioned against the shell */}
      {handles}
    </div>
  )
})
