// ============================================================
// ThunderBots — Audit Log API Client (NEW — v58)
// ============================================================
import { apiClient } from './client'
import type { AuditLogList, AuditLogEntry, AuditLogFilters } from '@/types/admin'

export const auditLogApi = {
  list: async (filters: AuditLogFilters = {}): Promise<AuditLogList> => {
    const { data } = await apiClient.get('/admin/audit-logs', { params: filters })
    return data
  },

  get: async (logId: string): Promise<AuditLogEntry> => {
    const { data } = await apiClient.get(`/admin/audit-logs/${logId}`)
    return data
  },

  actions: async (): Promise<string[]> => {
    const { data } = await apiClient.get('/admin/audit-logs/meta/actions')
    return data.actions
  },

  resourceTypes: async (): Promise<string[]> => {
    const { data } = await apiClient.get('/admin/audit-logs/meta/resource-types')
    return data.resource_types
  },

  // Triggers a browser download of the current filter set as CSV.
  exportCsv: async (filters: AuditLogFilters = {}): Promise<void> => {
    const { data } = await apiClient.get('/admin/audit-logs/export/csv', {
      params: filters,
      responseType: 'blob',
    })
    const url = window.URL.createObjectURL(new Blob([data], { type: 'text/csv' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `audit-log-export-${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  },
}
