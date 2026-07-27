import { apiClient } from './client'
import type {
  Campaign, CampaignHistoryEntry, CampaignTemplate, CampaignsAnalyticsOverview,
  CampaignCreateInput, CampaignUpdateInput, CampaignRecipientsPage, CampaignRecipient,
  ConnectedChannel, ContactsPage, ContactGroupSummary, AudienceResolveResult,
  AudienceType, AudienceConfig, AudienceEntry,
  QRChannelOption, CampaignQRCode, QRCodeCreateInput,
  GrowthRange, GrowthResponse, BroadcastHistoryEntry,
} from '@/types/campaigns'

export const campaignsApi = {
  list: (params?: { status?: string; channel?: string }) =>
    apiClient.get<Campaign[]>('/campaigns/', { params }).then(r => r.data),

  get: (id: string) =>
    apiClient.get<Campaign>(`/campaigns/${id}`).then(r => r.data),

  create: (data: CampaignCreateInput) =>
    apiClient.post<Campaign>('/campaigns/', data).then(r => r.data),

  update: (id: string, data: CampaignUpdateInput) =>
    apiClient.put<Campaign>(`/campaigns/${id}`, data).then(r => r.data),

  delete: (id: string) =>
    apiClient.delete(`/campaigns/${id}`),

  duplicate: (id: string) =>
    apiClient.post<Campaign>(`/campaigns/${id}/duplicate`).then(r => r.data),

  pause: (id: string) =>
    apiClient.post<Campaign>(`/campaigns/${id}/pause`).then(r => r.data),

  resume: (id: string) =>
    apiClient.post<Campaign>(`/campaigns/${id}/resume`).then(r => r.data),

  history: (id: string) =>
    apiClient.get<CampaignHistoryEntry[]>(`/campaigns/${id}/history`).then(r => r.data),

  templates: () =>
    apiClient.get<CampaignTemplate[]>('/campaigns/templates').then(r => r.data),

  analyticsOverview: () =>
    apiClient.get<CampaignsAnalyticsOverview>('/campaigns/analytics/overview').then(r => r.data),

  aiImprove: (data: { message: string; ai_prompt?: string | null; channel: string; campaign_id?: string }) =>
    apiClient.post<{ improved_message: string }>('/campaigns/ai/improve', data).then(r => r.data),

  // ── Broadcast & Auto-Reply Engine ──────────────────────────────────────
  launch: (id: string) =>
    apiClient.post<Campaign>(`/campaigns/${id}/launch`).then(r => r.data),

  recipients: (id: string, params?: { status?: string; page?: number; page_size?: number }) =>
    apiClient.get<CampaignRecipientsPage>(`/campaigns/${id}/recipients`, { params }).then(r => r.data),

  retryRecipients: (id: string, recipientIds?: string[]) =>
    apiClient.post<{ retried: number }>(`/campaigns/${id}/recipients/retry`, {
      recipient_ids: recipientIds,
    }).then(r => r.data),

  setTakeover: (id: string, recipientId: string, enabled: boolean) =>
    apiClient.post<CampaignRecipient>(
      `/campaigns/${id}/recipients/${recipientId}/takeover`, { enabled },
    ).then(r => r.data),

  recipientConversation: (id: string, recipientId: string) =>
    apiClient.get<{ recipient: CampaignRecipient; conversation: unknown }>(
      `/campaigns/${id}/recipients/${recipientId}/conversation`,
    ).then(r => r.data),

  // ── Audience Selection ──────────────────────────────────────────────────
  channels: (channel: string = 'whatsapp') =>
    apiClient.get<ConnectedChannel[]>('/campaigns/channels', { params: { channel } }).then(r => r.data),

  contacts: (workflowId: string, params?: { channel?: string; search?: string; tag?: string; page?: number; page_size?: number }) =>
    apiClient.get<ContactsPage>('/campaigns/contacts', { params: { workflow_id: workflowId, ...params } }).then(r => r.data),

  tags: (workflowId: string) =>
    apiClient.get<string[]>('/campaigns/tags', { params: { workflow_id: workflowId } }).then(r => r.data),

  groups: () =>
    apiClient.get<ContactGroupSummary[]>('/campaigns/groups').then(r => r.data),

  createGroup: (name: string, members: AudienceEntry[]) =>
    apiClient.post<ContactGroupSummary>('/campaigns/groups', { name, members }).then(r => r.data),

  addGroupMembers: (groupId: string, members: AudienceEntry[]) =>
    apiClient.post<ContactGroupSummary>(`/campaigns/groups/${groupId}/members`, { members }).then(r => r.data),

  deleteGroup: (groupId: string) =>
    apiClient.delete(`/campaigns/groups/${groupId}`),

  resolveAudience: (data: {
    workflow_id?: string | null
    channel?: string
    audience_type: AudienceType
    audience_config: AudienceConfig
    message?: string
    sample_size?: number
  }) =>
    apiClient.post<AudienceResolveResult>('/campaigns/audience/resolve', data).then(r => r.data),

  aiGenerate: (data: { ai_prompt: string; channel: string }) =>
    apiClient.post<{ improved_message: string }>('/campaigns/ai/generate', data).then(r => r.data),

  // ── QR Marketing System (Part 1) ────────────────────────────────────────
  qrChannels: () =>
    apiClient.get<QRChannelOption[]>('/campaigns/qr/channels').then(r => r.data),

  qrList: (params?: { workflow_id?: string; channel?: string }) =>
    apiClient.get<CampaignQRCode[]>('/campaigns/qr', { params }).then(r => r.data),

  qrCreate: (data: QRCodeCreateInput) =>
    apiClient.post<CampaignQRCode>('/campaigns/qr', data).then(r => r.data),

  qrSvg: (id: string) =>
    apiClient.get<{ qr_svg: string; invite_link: string }>(`/campaigns/qr/${id}/svg`).then(r => r.data),

  qrRegenerate: (id: string) =>
    apiClient.post<CampaignQRCode>(`/campaigns/qr/${id}/regenerate`).then(r => r.data),

  qrDelete: (id: string) =>
    apiClient.delete(`/campaigns/qr/${id}`),

  // ── QR Marketing Analytics (Part 3) ─────────────────────────────────────
  analyticsGrowth: (range: GrowthRange = 'daily') =>
    apiClient.get<GrowthResponse>('/campaigns/analytics/growth', { params: { range } }).then(r => r.data),

  broadcastHistory: (limit: number = 20) =>
    apiClient.get<BroadcastHistoryEntry[]>('/campaigns/analytics/broadcast-history', { params: { limit } }).then(r => r.data),
}
