// ============================================================
// ThunderBots — Personal Email AI Assistant Types (NEW — Part 1)
// ============================================================

export type PersonalEmailProvider = 'gmail' | 'outlook'
export type PersonalEmailStatus = 'connected' | 'expired' | 'error' | 'disconnected'
export type PersonalEmailFolder = 'inbox' | 'sent' | 'drafts' | 'starred'
export type PersonalEmailPriority = 'low' | 'medium' | 'high' | 'urgent'
export type PersonalEmailSentiment = 'positive' | 'neutral' | 'negative'
export type PersonalEmailDraftStyle = 'professional' | 'friendly' | 'short'
export type PersonalEmailCategory = 'work' | 'personal' | 'finance' | 'promotions' | 'social' | 'updates' | 'spam' | 'other'
export type PersonalEmailSendStatus = 'draft' | 'pending_approval' | 'scheduled' | 'sending' | 'sent' | 'failed'
export type PersonalEmailApprovalStatus = 'not_required' | 'pending' | 'approved' | 'rejected'

export interface PersonalEmailAccount {
  id: string
  provider: PersonalEmailProvider
  email_address: string
  display_name: string | null
  status: PersonalEmailStatus
  last_error: string | null
  sync_enabled: boolean
  digest_enabled: boolean
  last_sync_at: string | null
  last_sync_status: 'ok' | 'error' | null
  last_digest_at: string | null
  created_at: string | null
}

export interface PersonalEmailMessage {
  id: string
  account_id: string
  provider_thread_id: string | null
  folder: 'inbox' | 'sent' | 'drafts'
  is_starred: boolean
  is_read: boolean
  sender_name: string | null
  sender_email: string | null
  to_addresses: string | null
  subject: string | null
  snippet: string | null
  body_text?: string | null
  body_html?: string | null
  received_at: string | null
  ai_summary: string | null
  ai_priority: PersonalEmailPriority | null
  ai_sentiment: PersonalEmailSentiment | null
  ai_deadline: string | null
  ai_tasks: string[]
  ai_action_required: boolean | null
  ai_analyzed_at: string | null
  ai_analysis_error: string | null
  drafts?: PersonalEmailDraft[]
  // ── Part 2 ──────────────────────────────────────────────────────────
  category: PersonalEmailCategory | null
  labels: string[]
  is_spam: boolean
  spam_score: number | null
  spam_reason: string | null
  is_answered: boolean
  answered_at: string | null
  has_attachments: boolean
  attachments: { attachment_id: string; filename: string; mime_type: string; size: number }[]
}

export interface PersonalEmailDraft {
  id: string
  message_id: string
  style: PersonalEmailDraftStyle
  content: string
  is_edited: boolean
  language: string
  created_at: string | null
  updated_at: string | null
  // ── Part 2 ──────────────────────────────────────────────────────────
  send_status: PersonalEmailSendStatus
  approval_status: PersonalEmailApprovalStatus
  scheduled_at: string | null
  sent_at: string | null
  sent_provider_message_id: string | null
  send_error: string | null
  to_addresses: string | null
  cc: string | null
  bcc: string | null
  subject_override: string | null
  attachments: { filename: string; mime_type: string; size: number }[]
  created_by_rule_id: string | null
}

export interface PersonalEmailAutoReplyRule {
  id: string
  account_id: string
  name: string
  is_active: boolean
  sender_contains: string | null
  subject_contains: string | null
  category: PersonalEmailCategory | null
  priority: PersonalEmailPriority | null
  style: PersonalEmailDraftStyle
  instructions: string | null
  require_approval: boolean
  last_triggered_at: string | null
  trigger_count: number
  created_at: string | null
}

export interface PersonalEmailFollowUp {
  id: string
  message_id: string
  suggested_content: string
  status: 'suggested' | 'dismissed' | 'used'
  created_at: string | null
}

export interface PersonalEmailAnalytics {
  period_days: number
  total_received: number
  total_sent: number
  spam_caught: number
  unanswered_count: number
  ai_replies_sent: number
  avg_response_time_hours: number | null
  by_category: Record<string, number>
  by_priority: Record<string, number>
  by_sentiment: Record<string, number>
}

export interface PersonalEmailDigest {
  id: string
  account_id: string
  digest_date: string
  summary: string
  total_emails: number
  action_required_count: number
  high_priority_count: number
  highlights: { message_id: string; subject: string | null; reason: string }[]
  created_at: string | null
}

export interface PersonalEmailSyncResult {
  synced: number
  new_messages: number
  analyzed: number
  errors: string[]
}
