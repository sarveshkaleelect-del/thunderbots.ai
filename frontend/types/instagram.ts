// ============================================================
// ThunderBots — Instagram DM Channel Types
// ============================================================

export type InstagramStatus = 'disconnected' | 'connecting' | 'connected' | 'expired' | 'error'
export type InstagramHealth = 'unknown' | 'healthy' | 'degraded' | 'error'

export interface InstagramAccount {
  connected: boolean
  configured?: boolean
  id?: string
  workflow_id?: string
  platform?: string
  ig_user_id?: string
  ig_username?: string | null
  facebook_page_id?: string
  facebook_page_name?: string | null
  token_preview?: string
  token_expires_at?: string | null
  status?: InstagramStatus
  is_enabled?: boolean
  health_status?: InstagramHealth
  last_error?: string | null
  last_sync_at?: string | null
  last_webhook_at?: string | null
  last_tested_at?: string | null
  last_token_refresh_at?: string | null
  messages_received_count?: number
  messages_sent_count?: number
  messages_failed_count?: number
  created_at?: string
  updated_at?: string
}

export interface InstagramTestResult {
  ok: boolean
  latency_ms: number
  error?: string
  error_type?: string | null
  facebook_page_name?: string
  ig_username?: string
}

export interface InstagramReconnectResult {
  ok: boolean
  status: InstagramStatus
  needs_reauth: boolean
  token_refreshed?: boolean
  error?: string
}

export interface InstagramWebhookInfo {
  webhook_url: string
  verify_token_configured: boolean
  app_secret_configured: boolean
  subscribe_fields: string[]
  scope: string
}

export interface InstagramContactSummary {
  igsid: string
  username: string | null
  message_count: number
  last_message_at: string | null
}

export interface InstagramConversationItem {
  id: string
  session_id: string
  workflow_id: string
  workflow_name: string
  source: string
  status: string
  message_count: number
  user_message_count: number
  bot_message_count: number
  error_count: number
  avg_response_time_ms: number
  satisfaction_rating: number | null
  is_returning: boolean
  started_at: string
  last_activity_at: string
  ended_at: string | null
}

export interface InstagramStats {
  connected: boolean
  status?: InstagramStatus
  is_enabled?: boolean
  health_status?: InstagramHealth
  last_error?: string | null
  last_sync_at?: string | null
  last_webhook_at?: string | null
  messages_received_count?: number
  messages_sent_count?: number
  messages_failed_count?: number
  contact_count?: number
  contacts?: InstagramContactSummary[]
  conversations?: {
    items: InstagramConversationItem[]
    total: number
    page: number
    page_size: number
    total_pages: number
  }
}

export interface InstagramLogEntry {
  id: string
  event_type: string
  level: 'info' | 'warning' | 'error'
  message: string
  detail: Record<string, unknown>
  created_at: string
}
