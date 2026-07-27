// ============================================================
// ThunderBots — Analytics Dashboard Types (NEW)
// ============================================================

export type AnalyticsRangeKey = 'today' | '7d' | '30d' | '90d' | 'custom'

export interface AnalyticsOverview {
  total_chatbots: number
  live_chatbots: number
  total_conversations: number
  total_messages: number
  active_users: number
  returning_users: number
  avg_response_time_ms: number
  avg_conversation_length: number
  avg_satisfaction: number | null
  satisfaction_sample_size: number
  range: { start: string; end: string; key: string }
}

export interface TimeseriesPoint {
  date: string
  value: number
}

export type ChartMetric = 'conversations' | 'messages' | 'active_users' | 'response_time'

export interface TrafficSource {
  source: 'website' | 'embed_widget' | 'direct' | 'api' | 'whatsapp' | 'telegram'
  count: number
  percentage: number
}

export interface TopBot {
  workflow_id: string
  name: string
  status: string
  conversations: number
  messages: number
  avg_latency_ms: number
}

export interface TopDocument {
  document: string
  uses: number
}

export interface KBUsage {
  knowledge_bases: number
  documents: number
  grounded_responses: number
  total_bot_responses: number
  grounding_rate: number
}

export interface ProviderUsage {
  provider: 'gemini'
  requests: number
  percentage: number
  avg_latency_ms: number
}

export interface PerformanceStats {
  avg_latency_ms: number
  p95_latency_ms: number
  slow_requests: number
  slow_request_threshold_ms: number
  total_requests: number
  errors: number
  error_rate: number
  failed_requests: number
}

export interface RealtimeActivityItem {
  id: string
  role: 'user' | 'bot' | 'system'
  preview: string
  workflow_name: string
  is_error: boolean
  node_type: string | null
  created_at: string
}

export interface RealtimeStats {
  live_conversations: number
  messages_last_5m: number
  generated_at: string
  recent_activity: RealtimeActivityItem[]
}

export interface ConversationListItem {
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

export interface ConversationListResponse {
  items: ConversationListItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface ConversationMessage {
  id: string
  role: 'user' | 'bot' | 'system' | 'agent'
  content: string
  node_type: string | null
  provider: string | null
  model: string | null
  latency_ms: number | null
  is_error: boolean
  citations: any[]
  created_at: string
}

export interface ConversationDetail {
  id: string
  session_id: string
  workflow_id: string
  workflow_name: string
  source: string
  status: string
  satisfaction_rating: number | null
  is_returning: boolean
  started_at: string
  last_activity_at: string
  ended_at: string | null
  // NEW (Part 3, additive): AI vs. Live Agent handoff status for this
  // conversation — ai | waiting | active | paused | closed.
  handoff_status?: string
  assigned_agent_name?: string | null
  messages: ConversationMessage[]
}

export interface ConversationFilters {
  search?: string
  workflow_id?: string
  source?: string
  status?: string
  start?: string
  end?: string
  page?: number
  page_size?: number
}
