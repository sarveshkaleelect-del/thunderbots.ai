// ============================================================
// ThunderBots — Audit Log Hooks (NEW — v58)
// Thin useQuery wrappers, mirroring hooks/useAdmin.ts conventions.
// ============================================================
import { useQuery } from '@tanstack/react-query'
import { auditLogApi } from '@/lib/api/audit'
import type { AuditLogFilters } from '@/types/admin'

export function useAuditLogs(filters: AuditLogFilters) {
  return useQuery({
    queryKey: ['admin', 'audit-logs', filters],
    queryFn: () => auditLogApi.list(filters),
    staleTime: 5_000,
  })
}

export function useAuditLogActions() {
  return useQuery({
    queryKey: ['admin', 'audit-logs', 'actions'],
    queryFn: auditLogApi.actions,
    staleTime: 60_000,
  })
}

export function useAuditLogResourceTypes() {
  return useQuery({
    queryKey: ['admin', 'audit-logs', 'resource-types'],
    queryFn: auditLogApi.resourceTypes,
    staleTime: 60_000,
  })
}
