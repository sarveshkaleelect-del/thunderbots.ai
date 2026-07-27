'use client'
import { BarChart3 } from 'lucide-react'
import { Card, Badge } from '@/components/ui/Card'
import type { Campaign } from '@/types/campaigns'

function rate(n: number, d: number) {
  return d > 0 ? Math.round((n / d) * 100) : 0
}

export function CampaignPerformanceCard({ campaigns }: { campaigns: Campaign[] }) {
  const ranked = [...campaigns]
    .filter(c => c.sent_count > 0)
    .sort((a, b) => rate(b.replied_count, b.sent_count) - rate(a.replied_count, a.sent_count))
    .slice(0, 6)

  return (
    <Card className="tb2-rise p-5">
      <div className="flex items-center gap-2.5 mb-4">
        <div className="w-8 h-8 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center flex-shrink-0">
          <BarChart3 size={14} className="text-cyan-300" />
        </div>
        <h3 className="text-sm font-bold text-white">Campaign Performance</h3>
      </div>

      {ranked.length === 0 && (
        <p className="text-xs text-white/20 py-6 text-center">No sent campaigns yet</p>
      )}

      <div className="space-y-3">
        {ranked.map(c => {
          const deliveryRate = rate(c.delivered_count, c.sent_count)
          const replyRate = rate(c.replied_count, c.sent_count)
          return (
            <div key={c.id} className="flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between mb-1">
                  <p className="text-xs font-medium text-white/85 truncate">{c.name}</p>
                  <Badge tone="cyan">{replyRate}% replied</Badge>
                </div>
                <div className="h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-[#6366f1] to-cyan-400" style={{ width: `${deliveryRate}%` }} />
                </div>
                <p className="text-[10px] text-white/25 mt-1">
                  {c.sent_count} sent · {deliveryRate}% delivered
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}
