// ============================================================
// ThunderBots — Live Agent API Client (NEW)
// ============================================================
import { apiClient } from './client'

export type AgentStatus = 'online' | 'busy' | 'offline'
export type HandoffStatus = 'ai' | 'waiting' | 'active' | 'closed'

export interface Agent {
  id: string
  user_id: string
  name: string
  email: string
  status: AgentStatus
  active_chat_count: number
  max_concurrent_chats: number
  last_seen_at: string | null
}

export interface Handoff {
  id: string
  conversation_id: string
  workflow_id: string
  session_id: string
  status: HandoffStatus
  channel: string
  requested_by: string | null
  handoff_reason: string | null
  assigned_agent_id: string | null
  assigned_agent_name: string | null
  priority: number
  visitor_label: string
  last_message_preview: string | null
  last_message_at: string | null
  requested_at: string | null
  assigned_at: string | null
  closed_at: string | null
  created_at: string | null
  message_count: number | null
}

export interface HandoffMessage {
  id: string
  role: 'user' | 'bot' | 'agent' | 'system'
  content: string
  node_type: string | null
  created_at: string | null
}

export interface DashboardStats {
  active_chats: number
  waiting_chats: number
  closed_chats: number
  agents_online: number
  agents_busy: number
  agents_offline: number
}

export interface ConversationFilters {
  status?: HandoffStatus
  channel?: string
  agent_id?: string
  search?: string
  limit?: number
  offset?: number
  owner_id?: string
}

export const liveAgentApi = {
  getAgents: async (owner_id?: string): Promise<{ agents: Agent[] }> => {
    const { data } = await apiClient.get('/live-agent/agents', { params: { owner_id } })
    return data
  },

  updateMyStatus: async (status: AgentStatus, owner_id?: string, max_concurrent_chats?: number) => {
    const { data } = await apiClient.put('/live-agent/agents/me/status', { status, max_concurrent_chats }, {
      params: { owner_id },
    })
    return data
  },

  getDashboardStats: async (owner_id?: string): Promise<DashboardStats> => {
    const { data } = await apiClient.get('/live-agent/dashboard/stats', { params: { owner_id } })
    return data
  },

  getConversations: async (
    filters: ConversationFilters = {}
  ): Promise<{ items: Handoff[]; total: number; limit: number; offset: number }> => {
    const { owner_id, ...rest } = filters
    const { data } = await apiClient.get('/live-agent/conversations', { params: { owner_id, ...rest } })
    return data
  },

  getConversation: async (handoffId: string, owner_id?: string): Promise<{ handoff: Handoff; messages: HandoffMessage[] }> => {
    const { data } = await apiClient.get(`/live-agent/conversations/${handoffId}`, { params: { owner_id } })
    return data
  },

  takeOver: async (handoffId: string, owner_id?: string): Promise<Handoff> => {
    const { data } = await apiClient.post(`/live-agent/conversations/${handoffId}/take-over`, {}, { params: { owner_id } })
    return data
  },

  returnToAi: async (handoffId: string, owner_id?: string): Promise<Handoff> => {
    const { data } = await apiClient.post(`/live-agent/conversations/${handoffId}/return-to-ai`, {}, { params: { owner_id } })
    return data
  },

  close: async (handoffId: string, owner_id?: string): Promise<Handoff> => {
    const { data } = await apiClient.post(`/live-agent/conversations/${handoffId}/close`, {}, { params: { owner_id } })
    return data
  },

  sendMessage: async (handoffId: string, content: string, owner_id?: string): Promise<HandoffMessage> => {
    const { data } = await apiClient.post(`/live-agent/conversations/${handoffId}/messages`, { content }, { params: { owner_id } })
    return data
  },
}
