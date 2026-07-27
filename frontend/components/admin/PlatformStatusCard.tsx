'use client'
import { Card } from '@/components/ui/Card'
import { PageLoader, ErrorState } from '@/components/ui/States'
import { getErrorMessage } from '@/lib/utils/errors'
import { useAdminStatus } from '@/hooks/useAdmin'
import type { ServiceStatus } from '@/types/admin'
import { cn } from '@/lib/utils/cn'

const DOT: Record<ServiceStatus, string> = {
  operational: 'bg-emerald-400',
  degraded: 'bg-amber-400',
  down: 'bg-red-400',
  not_configured: 'bg-white/25',
}

const LABEL: Record<ServiceStatus, string> = {
  operational: 'Operational',
  degraded: 'Degraded',
  down: 'Down',
  not_configured: 'Not Configured',
}

const TEXT: Record<ServiceStatus, string> = {
  operational: 'text-emerald-400',
  degraded: 'text-amber-400',
  down: 'text-red-400',
  not_configured: 'text-white/35',
}

export default function PlatformStatusCard() {
  const { data, isLoading, error, refetch } = useAdminStatus()

  if (isLoading) return <Card className="p-5"><PageLoader label="Checking platform status…" /></Card>
  if (error) return <Card className="p-5"><ErrorState title="Couldn't check platform status" description={getErrorMessage(error)} onRetry={() => refetch()} /></Card>
  if (!data) return null

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white/85">Platform Status</h3>
        <span className={cn('flex items-center gap-1.5 text-[11px] font-medium', data.overall === 'operational' ? 'text-emerald-400' : 'text-amber-400')}>
          <span className={cn('w-1.5 h-1.5 rounded-full', data.overall === 'operational' ? 'bg-emerald-400 tb2-pulse-dot' : 'bg-amber-400')} />
          {data.overall === 'operational' ? 'All Systems Go' : 'Attention Needed'}
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        {data.services.map(s => (
          <div key={s.name} className="flex items-center justify-between gap-2 bg-white/[0.03] border border-white/[0.06] rounded-xl px-3.5 py-2.5">
            <div className="min-w-0">
              <p className="text-xs font-medium text-white/75 truncate">{s.name}</p>
              <p className="text-[10px] text-white/25 truncate">{s.detail}</p>
            </div>
            <span className={cn('flex items-center gap-1.5 text-[10px] font-semibold flex-shrink-0', TEXT[s.status])}>
              <span className={cn('w-1.5 h-1.5 rounded-full', DOT[s.status])} />
              {LABEL[s.status]}
            </span>
          </div>
        ))}
      </div>
    </Card>
  )
}
