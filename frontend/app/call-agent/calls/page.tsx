'use client'
/**
 * NEW (AI Call Agent — Voice AI Part 3) — /call-agent/calls
 *
 * Adds exactly what api/v1/call_agent.py (Part 2) explicitly left out:
 * the call dashboard (Active/Missed/Completed/Failed/Interrupted), call
 * history, and per-call transcript/duration/recording — all driven by the
 * new /call-agent/calls* endpoints (call_agent_calls.py). Placed on its
 * own route rather than folded into /call-agent/page.tsx so Part 2's page
 * is never touched by this part.
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  PhoneCall, PhoneMissed, PhoneOff, CheckCircle2, XCircle, Zap,
  Clock, Mic, User, Bot, AlertTriangle, RefreshCw, Search, Headset,
  UserCheck, Sparkles, Send, TrendingUp, Timer,
} from 'lucide-react'
import { getToken } from '@/lib/api/auth'
import { callAgentApi } from '@/lib/api/callAgent'
import type { Call, CallDashboardBucket, CallTranscriptEntry } from '@/types/callAgent'
import { Card, Badge } from '@/components/ui/Card'
import { Button, IconButton } from '@/components/ui/Button'
import { Select, Input } from '@/components/ui/Field'
import { SubPageBar } from '@/components/ui/TopBar'
import { CallAgentNav } from '@/components/callAgent/CallAgentNav'
import { PageLoader, ErrorState, EmptyState } from '@/components/ui/States'
import { Modal } from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/lib/utils/errors'

const BUCKETS: { key: CallDashboardBucket; label: string; icon: React.ReactNode }[] = [
  { key: 'active', label: 'Active', icon: <PhoneCall size={15} /> },
  { key: 'missed', label: 'Missed', icon: <PhoneMissed size={15} /> },
  { key: 'completed', label: 'Completed', icon: <CheckCircle2 size={15} /> },
  { key: 'failed', label: 'Failed', icon: <XCircle size={15} /> },
  { key: 'interrupted', label: 'Interrupted', icon: <Zap size={15} /> },
]

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function statusBadge(call: Call) {
  if (call.status === 'active' || call.status === 'ringing' || call.status === 'queued') {
    return <Badge tone="success" dot>Active</Badge>
  }
  if (call.status === 'missed' || call.status === 'no_answer') {
    return <Badge tone="warning">Missed</Badge>
  }
  if (call.status === 'failed') {
    return <Badge tone="danger">Failed</Badge>
  }
  if (call.status === 'completed' && call.interrupted_count > 0) {
    return <Badge tone="default">Interrupted</Badge>
  }
  return <Badge tone="default">Completed</Badge>
}

export default function CallsDashboardPage() {
  const router = useRouter()
  const [activeBucket, setActiveBucket] = useState<CallDashboardBucket | null>(null)
  const [selectedCallId, setSelectedCallId] = useState<string | null>(null)
  // NEW (Voice AI Part 4) — search + date range filters
  const [search, setSearch] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  useEffect(() => {
    if (typeof window !== 'undefined' && !getToken()) router.replace('/login')
  }, [router])

  const { data: summary, isLoading: summaryLoading, refetch: refetchSummary } = useQuery({
    queryKey: ['call-agent', 'dashboard'],
    queryFn: callAgentApi.dashboardSummary,
    refetchInterval: 15000,
  })

  const {
    data: calls = [], isLoading, error, refetch,
  } = useQuery({
    queryKey: ['call-agent', 'calls', activeBucket, search, dateFrom, dateTo],
    queryFn: () => callAgentApi.listCalls({
      status: activeBucket || undefined,
      search: search || undefined,
      date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
      date_to: dateTo ? new Date(dateTo).toISOString() : undefined,
    }),
    refetchInterval: 10000,
  })

  return (
    <div className="tb2-shell">
      <SubPageBar backHref="/call-agent" crumb="Calls" crumbIcon={<PhoneCall size={13} className="text-cyan-300/70" />} />
      <CallAgentNav />

      <div className="max-w-4xl mx-auto px-6 py-10 space-y-6">
        <div className="tb2-rise flex items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-white">Call Dashboard</h1>
            <p className="text-sm text-white/35 mt-1">
              Realtime AI phone calls — active, missed, completed, failed, and interrupted.
            </p>
          </div>
          <IconButton aria-label="Refresh" onClick={() => { refetchSummary(); refetch() }}>
            <RefreshCw size={14} />
          </IconButton>
        </div>

        {/* ── Dashboard cards ── */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 tb2-rise">
          {BUCKETS.map(b => (
            <button
              key={b.key}
              onClick={() => setActiveBucket(activeBucket === b.key ? null : b.key)}
              className={`text-left rounded-xl border p-3 transition ${
                activeBucket === b.key
                  ? 'border-cyan-500/40 bg-cyan-500/10'
                  : 'border-white/10 bg-white/[0.02] hover:bg-white/[0.05]'
              }`}
            >
              <div className="flex items-center gap-1.5 text-white/40">{b.icon}</div>
              <p className="text-2xl font-bold text-white mt-1.5">
                {summaryLoading ? '—' : (summary?.[b.key] ?? 0)}
              </p>
              <p className="text-[11px] text-white/40 mt-0.5">{b.label}</p>
            </button>
          ))}
        </div>

        {/* NEW (Voice AI Part 4) — extended analytics row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 tb2-rise">
          <Card className="p-3">
            <div className="flex items-center gap-1.5 text-white/40"><PhoneCall size={13} /></div>
            <p className="text-lg font-bold text-white mt-1">{summaryLoading ? '—' : summary?.total_calls ?? 0}</p>
            <p className="text-[11px] text-white/40 mt-0.5">Total calls</p>
          </Card>
          <Card className="p-3">
            <div className="flex items-center gap-1.5 text-white/40"><Timer size={13} /></div>
            <p className="text-lg font-bold text-white mt-1">
              {summaryLoading || summary?.avg_duration_seconds == null ? '—' : formatDuration(Math.round(summary.avg_duration_seconds))}
            </p>
            <p className="text-[11px] text-white/40 mt-0.5">Avg. duration</p>
          </Card>
          <Card className="p-3">
            <div className="flex items-center gap-1.5 text-white/40"><Zap size={13} /></div>
            <p className="text-lg font-bold text-white mt-1">
              {summaryLoading || summary?.avg_response_time_ms == null ? '—' : `${(summary.avg_response_time_ms / 1000).toFixed(1)}s`}
            </p>
            <p className="text-[11px] text-white/40 mt-0.5">Avg. response time</p>
          </Card>
          <Card className="p-3">
            <div className="flex items-center gap-1.5 text-white/40"><TrendingUp size={13} /></div>
            <p className="text-lg font-bold text-white mt-1">
              {summaryLoading || summary?.resolution_rate == null ? '—' : `${Math.round(summary.resolution_rate * 100)}%`}
            </p>
            <p className="text-[11px] text-white/40 mt-0.5">Resolved by AI</p>
          </Card>
        </div>

        {/* NEW (Voice AI Part 4) — search + date filters */}
        <div className="flex flex-col sm:flex-row gap-2 tb2-rise">
          <div className="relative flex-1">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
            <Input
              className="pl-8"
              placeholder="Search by phone number…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <input
            type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            className="bg-white/[0.04] border border-white/10 rounded-lg px-3 py-2 text-sm text-white/70"
          />
          <input
            type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
            className="bg-white/[0.04] border border-white/10 rounded-lg px-3 py-2 text-sm text-white/70"
          />
        </div>

        {/* ── Call history ── */}
        {isLoading ? (
          <PageLoader />
        ) : error ? (
          <ErrorState
            title="Couldn't load calls"
            description={getErrorMessage(error, 'Check your connection and that the backend is running.')}
            onRetry={() => refetch()}
          />
        ) : calls.length === 0 ? (
          <EmptyState
            icon={<PhoneCall size={26} />}
            title={activeBucket ? `No ${activeBucket} calls` : 'No calls yet'}
            description="Calls placed or received through an enabled AI Call Agent number will show up here."
          />
        ) : (
          <div className="space-y-2 tb2-rise">
            {calls.map(call => (
              <Card
                key={call.id}
                className="p-3 flex items-center justify-between gap-3 cursor-pointer hover:bg-white/[0.04] transition"
                onClick={() => setSelectedCallId(call.id)}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-9 h-9 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center flex-shrink-0">
                    {call.direction === 'inbound' ? <PhoneCall size={15} className="text-cyan-300" /> : <PhoneOff size={15} className="text-cyan-300 rotate-180" />}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-white/85 truncate">
                      {call.direction === 'inbound' ? call.from_number : call.to_number}
                    </p>
                    <p className="text-[11px] text-white/35 truncate flex items-center gap-2">
                      <Clock size={10} />{formatDuration(call.duration_seconds)}
                      {call.recording_url && <Mic size={10} className="text-white/30" />}
                      {call.interrupted_count > 0 && (
                        <span className="flex items-center gap-0.5">
                          <Zap size={10} className="text-amber-400/70" />{call.interrupted_count}
                        </span>
                      )}
                    </p>
                  </div>
                </div>
                <div className="flex-shrink-0">{statusBadge(call)}</div>
              </Card>
            ))}
          </div>
        )}
      </div>

      {selectedCallId && (
        <CallDetailModal callId={selectedCallId} onClose={() => setSelectedCallId(null)} />
      )}
    </div>
  )
}

