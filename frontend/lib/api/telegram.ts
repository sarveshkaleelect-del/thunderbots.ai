import { apiClient } from './client'
import type {
  TelegramChannel,
  TelegramConnectionPayload,
  TelegramTestResult,
  TelegramWebhookInfo,
  TelegramStats,
  TelegramAnalytics,
} from '@/types/telegram'

export const telegramApi = {
  get: (workflowId: string) =>
    apiClient.get<TelegramChannel>(`/telegram/channels/${workflowId}`).then(r => r.data),

  connect: (workflowId: string, payload: TelegramConnectionPayload) =>
    apiClient.put<TelegramChannel>(`/telegram/channels/${workflowId}`, payload).then(r => r.data),

  test: (workflowId: string) =>
    apiClient.post<TelegramTestResult>(`/telegram/channels/${workflowId}/test`).then(r => r.data),

  enable: (workflowId: string) =>
    apiClient.post<{ is_enabled: boolean; status: string }>(`/telegram/channels/${workflowId}/enable`).then(r => r.data),

  disable: (workflowId: string) =>
    apiClient.post<{ is_enabled: boolean; status: string }>(`/telegram/channels/${workflowId}/disable`).then(r => r.data),

  reconnect: (workflowId: string) =>
    apiClient.post<{ ok: boolean; status: string; latency_ms: number }>(`/telegram/channels/${workflowId}/reconnect`).then(r => r.data),

  disconnect: (workflowId: string) =>
    apiClient.post<{ disconnected: boolean }>(`/telegram/channels/${workflowId}/disconnect`).then(r => r.data),

  webhookInfo: (workflowId: string) =>
    apiClient.get<TelegramWebhookInfo>(`/telegram/channels/${workflowId}/webhook-info`).then(r => r.data),

  stats: (workflowId: string, page = 1, pageSize = 20) =>
    apiClient
      .get<TelegramStats>(`/telegram/channels/${workflowId}/stats`, { params: { page, page_size: pageSize } })
      .then(r => r.data),

  // NEW (Part 3): Active Conversations / AI Resolved / Human Handoff /
  // Replies / Failed Deliveries — backed by app/api/v1/telegram.py's new
  // GET /telegram/analytics/{workflow_id} route.
  analytics: (workflowId: string) =>
    apiClient.get<TelegramAnalytics>(`/telegram/analytics/${workflowId}`).then(r => r.data),
}
