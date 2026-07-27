// ============================================================
// ThunderBots — AI Supervisor Dashboard API Client (NEW)
// ============================================================
import { apiClient } from './client'
import type {
  SupervisorConversationListResponse, SupervisorConversationDetail,
  SupervisorStats, SupervisorFilters, SupervisorNote,
  SupervisorAgent, SupervisorActivityEntry, SupervisorTeamActivity,
  SupervisorExportPayload, BulkActionResult, BulkExportResult, Priority,
} from '@/types/aiSupervisor'

export const aiSupervisorApi = {
  stats: async (params: { start?: string; end?: string } = {}): Promise<SupervisorStats> => {
    const { data } = await apiClient.get('/ai-supervisor/stats', { params })
    return data
  },

  conversations: async (filters: SupervisorFilters = {}): Promise<SupervisorConversationListResponse> => {
    const { data } = await apiClient.get('/ai-supervisor/conversations', { params: filters })
    return data
  },

  conversationDetail: async (id: string): Promise<SupervisorConversationDetail> => {
    const { data } = await apiClient.get(`/ai-supervisor/conversations/${id}`)
    return data
  },

  // ── Interaction controls (NEW) ──────────────────────────────────────
  pause: async (id: string) => {
    const { data } = await apiClient.post(`/ai-supervisor/conversations/${id}/pause`)
    return data
  },

  resume: async (id: string) => {
    const { data } = await apiClient.post(`/ai-supervisor/conversations/${id}/resume`)
    return data
  },

  takeOver: async (id: string) => {
    const { data } = await apiClient.post(`/ai-supervisor/conversations/${id}/take-over`)
    return data
  },

  returnToAi: async (id: string) => {
    const { data } = await apiClient.post(`/ai-supervisor/conversations/${id}/return-to-ai`)
    return data
  },

  sendMessage: async (id: string, content: string) => {
    const { data } = await apiClient.post(`/ai-supervisor/conversations/${id}/messages`, { content })
    return data
  },

  listNotes: async (id: string): Promise<{ items: SupervisorNote[] }> => {
    const { data } = await apiClient.get(`/ai-supervisor/conversations/${id}/notes`)
    return data
  },

  addNote: async (id: string, content: string): Promise<SupervisorNote> => {
    const { data } = await apiClient.post(`/ai-supervisor/conversations/${id}/notes`, { content })
    return data
  },

  reviewMessage: async (messageId: string, verdict: 'correct' | 'incorrect') => {
    const { data } = await apiClient.post(`/ai-supervisor/messages/${messageId}/review`, { verdict })
    return data
  },

  // ── Final phase: assign/reassign, close/reopen, tags, priority, pin,
  // export, activity history, team activity, bulk actions (NEW) ────────

  agents: async (): Promise<{ items: SupervisorAgent[] }> => {
    const { data } = await apiClient.get('/ai-supervisor/agents')
    return data
  },

  assign: async (id: string, agentId: string) => {
    const { data } = await apiClient.post(`/ai-supervisor/conversations/${id}/assign`, { agent_id: agentId })
    return data
  },

  close: async (id: string) => {
    const { data } = await apiClient.post(`/ai-supervisor/conversations/${id}/close`)
    return data
  },

  reopen: async (id: string) => {
    const { data } = await apiClient.post(`/ai-supervisor/conversations/${id}/reopen`)
    return data
  },

  setPriority: async (id: string, priority: Priority) => {
    const { data } = await apiClient.put(`/ai-supervisor/conversations/${id}/priority`, { priority })
    return data
  },

  addTag: async (id: string, tag: string) => {
    const { data } = await apiClient.post(`/ai-supervisor/conversations/${id}/tags`, { tag })
    return data
  },

  removeTag: async (id: string, tag: string) => {
    const { data } = await apiClient.delete(`/ai-supervisor/conversations/${id}/tags/${encodeURIComponent(tag)}`)
    return data
  },

  setPinned: async (id: string, pinned: boolean) => {
    const { data } = await apiClient.put(`/ai-supervisor/conversations/${id}/pin`, { pinned })
    return data
  },

  activity: async (id: string): Promise<{ items: SupervisorActivityEntry[] }> => {
    const { data } = await apiClient.get(`/ai-supervisor/conversations/${id}/activity`)
    return data
  },

  teamActivity: async (limit = 30): Promise<SupervisorTeamActivity> => {
    const { data } = await apiClient.get('/ai-supervisor/team-activity', { params: { limit } })
    return data
  },

  exportConversation: async (id: string, format: 'json' | 'html' | 'pdf' = 'json'): Promise<SupervisorExportPayload | string> => {
    const { data } = await apiClient.get(`/ai-supervisor/conversations/${id}/export`, {
      params: { format },
      responseType: format === 'json' ? 'json' : 'text',
    })
    return data
  },

  bulkClose: async (conversationIds: string[]): Promise<BulkActionResult> => {
    const { data } = await apiClient.post('/ai-supervisor/conversations/bulk-close', { conversation_ids: conversationIds })
    return data
  },

  bulkAssign: async (conversationIds: string[], agentId: string): Promise<BulkActionResult> => {
    const { data } = await apiClient.post('/ai-supervisor/conversations/bulk-assign', {
      conversation_ids: conversationIds, agent_id: agentId,
    })
    return data
  },

  bulkTag: async (conversationIds: string[], tag: string): Promise<BulkActionResult> => {
    const { data } = await apiClient.post('/ai-supervisor/conversations/bulk-tags', {
      conversation_ids: conversationIds, tag,
    })
    return data
  },

  bulkExport: async (conversationIds: string[]): Promise<BulkExportResult> => {
    const { data } = await apiClient.post('/ai-supervisor/conversations/bulk-export', { conversation_ids: conversationIds })
    return data
  },
}
