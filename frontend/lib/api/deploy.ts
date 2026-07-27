import { apiClient } from './client'
import type { Deployment, BrandingBundle } from '@/types'

export const deployApi = {
  /**
   * Get deployment status for a workflow.
   * Returns { deployed: false } when not yet published,
   * or the full Deployment object when published.
   */
  get: (workflowId: string) =>
    apiClient
      .get<Deployment & { deployed?: boolean }>(`/deploy/${workflowId}`)
      .then(r => r.data),

  publish: (workflowId: string, options?: { slug?: string; embed_config?: object }) =>
    apiClient
      .post<Deployment>(`/deploy/${workflowId}/publish`, options || {})
      .then(r => r.data),

  unpublish: (workflowId: string) =>
    apiClient
      .post<{ published: boolean; workflow_id: string }>(`/deploy/${workflowId}/unpublish`)
      .then(r => r.data),

  /** Draft branding/design/settings — used for the instant live preview, no publish needed. */
  getBranding: (workflowId: string) =>
    apiClient.get<BrandingBundle>(`/deploy/${workflowId}/branding`).then(r => r.data),

  updateBranding: (
    workflowId: string,
    payload: Partial<Pick<BrandingBundle, 'branding' | 'design' | 'chat_settings' | 'widget_config'>>
  ) =>
    apiClient.put<BrandingBundle>(`/deploy/${workflowId}/branding`, payload).then(r => r.data),

  /** Upload logo / avatar / favicon / background image / launcher icon (png, jpg, svg, webp).
   * NOTE: do not set a manual Content-Type here — axios infers 'multipart/form-data'
   * with the correct boundary for FormData bodies on its own (see client.ts). */
  uploadAsset: (workflowId: string, field: string, file: File) => {
    const form = new FormData()
    form.append('field', field)
    form.append('file', file)
    return apiClient
      .post<{ field: string; url: string }>(`/deploy/${workflowId}/assets`, form)
      .then(r => r.data)
  },

  /** Rename the deploy URL slug without breaking the existing deployment. */
  updateSlug: (workflowId: string, slug: string) =>
    apiClient.put<Deployment>(`/deploy/${workflowId}/slug`, { slug }).then(r => r.data),
}
