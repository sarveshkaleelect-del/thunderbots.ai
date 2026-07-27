'use client'
import { useEffect, useState } from 'react'
import dynamic from 'next/dynamic'
import { useRouter } from 'next/navigation'
import {
  Users, Bot, GitBranch, MessagesSquare, Rocket,
  LayoutDashboard, ShieldAlert,
} from 'lucide-react'
import { useAdminOverview, useIsAdmin } from '@/hooks/useAdmin'
import { StatCard } from '@/components/analytics/StatCard'
import { TopBar } from '@/components/ui/TopBar'
import { PageLoader, EmptyState } from '@/components/ui/States'
import { cn } from '@/lib/utils/cn'
import PlatformStatusCard from '@/components/admin/PlatformStatusCard'

// Lazy-loaded tabs: each is only fetched/rendered once the admin actually
// clicks into it, so the initial /admin load stays light (overview + status
// only) regardless of how many users/bots exist on the platform.
const UsersTab = dynamic(() => import('@/components/admin/UsersTab'), {
  loading: () => <PageLoader label="Loading users…" />,
})
const BotsTab = dynamic(() => import('@/components/admin/BotsTab'), {
  loading: () => <PageLoader label="Loading bots…" />,
})
const ActivityTab = dynamic(() => import('@/components/admin/ActivityTab'), {
  loading: () => <PageLoader label="Loading activity…" />,
})
const AuditLogTab = dynamic(() => import('@/components/admin/AuditLogTab'), {
  loading: () => <PageLoader label="Loading audit log…" />,
})

type Tab = 'overview' | 'users' | 'bots' | 'activity' | 'audit'

const TABS: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'users', label: 'Users' },
  { key: 'bots', label: 'Bots' },
  { key: 'activity', label: 'Activity' },
  { key: 'audit', label: 'Audit Log' },
]

export default function AdminPage() {
  const router = useRouter()
  const [tab, setTab] = useState<Tab>('overview')

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('tb_token')) {
      router.replace('/login')
    }
  }, [router])

  const me = useIsAdmin()
  const overview = useAdminOverview()
  const o = overview.data

  // Access gate: only rendered once we know for certain the user isn't an
  // admin — while `me` is loading we show a loader, never the dashboard.
  if (me.isLoading) {
    return (
      <div className="tb2-shell">
        <TopBar />
        <PageLoader label="Checking access…" />
      </div>
    )
  }

  if (!me.data?.is_admin) {
    return (
      <div className="tb2-shell">
        <TopBar />
        <main className="max-w-2xl mx-auto px-6 py-10">
          <EmptyState
            icon={<ShieldAlert size={24} />}
            title="Admin access required"
            description="This area is only available to platform administrators."
          />
        </main>
      </div>
    )
  }

  const statCards = [
    { label: 'Total Users', value: o?.total_users ?? 0, icon: Users, accent: 'indigo' as const },
    { label: 'Total Bots', value: o?.total_bots ?? 0, icon: Bot, accent: 'emerald' as const },
    { label: 'Total Workflows', value: o?.total_workflows ?? 0, icon: GitBranch, accent: 'violet' as const },
    { label: 'Total Conversations', value: o?.total_conversations ?? 0, icon: MessagesSquare, accent: 'sky' as const },
    { label: 'Total Deployments', value: o?.total_deployments ?? 0, icon: Rocket, accent: 'cyan' as const },
  ]

  return (
    <div className="tb2-shell">
      <TopBar />

      <main className="max-w-6xl mx-auto px-6 py-10">
        <div className="flex items-center gap-2.5 mb-8">
          <div className="w-9 h-9 rounded-xl tb2-brand-mark flex items-center justify-center">
            <LayoutDashboard size={16} className="text-[#a5b4fc]" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white">Admin Dashboard</h1>
            <p className="text-[11px] text-white/30">Platform-wide management</p>
          </div>
        </div>

        <nav className="flex items-center gap-5 mb-8 border-b border-white/[0.06]">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                'text-xs font-medium pb-3 border-b-2 transition-colors',
                tab === t.key ? 'text-white border-[#818cf8]' : 'text-white/35 border-transparent hover:text-white/70'
              )}
            >
              {t.label}
            </button>
          ))}
        </nav>

        {tab === 'overview' && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
              {statCards.map(s => (
                <StatCard key={s.label} label={s.label} value={s.value} icon={s.icon} accent={s.accent} loading={overview.isLoading} />
              ))}
            </div>
            <PlatformStatusCard />
          </div>
        )}

        {tab === 'users' && <UsersTab />}
        {tab === 'bots' && <BotsTab />}
        {tab === 'activity' && <ActivityTab />}
        {tab === 'audit' && <AuditLogTab />}
      </main>
    </div>
  )
}
