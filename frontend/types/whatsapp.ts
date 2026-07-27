// ============================================================
// ThunderBots — WhatsApp Channel Types
// ============================================================

export type WhatsAppStatus = 'disconnected' | 'connecting' | 'connected' | 'error'
export type WhatsAppHealth = 'unknown' | 'healthy' | 'degraded' | 'error'

export interface WhatsAppChannel {
  connected: boolean
  id?: string
  workflow_id?: string
  phone_number_id?: string
  business_account_id?: string
  access_token_preview?: string
  has_app_secret?: boolean
  display_phone_number?: string | null
  verified_name?: string | null
  quality_rating?: string | null
  status?: WhatsAppStatus
  is_enabled?: boolean
  health_status?: WhatsAppHealth
  last_error?: string | null
  last_sync_at?: string | null
  last_webhook_at?: string | null
  last_tested_at?: string | null
  messages_received_count?: number
  messages_sent_count?: number
  messages_failed_count?: number
  webhook_url?: string
  created_at?: string
  updated_at?: string
}

export interface WhatsAppConnectionPayload {
  phone_number_id: string
  business_account_id: string
  access_token: string
  verify_token: string
  app_secret?: string
}

export interface WhatsAppTestResult {
  ok: boolean
  latency_ms: number
  error?: string
  display_phone_number?: string
  verified_name?: string
  quality_rating?: string
}

export interface WhatsAppWebhookInfo {
  webhook_url: string
  verify_token: string
  app_secret_configured: boolean
  subscribe_fields: string[]
}

export interface WhatsAppContactSummary {
  wa_id: string
  profile_name: string | null
  message_count: number
  last_message_at: string | null
}

export interface WhatsAppConversationItem {
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

export interface WhatsAppStats {
  connected: boolean
  status?: WhatsAppStatus
  is_enabled?: boolean
  health_status?: WhatsAppHealth
  last_error?: string | null
  last_sync_at?: string | null
  last_webhook_at?: string | null
  messages_received_count?: number
  messages_sent_count?: number
  messages_failed_count?: number
  contact_count?: number
  contacts?: WhatsAppContactSummary[]
  conversations?: {
    items: WhatsAppConversationItem[]
    total: number
    page: number
    page_size: number
    total_pages: number
  }
}
