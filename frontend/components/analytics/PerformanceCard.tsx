'use client'
import { memo } from 'react'
import { Loader2, Gauge, TriangleAlert, XCircle, Timer } from 'lucide-react'
import type { PerformanceStats } from '@/types/analytics'
import { cn } from '@/lib/utils/cn'

function Metric({ icon: Icon, label, value, tone }: { icon: any; label: string; value: string; tone: 'ok' | 'warn' | 'bad' }) {
  const toneClass = {
    ok: 'text-emerald-400',
    warn: 'text-amber-400',
    bad: 'text-rose-400',
  }[tone]
  return (
    <div className="bg-white/[0.03] rounded-xl p-3">
      <div className="flex items-center gap-1.5 mb-1.5">
        <Icon size={11} className={toneClass} />
        <span className="text-[10px] text-white/30">{label}</span>
      </div>
      <p className={cn('text-base font-bold tabular-nums', toneClass)}>{value}</p>
    </div>
  )
}

function PerformanceCardImpl({ data, loading }: { data: PerformanceStats | undefined; loading?: boolean }) {
  return (
    <div className="tb2-glass p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xs font-semibold text-white/60 uppercase tracking-wide">Performance</h3>
        {loading && <Loader2 size={12} className="text-white/20 animate-spin" />}
      </div>

      <div className="grid grid-cols-2 gap-2.5">
        <Metric
          icon={Gauge} label="Avg Latency"
          value={data ? `${Math.round(data.avg_latency_ms)}ms` : '—'}
          tone={!data ? 'ok' : data.avg_latency_ms > 5000 ? 'bad' : data.avg_latency_ms > 2000 ? 'warn' : 'ok'}
        />
        <Metric
          icon={Timer} label="P95 Latency"
          value={data ? `${Math.round(data.p95_latency_ms)}ms` : '—'}
          tone={!data ? 'ok' : data.p95_latency_ms > 8000 ? 'bad' : data.p95_latency_ms > 4000 ? 'warn' : 'ok'}
        />
        <Metric
          icon={TriangleAlert} label="Slow Requests"
          value={data ? `${data.slow_requests}` : '—'}
          tone={!data ? 'ok' : data.slow_requests > 0 ? 'warn' : 'ok'}
        />
        <Metric
          icon={XCircle} label="Errors"
          value={data ? `${data.errors} (${data.error_rate}%)` : '—'}
          tone={!data ? 'ok' : data.error_rate > 5 ? 'bad' : data.errors > 0 ? 'warn' : 'ok'}
        />
      </div>

      {data && (
        <p className="text-[10px] text-white/20 mt-3">
          {data.total_requests} bot response{data.total_requests === 1 ? '' : 's'} · slow = over {(data.slow_request_threshold_ms / 1000).toFixed(0)}s
        </p>
      )}
    </div>
  )
}

export const PerformanceCard = memo(PerformanceCardImpl)
