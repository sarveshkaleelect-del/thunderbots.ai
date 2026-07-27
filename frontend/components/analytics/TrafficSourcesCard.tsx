'use client'
import { memo } from 'react'
import { Loader2, Globe, Code2, MousePointer, Webhook, MessageCircle, Send } from 'lucide-react'
import type { TrafficSource } from '@/types/analytics'

const SOURCE_META: Record<string, { label: string; icon: any; color: string; future?: boolean }> = {
  website:      { label: 'Website',      icon: Globe,         color: '#6366f1' },
  embed_widget: { label: 'Embed Widget', icon: Code2,         color: '#818cf8' },
  direct:       { label: 'Direct',       icon: MousePointer,  color: '#a5b4fc' },
  api:          { label: 'API',          icon: Webhook,       color: '#38bdf8' },
  whatsapp:     { label: 'WhatsApp',     icon: MessageCircle, color: '#34d399', future: true },
  telegram:     { label: 'Telegram',     icon: Send,          color: '#60a5fa', future: true },
}

function TrafficSourcesCardImpl({ data, loading }: { data: TrafficSource[] | undefined; loading?: boolean }) {
  const total = (data || []).reduce((s, d) => s + d.count, 0)

  return (
    <div className="tb2-glass p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xs font-semibold text-white/60 uppercase tracking-wide">Traffic Sources</h3>
        {loading && <Loader2 size={12} className="text-white/20 animate-spin" />}
      </div>

      <div className="space-y-3">
        {(data || []).map(s => {
          const meta = SOURCE_META[s.source] || { label: s.source, icon: Globe, color: '#818cf8' }
          const Icon = meta.icon
          return (
            <div key={s.source} className="flex items-center gap-3">
              <div className="w-7 h-7 rounded-lg bg-white/5 flex items-center justify-center flex-shrink-0">
                <Icon size={12} style={{ color: meta.color }} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-white/60 flex items-center gap-1.5">
                    {meta.label}
                    {meta.future && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-white/25 border border-white/8">
                        soon
                      </span>
                    )}
                  </span>
                  <span className="text-xs text-white/40 tabular-nums">{s.count}</span>
                </div>
                <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{ width: `${s.percentage}%`, backgroundColor: meta.color }}
                  />
                </div>
              </div>
            </div>
          )
        })}
        {!loading && total === 0 && (
          <p className="text-xs text-white/20 text-center py-4">No conversations in this range yet</p>
        )}
      </div>
    </div>
  )
}

export const TrafficSourcesCard = memo(TrafficSourcesCardImpl)
