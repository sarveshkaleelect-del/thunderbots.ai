// ============================================================
// ThunderBots — AI Supervisor Dashboard Hooks (NEW)
// Thin useQuery wrappers, mirroring hooks/useAnalytics.ts. Live updates
// reuse the existing live-agent dashboard WebSocket (useLiveAgentDashboardSocket,
// hooks/useLiveAgent.ts) for handoff-related changes, plus a short poll
// interval so purely-AI conversations (which never touch that socket)
// still refresh — no new WebSocket channel or Runtime change required.
// ============================================================
import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { aiSupervisorApi } from '@/lib/api/aiSupervisor'
import type { SupervisorFilters, SupervisorNotification, Priority } from '@/types/aiSupervisor'
import { useLiveAgentDashboardSocket } from './useLiveAgent'

const POLL_MS = 8_000

export function useSupervisorStats(range: { start?: string; end?: string } = {}, live = true) {
  return useQuery({
    queryKey: ['ai-supervisor', 'stats', range],
    queryFn: () => aiSupervisorApi.stats(range),
    refetchInterval: live ? POLL_MS : false,
    staleTime: 4_000,
  })
}

export function useSupervisorConversations(filters: SupervisorFilters, live = true) {
  const key = useMemo(() => ({ ...filters }), [
    filters.state, filters.mode, filters.channel, filters.search,
    filters.start, filters.end, filters.priority, filters.tag,
    filters.pinned_only, filters.assigned_agent_id, filters.supervisor_closed,
    filters.page, filters.page_size,
  ])
  return useQuery({
    queryKey: ['ai-supervisor', 'conversations', key],
    queryFn: () => aiSupervisorApi.conversations(key),
    refetchInterval: live ? POLL_MS : false,
    staleTime: 4_000,
    placeholderData: (prev) => prev,
  })
}

export function useSupervisorConversationDetail(id: string | null, live = true) {
  return useQuery({
    queryKey: ['ai-supervisor', 'conversation-detail', id],
    queryFn: () => aiSupervisorApi.conversationDetail(id as string),
    enabled: !!id,
    refetchInterval: live && id ? POLL_MS : false,
    staleTime: 3_000,
  })
}

/** Subscribes to the existing Live Agent dashboard socket so a human
 * takeover / return-to-AI / new agent message — and, in the final phase,
 * an assign/reassign, close/reopen, tag/priority/pin change, or activity
 * log entry — shows up immediately instead of waiting for the next poll.
 * Falls back gracefully to the poll above if the socket can't connect
 * (same behavior as the Live Agent page). */
export function useSupervisorLiveUpdates(enabled = true) {
  const qc = useQueryClient()
  useLiveAgentDashboardSocket(undefined, (evt) => {
    if (!enabled) return
    if ([
      'handoff_waiting', 'handoff_updated', 'handoff_message',
      'supervisor_note_added', 'supervisor_review_updated',
      'supervisor_activity', 'supervisor_conversation_closed',
      'supervisor_conversation_reopened',
    ].includes(evt.type)) {
      qc.invalidateQueries({ queryKey: ['ai-supervisor'] })
    }
  })
}

/** Real-time notification toasts: New conversation, Human takeover, High
 * priority, AI paused, Conversation closed/reopened. The last five kinds
 * are pushed straight from the backend as `type: "supervisor_notification"`
 * over the same dashboard socket. "New conversation" is derived client-side
 * by diffing the polled/live conversation list for IDs not seen before —
 * this keeps the runtime/chat pipeline (where conversations are actually
 * created) completely untouched while still surfacing new conversations
 * within one poll/broadcast cycle. Returns a rolling list the caller can
 * render as toasts and a `dismiss` helper. */
export function useSupervisorNotifications(conversationIds: string[] | undefined, enabled = true) {
  const [notifications, setNotifications] = useState<SupervisorNotification[]>([])
  const seenIds = useRef<Set<string> | null>(null)

  const push = useCallback((n: SupervisorNotification) => {
    setNotifications((prev) => [n, ...prev].slice(0, 20))
  }, [])

  useLiveAgentDashboardSocket(undefined, (evt) => {
    if (!enabled) return
    if (evt.type === 'supervisor_notification') {
      push({
        id: `${evt.kind}-${evt.conversation_id}-${evt.created_at}`,
        type: 'supervisor_notification',
        kind: evt.kind, conversation_id: evt.conversation_id, title: evt.title,
        severity: evt.severity || 'info', detail: evt.detail || {}, created_at: evt.created_at,
      })
    }
  })

  useEffect(() => {
    if (!enabled || !conversationIds) return
    if (seenIds.current === null) {
      seenIds.current = new Set(conversationIds)
      return
    }
    const fresh = conversationIds.filter((id) => !seenIds.current!.has(id))
    fresh.forEach((id) => {
      seenIds.current!.add(id)
      push({
        id: `new_conversation-${id}-${Date.now()}`,
        type: 'supervisor_notification', kind: 'new_conversation', conversation_id: id,
        title: 'New conversation started', severity: 'info', detail: {},
        created_at: new Date().toISOString(),
      })
    })
  }, [conversationIds, enabled, push])

  const dismiss = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id))
  }, [])
  const clear = useCallback(() => setNotifications([]), [])

  return { notifications, dismiss, clear }
}

