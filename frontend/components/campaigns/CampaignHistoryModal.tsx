'use client'
import { useQuery } from '@tanstack/react-query'
import { History, CheckCircle2, Pause, Play, Copy, Wand2, Pencil, PlusCircle } from 'lucide-react'
import { campaignsApi } from '@/lib/api/campaigns'
import { Modal } from '@/components/ui/Modal'
import { PageLoader, EmptyState } from '@/components/ui/States'
import type { Campaign } from '@/types/campaigns'

const EVENT_META: Record<string, { label: string; icon: any }> = {
  created: { label: 'Campaign created', icon: PlusCircle },
  updated: { label: 'Campaign updated', icon: Pencil },
  duplicated: { label: 'Duplicated', icon: Copy },
  paused: { label: 'Paused', icon: Pause },
  resumed: { label: 'Resumed', icon: Play },
  ai_rewrite: { label: 'AI rewrote the message', icon: Wand2 },
  status_change: { label: 'Status changed', icon: CheckCircle2 },
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export function CampaignHistoryModal({
  campaign,
  onClose,
}: {
  campaign: Campaign
  onClose: () => void
}) {
  const { data, isLoading } = useQuery({
    queryKey: ['campaign-history', campaign.id],
    queryFn: () => campaignsApi.history(campaign.id),
  })

  return (
    <Modal onClose={onClose} title="Campaign History" subtitle={campaign.name} maxWidth="max-w-md">
      {isLoading ? (
        <PageLoader />
      ) : !data || data.length === 0 ? (
        <EmptyState icon={<History size={22} />} title="No history yet" description="Actions on this campaign will show up here." />
      ) : (
        <div className="space-y-1">
          {data.map(entry => {
            const meta = EVENT_META[entry.event_type] || { label: entry.event_type, icon: History }
            const Icon = meta.icon
            return (
              <div key={entry.id} className="flex items-start gap-3 py-2.5 border-b border-white/[0.06] last:border-0">
                <div className="w-7 h-7 rounded-lg bg-white/[0.05] border border-white/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Icon size={12} className="text-white/50" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-white/80">{meta.label}</p>
                  <p className="text-[10px] text-white/30 mt-0.5">{formatDate(entry.created_at)}</p>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </Modal>
  )
}