function CallDetailModal({ callId, onClose }: { callId: string; onClose: () => void }) {
  const { toast } = useToast()
  const qc = useQueryClient()
  const [agentMessage, setAgentMessage] = useState('')

  const { data: call } = useQuery({
    queryKey: ['call-agent', 'call', callId],
    queryFn: () => callAgentApi.getCall(callId),
    refetchInterval: 5000,
  })
  const { data: transcript = [], isLoading } = useQuery({
    queryKey: ['call-agent', 'transcript', callId],
    queryFn: () => callAgentApi.getTranscript(callId),
    refetchInterval: 3000,
  })
  // NEW (Voice AI Part 4) — human handoff status, polled while the call is live
  const { data: handoff } = useQuery({
    queryKey: ['call-agent', 'handoff-status', callId],
    queryFn: () => callAgentApi.getHandoffStatus(callId),
    refetchInterval: call && ['queued', 'ringing', 'active'].includes(call.status) ? 4000 : false,
  })

  const canHangup = call && ['queued', 'ringing', 'active'].includes(call.status)
  const canHandoff = call && ['queued', 'ringing', 'active'].includes(call.status)
    && (!handoff || !['active', 'paused'].includes(handoff.handoff_status))
  const isHandedOff = handoff && ['active', 'paused'].includes(handoff.handoff_status)

  const takeOver = async () => {
    try {
      await callAgentApi.handoffToHuman(callId)
      qc.invalidateQueries({ queryKey: ['call-agent', 'handoff-status', callId] })
      toast('success', "You've taken over this call.")
    } catch (err) {
      toast('error', getErrorMessage(err, 'Could not take over this call.'))
    }
  }

  const resumeAI = async () => {
    try {
      await callAgentApi.resumeAI(callId)
      qc.invalidateQueries({ queryKey: ['call-agent', 'handoff-status', callId] })
      toast('success', 'Returned the call to the AI Call Agent.')
    } catch (err) {
      toast('error', getErrorMessage(err, 'Could not resume the AI.'))
    }
  }

  const sendMessage = async () => {
    if (!agentMessage.trim()) return
    try {
      await callAgentApi.sendAgentMessage(callId, agentMessage)
      setAgentMessage('')
      qc.invalidateQueries({ queryKey: ['call-agent', 'transcript', callId] })
    } catch (err) {
      toast('error', getErrorMessage(err, 'Could not send that message.'))
    }
  }

  const regenSummary = async () => {
    try {
      await callAgentApi.regenerateSummary(callId)
      qc.invalidateQueries({ queryKey: ['call-agent', 'call', callId] })
      toast('success', 'Summary generated.')
    } catch (err) {
      toast('error', getErrorMessage(err, 'Not enough transcript to summarize yet.'))
    }
  }

  return (
    <Modal
      onClose={onClose}
      title="Call transcript"
      subtitle={call ? `${call.direction === 'inbound' ? call.from_number : call.to_number} · ${formatDuration(call.duration_seconds)}` : undefined}
      maxWidth="max-w-lg"
    >
      <div className="space-y-4">
        {call?.fallback_triggered && (
          <div className="flex items-start gap-2 text-xs text-amber-400/90 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
            <AlertTriangle size={13} className="flex-shrink-0 mt-0.5" />
            <span>
              The AI couldn't answer during this call and a fallback message played
              {call.handed_off_to_human ? ' — a live agent was requested.' : '.'}
            </span>
          </div>
        )}

        {/* NEW (Voice AI Part 4) — human handoff controls */}
        <div className="flex items-center justify-between gap-2 bg-white/[0.02] border border-white/10 rounded-lg px-3 py-2">
          <span className="flex items-center gap-1.5 text-xs text-white/60">
            <Headset size={13} />
            {isHandedOff ? 'A human agent has this call' : 'AI Call Agent is handling this call'}
          </span>
          {canHandoff && (
            <Button size="sm" variant="secondary" icon={<UserCheck size={12} />} onClick={takeOver}>
              Take over
            </Button>
          )}
          {isHandedOff && call && ['queued', 'ringing', 'active'].includes(call.status) && (
            <Button size="sm" variant="secondary" icon={<Sparkles size={12} />} onClick={resumeAI}>
              Resume AI
            </Button>
          )}
        </div>

        {/* NEW (Voice AI Part 4) — call recording summary */}
        <div className="bg-white/[0.02] border border-white/10 rounded-lg px-3 py-2 space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-white/40">Summary</span>
            {!canHangup && (
              <button onClick={regenSummary} className="text-[11px] text-cyan-300/80 hover:text-cyan-200">Regenerate</button>
            )}
          </div>
          <p className="text-xs text-white/60">{call?.summary || 'No summary yet.'}</p>
        </div>

        {call?.recording_url && (
          <audio controls src={call.recording_url} className="w-full h-9 rounded-lg" />
        )}

        {isLoading ? (
          <PageLoader />
        ) : transcript.length === 0 ? (
          <p className="text-xs text-white/35 py-6 text-center">No transcript yet.</p>
        ) : (
          <div className="space-y-2 max-h-[50vh] overflow-y-auto pr-1">
            {transcript.map((entry: CallTranscriptEntry) => (
              <div
                key={entry.id}
                className={`flex gap-2 text-xs rounded-lg px-3 py-2 ${
                  entry.role === 'caller'
                    ? 'bg-white/[0.04] border border-white/10'
                    : entry.role === 'ai'
                    ? 'bg-cyan-500/[0.06] border border-cyan-500/15'
                    : 'bg-amber-500/[0.06] border border-amber-500/15 italic'
                }`}
              >
                {entry.role === 'caller' && <User size={12} className="flex-shrink-0 mt-0.5 text-white/40" />}
                {entry.role === 'ai' && <Bot size={12} className="flex-shrink-0 mt-0.5 text-cyan-300/70" />}
                <span className="text-white/70">
                  {entry.content}
                  {entry.was_interrupted && <span className="text-amber-400/70"> (interrupted)</span>}
                  {entry.response_time_ms != null && (
                    <span className="text-white/25"> · {(entry.response_time_ms / 1000).toFixed(1)}s</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* NEW (Voice AI Part 4) — send a message spoken to the caller while handed off */}
        {isHandedOff && call && ['queued', 'ringing', 'active'].includes(call.status) && (
          <div className="flex items-center gap-2">
            <Input
              placeholder="Type a message — it'll be spoken to the caller…"
              value={agentMessage}
              onChange={e => setAgentMessage(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && sendMessage()}
            />
            <Button size="sm" icon={<Send size={12} />} onClick={sendMessage} disabled={!agentMessage.trim()}>
              Send
            </Button>
          </div>
        )}

        {canHangup && (
          <Button
            size="sm"
            variant="danger"
            icon={<PhoneOff size={12} />}
            onClick={async () => {
              try {
                await callAgentApi.hangupCall(callId)
                qc.invalidateQueries({ queryKey: ['call-agent'] })
                toast('success', 'Call ended.')
              } catch (err) {
                toast('error', getErrorMessage(err, 'Could not end the call.'))
              }
            }}
          >
            End call
          </Button>
        )}
      </div>
    </Modal>
  )
}
