import { apiClient } from './client'
import type { UserAPIKey, APIKeyCreate, UserPreferences, AIProvider } from '@/types'

export const settingsApi = {
  // API Keys
  listKeys: () =>
    apiClient.get<UserAPIKey[]>('/settings/api-keys').then(r => r.data),

  addKey: (data: APIKeyCreate) =>
    apiClient.post('/settings/api-keys', data).then(r => r.data),

  deleteKey: (id: string) =>
    apiClient.delete(`/settings/api-keys/${id}`),

  testKey: (id: string) =>
    apiClient.post<{ ok: boolean; latency_ms: number; error?: string; response?: string; models?: string[] }>(
      `/settings/api-keys/${id}/test`
    ).then(r => r.data),

  // Providers
  listProviders: () =>
    apiClient.get<AIProvider[]>('/settings/providers').then(r => r.data),

  // Preferences
  getPreferences: () =>
    apiClient.get<UserPreferences>('/settings/preferences').then(r => r.data),

  updatePreferences: (data: Partial<UserPreferences>) =>
    apiClient.patch<UserPreferences>('/settings/preferences', data).then(r => r.data),
}
