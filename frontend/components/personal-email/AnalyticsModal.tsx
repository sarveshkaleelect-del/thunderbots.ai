'use client'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, Inbox, Send, ShieldAlert, Clock3, Bot } from 'lucide-react'
import { Modal } from '@/components/ui/Modal'
import { Skeleton } from '@/components/ui/States'
import { Badge } from '@/components/ui/Card'
import { personalEmailApi } from '@/lib/api/personalEmail'

function StatTile({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="tb2-glass rounded-xl p-3 flex items-center gap-2.5">
      <div className="w-8 h-8 rounded-lg bg-[#6366f1]/15 text-[#a5b4fc] flex items-center justify-center flex-shrink-0">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-base font-semibold text-white leading-tight">{value}</p>
        <p className="text-[10px] text-white/35 truncate">{label}</p>
      </div>
    </div>
  )
}

function BreakdownList({ title, data }: { title: string; data: Record<string, number> }) {
  const entries = Object.entries(data).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1])
  if (entries.length === 0) return null
  const max = Math.max(...entries.map(([, v]) => v))
  return (
    <div className="space-y-1.5">
      <p className="text-[10px] font-semibold text-white/35 uppercase tracking-wide">{title}</p>
      {entries.map(([key, value]) => (
        <div key={key} className="flex items-center gap-2">
          <span className="text-xs text-white/55 w-24 truncate flex-shrink-0 capitalize">{key}</span>
          <div className="flex-1 h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
            <div className="h-full bg-[#6366f1]/60 rounded-full" style={{ width: `${(value / max) * 100}%` }} />
          </div>
          <span className="text-[11px] text-white/35 w-6 text-right flex-shrink-0">{value}</span>
        </div>
      ))}
    </div>
  )
}

export function AnalyticsModal({ accountId, onClose }: { accountId: string; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ['personal-email-analytics', accountId],
    queryFn: () => personalEmailApi.analytics(accountId, 30),
  })

  return (
    <Modal onClose={onClose} title="Email Analytics" subtitle="Last 30 days for this account" maxWidth="max-w-lg">
      <div className="space-y-4">
        {isLoading && <Skeleton className="h-48 w-full rounded-xl" />}

        {!isLoading && data && (
          <>
            <div className="grid grid-cols-2 gap-2.5">
              <StatTile icon={<Inbox size={15} />} label="Received" value={data.total_received} />
              <StatTile icon={<Send size={15} />} label="Sent" value={data.total_sent} />
              <StatTile icon={<Bot size={15} />} label="AI replies sent" value={data.ai_replies_sent} />
              <StatTile icon={<ShieldAlert size={15} />} label="Spam/phishing caught" value={data.spam_caught} />
            </div>

            <div className="tb2-glass rounded-xl p-3 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Clock3 size={14} className="text-white/40" />
                <span className="text-xs text-white/55">Avg. response time</span>
              </div>
              <span className="text-sm font-semibold text-white">
                {data.avg_response_time_hours != null ? `${data.avg_response_time_hours}h` : '—'}
              </span>
            </div>

            {data.unanswered_count > 0 && (
              <div className="flex items-center gap-2">
                <Badge tone="warning">{data.unanswered_count} unanswered right now</Badge>
              </div>
            )}

            <div className="tb2-glass rounded-xl p-4 space-y-4">
              <p className="text-xs font-semibold text-white/50 uppercase tracking-wide flex items-center gap-1.5">
                <BarChart3 size={12} /> Breakdown
              </p>
              <BreakdownList title="By category" data={data.by_category} />
              <BreakdownList title="By priority" data={data.by_priority} />
              <BreakdownList title="By sentiment" data={data.by_sentiment} />
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}
