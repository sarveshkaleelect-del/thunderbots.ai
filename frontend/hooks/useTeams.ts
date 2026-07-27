// ============================================================
// ThunderBots — Team Workspace Hooks (NEW)
// Thin useQuery/useMutation wrappers, mirroring hooks/useAdmin.ts.
//
// Deliberately NO refetchInterval anywhere in this file — Team Workspace
// data is fetched once when a page/component mounts (i.e. only when the
// user actually opens Team Workspace) and otherwise sits on react-query's
// normal staleTime, exactly like the rest of the app. No background polling.
// ============================================================
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { teamsApi } from '@/lib/api/teams'
import type { TeamRole } from '@/types/team'

export function useTeams() {
  return useQuery({
    queryKey: ['teams'],
    queryFn: teamsApi.list,
    staleTime: 30_000,
  })
}

export function useTeam(teamId: string | undefined) {
  return useQuery({
    queryKey: ['teams', teamId],
    queryFn: () => teamsApi.get(teamId as string),
    enabled: !!teamId,
    staleTime: 15_000,
  })
}

export function useTeamMembers(teamId: string | undefined) {
  return useQuery({
    queryKey: ['teams', teamId, 'members'],
    queryFn: () => teamsApi.members(teamId as string),
    enabled: !!teamId,
    staleTime: 10_000,
  })
}

export function useTeamInvites(teamId: string | undefined, canManage: boolean) {
  return useQuery({
    queryKey: ['teams', teamId, 'invites'],
    queryFn: () => teamsApi.invites(teamId as string),
    enabled: !!teamId && canManage,
    staleTime: 10_000,
  })
}

export function usePendingInvites() {
  return useQuery({
    queryKey: ['teams', 'invites', 'pending'],
    queryFn: teamsApi.pendingInvites,
    staleTime: 30_000,
  })
}

export function useCreateTeam() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => teamsApi.create(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['teams'] }),
  })
}

export function useDeleteTeam() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (teamId: string) => teamsApi.delete(teamId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['teams'] }),
  })
}

export function useLeaveTeam() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (teamId: string) => teamsApi.leave(teamId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['teams'] }),
  })
}

export function useUpdateMemberRole(teamId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ memberId, role }: { memberId: string; role: TeamRole }) =>
      teamsApi.updateMemberRole(teamId, memberId, role),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['teams', teamId, 'members'] }),
  })
}

export function useRemoveMember(teamId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (memberId: string) => teamsApi.removeMember(teamId, memberId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['teams', teamId, 'members'] })
      qc.invalidateQueries({ queryKey: ['teams', teamId] })
    },
  })
}

export function useCreateInvite(teamId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ email, role }: { email: string; role: TeamRole }) =>
      teamsApi.createInvite(teamId, email, role),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['teams', teamId, 'invites'] }),
  })
}

export function useRevokeInvite(teamId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (inviteId: string) => teamsApi.revokeInvite(teamId, inviteId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['teams', teamId, 'invites'] }),
  })
}

export function useAcceptInvite() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (token: string) => teamsApi.acceptInvite(token),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['teams'] })
      qc.invalidateQueries({ queryKey: ['teams', 'invites', 'pending'] })
    },
  })
}

export function useDeclineInvite() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (token: string) => teamsApi.declineInvite(token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['teams', 'invites', 'pending'] }),
  })
}

/** Convenience: does the current user's role in this team allow managing
 * membership (invite / remove / change role)? Mirrors backend MANAGE_ROLES. */
export function canManageTeam(role: TeamRole | null | undefined): boolean {
  return role === 'owner' || role === 'admin'
}

/** Convenience: does the current user's role allow creating/editing
 * workflows in the team context? Mirrors backend EDIT_ROLES. */
export function canEditTeam(role: TeamRole | null | undefined): boolean {
  return role === 'owner' || role === 'admin' || role === 'editor'
}
