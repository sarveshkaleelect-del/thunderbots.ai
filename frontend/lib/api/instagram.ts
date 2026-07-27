import { apiClient } from './client'
import type {
  InstagramAccount,
  InstagramTestResult,
  InstagramReconnectResult,
  InstagramWebhookInfo,
  InstagramStats,
  InstagramLogEntry,
} from '@/types/instagram'

export const instagramApi = {
  get: (workflowId: string) =>
    apiClient.get<InstagramAccount>(`/instagram/accounts/${workflowId}`).then(r => r.data),

  list: () =>
    apiClient.get<{ accounts: InstagramAccount[] }>('/instagram/accounts').then(r => r.data.accounts),

  authorizeUrl: (workflowId: string) =>
    apiClient.get<{ authorize_url: string }>(`/instagram/oauth/authorize/${workflowId}`).then(r => r.data),

  test: (workflowId: string) =>
    apiClient.post<InstagramTestResult>(`/instagram/accounts/${workflowId}/test`).then(r => r.data),

  enable: (workflowId: string) =>
    apiClient.post<{ is_enabled: boolean; status: string }>(`/instagram/accounts/${workflowId}/enable`).then(r => r.data),

  disable: (workflowId: string) =>
    apiClient.post<{ is_enabled: boolean; status: string }>(`/instagram/accounts/${workflowId}/disable`).then(r => r.data),

  reconnect: (workflowId: string) =>
    apiClient.post<InstagramReconnectResult>(`/instagram/accounts/${workflowId}/reconnect`).then(r => r.data),

  disconnect: (workflowId: string) =>
    apiClient.post<{ disconnected: boolean }>(`/instagram/accounts/${workflowId}/disconnect`).then(r => r.data),

  webhookInfo: (workflowId: string) =>
    apiClient.get<InstagramWebhookInfo>(`/instagram/accounts/${workflowId}/webhook-info`).then(r => r.data),

  stats: (workflowId: string, page = 1, pageSize = 20) =>
    apiClient
      .get<InstagramStats>(`/instagram/accounts/${workflowId}/stats`, { params: { page, page_size: pageSize } })
      .then(r => r.data),

  logs: (workflowId: string, limit = 50) =>
    apiClient
      .get<{ logs: InstagramLogEntry[] }>(`/instagram/accounts/${workflowId}/logs`, { params: { limit } })
      .then(r => r.data.logs),
}
