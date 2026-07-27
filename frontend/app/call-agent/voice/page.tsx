'use client'
/**
 * AI Call Agent — Web Voice Bubble mode — /call-agent/voice
 *
 * REWRITTEN (Voice AI Part 5). Root cause of the previous version: this
 * page used to list `workflowsApi.list()` bots and send visitors into the
 * Builder to "configure voice & KB" — meaning the Web Voice Bubble product
 * WAS the chatbot Workflow, with no independent identity of its own. That
 * violated the requirement that this module never reuse the chatbot page
 * as the voice product UI.
 *
 * Now: lists standalone Voice Agents (own provider/instructions/voice/
 * Knowledge Base — see /call-agent/agents) and offers the embed snippet
 * for each one directly, from /call-agent/agents/{id}/embed. No import of
 * workflowsApi or deployApi anywhere in this file.
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Globe, Mic, BookOpen, Rocket, Code2, Copy, Check, Settings2, Bot } from 'lucide-react'
import { getToken } from '@/lib/api/auth'
import { voiceAgentsApi } from '@/lib/api/callAgent'
import type { VoiceAgent } from '@/types/callAgent'
import { Card, Badge } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { SubPageBar } from '@/components/ui/TopBar'
import { CallAgentNav } from '@/components/callAgent/CallAgentNav'
import { PageLoader, ErrorState, EmptyState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/lib/utils/errors'

export default function VoiceBubblePage() {
  const router = useRouter()

  useEffect(() => {
    if (typeof window !== 'undefined' && !getToken()) router.replace('/login')
  }, [router])

  const { data: agents = [], isLoading, error, refetch } = useQuery({
    queryKey: ['voice-agents'],
    queryFn: voiceAgentsApi.list,
  })

  return (
    <div className="tb2-shell">
      <SubPageBar backHref="/call-agent" crumb="Web Voice Bubble" crumbIcon={<Globe size={13} className="text-cyan-300/70" />} />
      <CallAgentNav />

      <div className="max-w-2xl mx-auto px-6 py-8 space-y-6">
        <div className="tb2-rise space-y-2">
          <h1 className="text-xl font-bold text-white">Web Voice Bubble</h1>
          <p className="text-sm text-white/35">
            Let visitors talk to a standalone Voice Agent right on your website — own instructions, voice, and Knowledge Base, independent of your chatbot.
          </p>
          <div className="flex items-center gap-2 text-[11px] text-emerald-400/90 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-2 w-fit">
            <Check size={12} />
            No phone number required for this mode.
          </div>
        </div>

        {isLoading ? (
          <PageLoader />
        ) : error ? (
          <ErrorState
            title="Couldn't load your Voice Agents"
            description={getErrorMessage(error, 'Check your connection and that the backend is running.')}
            onRetry={() => refetch()}
          />
        ) : agents.length === 0 ? (
          <EmptyState
            icon={<Bot size={26} />}
            title="No Voice Agents yet"
            description="Create a Voice Agent first, then come back here to embed it as a Web Voice Bubble."
            action={
              <Button size="sm" icon={<Rocket size={13} />} onClick={() => router.push('/call-agent/agents')}>
                Create a Voice Agent
              </Button>
            }
          />
        ) : (
          <div className="space-y-3">
            {agents.map(agent => <VoiceAgentCard key={agent.id} agent={agent} />)}
          </div>
        )}
      </div>
    </div>
  )
}

function VoiceAgentCard({ agent }: { agent: VoiceAgent }) {
  const router = useRouter()
  const { toast } = useToast()
  const [copied, setCopied] = useState(false)

  const { data: embed } = useQuery({
    queryKey: ['voice-agent-embed', agent.id],
    queryFn: () => voiceAgentsApi.embedSnippet(agent.id),
  })

  const hasKnowledgeBase = true // Knowledge Base is always available per agent — see /call-agent/agents/[id]

  const copyEmbed = () => {
    if (!embed) return
    navigator.clipboard.writeText(embed.embed_snippet).then(() => {
      setCopied(true)
      toast('success', 'Embed code copied.')
      setTimeout(() => setCopied(false), 2000)
    }).catch(() => toast('error', 'Could not copy embed code.'))
  }

  return (
    <Card className="p-4 space-y-3 tb2-rise">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-white/85 truncate">{agent.name}</p>
          <p className="text-[11px] text-white/35 truncate">{agent.description || 'No description'}</p>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {agent.is_enabled ? (
            <Badge tone="success" dot>Enabled</Badge>
          ) : (
            <Badge tone="default">Disabled</Badge>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        <Badge tone="cyan">
          <Mic size={9} className="mr-0.5" />
          {agent.voice_id ? `Voice: ${agent.voice_id}` : 'Default voice'}
        </Badge>
        <Badge tone={hasKnowledgeBase ? 'accent' : 'default'}>
          <BookOpen size={9} className="mr-0.5" />
          Knowledge Base
        </Badge>
      </div>

      <div className="flex flex-wrap gap-2 pt-1">
        <Button
          size="sm"
          icon={<Settings2 size={12} />}
          onClick={() => router.push(`/call-agent/agents/${agent.id}`)}
        >
          Edit voice & Knowledge Base
        </Button>
        {embed && (
          <Button
            size="sm"
            variant="secondary"
            icon={copied ? <Check size={12} /> : <Code2 size={12} />}
            onClick={copyEmbed}
          >
            {copied ? 'Copied!' : 'Copy embed code'}
          </Button>
        )}
        {!embed && (
          <span className="text-[11px] text-white/30 self-center flex items-center gap-1">
            <Copy size={11} /> Loading embed snippet…
          </span>
        )}
      </div>
    </Card>
  )
}
