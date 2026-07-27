'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { MessageCircle, Bot, Headset, Timer, RadioTower } from 'lucide-react'
import { useSupervisorStats, useSupervisorLiveUpdates } from '@/hooks/useAiSupervisor'
import { StatCard } from '@/components/analytics/StatCard'
import { AiSupervisorTable } from '@/components/ai-supervisor/AiSupervisorTable'
import { TeamActivityPanel } from '@/components/ai-supervisor/TeamActivityPanel'
import { NotificationToasts } from '@/components/ai-supervisor/NotificationToasts'
import { SubPageBar } from '@/components/ui/TopBar'

function msFmt(ms: number) {
  if (!ms) return '0ms'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export default function AiSupervisorPage() {
  const router = useRouter()

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('tb_token')) {
      router.replace('/login')
    }
  }, [router])

  const { data: stats, isLoading } = useSupervisorStats()
  useSupervisorLiveUpdates()

  const statCards = [
    { label: 'Active chats', value: stats?.active_chats ?? 0, icon: MessageCircle, accent: 'emerald' as const },
    { label: 'AI resolved', value: stats?.ai_resolved ?? 0, icon: Bot, accent: 'indigo' as const },
    { label: 'Human resolved', value: stats?.human_resolved ?? 0, icon: Headset, accent: 'amber' as const },
    { label: 'Avg response time', value: stats ? msFmt(stats.avg_response_time_ms) : '0ms', icon: Timer, accent: 'sky' as const, raw: true },
  ]

  return (
    <div className="tb2-shell">
      <NotificationToasts />
      <SubPageBar
        crumb="AI Supervisor"
        crumbIcon={<RadioTower size={13} className="text-white/30" />}
        right={
          <span className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-[11px] font-medium border bg-emerald-500/10 border-emerald-500/20 text-emerald-400">
            <RadioTower size={11} className="animate-pulse" /> Live
          </span>
        }
      />

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-6">
        <div>
          <h1 className="text-lg font-bold text-white">AI Supervisor</h1>
          <p className="text-xs text-white/40 mt-0.5">
            All conversations across every channel and workflow — active and completed, AI-handled and human-handled.
          </p>
        </div>

        {/* Summary stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {statCards.map(c => (
            <StatCard
              key={c.label}
              label={c.label}
              value={c.value}
              icon={c.icon}
              accent={c.accent}
              loading={isLoading}
            />
          ))}
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1fr_280px] gap-6 items-start">
          <AiSupervisorTable />
          <TeamActivityPanel />
        </div>
      </main>
    </div>
  )
}