export function useAssignableAgents(live = true) {
  return useQuery({
    queryKey: ['ai-supervisor', 'agents'],
    queryFn: () => aiSupervisorApi.agents(),
    refetchInterval: live ? POLL_MS * 2 : false,
    staleTime: 10_000,
  })
}

export function useTeamActivity(limit = 30, live = true) {
  return useQuery({
    queryKey: ['ai-supervisor', 'team-activity', limit],
    queryFn: () => aiSupervisorApi.teamActivity(limit),
    refetchInterval: live ? POLL_MS : false,
    staleTime: 4_000,
  })
}

export function useSupervisorActivity(conversationId: string | null, live = true) {
  return useQuery({
    queryKey: ['ai-supervisor', 'activity', conversationId],
    queryFn: () => aiSupervisorApi.activity(conversationId as string),
    enabled: !!conversationId,
    refetchInterval: live && conversationId ? POLL_MS : false,
    staleTime: 3_000,
  })
}

/** Interaction-control mutations for the conversation detail view — pause/
 * resume AI, take over/return to AI, send a manual message, add an internal
 * note, and mark a reply Correct/Incorrect. Every mutation invalidates the
 * detail + list + stats queries so the UI reflects the change immediately,
 * on top of (not instead of) the live-update socket above. */
export function useSupervisorActions(conversationId: string | null) {
  const qc = useQueryClient()
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['ai-supervisor'] })
  }

  const pause = useMutation({
    mutationFn: () => aiSupervisorApi.pause(conversationId as string),
    onSuccess: invalidate,
  })
  const resume = useMutation({
    mutationFn: () => aiSupervisorApi.resume(conversationId as string),
    onSuccess: invalidate,
  })
  const takeOver = useMutation({
    mutationFn: () => aiSupervisorApi.takeOver(conversationId as string),
    onSuccess: invalidate,
  })
  const returnToAi = useMutation({
    mutationFn: () => aiSupervisorApi.returnToAi(conversationId as string),
    onSuccess: invalidate,
  })
  const sendMessage = useMutation({
    mutationFn: (content: string) => aiSupervisorApi.sendMessage(conversationId as string, content),
    onSuccess: invalidate,
  })
  const addNote = useMutation({
    mutationFn: (content: string) => aiSupervisorApi.addNote(conversationId as string, content),
    onSuccess: invalidate,
  })
  const reviewMessage = useMutation({
    mutationFn: ({ messageId, verdict }: { messageId: string; verdict: 'correct' | 'incorrect' }) =>
      aiSupervisorApi.reviewMessage(messageId, verdict),
    onSuccess: invalidate,
  })

  // ── Final phase (NEW) ────────────────────────────────────────────────
  const assign = useMutation({
    mutationFn: (agentId: string) => aiSupervisorApi.assign(conversationId as string, agentId),
    onSuccess: invalidate,
  })
  const close = useMutation({
    mutationFn: () => aiSupervisorApi.close(conversationId as string),
    onSuccess: invalidate,
  })
  const reopen = useMutation({
    mutationFn: () => aiSupervisorApi.reopen(conversationId as string),
    onSuccess: invalidate,
  })
  const setPriority = useMutation({
    mutationFn: (priority: Priority) => aiSupervisorApi.setPriority(conversationId as string, priority),
    onSuccess: invalidate,
  })
  const addTag = useMutation({
    mutationFn: (tag: string) => aiSupervisorApi.addTag(conversationId as string, tag),
    onSuccess: invalidate,
  })
  const removeTag = useMutation({
    mutationFn: (tag: string) => aiSupervisorApi.removeTag(conversationId as string, tag),
    onSuccess: invalidate,
  })
  const setPinned = useMutation({
    mutationFn: (pinned: boolean) => aiSupervisorApi.setPinned(conversationId as string, pinned),
    onSuccess: invalidate,
  })
  const exportConversation = useMutation({
    mutationFn: (format: 'json' | 'html' | 'pdf' = 'json') => aiSupervisorApi.exportConversation(conversationId as string, format),
  })

  return {
    pause, resume, takeOver, returnToAi, sendMessage, addNote, reviewMessage,
    assign, close, reopen, setPriority, addTag, removeTag, setPinned, exportConversation,
  }
}

/** Bulk actions across a selected set of conversation IDs (checkboxes in
 * the table) — close, assign, add a tag, or export. */
export function useSupervisorBulkActions() {
  const qc = useQueryClient()
  const invalidate = () => qc.invalidateQueries({ queryKey: ['ai-supervisor'] })

  const bulkClose = useMutation({
    mutationFn: (conversationIds: string[]) => aiSupervisorApi.bulkClose(conversationIds),
    onSuccess: invalidate,
  })
  const bulkAssign = useMutation({
    mutationFn: ({ conversationIds, agentId }: { conversationIds: string[]; agentId: string }) =>
      aiSupervisorApi.bulkAssign(conversationIds, agentId),
    onSuccess: invalidate,
  })
  const bulkTag = useMutation({
    mutationFn: ({ conversationIds, tag }: { conversationIds: string[]; tag: string }) =>
      aiSupervisorApi.bulkTag(conversationIds, tag),
    onSuccess: invalidate,
  })
  const bulkExport = useMutation({
    mutationFn: (conversationIds: string[]) => aiSupervisorApi.bulkExport(conversationIds),
  })

  return { bulkClose, bulkAssign, bulkTag, bulkExport }
}
