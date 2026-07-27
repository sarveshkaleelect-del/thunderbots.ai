'use client'
import { useState } from 'react'
import { UserMinus, Mail } from 'lucide-react'
import { useTeamMembers, useUpdateMemberRole, useRemoveMember, canManageTeam } from '@/hooks/useTeams'
import { Card } from '@/components/ui/Card'
import { Select } from '@/components/ui/Field'
import { IconButton } from '@/components/ui/Button'
import { SkeletonRows, ErrorState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/lib/utils/errors'
import { RoleBadge } from './RoleBadge'
import type { TeamRole } from '@/types/team'

const ASSIGNABLE_ROLES: TeamRole[] = ['admin', 'editor', 'viewer']

export default function MembersTab({ teamId, myRole }: { teamId: string; myRole: TeamRole | null }) {
  const { toast } = useToast()
  const { data, isLoading, error, refetch } = useTeamMembers(teamId)
  const updateRole = useUpdateMemberRole(teamId)
  const removeMember = useRemoveMember(teamId)
  const canManage = canManageTeam(myRole)
  const [pendingId, setPendingId] = useState<string | null>(null)

  if (isLoading) return <SkeletonRows count={4} />
  if (error) {
    return (
      <ErrorState
        title="Couldn't load members"
        description={getErrorMessage(error)}
        onRetry={() => refetch()}
      />
    )
  }

  const members = data?.members ?? []

  return (
    <div className="space-y-2.5">
      {members.map(m => (
        <Card key={m.id} className="p-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-xl tb2-brand-mark flex items-center justify-center flex-shrink-0 text-xs font-semibold text-[#a5b4fc]">
              {(m.name || m.email || '?').slice(0, 1).toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-medium text-white/90 truncate">{m.name || m.email}</p>
              <p className="flex items-center gap-1 text-[11px] text-white/30 truncate">
                <Mail size={9} />{m.email}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            {canManage && m.role !== 'owner' ? (
              <Select
                className="!py-1.5 !pr-8 !text-xs w-28"
                value={m.role}
                disabled={updateRole.isPending && pendingId === m.id}
                onChange={e => {
                  setPendingId(m.id)
                  updateRole.mutate(
                    { memberId: m.id, role: e.target.value as TeamRole },
                    { onError: err => toast('error', getErrorMessage(err, 'Could not update role.')) }
                  )
                }}
              >
                {ASSIGNABLE_ROLES.map(r => (
                  <option key={r} value={r}>{r[0].toUpperCase() + r.slice(1)}</option>
                ))}
              </Select>
            ) : (
              <RoleBadge role={m.role} />
            )}

            {canManage && m.role !== 'owner' && (
              <IconButton
                aria-label="Remove member"
                variant="danger"
                onClick={() => {
                  if (window.confirm(`Remove ${m.name || m.email} from the team?`)) {
                    removeMember.mutate(m.id, {
                      onSuccess: () => toast('success', 'Member removed.'),
                      onError: err => toast('error', getErrorMessage(err, 'Could not remove member.')),
                    })
                  }
                }}
              >
                <UserMinus size={13} />
              </IconButton>
            )}
          </div>
        </Card>
      ))}
    </div>
  )
}
