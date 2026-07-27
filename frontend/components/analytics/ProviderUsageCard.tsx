'use client'
import { memo } from 'react'
import { Loader2 } from 'lucide-react'
import type { ProviderUsage } from '@/types/analytics'

const PROVIDER_META: Record<string, { label: string; color: string }> = {
  gemini: { label: 'Gemini', color: '#4285f4' },
}

function ProviderUsageCardImpl({ data, loading }: { data: ProviderUsage[] | undefined; loading?: boolean }) {
  const providers = data || []
  const totalRequests = providers.reduce((s, p) => s + p.requests, 0)

  return (
    <div className="tb2-glass p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xs font-semibold text-white/60 uppercase tracking-wide">AI Provider Usage</h3>
        {loading && <Loader2 size={12} className="text-white/20 animate-spin" />}
      </div>

      {totalRequests > 0 && (
        <div className="flex h-2 rounded-full overflow-hidden mb-4 bg-white/5">
          {providers.filter(p => p.requests > 0).map(p => (
            <div
              key={p.provider}
              style={{ width: `${p.percentage}%`, backgroundColor: PROVIDER_META[p.provider]?.color }}
            />
          ))}
        </div>
      )}

      <div className="space-y-3">
        {providers.map(p => {
          const meta = PROVIDER_META[p.provider] || { label: p.provider, color: '#818cf8' }
          return (
            <div key={p.provider} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: meta.color }} />
                <span className="text-xs text-white/60">{meta.label}</span>
              </div>
              <div className="flex items-center gap-3">
                {p.requests > 0 && (
                  <span className="text-[10px] text-white/25">{Math.round(p.avg_latency_ms)}ms avg</span>
                )}
                <span className="text-xs font-semibold text-white/70 tabular-nums w-10 text-right">
                  {p.requests}
                </span>
              </div>
            </div>
          )
        })}
        {!loading && totalRequests === 0 && (
          <p className="text-xs text-white/20 text-center py-4">No AI Agent responses in this range yet</p>
        )}
      </div>
    </div>
  )
}

export const ProviderUsageCard = memo(ProviderUsageCardImpl)
