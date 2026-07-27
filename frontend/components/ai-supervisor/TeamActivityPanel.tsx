// ============================================================
// ThunderBots — AI Supervisor: Team Activity Panel (NEW, final phase)
// Agent presence/load (reuses live_agent_service's AgentProfile data via
// GET /ai-supervisor/agents) plus the most recent supervisor actions
// across the whole workspace (assign/reassign, close/reopen, tags,
// priority, pin, export, bulk actions). Matches the visual language of
// the rest of the AI Supervisor page — no new design system introduced.
// ============================================================
'use client'
import { memo } from 'react'
import { Loader2, Circle } from 'lucide-react'
import { useTeamActivity } from '@/hooks/useAiSupervisor'
import { cn } from '@/lib/utils/cn'

function fmtDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

const STATUS_STYLES: Record<string, string> = {
  online: 'text-emerald-400',
  busy: 'text-amber-400',
  offline: 'text-white/20',
}

function TeamActivityPanelImpl() {
  const { data, isLoading } = useTeamActivity(30)
  const agents = data?.agents || []
  const recent = data?.recent_activity || []

  return (
    <div className="tb2-glass overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1a1a1a]">
        <p className="text-xs font-semibold text-white/70">Team activity</p>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-10">
          <Loader2 size={16} className="text-[#6366f1] animate-spin" />
        </div>
      )}

      {!isLoading && (
        <>
          <div className="px-4 py-3 border-b border-[#1a1a1a] space-y-2 max-h-48 overflow-y-auto">
            {agents.length === 0 && (
              <p className="text-[11px] text-white/20 italic">No team members yet.</p>
            )}
            {agents.map(a => (
              <div key={a.user_id} className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 min-w-0">
                  <Circle size={7} className={cn('flex-shrink-0 fill-current', STATUS_STYLES[a.status] || 'text-white/20')} />
                  <span className="text-[11px] text-white/70 truncate">{a.name}</span>
                </div>
                <span className="text-[10px] text-white/30 whitespace-nowrap">
                  {a.active_chat_count}/{a.max_concurrent_chats} chats
                </span>
              </div>
            ))}
          </div>

          <div className="px-4 py-3 space-y-2 max-h-64 overflow-y-auto">
            <p className="text-[10px] text-white/25 uppercase tracking-wider mb-1">Recent activity</p>
            {recent.length === 0 && (
              <p className="text-[11px] text-white/20 italic">No supervisor activity yet.</p>
            )}
            {recent.map(a => (
              <div key={a.id} className="text-[10px] text-white/40 flex items-start gap-1.5">
                <span className="text-white/20 whitespace-nowrap">{fmtDate(a.created_at)}</span>
                <span className="text-white/60 capitalize">{a.event_type.replace(/_/g, ' ')}</span>
                {a.actor_name && <span className="text-white/25">by {a.actor_name}</span>}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export const TeamActivityPanel = memo(TeamActivityPanelImpl)
