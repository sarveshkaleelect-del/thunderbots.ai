'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Plus, Users, ArrowRight } from 'lucide-react'
import { useTeams, useCreateTeam } from '@/hooks/useTeams'
import { TopBar } from '@/components/ui/TopBar'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { SkeletonGrid, EmptyState, ErrorState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/lib/utils/errors'
import { CreateTeamModal } from '@/components/teams/CreateTeamModal'
import { RoleBadge } from '@/components/teams/RoleBadge'

export default function TeamsPage() {
  const router = useRouter()
  const { toast } = useToast()
  const [showCreate, setShowCreate] = useState(false)

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('tb_token')) {
      router.replace('/login')
    }
  }, [router])

  // This is the ONLY network call made when Team Workspace is opened: the
  // caller's own team list (id/name/role/member_count). Members, invites,
  // and any other per-team data are fetched only after a specific team is
  // opened (see app/teams/[teamId]/page.tsx).
  const { data, isLoading, error, refetch } = useTeams()
  const createTeam = useCreateTeam()

  const teams = data?.teams ?? []

  return (
    <div className="tb2-shell">
      <TopBar
        right={
          <Button size="sm" onClick={() => setShowCreate(true)} icon={<Plus size={14} />} data-tutorial="teams-new">
            New Team
          </Button>
        }
      />

      <main className="max-w-6xl mx-auto px-6 py-10">
        <div className="flex items-center gap-2.5 mb-8" data-tutorial="page-header">
          <div className="w-9 h-9 rounded-xl tb2-brand-mark flex items-center justify-center">
            <Users size={16} className="text-[#a5b4fc]" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white">Team Workspace</h1>
            <p className="text-[11px] text-white/30">Collaborate with your team, separate from your personal workflows</p>
          </div>
        </div>

        {isLoading && <SkeletonGrid count={3} />}

        {error && !isLoading && (
          <ErrorState
            title="Couldn't load your teams"
            description={getErrorMessage(error, 'Check your connection and that the backend is running.')}
            onRetry={() => refetch()}
          />
        )}

        {!isLoading && !error && teams.length === 0 && (
          <EmptyState
            icon={<Users size={28} />}
            title="No teams yet"
            description="Create a team to start collaborating with others"
            action={
              <Button onClick={() => setShowCreate(true)} icon={<Plus size={14} />}>
                Create Team
              </Button>
            }
          />
        )}

        {teams.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {teams.map(team => (
              <Card
                key={team.id}
                hover
                className="p-5"
                onClick={() => router.push(`/teams/${team.id}`)}
              >
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-9 h-9 rounded-xl tb2-brand-mark flex items-center justify-center flex-shrink-0">
                      <Users size={15} className="text-[#a5b4fc]" />
                    </div>
                    <div className="min-w-0">
                      <p className="font-semibold text-sm text-white/90 truncate">{team.name}</p>
                      <p className="text-[11px] text-white/30">{team.member_count ?? 0} member{team.member_count === 1 ? '' : 's'}</p>
                    </div>
                  </div>
                  <ArrowRight size={13} className="text-white/20 flex-shrink-0 mt-1" />
                </div>
                {team.my_role && <RoleBadge role={team.my_role} />}
              </Card>
            ))}
          </div>
        )}
      </main>

      {showCreate && (
        <CreateTeamModal
          onClose={() => setShowCreate(false)}
          loading={createTeam.isPending}
          onCreate={name => createTeam.mutate(name, {
            onSuccess: team => {
              setShowCreate(false)
              router.push(`/teams/${team.id}`)
            },
            onError: err => toast('error', getErrorMessage(err, 'Could not create the team.')),
          })}
        />
      )}
    </div>
  )
}
