// ============================================================
// ThunderBots — Admin Dashboard Types (NEW)
// ============================================================

export interface AdminOverview {
  total_users: number
  total_bots: number
  total_workflows: number
  total_conversations: number
  total_deployments: number
}

export type ServiceStatus = 'operational' | 'degraded' | 'down' | 'not_configured'

export interface AdminServiceCheck {
  name: string
  status: ServiceStatus
  detail: string
}

export interface AdminPlatformStatus {
  overall: 'operational' | 'degraded'
  services: AdminServiceCheck[]
}

export interface AdminUser {
  id: string
  name: string
  email: string
  is_admin: boolean
  is_active: boolean
  created_at: string | null
}

export interface AdminUserList {
  users: AdminUser[]
  total: number
  page: number
  page_size: number
}

export interface AdminBot {
  id: string
  name: string
  status: string
  owner_id: string
  owner_email: string | null
  created_at: string | null
  updated_at: string | null
}

export interface AdminBotList {
  bots: AdminBot[]
  total: number
  page: number
  page_size: number
}

export interface AdminActivity {
  new_users: Array<{ id: string; name: string; email: string; created_at: string | null }>
  new_bots: Array<{ id: string; name: string; status: string; created_at: string | null }>
  recent_deployments: Array<{
    id: string
    workflow_id: string
    slug: string
    owner_email: string | null
    is_active: boolean
    deployed_at: string | null
  }>
}

// ============================================================
// Audit Log (NEW — v58)
// ============================================================

export type AuditLogStatus = 'success' | 'failure'

export interface AuditLogEntry {
  id: string
  actor_id: string | null
  actor_email: string | null
  actor_name: string | null
  actor_type: 'user' | 'admin' | 'system'
  action: string
  resource_type: string
  target_type: string | null
  target_id: string | null
  target_label: string | null
  status: AuditLogStatus
  status_detail: string | null
  ip_address: string | null
  user_agent: string | null
  request_id: string
  metadata: Record<string, any>
  created_at: string | null
}

export interface AuditLogList {
  logs: AuditLogEntry[]
  total: number
  page: number
  page_size: number
}

export interface AuditLogFilters {
  search?: string
  actor_id?: string
  action?: string
  resource_type?: string
  status?: AuditLogStatus | ''
  date_from?: string
  date_to?: string
  page?: number
  page_size?: number
}
