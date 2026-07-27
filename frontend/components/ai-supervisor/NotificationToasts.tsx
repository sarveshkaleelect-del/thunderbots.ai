// ============================================================
// ThunderBots — AI Supervisor: Real-time Notifications (NEW, final phase)
//
// Toasts for: new conversation, human takeover, high priority conversation,
// AI paused, conversation closed. Four of the five kinds are pushed by the
// backend the instant the relevant supervisor action happens (see
// services/ai_supervisor_service.py `_notify`, broadcast over the existing
// agent-dashboard WebSocket — no new socket channel). "New conversation" is
// derived client-side by diffing the conversation list for IDs not seen
// before, so the Runtime/chat pipeline that actually creates conversations
// never needs to change.
// ============================================================
'use client'
import { memo } from 'react'
import { X, MessageSquarePlus, Headset, Flag, PauseCircle, Archive, ArchiveRestore, Bell } from 'lucide-react'
import { useSupervisorConversations, useSupervisorNotifications } from '@/hooks/useAiSupervisor'
import type { NotificationKind } from '@/types/aiSupervisor'
import { cn } from '@/lib/utils/cn'

const KIND_ICON: Record<NotificationKind, any> = {
  new_conversation: MessageSquarePlus,
  human_takeover: Headset,
  high_priority: Flag,
  ai_paused: PauseCircle,
  conversation_closed: Archive,
  conversation_reopened: ArchiveRestore,
}

const SEVERITY_STYLES: Record<string, string> = {
  info: 'border-white/10 text-white/70',
  warning: 'border-amber-500/30 text-amber-300',
  critical: 'border-rose-500/30 text-rose-300',
}

function NotificationToastsImpl() {
  // Broad, filter-independent view of active conversations purely so
  // "new conversation" can be detected by diffing IDs — decoupled from
  // whatever filters/pagination the supervisor has applied to the table.
  const { data } = useSupervisorConversations({ state: 'active', page: 1, page_size: 50 })
  const conversationIds = data?.items.map(i => i.id)
  const { notifications, dismiss } = useSupervisorNotifications(conversationIds)

  if (notifications.length === 0) return null

  return (
    <div className="fixed top-4 right-4 z-[60] flex flex-col gap-2 w-80 max-w-[calc(100vw-2rem)]">
      {notifications.map(n => {
        const Icon = KIND_ICON[n.kind] || Bell
        return (
          <div
            key={n.id}
            className={cn(
              'flex items-start gap-2.5 px-3.5 py-3 rounded-xl bg-[#141414] border shadow-xl animate-slide-up',
              SEVERITY_STYLES[n.severity] || SEVERITY_STYLES.info
            )}
          >
            <Icon size={14} className="flex-shrink-0 mt-0.5" />
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-medium leading-snug">{n.title}</p>
              <p className="text-[9px] text-white/25 mt-0.5">{new Date(n.created_at).toLocaleTimeString()}</p>
            </div>
            <button onClick={() => dismiss(n.id)} className="text-white/20 hover:text-white/60 flex-shrink-0">
              <X size={12} />
            </button>
          </div>
        )
      })}
    </div>
  )
}

export const NotificationToasts = memo(NotificationToastsImpl)
