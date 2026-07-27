// ============================================================
// ThunderBots — AI Supervisor Dashboard Types (NEW)
// ============================================================

export type SupervisorState = 'active' | 'closed'
export type SupervisorMode = 'human' | 'ai_only'
export type Priority = 'low' | 'medium' | 'high' | 'critical'

export interface SupervisorConversationListItem {
  id: string
  session_id: string
  workflow_id: string
  workflow_name: string
  channel: string
  status: 'active' | 'ended'
  handoff_status: 'ai' | 'waiting' | 'active' | 'paused' | 'closed'
  is_human_takeover: boolean
  is_paused: boolean
  customer_display: string
  customer_handle: string | null
  assigned_agent_id: string | null
  assigned_agent_name: string | null
  last_customer_message: string | null
  last_customer_message_at: string | null
  last_ai_reply: string | null
  last_ai_reply_at: string | null
  ai_confidence: number | null
  message_count: number
  avg_response_time_ms: number | null
  started_at: string
  last_activity_at: string
  ended_at: string | null
  // Final phase (NEW)
  priority: Priority
  tags: string[]
  is_pinned: boolean
  is_closed: boolean
}

export interface SupervisorConversationListResponse {
  items: SupervisorConversationListItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface SupervisorMessageReview {
  verdict: 'correct' | 'incorrect'
  reviewer_id: string | null
  reviewer_name: string | null
  updated_at: string | null
}

export interface SupervisorMessage {
  id: string
  role: 'user' | 'bot' | 'agent' | 'system'
  content: string
  node_type: string | null
  provider: string | null
  model: string | null
  latency_ms: number | null
  is_error: boolean
  ai_confidence: number | null
  review: SupervisorMessageReview | null
  created_at: string
}

export interface SupervisorNote {
  id: string
  conversation_id: string
  author_id: string | null
  author_name: string | null
  content: string
  created_at: string
}

export interface SupervisorConversationDetail {
  id: string
  session_id: string
  workflow_id: string
  workflow_name: string
  channel: string
  status: 'active' | 'ended'
  handoff_status: 'ai' | 'waiting' | 'active' | 'paused' | 'closed'
  is_human_takeover: boolean
  is_paused: boolean
  assigned_agent_id: string | null
  assigned_agent_name: string | null
  customer_display: string
  customer_handle: string | null
  started_at: string
  last_activity_at: string
  ended_at: string | null
  avg_response_time_ms: number | null
  messages: SupervisorMessage[]
  notes: SupervisorNote[]
  // Final phase (NEW)
  priority: Priority
  tags: string[]
  is_pinned: boolean
  is_closed: boolean
}

export interface SupervisorStats {
  active_chats: number
  ai_resolved: number
  human_resolved: number
  avg_response_time_ms: number
  generated_at: string
}

export interface SupervisorFilters {
  state?: SupervisorState
  mode?: SupervisorMode
  channel?: string
  search?: string
  start?: string
  end?: string
  // Final phase (NEW)
  priority?: Priority
  tag?: string
  pinned_only?: boolean
  assigned_agent_id?: string
  supervisor_closed?: boolean
  page?: number
  page_size?: number
}

// ============================================================
// Final phase (NEW): assign/reassign, close/reopen, activity,
// team activity, export, notifications, bulk actions
// ============================================================

export interface SupervisorAgent {
  user_id: string
  name: string
  email: string
  status: 'online' | 'busy' | 'offline' | string
  active_chat_count: number
  max_concurrent_chats: number
}

export interface SupervisorActivityEntry {
  id: string
  conversation_id?: string | null
  actor_id: string | null
  actor_name: string | null
  event_type: string
  detail: Record<string, unknown>
  created_at: string
}

export interface SupervisorTeamActivity {
  agents: SupervisorAgent[]
  recent_activity: SupervisorActivityEntry[]
}

export type NotificationKind =
  | 'new_conversation'
  | 'human_takeover'
  | 'high_priority'
  | 'ai_paused'
  | 'conversation_closed'
  | 'conversation_reopened'

export interface SupervisorNotification {
  id: string
  type: 'supervisor_notification'
  kind: NotificationKind
  conversation_id: string | null
  title: string
  severity: 'info' | 'warning' | 'critical'
  detail: Record<string, unknown>
  created_at: string
}

export interface SupervisorExportPayload {
  conversation: Omit<SupervisorConversationDetail, 'messages' | 'notes'>
  messages: SupervisorMessage[]
  notes: SupervisorNote[]
  activity: SupervisorActivityEntry[]
  exported_at: string
  format: 'json' | 'html' | 'pdf'
}

export interface BulkActionResult {
  succeeded: string[]
  failed: { id: string; error: string }[]
}

export interface BulkExportResult {
  items: SupervisorExportPayload[]
  failed: { id: string; error: string }[]
  exported_at: string
}
