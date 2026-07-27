'use client'
/**
 * AI Call Agent — Embed — /call-agent/embed
 *
 * NEW (Voice AI Part 5). Per-Voice-Agent embed snippet for the Web Voice
 * Bubble, reusing GET /call-agent/agents/{id}/embed. Independent of the
 * chatbot's own deploy/embed flow (lib/api/deploy.ts) — not imported here.
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Code2, Copy, Check } from 'lucide-react'
import { getToken } from '@/lib/api/auth'
import { voiceAgentsApi } from '@/lib/api/callAgent'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Field'
import { SubPageBar } from '@/components/ui/TopBar'
import { CallAgentNav } from '@/components/callAgent/CallAgentNav'
import { EmptyState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'

export default function EmbedPage() {
  const router = useRouter()
  const { toast } = useToast()
  const [agentId, setAgentId] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (typeof window !== 'undefined' && !getToken()) router.replace('/login')
  }, [router])

  const { data: agents = [] } = useQuery({ queryKey: ['voice-agents'], queryFn: voiceAgentsApi.list })
  useEffect(() => {
    if (!agentId && agents.length > 0) setAgentId(agents[0].id)
  }, [agents, agentId])

  const { data: embed } = useQuery({
    queryKey: ['voice-agent-embed', agentId],
    queryFn: () => voiceAgentsApi.embedSnippet(agentId),
    enabled: !!agentId,
  })

  const copy = () => {
    if (!embed) return
    navigator.clipboard.writeText(embed.embed_snippet).then(() => {
      setCopied(true)
      toast('success', 'Embed code copied.')
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="tb2-shell">
      <SubPageBar backHref="/call-agent" crumb="Embed" crumbIcon={<Code2 size={13} className="text-cyan-300/70" />} />
      <CallAgentNav />

      <div className="max-w-2xl mx-auto px-3 sm:px-6 py-8 space-y-6">
        <div className="tb2-rise">
          <h1 className="text-xl font-bold text-white">Embed</h1>
          <p className="text-sm text-white/35 mt-1">Add a Voice Agent's voice bubble to any website.</p>
        </div>

        {agents.length === 0 ? (
          <EmptyState icon={<Code2 size={22} />} title="No Voice Agents yet" description="Create a Voice Agent first, then come back here to embed it." />
        ) : (
          <>
            <div>
              <Select value={agentId} onChange={e => setAgentId(e.target.value)}>
                {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
              </Select>
            </div>

            <Card className="p-4 space-y-3">
              <pre className="text-xs text-white/60 bg-black/30 rounded-xl p-3 overflow-x-auto whitespace-pre-wrap break-all">
                {embed?.embed_snippet || 'Loading…'}
              </pre>
              <Button size="sm" variant="secondary" icon={copied ? <Check size={12} /> : <Copy size={12} />} onClick={copy} disabled={!embed}>
                {copied ? 'Copied!' : 'Copy snippet'}
              </Button>
            </Card>

            <p className="text-xs text-white/30">
              Paste this snippet right before the closing <code className="text-white/50">&lt;/body&gt;</code> tag of your site.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
