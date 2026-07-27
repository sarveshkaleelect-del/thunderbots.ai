// ============================================================
// ThunderBots — Live Agent Hooks (NEW)
// Thin useQuery/useMutation wrappers, mirroring hooks/useAuditLog.ts.
// ============================================================
import { useEffect, useRef, useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { liveAgentApi, ConversationFilters, AgentStatus } from '@/lib/api/liveAgent'
import { WS_URL } from '@/lib/api/client'

export function useAgents(owner_id?: string) {
  return useQuery({
    queryKey: ['live-agent', 'agents', owner_id],
    queryFn: () => liveAgentApi.getAgents(owner_id),
    staleTime: 10_000,
  })
}

export function useUpdateMyStatus(owner_id?: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (status: AgentStatus) => liveAgentApi.updateMyStatus(status, owner_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['live-agent', 'agents'] }),
  })
}

export function useDashboardStats(owner_id?: string) {
  return useQuery({
    queryKey: ['live-agent', 'stats', owner_id],
    queryFn: () => liveAgentApi.getDashboardStats(owner_id),
    staleTime: 5_000,
    refetchInterval: 15_000,
  })
}

export function useConversations(filters: ConversationFilters) {
  return useQuery({
    queryKey: ['live-agent', 'conversations', filters],
    queryFn: () => liveAgentApi.getConversations(filters),
    staleTime: 5_000,
  })
}

export function useConversationDetail(handoffId: string | null, owner_id?: string) {
  return useQuery({
    queryKey: ['live-agent', 'conversation', handoffId, owner_id],
    queryFn: () => liveAgentApi.getConversation(handoffId as string, owner_id),
    enabled: !!handoffId,
    staleTime: 2_000,
  })
}

export function useHandoffActions(owner_id?: string) {
  const qc = useQueryClient()
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['live-agent'] })
  }
  const takeOver = useMutation({
    mutationFn: (handoffId: string) => liveAgentApi.takeOver(handoffId, owner_id),
    onSuccess: invalidate,
  })
  const returnToAi = useMutation({
    mutationFn: (handoffId: string) => liveAgentApi.returnToAi(handoffId, owner_id),
    onSuccess: invalidate,
  })
  const close = useMutation({
    mutationFn: (handoffId: string) => liveAgentApi.close(handoffId, owner_id),
    onSuccess: invalidate,
  })
  const sendMessage = useMutation({
    mutationFn: ({ handoffId, content }: { handoffId: string; content: string }) =>
      liveAgentApi.sendMessage(handoffId, content, owner_id),
    onSuccess: invalidate,
  })
  return { takeOver, returnToAi, close, sendMessage }
}

/** Real-time dashboard events (new waiting chats, assignment changes, new
 * messages) — falls back gracefully to the 15s poll in useDashboardStats/
 * useConversations if the socket can't connect. */
export function useLiveAgentDashboardSocket(owner_id: string | undefined, onEvent: (evt: any) => void) {
  const wsRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  const connect = useCallback(() => {
    if (typeof window === 'undefined') return
    const token = localStorage.getItem('tb_token')
    if (!token) return
    const params = new URLSearchParams({ token, ...(owner_id ? { owner_id } : {}) })
    const ws = new WebSocket(`${WS_URL}/ws/agent-dashboard?${params.toString()}`)
    wsRef.current = ws
    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type !== 'connected') onEventRef.current(data)
      } catch {
        // ignore malformed frames
      }
    }
  }, [owner_id])

  useEffect(() => {
    connect()
    return () => wsRef.current?.close()
  }, [connect])

  return { connected }
}
