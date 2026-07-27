'use client'
import { memo } from 'react'
import { Loader2, Bot, Globe } from 'lucide-react'
import type { TopBot } from '@/types/analytics'

function TopBotsTableImpl({ data, loading }: { data: TopBot[] | undefined; loading?: boolean }) {
  const bots = data || []
  const maxConv = Math.max(1, ...bots.map(b => b.conversations))

  return (
    <div className="tb2-glass p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xs font-semibold text-white/60 uppercase tracking-wide">Top Performing Bots</h3>
        {loading && <Loader2 size={12} className="text-white/20 animate-spin" />}
      </div>

      {!loading && bots.length === 0 && (
        <p className="text-xs text-white/20 text-center py-8">No chatbots yet</p>
      )}

      <div className="space-y-2">
        {bots.map((bot, i) => (
          <div key={bot.workflow_id} className="flex items-center gap-3 p-2.5 rounded-xl hover:bg-white/[0.03] transition">
            <span className="text-[10px] text-white/20 w-4 text-right tabular-nums flex-shrink-0">{i + 1}</span>
            <div className="w-7 h-7 rounded-lg bg-[#6366f1]/10 border border-[#6366f1]/20 flex items-center justify-center flex-shrink-0">
              <Bot size={12} className="text-[#818cf8]" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <p className="text-xs font-medium text-white/80 truncate">{bot.name}</p>
                {bot.status === 'published' && <Globe size={9} className="text-emerald-400 flex-shrink-0" />}
              </div>
              <div className="h-1 bg-white/5 rounded-full overflow-hidden mt-1.5">
                <div
                  className="h-full rounded-full bg-[#6366f1] transition-all"
                  style={{ width: `${(bot.conversations / maxConv) * 100}%` }}
                />
              </div>
            </div>
            <div className="text-right flex-shrink-0">
              <p className="text-xs font-semibold text-white/70 tabular-nums">{bot.conversations}</p>
              <p className="text-[9px] text-white/25">{bot.messages} msgs</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export const TopBotsTable = memo(TopBotsTableImpl)
