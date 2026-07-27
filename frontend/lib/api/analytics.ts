// ============================================================
// ThunderBots — Analytics API Client (NEW)
// ============================================================
import { apiClient } from './client'
import type {
  AnalyticsOverview, TimeseriesPoint, ChartMetric, TrafficSource, TopBot, TopDocument,
  KBUsage, ProviderUsage, PerformanceStats, RealtimeStats, ConversationListResponse,
  ConversationDetail, ConversationFilters,
} from '@/types/analytics'

interface RangeParams {
  range?: string
  start?: string
  end?: string
}

export const analyticsApi = {
  overview: async (params: RangeParams = {}): Promise<AnalyticsOverview> => {
    const { data } = await apiClient.get('/analytics/overview', { params })
    return data
  },

  chart: async (metric: ChartMetric, params: RangeParams = {}): Promise<TimeseriesPoint[]> => {
    const { data } = await apiClient.get(`/analytics/charts/${metric}`, { params })
    return data.series
  },

  trafficSources: async (params: RangeParams = {}): Promise<TrafficSource[]> => {
    const { data } = await apiClient.get('/analytics/traffic-sources', { params })
    return data.sources
  },

  topBots: async (params: RangeParams & { limit?: number } = {}): Promise<TopBot[]> => {
    const { data } = await apiClient.get('/analytics/top-bots', { params })
    return data.bots
  },

  topDocuments: async (limit = 10): Promise<TopDocument[]> => {
    const { data } = await apiClient.get('/analytics/top-documents', { params: { limit } })
    return data.documents
  },

  kbUsage: async (params: RangeParams = {}): Promise<KBUsage> => {
    const { data } = await apiClient.get('/analytics/kb-usage', { params })
    return data
  },

  providerUsage: async (params: RangeParams = {}): Promise<ProviderUsage[]> => {
    const { data } = await apiClient.get('/analytics/provider-usage', { params })
    return data.providers
  },

  performance: async (params: RangeParams = {}): Promise<PerformanceStats> => {
    const { data } = await apiClient.get('/analytics/performance', { params })
    return data
  },

  realtime: async (): Promise<RealtimeStats> => {
    const { data } = await apiClient.get('/analytics/realtime')
    return data
  },

  conversations: async (filters: ConversationFilters = {}): Promise<ConversationListResponse> => {
    const { data } = await apiClient.get('/analytics/conversations', { params: filters })
    return data
  },

  conversationDetail: async (id: string): Promise<ConversationDetail> => {
    const { data } = await apiClient.get(`/analytics/conversations/${id}`)
    return data
  },

  exportCsvUrl: (filters: ConversationFilters = {}): string => {
    const params = new URLSearchParams()
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') params.set(k, String(v))
    })
    const base = apiClient.defaults.baseURL || ''
    return `${base}/analytics/conversations/export/csv?${params.toString()}`
  },

  exportJsonUrl: (filters: ConversationFilters = {}): string => {
    const params = new URLSearchParams()
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') params.set(k, String(v))
    })
    const base = apiClient.defaults.baseURL || ''
    return `${base}/analytics/conversations/export/json?${params.toString()}`
  },

  /** Downloads via an authenticated blob fetch (export endpoints require the
   * same Bearer token as everything else, so a plain <a href> won't carry it). */
  downloadExport: async (format: 'csv' | 'json', filters: ConversationFilters = {}): Promise<void> => {
    const { data } = await apiClient.get(`/analytics/conversations/export/${format}`, {
      params: filters,
      responseType: 'blob',
    })
    const blob = new Blob([data], { type: format === 'csv' ? 'text/csv' : 'application/json' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `conversations.${format}`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
  },
}
