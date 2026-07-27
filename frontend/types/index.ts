// ============================================================
// ThunderBots v3 — TypeScript Types
// ============================================================

// ── Auth ─────────────────────────────────────────────────────
export interface User {
  id: string
  name: string
  email: string
  preferences?: UserPreferences
  is_admin?: boolean
  is_active?: boolean
  // NEW (Google SSO & 2FA) — additive/optional so any code constructing a
  // User without these fields (existing tests, mocks, etc) still compiles.
  totp_enabled?: boolean
  google_linked?: boolean
  has_password?: boolean
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}

// NEW (Google SSO & 2FA): returned by /login, /google instead of
// AuthResponse when the account has TOTP 2FA enabled. The caller must
// complete POST /auth/2fa/verify with mfa_token + a code to get a real
// AuthResponse.
export interface MfaRequiredResponse {
  mfa_required: true
  mfa_token: string
}

export type LoginResult = AuthResponse | MfaRequiredResponse

export function isMfaRequired(result: LoginResult): result is MfaRequiredResponse {
  return (result as MfaRequiredResponse).mfa_required === true
}

// NEW (Active Sessions & Device Management — Phase 2)
export interface UserSession {
  id: string
  device_name: string
  browser: string
  os: string
  device_type: 'desktop' | 'mobile' | 'tablet' | 'unknown'
  ip_address: string
  location: string | null
  created_at: string
  last_active_at: string
  is_current: boolean
}

// ── Preferences ───────────────────────────────────────────────
export interface UserPreferences {
  default_provider: string
  default_model: string
  theme: 'dark' | 'light' | 'midnight' | 'thunder'
  language: string
}

// ── API Keys ──────────────────────────────────────────────────
export interface UserAPIKey {
  id: string
  provider: string
  label: string
  base_url?: string
  is_valid: boolean
  has_key: boolean
  key_preview?: string
  created_at: string
  last_tested?: string
}

export interface APIKeyCreate {
  provider: string
  api_key: string
  label?: string
  base_url?: string
}

// ── AI Providers ──────────────────────────────────────────────
export interface AIProvider {
  id: string
  name: string
  requires_key: boolean
  models: string[]
  default: string
  configured: boolean
  base_url?: string
}

// ── Workflow ──────────────────────────────────────────────────
export interface Workflow {
  id: string
  name: string
  description?: string
  status: 'draft' | 'published'
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
  canvas_state: CanvasState
  settings: WorkflowSettings
  knowledge_base_id?: string
  created_at: string
  updated_at: string
}

export interface WorkflowListItem {
  id: string
  name: string
  description?: string
  status: string
  node_count: number
  knowledge_base_id?: string
  created_at: string
  updated_at: string
}

export interface CanvasState { x: number; y: number; zoom: number }
export interface WorkflowSettings { theme?: string; language?: string }

// ── Nodes ─────────────────────────────────────────────────────
export type NodeType =
  | 'start' | 'text_card' | 'multiple_choice'
  | 'ai_agent' | 'transition' | 'end'
  | 'condition' | 'link' | 'rating' | 'location' | 'video'

export interface WorkflowNode {
  id: string
  type: NodeType
  position: { x: number; y: number }
  data: NodeData
}

export type NodeData =
  | StartNodeData | TextCardNodeData | MultipleChoiceNodeData
  | AIAgentNodeData | TransitionNodeData | EndNodeData
  | ConditionNodeData | LinkNodeData | RatingNodeData | LocationNodeData | VideoNodeData

export interface StartNodeData { label?: string; welcomeMessage?: string }
export interface TextCardNodeData { label?: string; content: string }
export interface NodeMediaAttachment {
  url: string
  filename?: string
  size?: number
  mime_type?: string
}
export interface MultipleChoiceNodeData {
  label?: string; question: string
  choices: Array<{ label: string; value: string }>
  image?: NodeMediaAttachment | null
}
export interface AIAgentNodeData {
  label?: string
  provider: 'gemini'
  model?: string
  systemPrompt: string
  instructions?: string
  temperature: number
  maxTokens: number
  contextWindow: number
  memoryEnabled: boolean
  stayOnNode: boolean
  knowledgeBaseId?: string
}
export interface TransitionNodeData {
  label?: string
  conditions: TransitionCondition[]
}
export interface TransitionCondition {
  id: string
  field: string
  operator: 'contains' | 'equals' | 'starts_with' | 'ends_with' | 'not_contains' | 'greater_than' | 'less_than'
  value: string
  handle: string
}
export interface EndNodeData { label?: string; message?: string }

// ── Condition (🔀) ────────────────────────────────────────────
/** Simple single-comparison branch: variable == value → IF, else → ELSE. */
export interface ConditionNodeData {
  label?: string
  variable: string
  value: string
}

// ── Link (🔗) ─────────────────────────────────────────────────
export type LinkType = 'website' | 'pdf' | 'google_maps' | 'whatsapp' | 'email' | 'phone'
export interface LinkNodeData {
  label?: string
  linkType: LinkType
  url: string
  buttonText: string
  openInNewTab: boolean
}

// ── Rating (⭐) ────────────────────────────────────────────────
export interface RatingNodeData {
  label?: string
  question?: string
  allowFeedback: boolean
  feedbackPlaceholder?: string
  /** Variable name the selected 1–5 rating (and optional feedback) is stored under. */
  variableName: string
}

// ── Location (📍) ─────────────────────────────────────────────
export interface LocationNodeData {
  label?: string
  address: string
  latitude?: number | null
  longitude?: number | null
  buttonText?: string
}

