// ============================================================
// ThunderBots — AI Business Advisor API Client (NEW)
// Independent, additive module on top of the Smart Shop Assistant.
// ============================================================
import { apiClient } from './client'
import type {
  AdvisorOverview, Recommendation, AdvisorPredictions, AdvisorAlert,
  ChatResponse, ReportPeriod, BusinessReport,
} from '@/types/businessAdvisor'

function downloadBlob(data: BlobPart, filename: string, mime: string) {
  const url = window.URL.createObjectURL(new Blob([data], { type: mime }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

export const businessAdvisorApi = {
  getOverview: async (shopId: string): Promise<AdvisorOverview> => {
    const { data } = await apiClient.get(`/business-advisor/shops/${shopId}/overview`)
    return data
  },

  getRecommendations: async (shopId: string): Promise<Recommendation[]> => {
    const { data } = await apiClient.get(`/business-advisor/shops/${shopId}/recommendations`)
    return data.recommendations
  },

  getPredictions: async (shopId: string): Promise<AdvisorPredictions> => {
    const { data } = await apiClient.get(`/business-advisor/shops/${shopId}/predictions`)
    return data
  },

  getAlerts: async (shopId: string): Promise<AdvisorAlert[]> => {
    const { data } = await apiClient.get(`/business-advisor/shops/${shopId}/alerts`)
    return data.alerts
  },

  chat: async (shopId: string, question: string): Promise<ChatResponse> => {
    const { data } = await apiClient.post(`/business-advisor/shops/${shopId}/chat`, { question })
    return data
  },

  getDailySummary: async (shopId: string): Promise<ChatResponse> => {
    const { data } = await apiClient.get(`/business-advisor/shops/${shopId}/daily-summary`)
    return data
  },

  getReport: async (shopId: string, period: ReportPeriod): Promise<BusinessReport> => {
    const { data } = await apiClient.get(`/business-advisor/shops/${shopId}/reports/${period}`)
    return data
  },

  exportReportPdf: async (shopId: string, period: ReportPeriod, shopName: string): Promise<void> => {
    const { data } = await apiClient.get(`/business-advisor/shops/${shopId}/reports/${period}/export/pdf`, {
      responseType: 'blob',
    })
    downloadBlob(data, `${shopName.replace(/\s+/g, '_')}_${period}_business_report.pdf`, 'application/pdf')
  },

  exportReportXlsx: async (shopId: string, period: ReportPeriod, shopName: string): Promise<void> => {
    const { data } = await apiClient.get(`/business-advisor/shops/${shopId}/reports/${period}/export/xlsx`, {
      responseType: 'blob',
    })
    downloadBlob(
      data,
      `${shopName.replace(/\s+/g, '_')}_${period}_business_report.xlsx`,
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
  },
}
