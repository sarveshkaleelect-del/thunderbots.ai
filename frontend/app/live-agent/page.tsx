'use client'
import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQueryClient } from '@tanstack/react-query'
import {
  Headset, Search, Users, Clock, CheckCircle2, MessageCircle, ArrowRightLeft,
  Bot, Send, X, Circle,
} from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import { Button } from '@/components/ui/Button'
import { Card, Badge } from '@/components/ui/Card'
import { TopBar } from '@/components/ui/TopBar'
import { Footer } from '@/components/ui/Footer'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/lib/utils/errors'
import type { AgentStatus, HandoffStatus } from '@/lib/api/liveAgent'
import { useIsAdmin } from '@/hooks/useAdmin'
import {
  useAgents, useUpdateMyStatus, useDashboardStats, useConversations,
  useConversationDetail, useHandoffActions, useLiveAgentDashboardSocket,
} from '@/hooks/useLiveAgent'

const TABS: { key: HandoffStatus; label: string }[] = [
  { key: 'waiting', label: 'Waiting' },
  { key: 'active', label: 'Active' },
  { key: 'closed', label: 'Closed' },
]

function timeAgo(iso: string | null): string {
  if (!iso) return ''
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.max(0, Math.floor(diffMs / 60000))
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export default function LiveAgentPage() {
  const router = useRouter()
  const qc = useQueryClient()
  const { toast } = useToast()

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('tb_token')) {
      router.replace('/login')
    }
  }, [router])

  const [tab, setTab] = useState<HandoffStatus>('waiting')
  const [search, setSearch] = useState('')
  const [channelFilter, setChannelFilter] = useState('')
  const [agentFilter, setAgentFilter] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [messageDraft, setMessageDraft] = useState('')

  const { data: me } = useIsAdmin()
  const { data: agentsData } = useAgents()
  const { data: stats } = useDashboardStats()
  const { data: convData, isLoading, error, refetch } = useConversations({
    status: tab, search, channel: channelFilter || undefined, agent_id: agentFilter || undefined,
  })
  const { data: detail } = useConversationDetail(selectedId)
  const updateStatus = useUpdateMyStatus()
  const { takeOver, returnToAi, close, sendMessage } = useHandoffActions()

  useLiveAgentDashboardSocket(undefined, (evt) => {
    if (evt.type === 'handoff_waiting' || evt.type === 'handoff_updated' || evt.type === 'handoff_message') {
      qc.invalidateQueries({ queryKey: ['live-agent'] })
    }
  })

  const myProfile = useMemo(
    () => agentsData?.agents.find(a => a.user_id === me?.id) || null,
    [agentsData, me]
  )

  const selected = detail?.handoff

  const handleAction = async (fn: () => Promise<any>, successMsg: string) => {
    try {
      await fn()
      toast('success', successMsg)
    } catch (err) {
      toast('error', getErrorMessage(err, 'Something went wrong'))
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-[#070708]">
      <TopBar />
      <main className="flex-1 w-full max-w-[1400px] mx-auto px-4 sm:px-6 py-6 flex flex-col gap-5">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-[#6366f1]/10 border border-[#6366f1]/25 flex items-center justify-center">
              <Headset size={16} className="text-[#a5b4fc]" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">Live Agent</h1>
              <p className="text-xs text-white/40">Human handoff & live conversations</p>
            </div>
          </div>

          {/* Agent status toggle */}
          <div className="flex items-center gap-1.5 tb2-glass px-2 py-1.5 rounded-xl">
            {(['online', 'busy', 'offline'] as AgentStatus[]).map(s => (
              <button
                key={s}
                onClick={() => handleAction(() => updateStatus.mutateAsync(s), `Status set to ${s}`)}
                className={cn(
                  'flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg font-medium transition capitalize',
                  myProfile?.status === s ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/75'
                )}
              >
                <Circle size={7} className={cn(
                  'fill-current',
                  s === 'online' ? 'text-emerald-400' : s === 'busy' ? 'text-amber-400' : 'text-zinc-500'
                )} />
                {s}
              </button>
            ))}
          </div>
        </div>

        {/* Dashboard stats */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {[
            { label: 'Active chats', value: stats?.active_chats ?? '—', icon: MessageCircle, tone: 'text-emerald-400' },
            { label: 'Waiting', value: stats?.waiting_chats ?? '—', icon: Clock, tone: 'text-amber-400' },
            { label: 'Closed', value: stats?.closed_chats ?? '—', icon: CheckCircle2, tone: 'text-white/50' },
            { label: 'Agents online', value: stats?.agents_online ?? '—', icon: Users, tone: 'text-emerald-400' },
            { label: 'Agents busy', value: stats?.agents_busy ?? '—', icon: Users, tone: 'text-amber-400' },
            { label: 'Agents offline', value: stats?.agents_offline ?? '—', icon: Users, tone: 'text-white/40' },
          ].map(s => (
            <Card key={s.label} className="p-3.5">
              <s.icon size={14} className={cn('mb-2', s.tone)} />
              <p className="text-xl font-bold text-white">{s.value}</p>
              <p className="text-[11px] text-white/40 mt-0.5">{s.label}</p>
            </Card>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-5 flex-1 min-h-0">
          {/* Conversation list */}
          <Card className="p-0 flex flex-col overflow-hidden">
            <div className="p-3 border-b border-white/[0.06] space-y-2.5">
              <div className="flex items-center gap-1 bg-white/[0.03] rounded-lg p-1">
                {TABS.map(t => (
                  <button
                    key={t.key}
                    onClick={() => { setTab(t.key); setSelectedId(null) }}
                    className={cn(
                      'flex-1 text-xs font-medium py-1.5 rounded-md transition',
                      tab === t.key ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'
                    )}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              <div className="relative">
                <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-white/30" />
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Search conversations…"
                  className="w-full text-xs pl-8 pr-3 py-2 rounded-lg bg-white/[0.04] border border-white/10 text-white/80 outline-none focus:border-white/25"
                />
              </div>
              <div className="flex gap-2">
                <select
                  value={channelFilter}
                  onChange={e => setChannelFilter(e.target.value)}
                  className="flex-1 text-[11px] px-2 py-1.5 rounded-lg bg-white/[0.04] border border-white/10 text-white/60"
                >
                  <option value="">All channels</option>
                  <option value="web_chat">Web Chat</option>
                  <option value="embed_widget">Embed Widget</option>
                  <option value="whatsapp">WhatsApp</option>
                  <option value="telegram">Telegram</option>
                  <option value="instagram">Instagram</option>
                </select>
                <select
                  value={agentFilter}
                  onChange={e => setAgentFilter(e.target.value)}
                  className="flex-1 text-[11px] px-2 py-1.5 rounded-lg bg-white/[0.04] border border-white/10 text-white/60"
                >
                  <option value="">All agents</option>
                  {agentsData?.agents.map(a => (
                    <option key={a.user_id} value={a.user_id}>{a.name}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto">
              {isLoading && <div className="p-3"><SkeletonRows count={5} /></div>}
              {error && <div className="p-3"><ErrorState description={getErrorMessage(error, 'Failed to load conversations')} onRetry={refetch} /></div>}
              {!isLoading && !error && (convData?.items.length ?? 0) === 0 && (
                <div className="p-6"><EmptyState icon={<Headset size={22} />} title="No conversations" description={`No ${tab} conversations right now.`} /></div>
              )}
              {convData?.items.map(h => (
                <button
                  key={h.id}
                  onClick={() => setSelectedId(h.id)}
                  className={cn(
                    'w-full text-left px-3.5 py-3 border-b border-white/[0.04] transition hover:bg-white/[0.03]',
                    selectedId === h.id && 'bg-white/[0.06]'
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium text-white/85 truncate">{h.visitor_label}</p>
                    <Badge tone={h.status === 'active' ? 'success' : h.status === 'waiting' ? 'warning' : 'default'}>
                      {h.status}
                    </Badge>
                  </div>
                  <p className="text-xs text-white/40 truncate mt-1">{h.last_message_preview || 'No messages yet'}</p>
                  <div className="flex items-center gap-2 mt-1.5 text-[10px] text-white/30">
                    <span className="capitalize">{h.channel.replace('_', ' ')}</span>
                    <span>·</span>
                    <span>{timeAgo(h.last_message_at)}</span>
                    {h.assigned_agent_name && <><span>·</span><span>{h.assigned_agent_name}</span></>}
                  </div>
                </button>
              ))}
            </div>
          </Card>

          {/* Conversation detail */}
          <Card className="p-0 flex flex-col overflow-hidden">
            {!selected ? (
              <div className="flex-1 flex items-center justify-center">
                <EmptyState icon={<MessageCircle size={22} />} title="Select a conversation" description="Choose a conversation from the list to view history and respond." />
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06]">
                  <div>
                    <p className="text-sm font-semibold text-white">{selected.visitor_label}</p>
                    <p className="text-[11px] text-white/40 capitalize">{selected.channel.replace('_', ' ')} · {selected.status}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {selected.status !== 'active' && selected.status !== 'closed' && (
                      <Button size="sm" variant="primary" icon={<ArrowRightLeft size={13} />}
                        onClick={() => handleAction(() => takeOver.mutateAsync(selected.id), 'Conversation taken over')}>
                        Take Over
                      </Button>
                    )}
                    {selected.status === 'active' && (
                      <Button size="sm" variant="secondary" icon={<Bot size={13} />}
                        onClick={() => handleAction(() => returnToAi.mutateAsync(selected.id), 'Returned to AI Agent')}>
                        Return to AI
                      </Button>
                    )}
                    {selected.status !== 'closed' && (
                      <Button size="sm" variant="ghost" icon={<X size={13} />}
                        onClick={() => handleAction(() => close.mutateAsync(selected.id), 'Conversation closed')}>
                        Close
                      </Button>
                    )}
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
                  {detail?.messages.map(m => (
                    <div key={m.id} className={cn('flex', m.role === 'user' ? 'justify-start' : 'justify-end')}>
                      {m.role === 'system' ? (
                        <p className="w-full text-center text-[11px] italic text-amber-300/70 py-1">{m.content}</p>
                      ) : (
                        <div
                          className={cn(
                            'max-w-[75%] px-3.5 py-2 rounded-2xl text-sm leading-relaxed',
                            m.role === 'user' ? 'bg-white/[0.06] text-white/85 rounded-bl-md'
                              : m.role === 'agent' ? 'bg-[#6366f1] text-white rounded-br-md'
                              : 'bg-[#6366f1]/40 text-white rounded-br-md'
                          )}
                        >
                          {m.role !== 'user' && (
                            <p className="text-[10px] opacity-60 mb-0.5 font-medium">
                              {m.role === 'agent' ? 'Agent' : 'AI Agent'}
                            </p>
                          )}
                          {m.content}
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                <div className="p-3 border-t border-white/[0.06] flex gap-2">
                  <input
                    value={messageDraft}
                    onChange={e => setMessageDraft(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter' && messageDraft.trim()) {
                        sendMessage.mutate({ handoffId: selected.id, content: messageDraft.trim() })
                        setMessageDraft('')
                      }
                    }}
                    placeholder={selected.status === 'active' ? 'Reply as agent…' : 'Take over to reply'}
                    disabled={selected.status !== 'active'}
                    className="flex-1 text-sm px-3.5 py-2.5 rounded-xl bg-white/[0.04] border border-white/10 text-white/85 outline-none focus:border-white/25 disabled:opacity-40"
                  />
                  <Button
                    size="md"
                    disabled={selected.status !== 'active' || !messageDraft.trim()}
                    onClick={() => { sendMessage.mutate({ handoffId: selected.id, content: messageDraft.trim() }); setMessageDraft('') }}
                    icon={<Send size={14} />}
                  >
                    Send
                  </Button>
                </div>
              </>
            )}
          </Card>
        </div>
      </main>
      <Footer />
    </div>
  )
}
