'use client'
import { useEffect, useRef, useState } from 'react'
import {
  MessageCircle, Instagram, Send, Mail, MoreVertical, Pencil, Copy,
  Pause, Play, Trash2, History, CheckCircle2,
  XCircle, Reply, Clock, Activity,
} from 'lucide-react'
import { Card, Badge } from '@/components/ui/Card'
import { IconButton } from '@/components/ui/Button'
import { cn } from '@/lib/utils/cn'
import type { Campaign, CampaignChannel, CampaignStatus } from '@/types/campaigns'

const CHANNEL_ICON: Record<CampaignChannel, any> = {
  whatsapp: MessageCircle,
  instagram: Instagram,
  telegram: Send,
  email: Mail,
}

const STATUS_TONE: Record<CampaignStatus, 'default' | 'success' | 'warning' | 'danger' | 'accent' | 'cyan'> = {
  draft: 'default',
  scheduled: 'cyan',
  active: 'success',
  paused: 'warning',
  completed: 'accent',
  cancelled: 'danger',
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function CampaignCard({
  campaign,
  onEdit,
  onDuplicate,
  onDelete,
  onPause,
  onResume,
  onHistory,
  onProgress,
  style,
}: {
  campaign: Campaign
  onEdit: () => void
  onDuplicate: () => void
  onDelete: () => void
  onPause: () => void
  onResume: () => void
  onHistory: () => void
  onProgress: () => void
  style?: React.CSSProperties
}) {
  const ChannelIcon = CHANNEL_ICON[campaign.channel] || MessageCircle
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const act = (fn: () => void) => () => { setOpen(false); fn() }

  return (
    <Card hover className="tb2-rise group relative overflow-hidden p-5" style={style} onClick={onEdit}>
      <div className="flex items-start justify-between gap-3 mb-3.5">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-xl tb2-brand-mark flex items-center justify-center flex-shrink-0">
            <ChannelIcon size={15} className="text-[#a5b4fc]" />
          </div>
          <div className="min-w-0">
            <p className="font-semibold text-sm text-white/90 truncate">{campaign.name}</p>
            <p className="text-[11px] text-white/30 truncate mt-0.5 capitalize">{campaign.channel}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <Badge tone={STATUS_TONE[campaign.status]} dot>{campaign.status}</Badge>
          <div className="relative" ref={ref}>
            <IconButton
              aria-label="Campaign actions"
              className={cn('transition-opacity', open ? 'opacity-100' : 'opacity-0 group-hover:opacity-100')}
              onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
            >
              <MoreVertical size={14} />
            </IconButton>
            {open && (
              <div className="tb2-glass tb2-popover-in origin-top-right absolute right-0 top-[calc(100%+6px)] z-30 w-44 p-1.5 rounded-2xl shadow-2xl overflow-hidden">
                <button onClick={e => { e.stopPropagation(); act(onEdit)() }} className="tb2-row w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-white/70 hover:bg-white/[0.06] hover:text-white text-left">
                  <Pencil size={13} className="text-white/40" /> Edit
                </button>
                <button onClick={e => { e.stopPropagation(); act(onDuplicate)() }} className="tb2-row w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-white/70 hover:bg-white/[0.06] hover:text-white text-left">
                  <Copy size={13} className="text-white/40" /> Duplicate
                </button>
                {(campaign.status === 'active' || campaign.status === 'scheduled') && (
                  <button onClick={e => { e.stopPropagation(); act(onPause)() }} className="tb2-row w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-white/70 hover:bg-amber-500/10 hover:text-amber-300 text-left">
                    <Pause size={13} className="text-white/40" /> Pause
                  </button>
                )}
                {campaign.status === 'paused' && (
                  <button onClick={e => { e.stopPropagation(); act(onResume)() }} className="tb2-row w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-white/70 hover:bg-emerald-500/10 hover:text-emerald-300 text-left">
                    <Play size={13} className="text-white/40" /> Resume
                  </button>
                )}
                {campaign.status !== 'draft' && (
                  <button onClick={e => { e.stopPropagation(); act(onProgress)() }} className="tb2-row w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-white/70 hover:bg-white/[0.06] hover:text-white text-left">
                    <Activity size={13} className="text-white/40" /> View Progress
                  </button>
                )}
                <button onClick={e => { e.stopPropagation(); act(onHistory)() }} className="tb2-row w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-white/70 hover:bg-white/[0.06] hover:text-white text-left">
                  <History size={13} className="text-white/40" /> History
                </button>
                <div className="h-px bg-white/[0.06] mx-1 my-1" />
                <button
                  onClick={e => {
                    e.stopPropagation()
                    setOpen(false)
                    if (window.confirm(`Delete "${campaign.name}"? This cannot be undone.`)) onDelete()
                  }}
                  className="tb2-row w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-red-400/90 hover:bg-red-500/10 text-left"
                >
                  <Trash2 size={13} /> Delete
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <p className="text-xs text-white/45 line-clamp-2 min-h-[2.5em] mb-4">{campaign.message || 'No message yet.'}</p>

      <div
        className="grid grid-cols-4 gap-2 mb-3 -mx-1 px-1 py-1 rounded-lg hover:bg-white/[0.03]"
        onClick={e => { e.stopPropagation(); onProgress() }}
      >
        {[
          { label: 'Sent', value: campaign.sent_count, icon: Send },
          { label: 'Delivered', value: campaign.delivered_count, icon: CheckCircle2 },
          { label: 'Failed', value: campaign.failed_count, icon: XCircle },
          { label: 'Replied', value: campaign.replied_count, icon: Reply },
        ].map(s => (
          <div key={s.label} className="text-center">
            <p className="text-sm font-bold text-white/80 tabular-nums">{s.value}</p>
            <p className="text-[9px] text-white/25 uppercase tracking-wide mt-0.5">{s.label}</p>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-1.5 text-[10px] text-white/25 pt-2 border-t border-white/[0.06]">
        <Clock size={10} />
        {campaign.schedule_type === 'later' && campaign.scheduled_at
          ? `Scheduled for ${formatDate(campaign.scheduled_at)}`
          : `Created ${formatDate(campaign.created_at)}`}
      </div>
    </Card>
  )
}
