'use client'
import { memo, useState, useCallback, useMemo } from 'react'
import {
  Search, Loader2, ChevronLeft, ChevronRight, X, Bot, User as UserIcon,
  AlertCircle, Headset, RotateCcw, Pause, Play, LogIn, LogOut, Send,
  ThumbsUp, ThumbsDown, StickyNote, Plus, Pin, PinOff, Tag as TagIcon,
  Download, UserPlus, Archive, ArchiveRestore, History, CheckSquare, Square,
  Flag, ChevronDown,
} from 'lucide-react'
import {
  useSupervisorConversations, useSupervisorConversationDetail, useSupervisorActions,
  useAssignableAgents, useSupervisorActivity, useSupervisorBulkActions,
} from '@/hooks/useAiSupervisor'
import type {
  SupervisorFilters, SupervisorConversationListItem, SupervisorMessage, Priority,
} from '@/types/aiSupervisor'
import { cn } from '@/lib/utils/cn'

const CHANNEL_OPTIONS = [
  { value: '', label: 'All channels' },
  { value: 'website', label: 'Website' },
  { value: 'embed_widget', label: 'Embed Widget' },
  { value: 'direct', label: 'Direct' },
  { value: 'api', label: 'API' },
  { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'instagram', label: 'Instagram' },
]

const STATE_OPTIONS = [
  { value: '', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'closed', label: 'Closed' },
]

const MODE_OPTIONS = [
  { value: '', label: 'Human + AI' },
  { value: 'human', label: 'Human takeover' },
  { value: 'ai_only', label: 'AI only' },
]

const PRIORITY_OPTIONS: { value: Priority; label: string }[] = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
]

const PRIORITY_STYLES: Record<Priority, string> = {
  low: 'bg-white/5 text-white/40 border-white/10',
  medium: 'bg-sky-500/10 text-sky-400 border-sky-500/20',
  high: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  critical: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
}

function fmtDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function confidenceLabel(v: number | null) {
  if (v == null) return null
  return `${Math.round(v * 100)}%`
}

function HandoffBadge({ item }: { item: SupervisorConversationListItem }) {
  if (item.is_human_takeover) {
    return (
      <span className="flex items-center gap-1 text-[9px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
        <Headset size={9} /> Human
      </span>
    )
  }
  if (item.is_paused) {
    return (
      <span className="flex items-center gap-1 text-[9px] px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20">
        <Pause size={9} /> Paused
      </span>
    )
  }
  return (
    <span className="flex items-center gap-1 text-[9px] px-2 py-0.5 rounded-full bg-[#6366f1]/10 text-[#a5b4fc] border border-[#6366f1]/20">
      <Bot size={9} /> AI only
    </span>
  )
}

function PriorityBadge({ priority, onClick }: { priority: Priority; onClick?: (e: React.MouseEvent) => void }) {
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={cn(
        'flex items-center gap-1 text-[9px] px-2 py-0.5 rounded-full border uppercase font-medium transition',
        PRIORITY_STYLES[priority], onClick && 'hover:brightness-125 cursor-pointer'
      )}
    >
      <Flag size={8} /> {priority}
    </button>
  )
}

function PinToggle({ pinned, onToggle, pending }: { pinned: boolean; onToggle: () => void; pending?: boolean }) {
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onToggle() }}
      disabled={pending}
      title={pinned ? 'Unpin conversation' : 'Pin conversation'}
      className={cn(
        'p-1 rounded-md transition disabled:opacity-40',
        pinned ? 'text-amber-400 bg-amber-500/10' : 'text-white/20 hover:text-amber-400 hover:bg-amber-500/10'
      )}
    >
      {pinned ? <Pin size={11} className="fill-current" /> : <Pin size={11} />}
    </button>
  )
}

function TagChips({ tags, max = 2 }: { tags: string[]; max?: number }) {
  if (!tags?.length) return <span className="text-white/15 text-[10px]">—</span>
  const shown = tags.slice(0, max)
  const rest = tags.length - shown.length
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {shown.map(t => (
        <span key={t} className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-white/40 flex items-center gap-0.5">
          <TagIcon size={7} /> {t}
        </span>
      ))}
      {rest > 0 && <span className="text-[9px] text-white/25">+{rest}</span>}
    </div>
  )
}

