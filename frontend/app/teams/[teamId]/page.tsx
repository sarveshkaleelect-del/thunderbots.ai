'use client'
import { useEffect, useState } from 'react'
import dynamic from 'next/dynamic'
import { useParams, useRouter } from 'next/navigation'
import { Users, Mail, Trash2, LogOut } from 'lucide-react'
import { useTeam, useDeleteTeam, useLeaveTeam, canManageTeam } from '@/hooks/useTeams'
import { SubPageBar } from '@/components/ui/TopBar'
import { Button } from '@/components/ui/Button'
import { PageLoader, ErrorState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/lib/utils/errors'
import { RoleBadge } from '@/components/teams/RoleBadge'
import { cn } from '@/lib/utils/cn'

// Lazy-loaded tabs: neither members nor invites are fetched or rendered
// until the admin actually clicks into that tab, keeping the initial team
// page load to a single lightweight /teams/{id} call.
const MembersTab = dynamic(() => import('@/components/teams/MembersTab'), {
  loading: () => <PageLoader label="Loading members…" />,
})
const InvitesTab = dynamic(() => import('@/components/teams/InvitesTab'), {
  loading: () => <PageLoader label="Loading invites…" />,
})

type Tab = 'members' | 'invites'

export default function TeamDetailPage() {
  const params = useParams()
  const teamId = params?.teamId as string
  const router = useRouter()
  const { toast } = useToast()
  const [tab, setTab] = useState<Tab>('members')

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('tb_token')) {
      router.replace('/login')
    }
  }, [router])

  const { data: team, isLoading, error, refetch } = useTeam(teamId)
  const deleteTeam = useDeleteTeam()
  const leaveTeam = useLeaveTeam()

  if (isLoading) {
    return (
      <div className="tb2-shell">
        <SubPageBar backHref="/teams" crumb="Loading…" />
        <PageLoader label="Loading team…" />
      </div>
    )
  }

  if (error || !team) {
    return (
      <div className="tb2-shell">
        <SubPageBar backHref="/teams" crumb="Team" />
        <main className="max-w-2xl mx-auto px-6 py-10">
          <ErrorState
            title="Couldn't load this team"
            description={getErrorMessage(error, 'This team may not exist, or you may not be a member of it.')}
            onRetry={() => refetch()}
          />
        </main>
      </div>
    )
  }

  const canManage = canManageTeam(team.my_role)
  const isOwner = team.my_role === 'owner'
  const tabs: { key: Tab; label: string; icon: typeof Users }[] = [
    { key: 'members', label: 'Members', icon: Users },
    ...(canManage ? [{ key: 'invites' as Tab, label: 'Invites', icon: Mail }] : []),
  ]

  return (
    <div className="tb2-shell">
      <SubPageBar
        backHref="/teams"
        crumb={team.name}
        crumbIcon={<Users size={13} />}
        right={
          isOwner ? (
            <Button
              size="sm"
              variant="danger"
              icon={<Trash2 size={13} />}
              onClick={() => {
                if (window.confirm(`Delete "${team.name}"? This removes all members and cannot be undone.`)) {
                  deleteTeam.mutate(teamId, {
                    onSuccess: () => { toast('success', 'Team deleted.'); router.push('/teams') },
                    onError: err => toast('error', getErrorMessage(err, 'Could not delete the team.')),
                  })
                }
              }}
            >
              Delete Team
            </Button>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              icon={<LogOut size={13} />}
              onClick={() => {
                if (window.confirm(`Leave "${team.name}"?`)) {
                  leaveTeam.mutate(teamId, {
                    onSuccess: () => { toast('success', 'You left the team.'); router.push('/teams') },
                    onError: err => toast('error', getErrorMessage(err, 'Could not leave the team.')),
                  })
                }
              }}
            >
              Leave Team
            </Button>
          )
        }
      />

      <main className="max-w-4xl mx-auto px-6 py-10">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-lg font-bold text-white">{team.name}</h1>
            <p className="text-[11px] text-white/30 mt-0.5">{team.member_count ?? 0} member{team.member_count === 1 ? '' : 's'}</p>
          </div>
          {team.my_role && <RoleBadge role={team.my_role} />}
        </div>

        <nav className="flex items-center gap-5 mb-8 border-b border-white/[0.06]">
          {tabs.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                'flex items-center gap-1.5 text-xs font-medium pb-3 border-b-2 transition-colors',
                tab === t.key ? 'text-white border-[#818cf8]' : 'text-white/35 border-transparent hover:text-white/70'
              )}
            >
              <t.icon size={13} />
              {t.label}
            </button>
          ))}
        </nav>

        {tab === 'members' && <MembersTab teamId={teamId} myRole={team.my_role} />}
        {tab === 'invites' && canManage && <InvitesTab teamId={teamId} />}
      </main>
    </div>
  )
}
