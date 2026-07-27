'use client'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { TrendingUp, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { cn } from '@/lib/utils/cn'
import { campaignsApi } from '@/lib/api/campaigns'
import type { GrowthRange } from '@/types/campaigns'

const RANGES: [GrowthRange, string][] = [
  ['daily', 'Daily'],
  ['weekly', 'Weekly'],
  ['monthly', 'Monthly'],
]

function formatPeriodTick(p: string, range: GrowthRange) {
  if (range === 'monthly') {
    const [y, m] = p.split('-')
    return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
  }
  const dt = new Date(p)
  if (Number.isNaN(dt.getTime())) return p
  return dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function GrowthTooltip({ active, payload, label, range }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-[#141414] border border-[#2a2a2a] rounded-lg px-3 py-2 shadow-xl">
      <p className="text-[10px] text-white/40 mb-1">{formatPeriodTick(label, range)}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} className="text-xs font-semibold" style={{ color: p.color }}>
          {p.name}: {p.value}
        </p>
      ))}
    </div>
  )
}

export function SubscriberGrowthCard() {
  const [range, setRange] = useState<GrowthRange>('daily')

  const { data, isLoading } = useQuery({
    queryKey: ['campaigns-analytics-growth', range],
    queryFn: () => campaignsApi.analyticsGrowth(range),
  })

  const points = data?.points ?? []
  const hasData = points.length > 0

  return (
    <Card className="tb2-rise p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-[#6366f1]/10 border border-[#6366f1]/20 flex items-center justify-center flex-shrink-0">
            <TrendingUp size={14} className="text-[#a5b4fc]" />
          </div>
          <h3 className="text-sm font-bold text-white">Subscriber Growth</h3>
          {isLoading && <Loader2 size={12} className="text-white/20 animate-spin" />}
        </div>
        <div className="flex items-center gap-1">
          {RANGES.map(([value, label]) => (
            <button
              key={value}
              onClick={() => setRange(value)}
              className={cn(
                'text-[11px] font-medium px-2.5 py-1 rounded-md border transition-colors',
                range === value
                  ? 'bg-[#6366f1]/15 border-[#6366f1]/30 text-[#c7d2fe]'
                  : 'bg-transparent border-white/10 text-white/40 hover:text-white/70 hover:border-white/20'
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="h-56">
        {!isLoading && !hasData ? (
          <div className="h-full flex items-center justify-center">
            <p className="text-xs text-white/20">No growth data for this range yet</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={points} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="grad-subscribers" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6366f1" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="grad-scans" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#10b981" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1a1a1a" vertical={false} />
              <XAxis
                dataKey="period"
                tickFormatter={(p) => formatPeriodTick(p, range)}
                tick={{ fill: 'rgba(255,255,255,0.25)', fontSize: 10 }}
                axisLine={{ stroke: '#1a1a1a' }}
                tickLine={false}
              />
              <YAxis tick={{ fill: 'rgba(255,255,255,0.25)', fontSize: 10 }} axisLine={false} tickLine={false} width={32} />
              <Tooltip content={<GrowthTooltip range={range} />} cursor={{ stroke: '#2a2a2a' }} />
              <Legend wrapperStyle={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }} />
              <Area type="monotone" dataKey="subscribers" name="Subscribers" stroke="#6366f1" strokeWidth={2} fill="url(#grad-subscribers)" isAnimationActive={false} />
              <Area type="monotone" dataKey="qr_scans" name="QR Scans" stroke="#10b981" strokeWidth={2} fill="url(#grad-scans)" isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  )
}
