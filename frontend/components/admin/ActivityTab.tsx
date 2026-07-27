'use client'
import { UserPlus, Bot as BotIcon, Rocket } from 'lucide-react'
import { Card, Badge } from '@/components/ui/Card'
import { PageLoader, ErrorState, EmptyState } from '@/components/ui/States'
import { getErrorMessage } from '@/lib/utils/errors'
import { useAdminActivity } from '@/hooks/useAdmin'

function timeAgo(iso: string | null) {
  if (!iso) return '—'
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function Section({ icon, title, empty, children }: { icon: React.ReactNode; title: string; empty: boolean; children: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2.5">
        {icon}
        <h4 className="text-xs font-semibold text-white/60 uppercase tracking-wide">{title}</h4>
      </div>
      {empty ? (
        <p className="text-xs text-white/20 px-1">Nothing recent</p>
      ) : (
        <div className="space-y-1.5">{children}</div>
      )}
    </div>
  )
}

export default function ActivityTab() {
  const { data, isLoading, error, refetch } = useAdminActivity(8)

  if (isLoading) return <PageLoader label="Loading recent activity…" />
  if (error) return <ErrorState title="Couldn't load recent activity" description={getErrorMessage(error)} onRetry={() => refetch()} />
  if (!data) return null

  const { new_users, new_bots, recent_deployments } = data
  const nothing = new_users.length === 0 && new_bots.length === 0 && recent_deployments.length === 0

  if (nothing) {
    return <EmptyState icon={<Rocket size={24} />} title="No activity yet" description="New signups, bots, and deployments will show up here." />
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <Card className="p-4">
        <Section icon={<UserPlus size={13} className="text-[#818cf8]" />} title="New Users" empty={new_users.length === 0}>
          {new_users.map(u => (
            <div key={u.id} className="flex items-center justify-between gap-2 text-xs px-1 py-1.5">
              <div className="min-w-0">
                <p className="text-white/75 truncate">{u.name}</p>
                <p className="text-white/25 truncate text-[10px]">{u.email}</p>
              </div>
              <span className="text-[10px] text-white/25 flex-shrink-0">{timeAgo(u.created_at)}</span>
            </div>
          ))}
        </Section>
      </Card>

      <Card className="p-4">
        <Section icon={<BotIcon size={13} className="text-cyan-300" />} title="New Bots" empty={new_bots.length === 0}>
          {new_bots.map(b => (
            <div key={b.id} className="flex items-center justify-between gap-2 text-xs px-1 py-1.5">
              <p className="text-white/75 truncate min-w-0">{b.name}</p>
              <div className="flex items-center gap-2 flex-shrink-0">
                <Badge tone={b.status === 'published' ? 'success' : 'default'}>{b.status}</Badge>
                <span className="text-[10px] text-white/25">{timeAgo(b.created_at)}</span>
              </div>
            </div>
          ))}
        </Section>
      </Card>

      <Card className="p-4">
        <Section icon={<Rocket size={13} className="text-emerald-400" />} title="Recent Deployments" empty={recent_deployments.length === 0}>
          {recent_deployments.map(d => (
            <div key={d.id} className="flex items-center justify-between gap-2 text-xs px-1 py-1.5">
              <div className="min-w-0">
                <p className="text-white/75 truncate">/{d.slug}</p>
                <p className="text-white/25 truncate text-[10px]">{d.owner_email ?? 'Unknown owner'}</p>
              </div>
              <span className="text-[10px] text-white/25 flex-shrink-0">{timeAgo(d.deployed_at)}</span>
            </div>
          ))}
        </Section>
      </Card>
    </div>
  )
}
