// ============================================================
// ThunderBots — Team Workspace API Client (NEW)
// ============================================================
import { apiClient } from './client'
import type {
  Team, TeamList, TeamMemberList, TeamInviteList, PendingInviteList, TeamRole,
} from '@/types/team'

export const teamsApi = {
  list: async (): Promise<TeamList> => {
    const { data } = await apiClient.get('/teams')
    return data
  },

  get: async (teamId: string): Promise<Team> => {
    const { data } = await apiClient.get(`/teams/${teamId}`)
    return data
  },

  create: async (name: string): Promise<Team> => {
    const { data } = await apiClient.post('/teams', { name })
    return data
  },

  delete: async (teamId: string) => {
    await apiClient.delete(`/teams/${teamId}`)
  },

  leave: async (teamId: string) => {
    await apiClient.delete(`/teams/${teamId}/leave`)
  },

  members: async (teamId: string): Promise<TeamMemberList> => {
    const { data } = await apiClient.get(`/teams/${teamId}/members`)
    return data
  },

  updateMemberRole: async (teamId: string, memberId: string, role: TeamRole) => {
    const { data } = await apiClient.patch(`/teams/${teamId}/members/${memberId}/role`, { role })
    return data
  },

  removeMember: async (teamId: string, memberId: string) => {
    await apiClient.delete(`/teams/${teamId}/members/${memberId}`)
  },

  invites: async (teamId: string): Promise<TeamInviteList> => {
    const { data } = await apiClient.get(`/teams/${teamId}/invites`)
    return data
  },

  createInvite: async (teamId: string, email: string, role: TeamRole) => {
    const { data } = await apiClient.post(`/teams/${teamId}/invites`, { email, role })
    return data
  },

  revokeInvite: async (teamId: string, inviteId: string) => {
    await apiClient.delete(`/teams/${teamId}/invites/${inviteId}`)
  },

  pendingInvites: async (): Promise<PendingInviteList> => {
    const { data } = await apiClient.get('/teams/invites/pending')
    return data
  },

  acceptInvite: async (token: string): Promise<Team> => {
    const { data } = await apiClient.post(`/teams/invites/${token}/accept`)
    return data
  },

  declineInvite: async (token: string) => {
    await apiClient.post(`/teams/invites/${token}/decline`)
  },
}
