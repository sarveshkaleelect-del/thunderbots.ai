// ============================================================
// ThunderBots — Telegram Channel Types (Part 1)
// ============================================================

export type TelegramStatus = 'disconnected' | 'connecting' | 'connected' | 'invalid_token' | 'error'
export type TelegramHealth = 'unknown' | 'healthy' | 'degraded' | 'error'

export interface TelegramChannel {
  connected: boolean
  id?: string
  workflow_id?: string
  bot_id?: string | null
  bot_username?: string | null
  bot_first_name?: string | null
  status?: TelegramStatus
  is_enabled?: boolean
  health_status?: TelegramHealth
  last_error?: string | null
  webhook_registered?: boolean
  subscriber_count?: number
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

export interface TelegramConnectionPayload {
  bot_token: string
}

export interface TelegramTestResult {
  ok: boolean
  latency_ms: number
  error?: string
  bot_username?: string | null
}

export interface TelegramWebhookInfo {
  webhook_url: string
  webhook_registered: boolean
  managed_automatically: boolean
}

export interface TelegramSubscriberSummary {
  chat_id: string
  username: string | null
  first_name: string | null
  last_name: string | null
  message_count: number
  subscribed_at: string | null
  last_message_at: string | null
}

export interface TelegramConversationItem {
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

export interface TelegramStats {
  connected: boolean
  status?: TelegramStatus
  is_enabled?: boolean
  health_status?: TelegramHealth
  last_error?: string | null
  last_sync_at?: string | null
  last_webhook_at?: string | null
  messages_received_count?: number
  messages_sent_count?: number
  messages_failed_count?: number
  subscriber_count?: number
  subscribers?: TelegramSubscriberSummary[]
  conversations?: {
    items: TelegramConversationItem[]
    total: number
    page: number
    page_size: number
    total_pages: number
  }
}

// ============================================================
// Part 3 — AI Agent continuation, Live Agent handoff, analytics
// ============================================================

export interface TelegramAnalytics {
  active_conversations: number
  ai_resolved: number
  human_handoff: number
  replies: number
  failed_deliveries: number
}