function ActivityHistoryList({ conversationId }: { conversationId: string }) {
  const { data, isLoading } = useSupervisorActivity(conversationId)
  const items = data?.items || []
  return (
    <div className="space-y-1.5">
      {isLoading && (
        <div className="flex items-center justify-center py-6">
          <Loader2 size={14} className="text-[#6366f1] animate-spin" />
        </div>
      )}
      {!isLoading && items.length === 0 && (
        <p className="text-[10px] text-white/20 italic">No supervisor activity yet for this conversation.</p>
      )}
      {items.map(a => (
        <div key={a.id} className="text-[10px] text-white/40 flex items-start gap-1.5">
          <span className="text-white/20 whitespace-nowrap">{fmtDate(a.created_at)}</span>
          <span className="text-white/60 capitalize">{a.event_type.replace(/_/g, ' ')}</span>
          {a.actor_name && <span className="text-white/25">by {a.actor_name}</span>}
        </div>
      ))}
    </div>
  )
}
function RowPinButton({ conversationId, pinned }: { conversationId: string; pinned: boolean }) {
  const { setPinned } = useSupervisorActions(conversationId)
  return (
    <PinToggle pinned={pinned} pending={setPinned.isPending} onToggle={() => setPinned.mutate(!pinned)} />
  )
}

function ReviewButtons({ id, review, onReview, pending }: {
  id: string
  review: SupervisorMessage['review']
  onReview: (messageId: string, verdict: 'correct' | 'incorrect') => void
  pending: boolean
}) {
  return (
    <div className="flex items-center gap-1">
      <button
        disabled={pending}
        onClick={() => onReview(id, 'correct')}
        title={review?.verdict === 'correct' ? `Marked correct${review.reviewer_name ? ' by ' + review.reviewer_name : ''}` : 'Mark correct'}
        className={cn(
          'p-1 rounded-md transition disabled:opacity-40',
          review?.verdict === 'correct' ? 'bg-emerald-500/20 text-emerald-400' : 'text-white/20 hover:text-emerald-400 hover:bg-emerald-500/10'
        )}
      >
        <ThumbsUp size={10} />
      </button>
      <button
        disabled={pending}
        onClick={() => onReview(id, 'incorrect')}
        title={review?.verdict === 'incorrect' ? `Marked incorrect${review.reviewer_name ? ' by ' + review.reviewer_name : ''}` : 'Mark incorrect'}
        className={cn(
          'p-1 rounded-md transition disabled:opacity-40',
          review?.verdict === 'incorrect' ? 'bg-rose-500/20 text-rose-400' : 'text-white/20 hover:text-rose-400 hover:bg-rose-500/10'
        )}
      >
        <ThumbsDown size={10} />
      </button>
    </div>
  )
}

function SupervisorConversationDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const { data, isLoading } = useSupervisorConversationDetail(id)
  const {
    pause, resume, takeOver, returnToAi, sendMessage, addNote, reviewMessage,
    assign, close, reopen, setPriority, addTag, removeTag, setPinned, exportConversation,
  } = useSupervisorActions(id)
  const { data: agentsData } = useAssignableAgents()
  const [notesOpen, setNotesOpen] = useState(false)
  const [activityOpen, setActivityOpen] = useState(false)
  const [assignOpen, setAssignOpen] = useState(false)
  const [tagDraft, setTagDraft] = useState('')
  const [noteDraft, setNoteDraft] = useState('')
  const [messageDraft, setMessageDraft] = useState('')

  const isPaused = !!data?.is_paused
  const isHuman = !!data?.is_human_takeover
  const isClosed = data?.status === 'ended'
  const isSupervisorClosed = !!data?.is_closed
  const agents = agentsData?.items || []

  const handleSend = () => {
    const content = messageDraft.trim()
    if (!content) return
    sendMessage.mutate(content, { onSuccess: () => setMessageDraft('') })
  }

  const handleAddNote = () => {
    const content = noteDraft.trim()
    if (!content) return
    addNote.mutate(content, { onSuccess: () => setNoteDraft('') })
  }

  const handleAddTag = () => {
    const tag = tagDraft.trim()
    if (!tag) return
    addTag.mutate(tag, { onSuccess: () => setTagDraft('') })
  }

  const handleExport = (format: 'json' | 'html') => {
    exportConversation.mutate(format, {
      onSuccess: (payload) => {
        if (typeof window === 'undefined') return
        if (format === 'json') {
          const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = `conversation-${data?.session_id || id}.json`
          a.click()
          URL.revokeObjectURL(url)
        } else {
          const win = window.open('', '_blank')
          if (win) { win.document.write(payload as string); win.document.close() }
        }
      },
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg h-full bg-[#0b0b0b] border-l border-[#1a1a1a] flex flex-col animate-slide-up">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#1a1a1a] flex-shrink-0">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              {data && (
                <PinToggle pinned={!!data.is_pinned} pending={setPinned.isPending} onToggle={() => setPinned.mutate(!data.is_pinned)} />
              )}
              <p className="text-sm font-semibold text-white/90 truncate">
                {data?.customer_display || 'Conversation'}
              </p>
              {data && <PriorityBadge priority={data.priority} />}
            </div>
            <p className="text-[10px] text-white/25 truncate mt-0.5">
              {data?.workflow_name} · {data?.session_id}
              {data?.assigned_agent_name && <> · with {data.assigned_agent_name}</>}
              {isSupervisorClosed && <span className="text-rose-400/70"> · Closed by supervisor</span>}
            </p>
            {data && <div className="mt-1.5"><TagChips tags={data.tags} max={4} /></div>}
          </div>
          <button onClick={onClose} className="p-1.5 text-white/30 hover:text-white/70 rounded-lg hover:bg-white/5 flex-shrink-0 ml-2">
            <X size={16} />
          </button>
        </div>

        {/* Assign / priority / tag / close-reopen (NEW) */}
        {data && (
          <div className="flex items-center gap-1.5 px-5 py-2.5 border-b border-[#1a1a1a] flex-shrink-0 flex-wrap relative">
            <div className="relative">
              <button
                onClick={() => setAssignOpen(o => !o)}
                disabled={assign.isPending}
                className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1.5 rounded-lg bg-white/5 text-white/60 border border-white/10 hover:bg-white/10 transition disabled:opacity-40"
              >
                <UserPlus size={10} /> {data.assigned_agent_name ? 'Reassign' : 'Assign'} <ChevronDown size={9} />
              </button>
              {assignOpen && (
                <div className="absolute top-full left-0 mt-1 w-48 bg-[#161616] border border-[#2a2a2a] rounded-xl shadow-xl z-10 py-1 max-h-56 overflow-y-auto">
                  {agents.length === 0 && (
                    <p className="text-[10px] text-white/25 px-3 py-2">No team members yet</p>
                  )}
                  {agents.map(a => (
                    <button
                      key={a.user_id}
                      onClick={() => { assign.mutate(a.user_id); setAssignOpen(false) }}
                      className="w-full flex items-center justify-between text-left text-[11px] text-white/70 hover:bg-white/5 px-3 py-1.5"
                    >
                      <span className="truncate">{a.name}</span>
                      <span className="text-[9px] text-white/25 ml-2 flex-shrink-0">{a.active_chat_count} active</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <select
              value={data.priority}
              onChange={e => setPriority.mutate(e.target.value as Priority)}
              disabled={setPriority.isPending}
              className="bg-white/5 text-[10px] text-white/60 border border-white/10 rounded-lg px-2 py-1.5 outline-none focus:border-[#6366f1]/50 disabled:opacity-40"
            >
              {PRIORITY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label} priority</option>)}
            </select>

            {isSupervisorClosed ? (
              <button
                disabled={reopen.isPending}
                onClick={() => reopen.mutate()}
                className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition disabled:opacity-40"
              >
                <ArchiveRestore size={10} /> Reopen
              </button>
            ) : (
              <button
                disabled={close.isPending}
                onClick={() => close.mutate()}
                className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1.5 rounded-lg bg-white/5 text-white/50 border border-white/10 hover:bg-rose-500/10 hover:text-rose-400 hover:border-rose-500/20 transition disabled:opacity-40"
              >
                <Archive size={10} /> Close
              </button>
            )}

            <div className="relative group ml-auto">
              <button
                disabled={exportConversation.isPending}
                className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1.5 rounded-lg bg-white/5 text-white/40 border border-white/10 hover:bg-white/10 transition disabled:opacity-40"
              >
                <Download size={10} /> Export
              </button>
              <div className="absolute top-full right-0 mt-1 w-32 bg-[#161616] border border-[#2a2a2a] rounded-xl shadow-xl z-10 py-1 hidden group-hover:block">
                <button onClick={() => handleExport('json')} className="w-full text-left text-[11px] text-white/70 hover:bg-white/5 px-3 py-1.5">JSON</button>
                <button onClick={() => handleExport('html')} className="w-full text-left text-[11px] text-white/70 hover:bg-white/5 px-3 py-1.5">PDF (print)</button>
              </div>
            </div>
          </div>
        )}

        {/* Tag editor (NEW) */}
        {data && (
          <div className="flex items-center gap-1.5 px-5 py-2 border-b border-[#1a1a1a] flex-shrink-0 flex-wrap">
            {data.tags.map(t => (
              <span key={t} className="flex items-center gap-1 text-[10px] px-2 py-1 rounded-full bg-white/5 text-white/50 border border-white/10">
                <TagIcon size={9} /> {t}
                <button onClick={() => removeTag.mutate(t)} className="text-white/25 hover:text-rose-400 ml-0.5">
                  <X size={9} />
                </button>
              </span>
            ))}
            <div className="flex items-center gap-1">
              <input
                value={tagDraft}
                onChange={e => setTagDraft(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleAddTag()}
                placeholder="Add tag…"
                className="w-24 bg-[#1a1a1a] text-[10px] text-white border border-[#2a2a2a] rounded-lg px-2 py-1 outline-none focus:border-[#6366f1]/50 placeholder-white/20"
              />
              <button
                disabled={addTag.isPending || !tagDraft.trim()}
                onClick={handleAddTag}
                className="p-1 rounded-lg bg-white/5 text-white/40 hover:bg-white/10 disabled:opacity-30 transition"
              >
                <Plus size={11} />
              </button>
            </div>
          </div>
        )}

        {/* Interaction controls (NEW) */}
        {data && (
          <div className="flex items-center gap-1.5 px-5 py-2.5 border-b border-[#1a1a1a] flex-shrink-0 flex-wrap">
            {!isHuman && (
              isPaused ? (
                <button
                  disabled={resume.isPending || isClosed || isSupervisorClosed}
                  onClick={() => resume.mutate()}
                  className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition disabled:opacity-40"
                >
                  <Play size={10} /> Resume AI
                </button>
              ) : (
                <button
                  disabled={pause.isPending || isClosed || isSupervisorClosed}
                  onClick={() => pause.mutate()}
                  className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1.5 rounded-lg bg-white/5 text-white/60 border border-white/10 hover:bg-white/10 transition disabled:opacity-40"
                >
                  <Pause size={10} /> Pause AI
                </button>
              )
            )}

            {isHuman ? (
              <button
                disabled={returnToAi.isPending || isClosed || isSupervisorClosed}
                onClick={() => returnToAi.mutate()}
                className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1.5 rounded-lg bg-[#6366f1]/10 text-[#a5b4fc] border border-[#6366f1]/20 hover:bg-[#6366f1]/20 transition disabled:opacity-40"
              >
                <LogOut size={10} /> Return to AI
              </button>
            ) : (
              <button
                disabled={takeOver.isPending || isClosed || isSupervisorClosed}
                onClick={() => takeOver.mutate()}
                className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1.5 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition disabled:opacity-40"
              >
                <LogIn size={10} /> Take over
              </button>
            )}

            <button
              onClick={() => setNotesOpen(o => !o)}
              className={cn(
                'flex items-center gap-1 text-[10px] font-medium px-2.5 py-1.5 rounded-lg border transition ml-auto',
                notesOpen ? 'bg-white/10 text-white/80 border-white/20' : 'bg-white/5 text-white/40 border-white/10 hover:bg-white/10'
              )}
            >
              <StickyNote size={10} /> Notes{data.notes.length > 0 && ` (${data.notes.length})`}
            </button>

            <button
              onClick={() => setActivityOpen(o => !o)}
              className={cn(
                'flex items-center gap-1 text-[10px] font-medium px-2.5 py-1.5 rounded-lg border transition',
                activityOpen ? 'bg-white/10 text-white/80 border-white/20' : 'bg-white/5 text-white/40 border-white/10 hover:bg-white/10'
              )}
            >
              <History size={10} /> Activity
            </button>
          </div>
        )}

        {/* Activity history panel (NEW) */}
        {activityOpen && data && (
          <div className="px-5 py-3 border-b border-[#1a1a1a] flex-shrink-0 bg-white/[0.02] max-h-56 overflow-y-auto">
            <ActivityHistoryList conversationId={id} />
          </div>
        )}

        {/* Internal notes panel (NEW) — team-only, never sent to the visitor */}
        {notesOpen && data && (
          <div className="px-5 py-3 border-b border-[#1a1a1a] flex-shrink-0 bg-white/[0.02] max-h-56 overflow-y-auto space-y-2">
            {data.notes.length === 0 && (
              <p className="text-[10px] text-white/20 italic">No internal notes yet — visible only to your team.</p>
            )}
            {data.notes.map(n => (
              <div key={n.id} className="text-[11px] bg-white/5 rounded-lg px-2.5 py-2">
                <p className="text-white/70 whitespace-pre-wrap break-words">{n.content}</p>
                <p className="text-[9px] text-white/25 mt-1">{n.author_name || 'Team'} · {fmtDate(n.created_at)}</p>
              </div>
            ))}
            <div className="flex items-center gap-1.5 pt-1">
              <input
                value={noteDraft}
                onChange={e => setNoteDraft(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleAddNote()}
                placeholder="Add an internal note…"
                className="flex-1 bg-[#1a1a1a] text-[11px] text-white border border-[#2a2a2a] rounded-lg px-2.5 py-1.5 outline-none focus:border-[#6366f1]/50 placeholder-white/20"
              />
              <button
                disabled={addNote.isPending || !noteDraft.trim()}
                onClick={handleAddNote}
                className="p-1.5 rounded-lg bg-[#6366f1]/15 text-[#a5b4fc] hover:bg-[#6366f1]/25 disabled:opacity-30 transition"
              >
                <Plus size={12} />
              </button>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {isLoading && (
            <div className="flex items-center justify-center py-16">
              <Loader2 size={20} className="text-[#6366f1] animate-spin" />
            </div>
          )}
          {data && (
            <div className="space-y-4">
              {data.messages.map(m => (
                <div key={m.id} className={cn('flex gap-2.5', m.role === 'user' && 'flex-row-reverse')}>
                  {m.role === 'system' ? (
                    <p className="w-full text-center text-[11px] italic text-amber-300/70 py-1">{m.content}</p>
                  ) : (
                    <>
                      <div className={cn(
                        'w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0',
                        m.is_error ? 'bg-rose-500/10' : m.role === 'bot' ? 'bg-[#6366f1]/10' : m.role === 'agent' ? 'bg-amber-500/10' : 'bg-white/5'
                      )}>
                        {m.is_error
                          ? <AlertCircle size={12} className="text-rose-400" />
                          : m.role === 'bot'
                            ? <Bot size={12} className="text-[#818cf8]" />
                            : m.role === 'agent'
                              ? <Headset size={12} className="text-amber-400" />
                              : <UserIcon size={12} className="text-white/40" />}
                      </div>
                      <div className={cn(
                        'max-w-[80%] rounded-2xl px-3.5 py-2.5 text-xs leading-relaxed',
                        m.role === 'user' ? 'bg-white/5 text-white/70' : 'bg-[#6366f1]/15 text-white/90'
                      )}>
                        <p className="whitespace-pre-wrap break-words">{m.content || '(empty)'}</p>
                        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                          {m.provider && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-white/30">{m.provider}</span>
                          )}
                          {m.ai_confidence != null && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400">
                              ~{confidenceLabel(m.ai_confidence)} confidence
                            </span>
                          )}
                          {m.latency_ms != null && (
                            <span className="text-[9px] text-white/20">{m.latency_ms}ms</span>
                          )}
                          <span className="text-[9px] text-white/20 ml-auto">{fmtDate(m.created_at)}</span>
                        </div>
                        {m.role === 'bot' && (
                          <div className="flex items-center justify-between mt-1.5 pt-1.5 border-t border-white/10">
                            <span className="text-[9px] text-white/25">
                              {m.review ? (m.review.verdict === 'correct' ? 'Marked correct' : 'Marked incorrect') : 'QA:'}
                            </span>
                            <ReviewButtons
                              id={m.id}
                              review={m.review}
                              pending={reviewMessage.isPending}
                              onReview={(messageId, verdict) => reviewMessage.mutate({ messageId, verdict })}
                            />
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Manual takeover composer (NEW) — only while a human owns this conversation */}
        {isHuman && !isClosed && !isSupervisorClosed && (
          <div className="flex items-center gap-2 px-5 py-3 border-t border-[#1a1a1a] flex-shrink-0">
            <input
              value={messageDraft}
              onChange={e => setMessageDraft(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSend()}
              placeholder="Send a message as yourself…"
              className="flex-1 bg-[#1a1a1a] text-xs text-white border border-[#2a2a2a] rounded-xl px-3 py-2 outline-none focus:border-[#6366f1]/50 placeholder-white/20"
            />
            <button
              disabled={sendMessage.isPending || !messageDraft.trim()}
              onClick={handleSend}
              className="p-2 rounded-xl bg-[#6366f1]/15 text-[#a5b4fc] hover:bg-[#6366f1]/25 disabled:opacity-30 transition flex-shrink-0"
            >
              <Send size={14} />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function AiSupervisorTableImpl() {
  const [filters, setFilters] = useState<SupervisorFilters>({ page: 1, page_size: 25 })
  const [searchInput, setSearchInput] = useState('')
  const [tagInput, setTagInput] = useState('')
  const [openId, setOpenId] = useState<string | null>(null)
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkAssignOpen, setBulkAssignOpen] = useState(false)

  const dateFilters = {
    start: startDate ? new Date(startDate).toISOString() : undefined,
    end: endDate ? new Date(new Date(endDate).getTime() + 86_399_000).toISOString() : undefined,
  }

  const { data, isLoading, isFetching } = useSupervisorConversations({ ...filters, ...dateFilters })
  const { data: agentsData } = useAssignableAgents()
  const { bulkClose, bulkAssign, bulkTag, bulkExport } = useSupervisorBulkActions()

  const applySearch = useCallback(() => {
    setFilters(f => ({ ...f, search: searchInput.trim() || undefined, page: 1 }))
  }, [searchInput])

  const applyTag = useCallback(() => {
    setFilters(f => ({ ...f, tag: tagInput.trim() || undefined, page: 1 }))
  }, [tagInput])

  const updateFilter = useCallback((patch: Partial<SupervisorFilters>) => {
    setFilters(f => ({ ...f, ...patch, page: 1 }))
  }, [])

  const goToPage = useCallback((page: number) => {
    setFilters(f => ({ ...f, page }))
  }, [])

  // PERF FIX (v107): `data?.items || []` created a brand-new array reference
  // every render whenever data was still loading (the `[]` fallback is a new
  // literal each time) — that unstable reference was a dependency of
  // toggleSelectAll's useCallback below, so it was defeating its own
  // memoization and recreating the callback on every render instead of only
  // when the actual data changed.
  const items = useMemo(() => data?.items || [], [data?.items])
  const hasActiveFilters = !!(
    filters.search || filters.channel || filters.state || filters.mode || startDate || endDate ||
    filters.priority || filters.tag || filters.pinned_only
  )

  const toggleSelected = useCallback((id: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  const toggleSelectAll = useCallback(() => {
    setSelected(prev => (prev.size === items.length ? new Set() : new Set(items.map(i => i.id))))
  }, [items])

  const clearSelection = useCallback(() => setSelected(new Set()), [])
  const selectedIds = useMemo(() => Array.from(selected), [selected])
  const agents = agentsData?.items || []

  const handleBulkExport = () => {
    bulkExport.mutate(selectedIds, {
      onSuccess: (result) => {
        if (typeof window === 'undefined') return
        const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `conversations-export-${Date.now()}.json`
        a.click()
        URL.revokeObjectURL(url)
      },
    })
  }

  return (
    <div className="tb2-glass overflow-hidden">
      {/* Toolbar */}
      <div className="p-4 border-b border-[#1a1a1a] flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/25" />
          <input
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && applySearch()}
            placeholder="Search by customer name, phone, or session…"
            className="w-full bg-[#1a1a1a] text-xs text-white border border-[#2a2a2a] rounded-xl
                       pl-8 pr-3 py-2 outline-none focus:border-[#6366f1]/50 transition placeholder-white/20"
          />
        </div>

        <select
          value={filters.state || ''}
          onChange={e => updateFilter({ state: (e.target.value || undefined) as SupervisorFilters['state'] })}
          className="bg-[#1a1a1a] text-xs text-white/70 border border-[#2a2a2a] rounded-xl px-3 py-2 outline-none focus:border-[#6366f1]/50"
        >
          {STATE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>

        <select
          value={filters.mode || ''}
          onChange={e => updateFilter({ mode: (e.target.value || undefined) as SupervisorFilters['mode'] })}
          className="bg-[#1a1a1a] text-xs text-white/70 border border-[#2a2a2a] rounded-xl px-3 py-2 outline-none focus:border-[#6366f1]/50"
        >
          {MODE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>

        <select
          value={filters.channel || ''}
          onChange={e => updateFilter({ channel: e.target.value || undefined })}
          className="bg-[#1a1a1a] text-xs text-white/70 border border-[#2a2a2a] rounded-xl px-3 py-2 outline-none focus:border-[#6366f1]/50"
        >
          {CHANNEL_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>

        <select
          value={filters.priority || ''}
          onChange={e => updateFilter({ priority: (e.target.value || undefined) as Priority | undefined })}
          className="bg-[#1a1a1a] text-xs text-white/70 border border-[#2a2a2a] rounded-xl px-3 py-2 outline-none focus:border-[#6366f1]/50"
        >
          <option value="">All priorities</option>
          {PRIORITY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>

        <div className="relative">
          <TagIcon size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-white/25" />
          <input
            value={tagInput}
            onChange={e => setTagInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && applyTag()}
            placeholder="Tag…"
            className="w-24 bg-[#1a1a1a] text-xs text-white border border-[#2a2a2a] rounded-xl pl-7 pr-2 py-2 outline-none focus:border-[#6366f1]/50 placeholder-white/20"
          />
        </div>

        <button
          onClick={() => updateFilter({ pinned_only: !filters.pinned_only })}
          className={cn(
            'flex items-center gap-1 text-xs px-3 py-2 rounded-xl border transition',
            filters.pinned_only ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' : 'bg-[#1a1a1a] text-white/50 border-[#2a2a2a] hover:bg-white/5'
          )}
        >
          <Pin size={12} /> Pinned
        </button>

        <div className="flex items-center gap-1.5">
          <input
            type="date"
            value={startDate}
            onChange={e => setStartDate(e.target.value)}
            className="bg-[#1a1a1a] text-[11px] text-white/60 border border-[#2a2a2a] rounded-xl px-2.5 py-2 outline-none focus:border-[#6366f1]/50"
          />
          <span className="text-white/20 text-[11px]">to</span>
          <input
            type="date"
            value={endDate}
            onChange={e => setEndDate(e.target.value)}
            className="bg-[#1a1a1a] text-[11px] text-white/60 border border-[#2a2a2a] rounded-xl px-2.5 py-2 outline-none focus:border-[#6366f1]/50"
          />
        </div>

        {hasActiveFilters && (
          <button
            onClick={() => {
              setSearchInput(''); setTagInput('')
              setFilters({ page: 1, page_size: 25 }); setStartDate(''); setEndDate('')
            }}
            className="flex items-center gap-1 text-[11px] text-white/30 hover:text-white/60 px-2 py-2"
          >
            <RotateCcw size={11} /> Clear
          </button>
        )}
      </div>

      {/* Bulk action bar (NEW) — appears once one or more rows are selected */}
      {selected.size > 0 && (
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[#1a1a1a] bg-[#6366f1]/[0.04] flex-wrap">
          <span className="text-[11px] text-white/50">{selected.size} selected</span>

          <button
            disabled={bulkClose.isPending}
            onClick={() => bulkClose.mutate(selectedIds, { onSuccess: clearSelection })}
            className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1.5 rounded-lg bg-white/5 text-white/60 border border-white/10 hover:bg-rose-500/10 hover:text-rose-400 transition disabled:opacity-40"
          >
            <Archive size={10} /> Close
          </button>

          <div className="relative">
            <button
              onClick={() => setBulkAssignOpen(o => !o)}
              disabled={bulkAssign.isPending}
              className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1.5 rounded-lg bg-white/5 text-white/60 border border-white/10 hover:bg-white/10 transition disabled:opacity-40"
            >
              <UserPlus size={10} /> Assign <ChevronDown size={9} />
            </button>
            {bulkAssignOpen && (
              <div className="absolute top-full left-0 mt-1 w-48 bg-[#161616] border border-[#2a2a2a] rounded-xl shadow-xl z-10 py-1 max-h-56 overflow-y-auto">
                {agents.map(a => (
                  <button
                    key={a.user_id}
                    onClick={() => {
                      bulkAssign.mutate({ conversationIds: selectedIds, agentId: a.user_id }, { onSuccess: clearSelection })
                      setBulkAssignOpen(false)
                    }}
                    className="w-full text-left text-[11px] text-white/70 hover:bg-white/5 px-3 py-1.5 truncate"
                  >
                    {a.name}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="flex items-center gap-1">
            <input
              value={tagInput}
              onChange={e => setTagInput(e.target.value)}
              placeholder="Tag…"
              className="w-20 bg-[#1a1a1a] text-[10px] text-white border border-[#2a2a2a] rounded-lg px-2 py-1.5 outline-none focus:border-[#6366f1]/50 placeholder-white/20"
            />
            <button
              disabled={bulkTag.isPending || !tagInput.trim()}
              onClick={() => bulkTag.mutate({ conversationIds: selectedIds, tag: tagInput.trim() }, { onSuccess: clearSelection })}
              className="flex items-center gap-1 text-[10px] font-medium px-2 py-1.5 rounded-lg bg-white/5 text-white/60 border border-white/10 hover:bg-white/10 transition disabled:opacity-40"
            >
              <TagIcon size={10} /> Tag
            </button>
          </div>

          <button
            disabled={bulkExport.isPending}
            onClick={handleBulkExport}
            className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1.5 rounded-lg bg-white/5 text-white/60 border border-white/10 hover:bg-white/10 transition disabled:opacity-40"
          >
            <Download size={10} /> Export
          </button>

          <button
            onClick={clearSelection}
            className="flex items-center gap-1 text-[11px] text-white/30 hover:text-white/60 px-2 py-1.5 ml-auto"
          >
            <X size={11} /> Clear selection
          </button>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="text-[10px] text-white/25 uppercase tracking-wider">
              <th className="px-4 py-2.5 font-medium w-8">
                <button onClick={toggleSelectAll} className="text-white/25 hover:text-white/60">
                  {items.length > 0 && selected.size === items.length ? <CheckSquare size={13} /> : <Square size={13} />}
                </button>
              </th>
              <th className="px-4 py-2.5 font-medium w-6"></th>
              <th className="px-4 py-2.5 font-medium">Customer</th>
              <th className="px-4 py-2.5 font-medium">Channel</th>
              <th className="px-4 py-2.5 font-medium">Bot</th>
              <th className="px-4 py-2.5 font-medium">Last customer message</th>
              <th className="px-4 py-2.5 font-medium">Last AI reply</th>
              <th className="px-4 py-2.5 font-medium">Confidence</th>
              <th className="px-4 py-2.5 font-medium">Handling</th>
              <th className="px-4 py-2.5 font-medium">Assigned</th>
              <th className="px-4 py-2.5 font-medium">Priority</th>
              <th className="px-4 py-2.5 font-medium">Tags</th>
              <th className="px-4 py-2.5 font-medium">Status</th>
              <th className="px-4 py-2.5 font-medium">Last activity</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c: SupervisorConversationListItem) => (
              <tr
                key={c.id}
                onClick={() => setOpenId(c.id)}
                className={cn(
                  'border-t border-[#141414] hover:bg-white/[0.02] cursor-pointer transition',
                  c.is_pinned && 'bg-amber-500/[0.03]'
                )}
              >
                <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                  <button onClick={() => toggleSelected(c.id)} className="text-white/25 hover:text-white/60">
                    {selected.has(c.id) ? <CheckSquare size={13} /> : <Square size={13} />}
                  </button>
                </td>
                <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                  <RowPinButton conversationId={c.id} pinned={c.is_pinned} />
                </td>
                <td className="px-4 py-3">
                  <p className="text-xs text-white/70 font-medium truncate max-w-[140px]">{c.customer_display}</p>
                  {c.customer_handle && (
                    <p className="text-[9px] text-white/25 truncate max-w-[140px]">{c.customer_handle}</p>
                  )}
                </td>
                <td className="px-4 py-3">
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 text-white/40 capitalize">
                    {c.channel.replace('_', ' ')}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-white/50 truncate max-w-[120px]">{c.workflow_name}</td>
                <td className="px-4 py-3 text-[11px] text-white/50 truncate max-w-[200px]">
                  {c.last_customer_message || <span className="text-white/15">—</span>}
                </td>
                <td className="px-4 py-3 text-[11px] text-white/50 truncate max-w-[200px]">
                  {c.last_ai_reply || <span className="text-white/15">—</span>}
                </td>
                <td className="px-4 py-3 text-xs text-white/50 tabular-nums">
                  {confidenceLabel(c.ai_confidence) ?? <span className="text-white/15 text-[10px]">—</span>}
                </td>
                <td className="px-4 py-3"><HandoffBadge item={c} /></td>
                <td className="px-4 py-3 text-[11px] text-white/40 truncate max-w-[100px]">
                  {c.assigned_agent_name || <span className="text-white/15">—</span>}
                </td>
                <td className="px-4 py-3"><PriorityBadge priority={c.priority} /></td>
                <td className="px-4 py-3"><TagChips tags={c.tags} /></td>
                <td className="px-4 py-3">
                  <span className={cn(
                    'text-[9px] px-2 py-0.5 rounded-full uppercase font-medium',
                    c.status === 'active'
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      : 'bg-white/4 text-white/25 border border-white/8'
                  )}>
                    {c.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-[11px] text-white/30 whitespace-nowrap">{fmtDate(c.last_activity_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {isLoading && (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={18} className="text-[#6366f1] animate-spin" />
          </div>
        )}
        {!isLoading && items.length === 0 && (
          <div className="flex flex-col items-center py-16 gap-2">
            <p className="text-xs text-white/25">No conversations match these filters</p>
          </div>
        )}
      </div>

      {/* Pagination */}
      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-[#1a1a1a]">
          <p className="text-[11px] text-white/25">
            Page {data.page} of {data.total_pages} · {data.total} total {isFetching && '· refreshing…'}
          </p>
          <div className="flex items-center gap-1">
            <button
              disabled={data.page <= 1}
              onClick={() => goToPage(data.page - 1)}
              className="p-1.5 rounded-lg border border-[#2a2a2a] text-white/40 hover:text-white/70 disabled:opacity-30 disabled:cursor-not-allowed transition"
            >
              <ChevronLeft size={13} />
            </button>
            <button
              disabled={data.page >= data.total_pages}
              onClick={() => goToPage(data.page + 1)}
              className="p-1.5 rounded-lg border border-[#2a2a2a] text-white/40 hover:text-white/70 disabled:opacity-30 disabled:cursor-not-allowed transition"
            >
              <ChevronRight size={13} />
            </button>
          </div>
        </div>
      )}

      {openId && <SupervisorConversationDrawer id={openId} onClose={() => setOpenId(null)} />}
    </div>
  )
}

export const AiSupervisorTable = memo(AiSupervisorTableImpl)
