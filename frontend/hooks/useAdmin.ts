// ============================================================
// ThunderBots — Admin Dashboard Hooks (NEW)
// Thin useQuery wrappers, mirroring hooks/useAnalytics.ts conventions.
// ============================================================
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { adminApi } from '@/lib/api/admin'

const STATUS_REFETCH_MS = 20_000
const OVERVIEW_REFETCH_MS = 30_000

export function useAdminOverview(autoRefresh = true) {
  return useQuery({
    queryKey: ['admin', 'overview'],
    queryFn: adminApi.overview,
    refetchInterval: autoRefresh ? OVERVIEW_REFETCH_MS : false,
    staleTime: 10_000,
  })
}

export function useAdminStatus(autoRefresh = true) {
  return useQuery({
    queryKey: ['admin', 'status'],
    queryFn: adminApi.status,
    refetchInterval: autoRefresh ? STATUS_REFETCH_MS : false,
    staleTime: 5_000,
  })
}

export function useAdminActivity(limit = 8) {
  return useQuery({
    queryKey: ['admin', 'activity', limit],
    queryFn: () => adminApi.activity(limit),
    staleTime: 15_000,
  })
}

export function useAdminUsers(search: string, page: number, pageSize = 20) {
  return useQuery({
    queryKey: ['admin', 'users', search, page, pageSize],
    queryFn: () => adminApi.users({ search, page, page_size: pageSize }),
    staleTime: 5_000,
  })
}

export function useAdminBots(search: string, page: number, pageSize = 20) {
  return useQuery({
    queryKey: ['admin', 'bots', search, page, pageSize],
    queryFn: () => adminApi.bots({ search, page, page_size: pageSize }),
    staleTime: 5_000,
  })
}

export function useSetUserStatus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, isActive }: { userId: string; isActive: boolean }) =>
      adminApi.setUserStatus(userId, isActive),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  })
}

export function useDeleteUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => adminApi.deleteUser(userId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'users'] })
      qc.invalidateQueries({ queryKey: ['admin', 'overview'] })
    },
  })
}

export function useDeleteBot() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (botId: string) => adminApi.deleteBot(botId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'bots'] })
      qc.invalidateQueries({ queryKey: ['admin', 'overview'] })
    },
  })
}

export function useIsAdmin() {
  return useQuery({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      const { authApi } = await import('@/lib/api/auth')
      return authApi.me()
    },
    staleTime: 60_000,
    retry: false,
  })
}
