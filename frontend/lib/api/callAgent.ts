import { apiClient } from './client'
import type {
  PhoneNumber,
  AddPhoneNumberPayload,
  SendCodePayload,
  VerifyCodePayload,
  Call,
  CallTranscriptEntry,
  CallDashboardSummary,
  CallVoiceProvider,
  CallSettings,
  PhoneNumberCallSettings,
  OutboundCallPayload,
  CallDashboardBucket,
  CallHandoffResult,
  VoiceAgent,
  VoiceAgentCreatePayload,
  VoiceAgentUpdatePayload,
  VoiceAgentKBDocument,
  VoiceAgentDashboard,
  VoiceAgentAnalytics,
  VoiceAgentEmbedSnippet,
  VoiceAgentTestChatTurn,
  VoiceAgentTestChatResponse,
} from '@/types/callAgent'

export const callAgentApi = {
  list: () =>
    apiClient.get<PhoneNumber[]>('/call-agent/phone-numbers').then(r => r.data),

  add: (payload: AddPhoneNumberPayload) =>
    apiClient.post<PhoneNumber>('/call-agent/phone-numbers', payload).then(r => r.data),

  remove: (id: string) =>
    apiClient.delete<{ deleted: boolean }>(`/call-agent/phone-numbers/${id}`).then(r => r.data),

  sendCode: (id: string, payload: SendCodePayload) =>
    apiClient.post<PhoneNumber>(`/call-agent/phone-numbers/${id}/send-code`, payload).then(r => r.data),

  verifyCode: (id: string, payload: VerifyCodePayload) =>
    apiClient.post<PhoneNumber>(`/call-agent/phone-numbers/${id}/verify`, payload).then(r => r.data),

  disconnect: (id: string) =>
    apiClient.post<PhoneNumber>(`/call-agent/phone-numbers/${id}/disconnect`).then(r => r.data),

  reconnect: (id: string) =>
    apiClient.post<PhoneNumber>(`/call-agent/phone-numbers/${id}/reconnect`).then(r => r.data),

  enable: (id: string) =>
    apiClient.post<PhoneNumber>(`/call-agent/phone-numbers/${id}/enable`).then(r => r.data),

  disable: (id: string) =>
    apiClient.post<PhoneNumber>(`/call-agent/phone-numbers/${id}/disable`).then(r => r.data),

  // ── Voice AI Part 3 — call settings, calls, dashboard, transcript ────────
  // Extended in Part 4 with admin controls, filters, summary, and handoff.

  getCallSettings: (numberId: string) =>
    apiClient.get<PhoneNumberCallSettings>(`/call-agent/phone-numbers/${numberId}/call-settings`).then(r => r.data),

  updateCallSettings: (numberId: string, payload: { workflow_id?: string | null; voice_agent_id?: string | null } & CallSettings) =>
    apiClient.put<PhoneNumberCallSettings>(`/call-agent/phone-numbers/${numberId}/call-settings`, payload).then(r => r.data),

  listVoices: () =>
    apiClient.get<CallVoiceProvider[]>('/call-agent/voices').then(r => r.data),

  placeOutboundCall: (payload: OutboundCallPayload) =>
    apiClient.post<Call>('/call-agent/calls/outbound', payload).then(r => r.data),

  hangupCall: (callId: string) =>
    apiClient.post<Call>(`/call-agent/calls/${callId}/hangup`).then(r => r.data),

  dashboardSummary: () =>
    apiClient.get<CallDashboardSummary>('/call-agent/calls/dashboard').then(r => r.data),

  // NEW (Part 4): search (matches from/to number) + date range filters.
  listCalls: (params?: {
    status?: CallDashboardBucket | string
    phone_number_id?: string
    search?: string
    date_from?: string
    date_to?: string
    limit?: number
    offset?: number
  }) =>
    apiClient.get<Call[]>('/call-agent/calls', {
      params: {
        status_filter: params?.status,
        phone_number_id: params?.phone_number_id,
        search: params?.search,
        date_from: params?.date_from,
        date_to: params?.date_to,
        limit: params?.limit,
        offset: params?.offset,
      },
    }).then(r => r.data),

  getCall: (callId: string) =>
    apiClient.get<Call>(`/call-agent/calls/${callId}`).then(r => r.data),

  getTranscript: (callId: string) =>
    apiClient.get<CallTranscriptEntry[]>(`/call-agent/calls/${callId}/transcript`).then(r => r.data),

  // ── NEW (Voice AI Part 4) — call recording summary ──────────────────────

  regenerateSummary: (callId: string) =>
    apiClient.post<{ id: string; summary: string }>(`/call-agent/calls/${callId}/summary`).then(r => r.data),

  // ── NEW (Voice AI Part 4) — human handoff ────────────────────────────────

  handoffToHuman: (callId: string) =>
    apiClient.post<CallHandoffResult>(`/call-agent/calls/${callId}/handoff`).then(r => r.data),

  resumeAI: (callId: string) =>
    apiClient.post<CallHandoffResult>(`/call-agent/calls/${callId}/resume-ai`).then(r => r.data),

  getHandoffStatus: (callId: string) =>
    apiClient.get<CallHandoffResult>(`/call-agent/calls/${callId}/handoff-status`).then(r => r.data),

  sendAgentMessage: (callId: string, content: string) =>
    apiClient.post(`/call-agent/calls/${callId}/agent-message`, { content }).then(r => r.data),
}

