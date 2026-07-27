// ============================================================
// ThunderBots — AI Campaign Manager Types
// ============================================================

export type CampaignChannel = 'whatsapp' | 'instagram' | 'telegram' | 'email'
export type CampaignScheduleType = 'now' | 'later'
export type CampaignStatus = 'draft' | 'scheduled' | 'active' | 'paused' | 'completed' | 'cancelled'
export type AudienceType = 'contacts' | 'tags' | 'groups' | 'manual'

export interface AudienceEntry {
  identifier: string
  name?: string | null
  city?: string | null
  company?: string | null
}

export interface AudienceConfig {
  contact_ids?: string[]
  tags?: string[]
  group_ids?: string[]
  manual_entries?: AudienceEntry[]
}

export interface Campaign {
  id: string
  name: string
  channel: CampaignChannel
  template: string | null
  message: string
  ai_prompt: string | null
  audience_type: AudienceType
  audience_config: AudienceConfig
  schedule_type: CampaignScheduleType
  scheduled_at: string | null
  status: CampaignStatus
  workflow_id: string | null
  sent_count: number
  delivered_count: number
  failed_count: number
  replied_count: number
  created_at: string
  updated_at: string
}

export interface CampaignHistoryEntry {
  id: string
  event_type: string
  detail: Record<string, unknown>
  created_at: string
}

export interface CampaignTemplate {
  id: string
  name: string
  description: string
  message: string
  ai_prompt: string
}

export interface CampaignsAnalyticsOverview {
  total_campaigns: number
  active_campaigns: number
  paused_campaigns: number
  draft_campaigns: number
  scheduled_campaigns: number
  completed_campaigns: number
  sent: number
  delivered: number
  failed: number
  replied: number
  opened: number
  ai_resolved: number
  escalated: number
  subscribers: number
  qr_scans: number
  unique_qr_scans: number
  conversion_rate: number
}

// ============================================================
// QR Marketing Analytics (Part 3)
// ============================================================

export type GrowthRange = 'daily' | 'weekly' | 'monthly'

export interface GrowthPoint {
  period: string
  subscribers: number
  qr_scans: number
  sent: number
}

export interface GrowthResponse {
  range: GrowthRange
  points: GrowthPoint[]
}

export interface BroadcastHistoryEntry {
  id: string
  campaign_id: string
  campaign_name: string
  channel: CampaignChannel
  contact_identifier: string
  contact_name: string | null
  status: CampaignRecipientStatus
  replied: boolean
  ai_resolved: boolean
  escalated: boolean
  sent_at: string | null
  created_at: string
}

export type CampaignRecipientStatus =
  | 'pending' | 'queued' | 'sent' | 'delivered' | 'read' | 'failed' | 'opted_out'

export interface CampaignRecipient {
  id: string
  campaign_id: string
  channel: CampaignChannel
  contact_identifier: string
  contact_name: string | null
  status: CampaignRecipientStatus
  error_message: string | null
  retry_count: number
  max_retries: number
  opened: boolean
  replied: boolean
  ai_resolved: boolean
  escalated: boolean
  human_takeover: boolean
  sent_at: string | null
  delivered_at: string | null
  read_at: string | null
  replied_at: string | null
}

export interface CampaignRecipientsPage {
  recipients: CampaignRecipient[]
  total: number
  page: number
  page_size: number
}

export interface CampaignCreateInput {
  name: string
  channel: CampaignChannel
  template?: string | null
  message: string
  ai_prompt?: string | null
  audience_type?: AudienceType
  audience_config?: AudienceConfig
  schedule_type: CampaignScheduleType
  scheduled_at?: string | null
  workflow_id?: string | null
  launch?: boolean
}

export type CampaignUpdateInput = Partial<CampaignCreateInput> & { status?: CampaignStatus }

export interface ConnectedChannel {
  workflow_id: string
  bot_name: string
  display_phone_number: string | null
  bot_username?: string | null
  verified_name: string | null
  status: string
  is_enabled: boolean
}

export interface WhatsAppContactOption {
  id: string
  identifier: string
  name: string | null
  city: string | null
  company: string | null
  tags: string[]
  message_count: number
}

export interface ContactsPage {
  contacts: WhatsAppContactOption[]
  total: number
  page: number
  page_size: number
}

export interface ContactGroupSummary {
  id: string
  name: string
  member_count: number
  created_at: string | null
}

export interface AudienceEntryPreview {
  identifier: string
  name?: string | null
  city?: string | null
  company?: string | null
  valid: boolean
  reason?: string | null
  preview?: string | null
}

export interface AudienceResolveResult {
  total: number
  valid: number
  invalid: number
  duplicate: number
  sample: AudienceEntryPreview[]
}

// ============================================================
// QR Marketing System (Part 1)
// ============================================================

export type QRChannel = 'telegram' | 'whatsapp' | 'facebook' | 'instagram'

export type QRPlacement =
  | 'shop_entrance' | 'cash_counter' | 'product_packaging' | 'bills'
  | 'visiting_card' | 'posters' | 'menu' | 'website' | 'other'

export interface QRChannelOption {
  workflow_id: string | null
  bot_name: string | null
  channel: QRChannel
  identifier: string | null
  is_connected: boolean
  is_architecture_only: boolean
}

export interface CampaignQRCode {
  id: string
  workflow_id: string
  channel: QRChannel
  placement: QRPlacement
  label: string | null
  invite_link: string
  scan_count: number
  last_scanned_at: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface QRCodeCreateInput {
  workflow_id: string
  channel: QRChannel
  placement: QRPlacement
  label?: string | null
}

