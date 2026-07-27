import { apiClient } from '@/lib/api/client'
import type { MarketplaceTemplate, MarketplaceTemplateDetail, ImportedWorkflow } from './types'

export const marketplaceApi = {
  categories: () =>
    apiClient.get<string[]>('/marketplace/categories').then(r => r.data),

  templates: () =>
    apiClient.get<MarketplaceTemplate[]>('/marketplace/templates').then(r => r.data),

  templateDetail: (id: string) =>
    apiClient.get<MarketplaceTemplateDetail>(`/marketplace/templates/${id}`).then(r => r.data),

  importTemplate: (id: string) =>
    apiClient.post<ImportedWorkflow>(`/marketplace/templates/${id}/import`).then(r => r.data),
}
