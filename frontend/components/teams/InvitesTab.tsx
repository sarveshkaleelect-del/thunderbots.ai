'use client'
import { X, Mail, Plus } from 'lucide-react'
import { useState } from 'react'
import { useTeamInvites, useRevokeInvite, useCreateInvite } from '@/hooks/useTeams'
import { Card, Badge } from '@/components/ui/Card'
import { Button, IconButton } from '@/components/ui/Button'
import { SkeletonRows, ErrorState, EmptyState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/lib/utils/errors'
import { InviteMemberModal } from './InviteMemberModal'
import type { TeamRole } from '@/types/team'

export default function InvitesTab({ teamId }: { teamId: string }) {
  const { toast } = useToast()
  const { data, isLoading, error, refetch } = useTeamInvites(teamId, true)
  const revoke = useRevokeInvite(teamId)
  const createInvite = useCreateInvite(teamId)
  const [showInvite, setShowInvite] = useState(false)

  const handleInvite = (email: string, role: TeamRole) => {
    createInvite.mutate(
      { email, role },
      {
        onSuccess: () => {
          setShowInvite(false)
          toast('success', `Invite sent to ${email}.`)
        },
        onError: err => toast('error', getErrorMessage(err, 'Could not send invite.')),
      }
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" icon={<Plus size={13} />} onClick={() => setShowInvite(true)}>
          Invite Member
        </Button>
      </div>

      {isLoading && <SkeletonRows count={3} />}

      {error && !isLoading && (
        <ErrorState title="Couldn't load invites" description={getErrorMessage(error)} onRetry={() => refetch()} />
      )}

      {!isLoading && !error && (data?.invites.length ?? 0) === 0 && (
        <EmptyState icon={<Mail size={22} />} title="No pending invites" description="Invite teammates by email to get them started." />
      )}

      {!isLoading && !error && (data?.invites.length ?? 0) > 0 && (
        <div className="space-y-2.5">
          {data!.invites.map(inv => (
            <Card key={inv.id} className="p-4 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-white/90 truncate">{inv.email}</p>
                <p className="text-[11px] text-white/30">Invited as {inv.role}</p>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <Badge tone={inv.status === 'pending' ? 'warning' : inv.status === 'accepted' ? 'success' : 'default'}>
                  {inv.status}
                </Badge>
                {inv.status === 'pending' && (
                  <IconButton
                    aria-label="Revoke invite"
                    variant="danger"
                    onClick={() => revoke.mutate(inv.id, {
                      onSuccess: () => toast('success', 'Invite revoked.'),
                      onError: err => toast('error', getErrorMessage(err, 'Could not revoke invite.')),
                    })}
                  >
                    <X size={13} />
                  </IconButton>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      {showInvite && (
        <InviteMemberModal
          onClose={() => setShowInvite(false)}
          loading={createInvite.isPending}
          onInvite={handleInvite}
        />
      )}
    </div>
  )
}
