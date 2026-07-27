import { apiClient } from './client'
import type { Workflow, WorkflowListItem } from '@/types'

export const workflowsApi = {
  list: () =>
    apiClient.get<WorkflowListItem[]>('/workflows/').then(r => r.data),

  get: (id: string) =>
    apiClient.get<Workflow>(`/workflows/${id}`).then(r => r.data),

  create: (name: string, description?: string) =>
    apiClient.post<Workflow>('/workflows/', { name, description }).then(r => r.data),

  // FIX: explicit trailing slash prevents 307 redirect on some FastAPI setups
  save: (id: string, nodes: unknown[], edges: unknown[], canvas_state: unknown) =>
    apiClient.post<Workflow>(`/workflows/${id}/save`, { nodes, edges, canvas_state }).then(r => r.data),

  update: (id: string, data: {
    name?: string
    description?: string
    status?: string
    knowledge_base_id?: string | null
  }) =>
    apiClient.put<Workflow>(`/workflows/${id}`, data).then(r => r.data),

  delete: (id: string) =>
    apiClient.delete(`/workflows/${id}`),

  duplicate: (id: string) =>
    apiClient.post<Workflow>(`/workflows/${id}/duplicate`).then(r => r.data),

  /** Upload an optional image attachment for a workflow node (e.g. Multiple Choice). */
  uploadNodeMedia: (workflowId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return apiClient
      .post<{ url: string; filename: string; size: number; mime_type: string }>(
        `/workflows/${workflowId}/node-media`, form
      )
      .then(r => r.data)
  },

  getProviders: () =>
    apiClient.get('/settings/providers').then(r => r.data),
}
