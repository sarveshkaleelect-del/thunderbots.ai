'use client'
import { memo } from 'react'
import { Radio, Loader2, Bot, User as UserIcon, AlertCircle } from 'lucide-react'
import type { RealtimeStats } from '@/types/analytics'
import { cn } from '@/lib/utils/cn'

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const s = Math.max(0, Math.floor(diffMs / 1000))
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  return `${h}h ago`
}

function RealtimeFeedImpl({ data, loading }: { data: RealtimeStats | undefined; loading?: boolean }) {
  return (
    <div className="tb2-glass p-5 flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          <h3 className="text-xs font-semibold text-white/60 uppercase tracking-wide">Realtime</h3>
        </div>
        {loading && <Loader2 size={12} className="text-white/20 animate-spin" />}
      </div>

      <div className="grid grid-cols-2 gap-2.5 mb-4">
        <div className="bg-white/[0.03] rounded-xl p-3">
          <p className="text-lg font-bold text-white/80 tabular-nums">{data?.live_conversations ?? '—'}</p>
          <p className="text-[10px] text-white/25 mt-0.5">Active now</p>
        </div>
        <div className="bg-white/[0.03] rounded-xl p-3">
          <p className="text-lg font-bold text-white/80 tabular-nums">{data?.messages_last_5m ?? '—'}</p>
          <p className="text-[10px] text-white/25 mt-0.5">Msgs · 5min</p>
        </div>
      </div>

      <p className="text-[10px] font-semibold text-white/25 uppercase tracking-wider mb-2">Live Activity</p>
      <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
        {(data?.recent_activity || []).map(item => (
          <div key={item.id} className="flex items-start gap-2 py-1.5 border-b border-white/5 last:border-0">
            <div className={cn(
              'w-5 h-5 rounded-md flex items-center justify-center flex-shrink-0 mt-0.5',
              item.is_error ? 'bg-rose-500/10' : item.role === 'bot' ? 'bg-[#6366f1]/10' : 'bg-white/5'
            )}>
              {item.is_error
                ? <AlertCircle size={10} className="text-rose-400" />
                : item.role === 'bot'
                  ? <Bot size={10} className="text-[#818cf8]" />
                  : <UserIcon size={10} className="text-white/40" />}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[11px] text-white/60 truncate">{item.preview || '(empty)'}</p>
              <p className="text-[9px] text-white/20 mt-0.5">{item.workflow_name} · {timeAgo(item.created_at)}</p>
            </div>
          </div>
        ))}
        {!loading && (!data || data.recent_activity.length === 0) && (
          <div className="flex flex-col items-center py-8 gap-2">
            <Radio size={16} className="text-white/15" />
            <p className="text-[11px] text-white/20">Waiting for activity…</p>
          </div>
        )}
      </div>
    </div>
  )
}

export const RealtimeFeed = memo(RealtimeFeedImpl)