// ============================================================
// AI Call Agent — Standalone Voice Agents (NEW, Voice AI Part 5)
//
// Independent from `callAgentApi` above on purpose: this hits the new
// call_agent_agents.py router, never workflowsApi / knowledgeApi. A Voice
// Agent's Knowledge Base has its own endpoints/storage here — it is never
// the same request as knowledgeApi.upload / knowledgeApi.createTextEntry.
// ============================================================

export const voiceAgentsApi = {
  list: () =>
    apiClient.get<VoiceAgent[]>('/call-agent/agents').then(r => r.data),

  create: (payload: VoiceAgentCreatePayload) =>
    apiClient.post<VoiceAgent>('/call-agent/agents', payload).then(r => r.data),

  get: (agentId: string) =>
    apiClient.get<VoiceAgent>(`/call-agent/agents/${agentId}`).then(r => r.data),

  update: (agentId: string, payload: VoiceAgentUpdatePayload) =>
    apiClient.put<VoiceAgent>(`/call-agent/agents/${agentId}`, payload).then(r => r.data),

  remove: (agentId: string) =>
    apiClient.delete<{ deleted: boolean }>(`/call-agent/agents/${agentId}`).then(r => r.data),

  dashboard: () =>
    apiClient.get<VoiceAgentDashboard>('/call-agent/dashboard').then(r => r.data),

  analytics: (agentId: string) =>
    apiClient.get<VoiceAgentAnalytics>(`/call-agent/agents/${agentId}/analytics`).then(r => r.data),

  embedSnippet: (agentId: string) =>
    apiClient.get<VoiceAgentEmbedSnippet>(`/call-agent/agents/${agentId}/embed`).then(r => r.data),

  // ── NEW — Publish / Unpublish / Test (additive; Embed/Preview/Voice
  //     Widget above are untouched) ─────────────────────────────────────

  publish: (agentId: string) =>
    apiClient.post<VoiceAgent>(`/call-agent/agents/${agentId}/publish`).then(r => r.data),

  unpublish: (agentId: string) =>
    apiClient.post<VoiceAgent>(`/call-agent/agents/${agentId}/unpublish`).then(r => r.data),

  testChat: (agentId: string, messages: VoiceAgentTestChatTurn[]) =>
    apiClient.post<VoiceAgentTestChatResponse>(`/call-agent/agents/${agentId}/test-chat`, { messages }).then(r => r.data),

  // ── Knowledge Base (PDF / Text / FAQ) — independent storage ────────────

  listKnowledge: (agentId: string) =>
    apiClient.get<VoiceAgentKBDocument[]>(`/call-agent/agents/${agentId}/knowledge`).then(r => r.data),

  uploadPdf: (agentId: string, file: File, onProgress?: (pct: number) => void) => {
    const form = new FormData()
    form.append('file', file)
    // Same root-cause fix as knowledgeApi.upload: no manual Content-Type,
    // let Axios attach the multipart boundary itself.
    return apiClient.post(`/call-agent/agents/${agentId}/knowledge/upload`, form, {
      timeout: 120_000,
      onUploadProgress: (e) => {
        if (onProgress && e.total) onProgress(Math.round((e.loaded * 100) / e.total))
      },
    }).then(r => r.data)
  },

  createText: (agentId: string, title: string, content: string) =>
    apiClient.post(`/call-agent/agents/${agentId}/knowledge/text`, { title, content }).then(r => r.data),

  getText: (agentId: string, docId: string) =>
    apiClient.get<{ id: string; title: string; content: string; status: string }>(
      `/call-agent/agents/${agentId}/knowledge/${docId}/text`
    ).then(r => r.data),

  createFaq: (agentId: string, title: string, items: { question: string; answer: string }[]) =>
    apiClient.post(`/call-agent/agents/${agentId}/knowledge/faq`, { title, items }).then(r => r.data),

  retryDocument: (agentId: string, docId: string) =>
    apiClient.post(`/call-agent/agents/${agentId}/knowledge/${docId}/retry`).then(r => r.data),

  deleteDocument: (agentId: string, docId: string) =>
    apiClient.delete(`/call-agent/agents/${agentId}/knowledge/${docId}`),
}
