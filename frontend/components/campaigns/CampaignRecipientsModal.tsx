'use client'
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Send, CheckCircle2, XCircle, Reply, Eye, Clock, RefreshCw, UserCheck, Bot, HeartHandshake,
} from 'lucide-react'
import { campaignsApi } from '@/lib/api/campaigns'
import { getErrorMessage } from '@/lib/utils/errors'
import { useToast } from '@/components/ui/Toast'
import { cn } from '@/lib/utils/cn'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Card'
import { PageLoader, EmptyState } from '@/components/ui/States'
import type { Campaign, CampaignRecipient, CampaignRecipientStatus } from '@/types/campaigns'

const STATUS_TONE: Record<CampaignRecipientStatus, 'default' | 'success' | 'warning' | 'danger' | 'accent' | 'cyan'> = {
  pending: 'default',
  queued: 'cyan',
  sent: 'accent',
  delivered: 'success',
  read: 'success',
  failed: 'danger',
  opted_out: 'warning',
}

const FILTERS: { value: CampaignRecipientStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'queued', label: 'Queued' },
  { value: 'sent', label: 'Sent' },
  { value: 'delivered', label: 'Delivered' },
  { value: 'failed', label: 'Failed' },
]

/**
 * Requirement: "Show live progress: Queued / Sending / Sent / Delivered /
 * Failed" + Campaign Analytics (Replied / AI Resolved / Human Handoff).
 * Polls recipients every few seconds while the campaign is actively
 * sending so counters move without a manual refresh.
 */
