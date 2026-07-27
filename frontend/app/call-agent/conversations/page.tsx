'use client'
/**
 * AI Call Agent — Conversations — /call-agent/conversations
 *
 * NEW (Voice AI Part 5). A transcript-first view across every call this
 * account's Voice Agents and phone numbers have handled, reusing the
 * existing GET /call-agent/calls and GET /call-agent/calls/{id}/transcript
 * endpoints (backend/app/api/v1/call_agent_calls.py) — no new backend
 * surface needed. Complements /call-agent/calls (telephony status/ops
 * focused) with a conversation-content focused view.
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { MessagesSquare, ChevronDown, ChevronUp, User, Bot as BotIcon } from 'lucide-react'
import { getToken } from '@/lib/api/auth'
import { callAgentApi } from '@/lib/api/callAgent'
import type { Call } from '@/types/callAgent'
import { Card, Badge } from '@/components/ui/Card'
import { SubPageBar } from '@/components/ui/TopBar'
import { CallAgentNav } from '@/components/callAgent/CallAgentNav'
import { PageLoader, ErrorState, EmptyState, Skeleton } from '@/components/ui/States'
import { getErrorMessage } from '@/lib/utils/errors'

export default function ConversationsPage() {
  const router = useRouter()

  useEffect(() => {
    if (typeof window !== 'undefined' && !getToken()) router.replace('/login')
  }, [router])

  const { data: calls = [], isLoading, error, refetch } = useQuery({
    queryKey: ['call-agent-conversations'],
    queryFn: () => callAgentApi.listCalls({ limit: 50 }),
  })

  return (
    <div className="tb2-shell">
      <SubPageBar backHref="/call-agent" crumb="Conversations" crumbIcon={<MessagesSquare size={13} className="text-cyan-300/70" />} />
      <CallAgentNav />

      <div className="max-w-4xl mx-auto px-3 sm:px-6 py-8 space-y-4">
        <div className="tb2-rise">
          <h1 className="text-xl font-bold text-white">Conversations</h1>
          <p className="text-sm text-white/35 mt-1">Every AI Call Agent conversation, with full transcripts.</p>
        </div>

        {isLoading ? (
          <PageLoader />
        ) : error ? (
          <ErrorState title="Couldn't load conversations" description={getErrorMessage(error)} onRetry={() => refetch()} />
        ) : calls.length === 0 ? (
          <EmptyState icon={<MessagesSquare size={22} />} title="No conversations yet" description="Calls handled by your AI Call Agent will show up here." />
        ) : (
          <div className="space-y-2">
            {calls.map(call => <ConversationRow key={call.id} call={call} />)}
          </div>
        )}
      </div>
    </div>
  )
}

function ConversationRow({ call }: { call: Call }) {
  const [open, setOpen] = useState(false)
  const { data: transcript, isLoading } = useQuery({
    queryKey: ['call-transcript', call.id],
    queryFn: () => callAgentApi.getTranscript(call.id),
    enabled: open,
  })

  return (
    <Card className="p-4">
      <button className="w-full flex items-center justify-between gap-3 text-left" onClick={() => setOpen(o => !o)}>
        <div className="min-w-0">
          <p className="text-sm text-white/80 truncate">{call.from_number} → {call.to_number}</p>
          <p className="text-[11px] text-white/35">{call.started_at ? new Date(call.started_at).toLocaleString() : 'Not started'}</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <Badge tone={call.status === 'completed' ? 'success' : call.status === 'failed' ? 'danger' : 'default'}>{call.status}</Badge>
          {open ? <ChevronUp size={14} className="text-white/30" /> : <ChevronDown size={14} className="text-white/30" />}
        </div>
      </button>

      {open && (
        <div className="mt-3 pt-3 border-t border-white/10 space-y-2">
          {call.summary && <p className="text-xs text-white/50 italic mb-2">{call.summary}</p>}
          {isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : !transcript || transcript.length === 0 ? (
            <p className="text-xs text-white/25">No transcript recorded.</p>
          ) : (
            transcript.map(entry => (
              <div key={entry.id} className="flex items-start gap-2 text-xs">
                {entry.role === 'caller' ? <User size={12} className="text-cyan-300/70 mt-0.5 flex-shrink-0" /> : <BotIcon size={12} className="text-[#a5b4fc] mt-0.5 flex-shrink-0" />}
                <p className="text-white/60">{entry.content}</p>
              </div>
            ))
          )}
        </div>
      )}
    </Card>
  )
}
