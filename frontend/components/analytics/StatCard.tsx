'use client'
import { memo } from 'react'
import { LucideIcon, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils/cn'

interface StatCardProps {
  label: string
  value: string | number
  icon: LucideIcon
  accent?: 'indigo' | 'emerald' | 'amber' | 'rose' | 'sky' | 'violet' | 'cyan'
  loading?: boolean
  suffix?: string
  hint?: string
}

const ACCENTS: Record<NonNullable<StatCardProps['accent']>, string> = {
  indigo: 'bg-[#6366f1]/10 border-[#6366f1]/20 text-[#818cf8]',
  emerald: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400',
  amber: 'bg-amber-500/10 border-amber-500/20 text-amber-400',
  rose: 'bg-rose-500/10 border-rose-500/20 text-rose-400',
  sky: 'bg-sky-500/10 border-sky-500/20 text-sky-400',
  violet: 'bg-violet-500/10 border-violet-500/20 text-violet-400',
  cyan: 'bg-cyan-500/10 border-cyan-500/20 text-cyan-300',
}

function StatCardImpl({ label, value, icon: Icon, accent = 'indigo', loading, suffix, hint }: StatCardProps) {
  return (
    <div className="tb2-glass tb2-glass-hover p-4 flex flex-col gap-3 min-w-0">
      <div className="flex items-center justify-between">
        <div className={cn('w-8 h-8 rounded-xl border flex items-center justify-center', ACCENTS[accent])}>
          <Icon size={14} />
        </div>
        {loading && <Loader2 size={12} className="text-white/20 animate-spin" />}
      </div>
      <div>
        <p className="text-xl font-bold text-white/90 tabular-nums truncate">
          {loading ? '—' : value}{!loading && suffix ? <span className="text-xs text-white/30 ml-1">{suffix}</span> : null}
        </p>
        <p className="text-[11px] text-white/30 mt-0.5 truncate">{label}</p>
        {hint && <p className="text-[10px] text-white/20 mt-1 truncate">{hint}</p>}
      </div>
    </div>
  )
}

export const StatCard = memo(StatCardImpl)