export function CampaignRecipientsModal({
  campaign,
  onClose,
}: {
  campaign: Campaign
  onClose: () => void
}) {
  const { toast } = useToast()
  const qc = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<CampaignRecipientStatus | 'all'>('all')

  const isLive = campaign.status === 'active' || campaign.status === 'scheduled'

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['campaign-recipients', campaign.id, statusFilter],
    queryFn: () => campaignsApi.recipients(campaign.id, {
      status: statusFilter === 'all' ? undefined : statusFilter, page_size: 100,
    }),
    refetchInterval: isLive ? 4000 : false,
  })

  const retryMutation = useMutation({
    mutationFn: () => campaignsApi.retryRecipients(campaign.id),
    onSuccess: (r) => { toast('success', `Retrying ${r.retried} failed message(s).`); refetch() },
    onError: err => toast('error', getErrorMessage(err, 'Could not retry failed recipients.')),
  })

  const takeoverMutation = useMutation({
    mutationFn: ({ recipientId, enabled }: { recipientId: string; enabled: boolean }) =>
      campaignsApi.setTakeover(campaign.id, recipientId, enabled),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['campaign-recipients', campaign.id] }) },
    onError: err => toast('error', getErrorMessage(err, 'Could not update handoff for this recipient.')),
  })

  const recipients = data?.recipients || []
  const outcomeCounts = {
    replied: recipients.filter(r => r.replied).length,
    aiResolved: recipients.filter(r => r.ai_resolved).length,
    escalated: recipients.filter(r => r.escalated).length,
  }
  const failedCount = recipients.filter(r => r.status === 'failed').length

  return (
    <Modal onClose={onClose} title="Campaign Progress" subtitle={campaign.name} maxWidth="max-w-2xl">
      {/* Live send progress */}
      <div className="grid grid-cols-4 gap-2 mb-4">
        {[
          { label: 'Sent', value: campaign.sent_count, icon: Send, tone: 'text-white/80' },
          { label: 'Delivered', value: campaign.delivered_count, icon: CheckCircle2, tone: 'text-emerald-400' },
          { label: 'Failed', value: campaign.failed_count, icon: XCircle, tone: 'text-red-400' },
          { label: 'Replied', value: campaign.replied_count, icon: Reply, tone: 'text-cyan-300' },
        ].map(s => (
          <div key={s.label} className="rounded-xl border border-white/10 bg-white/[0.03] p-3 text-center">
            <s.icon size={14} className={cn('mx-auto mb-1', s.tone)} />
            <p className={cn('text-lg font-bold tabular-nums', s.tone)}>{s.value}</p>
            <p className="text-[9px] text-white/25 uppercase tracking-wide mt-0.5">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Auto-reply / conversation outcome analytics */}
      <div className="grid grid-cols-3 gap-2 mb-4">
        {[
          { label: 'AI Resolved', value: outcomeCounts.aiResolved, icon: Bot, tone: 'text-[#a5b4fc]' },
          { label: 'Human Handoff', value: outcomeCounts.escalated, icon: HeartHandshake, tone: 'text-amber-400' },
          { label: 'Total Replies', value: outcomeCounts.replied, icon: Reply, tone: 'text-cyan-300' },
        ].map(s => (
          <div key={s.label} className="rounded-xl border border-white/10 bg-white/[0.03] p-3 text-center">
            <s.icon size={14} className={cn('mx-auto mb-1', s.tone)} />
            <p className={cn('text-lg font-bold tabular-nums', s.tone)}>{s.value}</p>
            <p className="text-[9px] text-white/25 uppercase tracking-wide mt-0.5">{s.label}</p>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1.5 flex-wrap">
          {FILTERS.map(f => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              className={cn(
                'text-[11px] font-medium px-2.5 py-1 rounded-lg border',
                statusFilter === f.value ? 'bg-[#6366f1]/15 border-[#6366f1]/30 text-[#c7d2fe]' : 'border-white/10 text-white/40 hover:text-white/70'
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        {failedCount > 0 && (
          <Button size="sm" variant="secondary" icon={<RefreshCw size={12} />} onClick={() => retryMutation.mutate()} loading={retryMutation.isPending}>
            Retry Failed ({failedCount})
          </Button>
        )}
      </div>

      {isLoading ? (
        <PageLoader />
      ) : recipients.length === 0 ? (
        <EmptyState icon={<Send size={22} />} title="No recipients yet" description="Recipients will appear here once the campaign starts sending." />
      ) : (
        <div className="max-h-96 overflow-y-auto space-y-1.5">
          {recipients.map(r => (
            <RecipientRow key={r.id} recipient={r} onTakeover={enabled => takeoverMutation.mutate({ recipientId: r.id, enabled })} />
          ))}
        </div>
      )}
    </Modal>
  )
}

function RecipientRow({ recipient, onTakeover }: { recipient: CampaignRecipient; onTakeover: (enabled: boolean) => void }) {
  return (
    <div className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-xl border border-white/10 bg-white/[0.02]">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="text-xs font-semibold text-white/80 truncate">{recipient.contact_name || recipient.contact_identifier}</p>
          <Badge tone={STATUS_TONE[recipient.status]} dot>{recipient.status}</Badge>
          {recipient.replied && <Badge tone="cyan">Replied</Badge>}
          {recipient.ai_resolved && <Badge tone="accent">AI Resolved</Badge>}
          {recipient.escalated && <Badge tone="warning">Human Handoff</Badge>}
        </div>
        <p className="text-[10px] text-white/30 mt-0.5">{recipient.contact_identifier}</p>
        {recipient.error_message && <p className="text-[10px] text-red-400/80 mt-0.5">{recipient.error_message}</p>}
      </div>
      <button
        onClick={() => onTakeover(!recipient.human_takeover)}
        className={cn(
          'flex items-center gap-1 text-[10px] font-medium px-2.5 py-1.5 rounded-lg border flex-shrink-0',
          recipient.human_takeover ? 'bg-amber-500/10 border-amber-500/30 text-amber-300' : 'border-white/10 text-white/40 hover:text-white/70'
        )}
        title={recipient.human_takeover ? 'AI is paused — you are replying manually' : 'Take over this conversation from the AI'}
      >
        <UserCheck size={11} />
        {recipient.human_takeover ? 'AI Paused' : 'Take Over'}
      </button>
    </div>
  )
}
