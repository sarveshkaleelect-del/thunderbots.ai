'use client'
import { memo, useMemo } from 'react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { Loader2 } from 'lucide-react'
import type { TimeseriesPoint } from '@/types/analytics'

interface ChartCardProps {
  title: string
  data: TimeseriesPoint[] | undefined
  loading?: boolean
  color?: string
  valueFormatter?: (v: number) => string
  emptyLabel?: string
}

function formatDateTick(d: string) {
  const dt = new Date(d)
  if (Number.isNaN(dt.getTime())) return d
  return dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function ChartTooltip({ active, payload, label, valueFormatter }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-[#141414] border border-[#2a2a2a] rounded-lg px-3 py-2 shadow-xl">
      <p className="text-[10px] text-white/40 mb-0.5">{formatDateTick(label)}</p>
      <p className="text-xs font-semibold text-white">
        {valueFormatter ? valueFormatter(payload[0].value) : payload[0].value}
      </p>
    </div>
  )
}

function ChartCardImpl({ title, data, loading, color = '#6366f1', valueFormatter, emptyLabel }: ChartCardProps) {
  const gradientId = useMemo(() => `grad-${title.replace(/\s+/g, '-').toLowerCase()}`, [title])
  const hasData = data && data.length > 0 && data.some(d => d.value > 0)

  return (
    <div className="tb2-glass p-5 flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xs font-semibold text-white/60 uppercase tracking-wide">{title}</h3>
        {loading && <Loader2 size={12} className="text-white/20 animate-spin" />}
      </div>

      <div className="h-48">
        {!loading && !hasData ? (
          <div className="h-full flex items-center justify-center">
            <p className="text-xs text-white/20">{emptyLabel || 'No data for this range yet'}</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data || []} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1a1a1a" vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={formatDateTick}
                tick={{ fill: 'rgba(255,255,255,0.25)', fontSize: 10 }}
                axisLine={{ stroke: '#1a1a1a' }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: 'rgba(255,255,255,0.25)', fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                width={36}
              />
              <Tooltip content={<ChartTooltip valueFormatter={valueFormatter} />} cursor={{ stroke: '#2a2a2a' }} />
              <Area
                type="monotone"
                dataKey="value"
                stroke={color}
                strokeWidth={2}
                fill={`url(#${gradientId})`}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}

export const ChartCard = memo(ChartCardImpl)
