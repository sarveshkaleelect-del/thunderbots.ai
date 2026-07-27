'use client'
import { cn } from '@/lib/utils/cn'

export function Card({
  className,
  hover = false,
  as: As = 'div',
  ...rest
}: React.HTMLAttributes<HTMLDivElement> & { hover?: boolean; as?: any }) {
  return (
    <As
      className={cn('tb2-glass', hover && 'tb2-glass-hover tb2-card cursor-pointer', className)}
      {...rest}
    />
  )
}

type BadgeTone = 'default' | 'success' | 'warning' | 'danger' | 'accent' | 'cyan'

const toneCls: Record<BadgeTone, string> = {
  default: 'bg-white/[0.05] text-white/40 border-white/10',
  success: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  warning: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  danger: 'bg-red-500/10 text-red-400 border-red-500/20',
  accent: 'bg-[#6366f1]/10 text-[#a5b4fc] border-[#6366f1]/25',
  cyan: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/25',
}

export function Badge({
  tone = 'default',
  className,
  children,
  dot,
}: {
  tone?: BadgeTone
  className?: string
  children: React.ReactNode
  dot?: boolean
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 text-[9px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wide border',
        toneCls[tone],
        className
      )}
    >
      {dot && (
        <span
          className={cn(
            'w-1.5 h-1.5 rounded-full',
            tone === 'success' && 'bg-emerald-400 tb2-pulse-dot',
            tone === 'warning' && 'bg-amber-400',
            tone === 'danger' && 'bg-red-400',
            tone === 'accent' && 'bg-[#818cf8]',
            tone === 'cyan' && 'bg-cyan-300',
            tone === 'default' && 'bg-white/30'
          )}
        />
      )}
      {children}
    </span>
  )
}
