'use client'
import { useState, useMemo, useCallback, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import {
  Bot, Radio, MessagesSquare, MessageCircle, Users, Repeat,
  Timer, GitBranch, Star, RefreshCw, LayoutDashboard, History as HistoryIcon,
} from 'lucide-react'
import {
  useAnalyticsOverview, useAnalyticsChart, useTrafficSources, useTopBots,
  useTopDocuments, useKBUsage, useProviderUsage, usePerformance, useRealtime,
  type DateRange,
} from '@/hooks/useAnalytics'
import { StatCard } from '@/components/analytics/StatCard'
import { DateRangePicker } from '@/components/analytics/DateRangePicker'
import { ChartCard } from '@/components/analytics/ChartCard'
import { TrafficSourcesCard } from '@/components/analytics/TrafficSourcesCard'
import { TopBotsTable } from '@/components/analytics/TopBotsTable'
import { KnowledgeBaseUsageCard } from '@/components/analytics/KnowledgeBaseUsageCard'
import { ProviderUsageCard } from '@/components/analytics/ProviderUsageCard'
import { PerformanceCard } from '@/components/analytics/PerformanceCard'
import { RealtimeFeed } from '@/components/analytics/RealtimeFeed'
import { ConversationsTable } from '@/components/analytics/ConversationsTable'
import { cn } from '@/lib/utils/cn'
import { SubPageBar } from '@/components/ui/TopBar'

type Tab = 'overview' | 'conversations'

function msFmt(ms: number) {
  if (!ms) return '0ms'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export default function AnalyticsPage() {
  const router = useRouter()
  const [tab, setTab] = useState<Tab>('overview')
  const [range, setRange] = useState<DateRange>({ key: '7d' })
  const [autoRefresh, setAutoRefresh] = useState(true)

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('tb_token')) {
      router.replace('/login')
    }
  }, [router])

  const overview = useAnalyticsOverview(range, autoRefresh)
  const convChart = useAnalyticsChart('conversations', range, autoRefresh)
  const msgChart = useAnalyticsChart('messages', range, autoRefresh)
  const activeUsersChart = useAnalyticsChart('active_users', range, autoRefresh)
  const responseTimeChart = useAnalyticsChart('response_time', range, autoRefresh)
  const traffic = useTrafficSources(range, autoRefresh)
  const topBots = useTopBots(range, 8)
  const topDocs = useTopDocuments(8)
  const kbUsage = useKBUsage(range)
  const providerUsage = useProviderUsage(range)
  const performance = usePerformance(range, autoRefresh)
  const realtime = useRealtime(autoRefresh)

  const o = overview.data

  const statCards = useMemo(() => ([
    { label: 'Total Chatbots', value: o?.total_chatbots ?? 0, icon: Bot, accent: 'indigo' as const },
    { label: 'Live Chatbots', value: o?.live_chatbots ?? 0, icon: Radio, accent: 'emerald' as const },
    { label: 'Total Conversations', value: o?.total_conversations ?? 0, icon: MessagesSquare, accent: 'sky' as const },
    { label: 'Total Messages', value: o?.total_messages ?? 0, icon: MessageCircle, accent: 'violet' as const },
    { label: 'Active Users', value: o?.active_users ?? 0, icon: Users, accent: 'indigo' as const },
    { label: 'Returning Users', value: o?.returning_users ?? 0, icon: Repeat, accent: 'cyan' as const },
    { label: 'Avg Response Time', value: o ? msFmt(o.avg_response_time_ms) : '0ms', icon: Timer, accent: 'amber' as const, raw: true },
    { label: 'Avg Conversation Length', value: o?.avg_conversation_length ?? 0, icon: GitBranch, accent: 'violet' as const, suffix: 'msgs' },
    {
      label: 'Avg User Satisfaction',
      value: o?.avg_satisfaction != null ? o.avg_satisfaction.toFixed(1) : '—',
      icon: Star, accent: 'amber' as const,
      suffix: o?.avg_satisfaction != null ? '/ 5' : undefined,
      hint: o?.avg_satisfaction != null ? `${o.satisfaction_sample_size} ratings` : 'Ratings coming soon',
    },
  ]), [o])

  const handleRangeChange = useCallback((r: DateRange) => setRange(r), [])

  return (
    <div className="tb2-shell">
      <SubPageBar
        crumb="Analytics"
        right={
          <>
            <button
              onClick={() => setAutoRefresh(v => !v)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-2 rounded-xl text-[11px] font-medium border transition',
                autoRefresh
                  ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                  : 'bg-white/[0.03] border-white/10 text-white/30 hover:text-white/60'
              )}
              title="Toggle auto-refresh"
            >
              <RefreshCw size={11} className={autoRefresh ? 'animate-spin-slow' : ''} />
              {autoRefresh ? 'Live' : 'Paused'}
            </button>
            <DateRangePicker value={range} onChange={handleRangeChange} />
          </>
        }
      />

      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Tabs */}
        <div className="flex items-center gap-1 mb-6 tb2-glass p-1 w-fit">
          <button
            onClick={() => setTab('overview')}
            className={cn(
              'flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold transition',
              tab === 'overview' ? 'tb2-btn-primary text-white' : 'text-white/40 hover:text-white/70'
            )}
          >
            <LayoutDashboard size={12} /> Overview
          </button>
          <button
            onClick={() => setTab('conversations')}
            className={cn(
              'flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold transition',
              tab === 'conversations' ? 'tb2-btn-primary text-white' : 'text-white/40 hover:text-white/70'
            )}
          >
            <HistoryIcon size={12} /> Conversation History
          </button>
        </div>

        {tab === 'overview' ? (
          <div className="space-y-6">
            {/* Stat cards */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              {statCards.map(c => (
                <StatCard
                  key={c.label}
                  label={c.label}
                  value={c.value}
                  icon={c.icon}
                  accent={c.accent}
                  suffix={(c as any).suffix}
                  hint={(c as any).hint}
                  loading={overview.isLoading}
                />
              ))}
            </div>

            {/* Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <ChartCard title="Conversations" data={convChart.data} loading={convChart.isLoading} color="#6366f1" />
              <ChartCard title="Messages" data={msgChart.data} loading={msgChart.isLoading} color="#38bdf8" />
              <ChartCard title="Active Users" data={activeUsersChart.data} loading={activeUsersChart.isLoading} color="#34d399" />
              <ChartCard
                title="Response Time"
                data={responseTimeChart.data}
                loading={responseTimeChart.isLoading}
                color="#f59e0b"
                valueFormatter={v => msFmt(v)}
              />
            </div>

            {/* Traffic / Top bots / Realtime */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <TrafficSourcesCard data={traffic.data} loading={traffic.isLoading} />
              <TopBotsTable data={topBots.data} loading={topBots.isLoading} />
              <RealtimeFeed data={realtime.data} loading={realtime.isLoading} />
            </div>

            {/* KB / Provider / Performance */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <KnowledgeBaseUsageCard
                documents={topDocs.data} documentsLoading={topDocs.isLoading}
                kbUsage={kbUsage.data} kbLoading={kbUsage.isLoading}
              />
              <ProviderUsageCard data={providerUsage.data} loading={providerUsage.isLoading} />
              <PerformanceCard data={performance.data} loading={performance.isLoading} />
            </div>
          </div>
        ) : (
          <ConversationsTable />
        )}
      </main>
    </div>
  )
}
