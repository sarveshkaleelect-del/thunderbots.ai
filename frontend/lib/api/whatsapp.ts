import { apiClient } from './client'
import type {
  WhatsAppChannel,
  WhatsAppConnectionPayload,
  WhatsAppTestResult,
  WhatsAppWebhookInfo,
  WhatsAppStats,
} from '@/types/whatsapp'

export const whatsappApi = {
  get: (workflowId: string) =>
    apiClient.get<WhatsAppChannel>(`/whatsapp/channels/${workflowId}`).then(r => r.data),

  connect: (workflowId: string, payload: WhatsAppConnectionPayload) =>
    apiClient.put<WhatsAppChannel>(`/whatsapp/channels/${workflowId}`, payload).then(r => r.data),

  test: (workflowId: string, payload?: { phone_number_id?: string; access_token?: string }) =>
    apiClient
      .post<WhatsAppTestResult>(`/whatsapp/channels/${workflowId}/test`, payload || {})
      .then(r => r.data),

  enable: (workflowId: string) =>
    apiClient.post<{ is_enabled: boolean; status: string }>(`/whatsapp/channels/${workflowId}/enable`).then(r => r.data),

  disable: (workflowId: string) =>
    apiClient.post<{ is_enabled: boolean; status: string }>(`/whatsapp/channels/${workflowId}/disable`).then(r => r.data),

  reconnect: (workflowId: string) =>
    apiClient.post<{ ok: boolean; status: string; latency_ms: number }>(`/whatsapp/channels/${workflowId}/reconnect`).then(r => r.data),

  disconnect: (workflowId: string) =>
    apiClient.post<{ disconnected: boolean }>(`/whatsapp/channels/${workflowId}/disconnect`).then(r => r.data),

  webhookInfo: (workflowId: string) =>
    apiClient.get<WhatsAppWebhookInfo>(`/whatsapp/channels/${workflowId}/webhook-info`).then(r => r.data),

  stats: (workflowId: string, page = 1, pageSize = 20) =>
    apiClient
      .get<WhatsAppStats>(`/whatsapp/channels/${workflowId}/stats`, { params: { page, page_size: pageSize } })
      .then(r => r.data),
}