// ── Video (🎥) ────────────────────────────────────────────────
export type VideoType = 'youtube' | 'vimeo' | 'mp4'
export interface VideoNodeData {
  label?: string
  videoType: VideoType
  url: string
}

// ── Edges ─────────────────────────────────────────────────────
export interface WorkflowEdge {
  id: string; source: string; target: string
  sourceHandle?: string; targetHandle?: string
  type?: string; data?: { label?: string; condition?: string }
}

// ── History ───────────────────────────────────────────────────
export interface WorkflowVersion {
  id: string; version_number: number; label?: string; created_at: string
}

// ── Knowledge Base ────────────────────────────────────────────
export interface KnowledgeBase {
  id: string; name: string; description?: string
  kb_type?: 'file' | 'text'   // NEW (Voice AI Part 4)
  document_count: number; chunk_count: number; created_at: string
}
export interface KBDocument {
  id: string; filename: string; file_type: string; file_size: number
  status: 'processing' | 'ready' | 'error'; chunk_count: number
  error_message?: string; created_at: string; processed_at?: string
  source_type?: 'upload' | 'pasted_text'   // NEW (Voice AI Part 4)
  text_preview?: string                     // NEW (Voice AI Part 4)
}

// ── Chat ──────────────────────────────────────────────────────
export interface ChatMessage {
  id: string
  role: 'user' | 'bot' | 'system'
  content: string
  choices?: Array<{ label: string; value: string }>
  image?: NodeMediaAttachment | null
  citations?: Citation[]
  nodeId?: string; nodeType?: string
  isStreaming?: boolean
  timestamp: Date
}
export interface Citation { index: number; source: string; score: number; excerpt: string }
export interface ChatContext {
  current_node_id?: string
  variables: Record<string, unknown>
  message_history: Array<{ role: string; content: string }>
  session_id?: string; workflow_id?: string; turn_count: number
}

// ── Deploy ────────────────────────────────────────────────────
export interface BotBranding {
  bot_name: string
  logo_url: string | null
  avatar_url: string | null
  welcome_title: string
  welcome_description: string
  browser_title: string | null
  favicon_url: string | null
  theme_color: string
  accent_color: string
}
export interface DesignConfig {
  background_color: string
  background_gradient: string | null
  background_image: string | null
  bot_bubble_color: string
  user_bubble_color: string
  font_family: string
  font_size: number
  border_radius: number
  shadows: boolean
  glassmorphism: boolean
  mode: 'dark' | 'light'
}
export type VoiceResponseMode = 'text_only' | 'voice_text' | 'voice_only'
export type VoiceProviderId = 'browser' | 'gemini' | 'elevenlabs' | 'azure_speech' | 'google_tts'
export type VoiceGender = 'male' | 'female' | 'neutral'
/** Voice Personality — affects ONLY how a reply is spoken (rate/pitch/tone
 * on providers that support it). Never changes the bot's text response. */
export type VoicePersonality = 'friendly' | 'professional' | 'energetic' | 'calm' | 'formal'

export interface VoiceOption {
  id: string
  name: string
  gender: VoiceGender
}

export interface VoiceProviderInfo {
  id: VoiceProviderId
  name: string
  requires_key: boolean
  requires_region: boolean
  configured: boolean
  voices: VoiceOption[]
}

export interface VoiceSettings {
  /** Backward-compatible: 'text_only' means Voice Responses are off. */
  response_mode: VoiceResponseMode
  /** Explicit on/off — kept in sync with response_mode by the UI. */
  enabled: boolean
  provider: VoiceProviderId
  voice_id: string | null
  gender: VoiceGender
  /** Optional — purely a playback style. Defaults to 'friendly' when unset. */
  personality?: VoicePersonality
  /** Whether the deployed chatbot shows a Speaker ON/OFF control at all. */
  allow_mute: boolean
  /** Initial Speaker state shown to end users. */
  default_state: 'on' | 'off'
}
export interface ChatSettings {
  show_bot_logo: boolean
  show_bot_name: boolean
  show_timestamp: boolean
  show_typing_indicator: boolean
  show_restart_button: boolean
  show_powered_by: boolean
  enable_sound: boolean
  enable_file_upload: boolean
  enable_markdown: boolean
  enable_auto_scroll: boolean
  voice: VoiceSettings
}
export interface WidgetConfig {
  launcher_icon: string | null
  launcher_color: string
  size: 'small' | 'medium' | 'large'
  position: 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left'
  border_radius: number
  animation: 'pop' | 'slide' | 'fade' | 'none'
  initial_greeting: string
}
export interface BrandingBundle {
  workflow_id: string
  branding: BotBranding
  design: DesignConfig
  chat_settings: ChatSettings
  widget_config: WidgetConfig
}
export interface Deployment {
  id: string
  workflow_id: string
  slug: string
  is_active: boolean
  embed_config: WidgetConfig
  branding: BotBranding
  design: DesignConfig
  chat_settings: ChatSettings
  share_url: string
  share_url_alt: string
  embed_snippet: string
  widget_script: string
  deployed_at: string
  updated_at: string
}
export interface EmbedConfig {
  theme: 'dark' | 'light'
  position: 'bottom-right' | 'bottom-left' | 'center'
  button_text: string
  button_color: string
  width: number
  height: number
}

// ── Node Library ──────────────────────────────────────────────
export interface NodeLibraryItem {
  type: NodeType; label: string; description: string; icon: string; color: string
  defaultData: Partial<NodeData>
}
