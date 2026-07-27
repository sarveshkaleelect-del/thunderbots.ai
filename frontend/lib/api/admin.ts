// ============================================================
// ThunderBots — Admin Dashboard API Client (NEW)
// ============================================================
import { apiClient } from './client'
import type {
  AdminOverview, AdminPlatformStatus, AdminUserList, AdminBotList, AdminActivity,
} from '@/types/admin'

export const adminApi = {
  overview: async (): Promise<AdminOverview> => {
    const { data } = await apiClient.get('/admin/overview')
    return data
  },

  status: async (): Promise<AdminPlatformStatus> => {
    const { data } = await apiClient.get('/admin/status')
    return data
  },

  activity: async (limit = 8): Promise<AdminActivity> => {
    const { data } = await apiClient.get('/admin/activity', { params: { limit } })
    return data
  },

  users: async (params: { search?: string; page?: number; page_size?: number } = {}): Promise<AdminUserList> => {
    const { data } = await apiClient.get('/admin/users', { params })
    return data
  },

  setUserStatus: async (userId: string, is_active: boolean) => {
    const { data } = await apiClient.patch(`/admin/users/${userId}/status`, null, { params: { is_active } })
    return data
  },

  deleteUser: async (userId: string) => {
    await apiClient.delete(`/admin/users/${userId}`)
  },

  bots: async (params: { search?: string; page?: number; page_size?: number } = {}): Promise<AdminBotList> => {
    const { data } = await apiClient.get('/admin/bots', { params })
    return data
  },

  deleteBot: async (botId: string) => {
    await apiClient.delete(`/admin/bots/${botId}`)
  },
}
