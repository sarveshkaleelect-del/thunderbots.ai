// ============================================================
// ThunderBots — Analytics Dashboard Hooks (NEW)
// Thin, memoized React Query wrappers. Keeping each metric in its own query
// key means a chart re-fetching (e.g. on interval) never re-renders unrelated
// cards — React Query only notifies subscribers of the exact key that changed,
// and each component only subscribes to the slice it renders.
// ============================================================
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { analyticsApi } from '@/lib/api/analytics'
import type { ChartMetric, ConversationFilters } from '@/types/analytics'

export interface DateRange {
  key: string
  start?: string
  end?: string
}

const REALTIME_REFETCH_MS = 15_000
const OVERVIEW_REFETCH_MS = 30_000

function rangeParams(range: DateRange) {
  return { range: range.key, start: range.start, end: range.end }
}

export function useAnalyticsOverview(range: DateRange, autoRefresh = true) {
  const params = useMemo(() => rangeParams(range), [range.key, range.start, range.end])
  return useQuery({
    queryKey: ['analytics', 'overview', params],
    queryFn: () => analyticsApi.overview(params),
    refetchInterval: autoRefresh ? OVERVIEW_REFETCH_MS : false,
    staleTime: 10_000,
  })
}

export function useAnalyticsChart(metric: ChartMetric, range: DateRange, autoRefresh = true) {
  const params = useMemo(() => rangeParams(range), [range.key, range.start, range.end])
  return useQuery({
    queryKey: ['analytics', 'chart', metric, params],
    queryFn: () => analyticsApi.chart(metric, params),
    refetchInterval: autoRefresh ? OVERVIEW_REFETCH_MS : false,
    staleTime: 10_000,
  })
}

export function useTrafficSources(range: DateRange, autoRefresh = true) {
  const params = useMemo(() => rangeParams(range), [range.key, range.start, range.end])
  return useQuery({
    queryKey: ['analytics', 'traffic-sources', params],
    queryFn: () => analyticsApi.trafficSources(params),
    refetchInterval: autoRefresh ? OVERVIEW_REFETCH_MS : false,
    staleTime: 10_000,
  })
}

export function useTopBots(range: DateRange, limit = 10) {
  const params = useMemo(() => ({ ...rangeParams(range), limit }), [range.key, range.start, range.end, limit])
  return useQuery({
    queryKey: ['analytics', 'top-bots', params],
    queryFn: () => analyticsApi.topBots(params),
    staleTime: 15_000,
  })
}

export function useTopDocuments(limit = 10) {
  return useQuery({
    queryKey: ['analytics', 'top-documents', limit],
    queryFn: () => analyticsApi.topDocuments(limit),
    staleTime: 30_000,
  })
}

export function useKBUsage(range: DateRange) {
  const params = useMemo(() => rangeParams(range), [range.key, range.start, range.end])
  return useQuery({
    queryKey: ['analytics', 'kb-usage', params],
    queryFn: () => analyticsApi.kbUsage(params),
    staleTime: 15_000,
  })
}

export function useProviderUsage(range: DateRange) {
  const params = useMemo(() => rangeParams(range), [range.key, range.start, range.end])
  return useQuery({
    queryKey: ['analytics', 'provider-usage', params],
    queryFn: () => analyticsApi.providerUsage(params),
    staleTime: 15_000,
  })
}

export function usePerformance(range: DateRange, autoRefresh = true) {
  const params = useMemo(() => rangeParams(range), [range.key, range.start, range.end])
  return useQuery({
    queryKey: ['analytics', 'performance', params],
    queryFn: () => analyticsApi.performance(params),
    refetchInterval: autoRefresh ? OVERVIEW_REFETCH_MS : false,
    staleTime: 10_000,
  })
}

export function useRealtime(enabled = true) {
  return useQuery({
    queryKey: ['analytics', 'realtime'],
    queryFn: () => analyticsApi.realtime(),
    refetchInterval: enabled ? REALTIME_REFETCH_MS : false,
    staleTime: 5_000,
  })
}

export function useConversations(filters: ConversationFilters) {
  const key = useMemo(() => ({ ...filters }), [
    filters.search, filters.workflow_id, filters.source, filters.status,
    filters.start, filters.end, filters.page, filters.page_size,
  ])
  return useQuery({
    queryKey: ['analytics', 'conversations', key],
    queryFn: () => analyticsApi.conversations(key),
    staleTime: 10_000,
    placeholderData: (prev) => prev,
  })
}

export function useConversationDetail(id: string | null) {
  return useQuery({
    queryKey: ['analytics', 'conversation-detail', id],
    queryFn: () => analyticsApi.conversationDetail(id as string),
    enabled: !!id,
  })
}
