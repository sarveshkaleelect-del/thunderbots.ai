// ============================================================
// ThunderBots — AI Call Agent: Phone Number Types (Voice AI Part 2)
//
// Phone number connection + verification only. No call session, no
// workflow binding, no call automation types here — that is explicitly
// out of scope for this part.
// ============================================================

export type PhoneVerificationStatus = 'pending' | 'verified' | 'failed' | 'expired'
export type PhoneVerificationMethod = 'otp' | 'sms' | 'call'

export interface PhoneNumber {
  id: string
  phone_number: string
  label: string
  status: PhoneVerificationStatus
  verification_method: PhoneVerificationMethod | null
  is_connected: boolean
  is_enabled: boolean
  last_verified_at: string | null
  last_error: string | null
  disconnected_at: string | null
  created_at: string
  updated_at: string
}

export interface AddPhoneNumberPayload {
  phone_number: string
  label?: string
}

export interface SendCodePayload {
  method: PhoneVerificationMethod
}

export interface VerifyCodePayload {
  code: string
}

// ============================================================
// AI Call Agent — Realtime Calls (NEW, Voice AI Part 3)
// ============================================================

export type CallDirection = 'inbound' | 'outbound'
export type CallStatus =
  | 'queued' | 'ringing' | 'active' | 'completed' | 'failed' | 'missed' | 'no_answer'
export type CallDashboardBucket = 'active' | 'missed' | 'completed' | 'failed' | 'interrupted'

export interface Call {
  id: string
  phone_number_id: string
  workflow_id: string | null
  direction: CallDirection
  from_number: string
  to_number: string
  status: CallStatus
  end_reason: string | null
  error_message: string | null
  ai_voice_provider: string | null
  ai_voice_id: string | null
  voice_speed: number
  language: string
  recording_enabled: boolean
  recording_url: string | null
  interrupted_count: number
  fallback_triggered: boolean
  handed_off_to_human: boolean
  summary: string | null   // NEW (Voice AI Part 4)
  started_at: string | null
  answered_at: string | null
  ended_at: string | null
  duration_seconds: number
  created_at: string
}

export interface CallTranscriptEntry {
  id: string
  role: 'caller' | 'ai' | 'system'
  content: string
  sequence: number
  was_interrupted: boolean
  response_time_ms: number | null   // NEW (Voice AI Part 4)
  created_at: string
}

// NEW (Voice AI Part 4): extended analytics on top of the Part 3 counts.
export interface CallDashboardSummary {
  total_calls: number
  active: number
  missed: number
  completed: number
  failed: number
  interrupted: number
  interrupt_count: number
  avg_duration_seconds: number | null
  avg_response_time_ms: number | null
  resolution_rate: number | null
}

export interface CallVoiceOption {
  id: string
  name: string
  gender: string
}

export interface CallVoiceProvider {
  name: string
  credential_provider: string
  requires_region: boolean
  voices: CallVoiceOption[]
  configured: boolean
}

// NEW (Voice AI Part 4)
export type PromptScope = 'strict' | 'open'
export type InterruptBehavior = 'interrupt' | 'queue' | 'ignore'

export interface BusinessHoursDay { open: string; close: string }
export interface BusinessHours {
  enabled: boolean
  timezone: string
  days: Partial<Record<'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun', BusinessHoursDay>>
}

export interface CallSettings {
  voice_provider?: string
  voice_id?: string
  speed?: number
  language?: string
  recording_enabled?: boolean
  // NEW (Voice AI Part 4) — admin controls
  greeting_message?: string
  fallback_prompt?: string
  system_prompt?: string
  knowledge_base_ids?: string[]
  prompt_scope?: PromptScope
  interrupt_behavior?: InterruptBehavior
  business_hours?: BusinessHours
}

export interface PhoneNumberCallSettings {
  id: string
  workflow_id: string | null
  voice_agent_id: string | null
  call_settings: CallSettings
}

export interface OutboundCallPayload {
  phone_number_id: string
  to_number: string
}

// NEW (Voice AI Part 4) — Human handoff
export type HandoffStatus = 'ai' | 'waiting' | 'active' | 'paused' | 'closed'
export interface CallHandoffResult {
  call_id: string
  handoff_status: HandoffStatus
  handoff?: Record<string, unknown>
}

// ============================================================
// AI Call Agent — Standalone Voice Agents (NEW, Voice AI Part 5)
//
// A Voice Agent is its own product entity — own AI provider/model,
// Instructions, personality, goals, voice, and Knowledge Base — with NO
// dependency on the chatbot Workflow/Builder module and no shared storage
// with the chatbot's own Knowledge Base. See PhoneNumber.voice_agent_id
// above for how a phone number gets bound to one.
// ============================================================

export interface VoiceAgentInstructions {
  behaviour?: string
  role?: string
  rules?: string
  business_policies?: string
  tone?: string
  sales_instructions?: string
  appointment_booking_rules?: string
  escalation_rules?: string
  response_restrictions?: string
}

export interface VoiceAgent {
  id: string
  name: string
  description: string
  ai_provider: string | null
  ai_model: string | null
  instructions: VoiceAgentInstructions
  personality: string
  goals: string
  welcome_message: string
  fallback_message: string
  voice_provider: string | null
  voice_id: string | null
  language: string
  speaking_speed: number
  temperature: number
  silence_timeout_seconds: number
  interrupt_enabled: boolean
  memory_enabled: boolean
  conversation_history_enabled: boolean
  is_enabled: boolean
  /** NEW — Publish/Unpublish lifecycle, independent of is_enabled. */
  status: 'draft' | 'published'
  created_at: string
  updated_at: string
}

export interface VoiceAgentCreatePayload {
  name: string
  description?: string
}

export type VoiceAgentUpdatePayload = Partial<
  Omit<VoiceAgent, 'id' | 'created_at' | 'updated_at' | 'instructions'>
> & { instructions?: VoiceAgentInstructions }

/** NEW — Test Voice Agent dialog */
export interface VoiceAgentTestChatTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface VoiceAgentTestChatResponse {
  role: 'assistant'
  content: string
}


export type VoiceAgentKBType = 'pdf' | 'text' | 'faq' | 'url'
export type VoiceAgentKBStatus = 'processing' | 'ready' | 'error'

export interface VoiceAgentKBDocument {
  id: string
  agent_id: string
  kb_type: VoiceAgentKBType
  title: string
  file_type: string
  file_size: number
  status: VoiceAgentKBStatus
  error_message: string | null
  chunk_count: number
  faq_items: { question: string; answer: string }[] | null
  created_at: string
  processed_at: string | null
}

export interface VoiceAgentDashboard {
  total_agents: number
  enabled_agents: number
  bound_phone_numbers: number
  total_calls: number
  total_knowledge_documents: number
}

export interface VoiceAgentAnalytics {
  agent_id: string
  total_calls: number
  completed_calls: number
  failed_calls: number
  interrupted_calls: number
  avg_duration_seconds: number | null
  resolution_rate: number | null
}

export interface VoiceAgentEmbedSnippet {
  agent_id: string
  embed_snippet: string
}
