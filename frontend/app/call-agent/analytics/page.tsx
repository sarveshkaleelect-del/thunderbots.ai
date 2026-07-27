'use client'
/**
 * AI Call Agent — Analytics — /call-agent/analytics
 *
 * NEW (Voice AI Part 5). Per-Voice-Agent analytics, reusing the new
 * GET /call-agent/agents/{id}/analytics endpoint.
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, PhoneCall, CheckCircle2, XCircle, ZapOff, Timer, Percent } from 'lucide-react'
import { getToken } from '@/lib/api/auth'
import { voiceAgentsApi } from '@/lib/api/callAgent'
import { Card } from '@/components/ui/Card'
import { Select } from '@/components/ui/Field'
import { SubPageBar } from '@/components/ui/TopBar'
import { CallAgentNav } from '@/components/callAgent/CallAgentNav'
import { PageLoader, ErrorState, EmptyState } from '@/components/ui/States'
import { getErrorMessage } from '@/lib/utils/errors'

export default function AnalyticsPage() {
  const router = useRouter()
  const [agentId, setAgentId] = useState<string>('')

  useEffect(() => {
    if (typeof window !== 'undefined' && !getToken()) router.replace('/login')
  }, [router])

  const { data: agents = [] } = useQuery({ queryKey: ['voice-agents'], queryFn: voiceAgentsApi.list })

  useEffect(() => {
    if (!agentId && agents.length > 0) setAgentId(agents[0].id)
  }, [agents, agentId])

  const { data: analytics, isLoading, error, refetch } = useQuery({
    queryKey: ['voice-agent-analytics', agentId],
    queryFn: () => voiceAgentsApi.analytics(agentId),
    enabled: !!agentId,
  })

  const cards = analytics ? [
    { label: 'Total calls', value: analytics.total_calls, icon: PhoneCall },
    { label: 'Completed', value: analytics.completed_calls, icon: CheckCircle2 },
    { label: 'Failed', value: analytics.failed_calls, icon: XCircle },
    { label: 'Interrupted', value: analytics.interrupted_calls, icon: ZapOff },
    { label: 'Avg duration', value: analytics.avg_duration_seconds ? `${Math.round(analytics.avg_duration_seconds)}s` : '—', icon: Timer },
    { label: 'Resolution rate', value: analytics.resolution_rate != null ? `${Math.round(analytics.resolution_rate * 100)}%` : '—', icon: Percent },
  ] : []

  return (
    <div className="tb2-shell">
      <SubPageBar backHref="/call-agent" crumb="Analytics" crumbIcon={<BarChart3 size={13} className="text-cyan-300/70" />} />
      <CallAgentNav />

      <div className="max-w-4xl mx-auto px-3 sm:px-6 py-8 space-y-6">
        <div className="flex items-center justify-between gap-3 tb2-rise">
          <div>
            <h1 className="text-xl font-bold text-white">Analytics</h1>
            <p className="text-sm text-white/35 mt-1">Call performance for each Voice Agent.</p>
          </div>
          {agents.length > 0 && (
            <Select value={agentId} onChange={e => setAgentId(e.target.value)} className="w-56">
              {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </Select>
          )}
        </div>

        {agents.length === 0 ? (
          <EmptyState icon={<BarChart3 size={22} />} title="No Voice Agents yet" description="Create a Voice Agent to see its analytics here." />
        ) : isLoading ? (
          <PageLoader />
        ) : error ? (
          <ErrorState title="Couldn't load analytics" description={getErrorMessage(error)} onRetry={() => refetch()} />
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {cards.map(c => (
              <Card key={c.label} className="p-4">
                <c.icon size={14} className="text-cyan-300/70 mb-2" />
                <p className="text-lg font-bold text-white">{c.value}</p>
                <p className="text-[10px] text-white/35 uppercase tracking-wide mt-0.5">{c.label}</p>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
