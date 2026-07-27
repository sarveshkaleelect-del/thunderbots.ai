// ============================================================
// ThunderBots — Team Workspace Types (NEW)
// ============================================================

export type TeamRole = 'owner' | 'admin' | 'editor' | 'viewer'

export interface Team {
  id: string
  name: string
  created_by: string | null
  created_at: string | null
  updated_at: string | null
  my_role: TeamRole | null
  member_count: number | null
}

export interface TeamList {
  teams: Team[]
}

export interface TeamMember {
  id: string
  team_id: string
  user_id: string
  email: string | null
  name: string | null
  role: TeamRole
  joined_at: string | null
}

export interface TeamMemberList {
  members: TeamMember[]
}

export type InviteStatus = 'pending' | 'accepted' | 'revoked'

export interface TeamInvite {
  id: string
  team_id: string
  email: string
  role: TeamRole
  status: InviteStatus
  created_at: string | null
  resolved_at: string | null
}

export interface TeamInviteList {
  invites: TeamInvite[]
}

export interface PendingInvite extends TeamInvite {
  team_name: string
}

export interface PendingInviteList {
  invites: PendingInvite[]
}
