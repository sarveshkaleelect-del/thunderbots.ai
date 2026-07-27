'use client'
import { useQuery } from '@tanstack/react-query'
import { History, Loader2, Bot, HeartHandshake, Reply as ReplyIcon } from 'lucide-react'
import { Card, Badge } from '@/components/ui/Card'
import { campaignsApi } from '@/lib/api/campaigns'

function formatDateTime(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function BroadcastHistoryCard() {
  const { data = [], isLoading } = useQuery({
    queryKey: ['campaigns-broadcast-history'],
    queryFn: () => campaignsApi.broadcastHistory(20),
  })

  return (
    <Card className="tb2-rise p-5">
      <div className="flex items-center gap-2.5 mb-4">
        <div className="w-8 h-8 rounded-xl bg-white/[0.06] border border-white/10 flex items-center justify-center flex-shrink-0">
          <History size={14} className="text-white/60" />
        </div>
        <h3 className="text-sm font-bold text-white">Broadcast History</h3>
        {isLoading && <Loader2 size={12} className="text-white/20 animate-spin" />}
      </div>

      {!isLoading && data.length === 0 && (
        <p className="text-xs text-white/20 py-6 text-center">No broadcasts sent yet</p>
      )}

      <div className="space-y-1.5 max-h-80 overflow-y-auto">
        {data.map(entry => (
          <div key={entry.id} className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-xl bg-white/[0.02] border border-white/[0.05]">
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-white/85 truncate">{entry.campaign_name}</p>
              <p className="text-[11px] text-white/30 mt-0.5 truncate">
                {entry.contact_name || entry.contact_identifier} · {entry.channel} · {formatDateTime(entry.sent_at)}
              </p>
            </div>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <Badge tone={entry.status === 'failed' ? 'danger' : entry.status === 'delivered' || entry.status === 'read' ? 'success' : 'default'}>
                {entry.status}
              </Badge>
              {entry.replied && <ReplyIcon size={12} className="text-cyan-300" />}
              {entry.ai_resolved && <Bot size={12} className="text-[#a5b4fc]" />}
              {entry.escalated && <HeartHandshake size={12} className="text-amber-400" />}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
