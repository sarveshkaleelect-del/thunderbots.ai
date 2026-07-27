'use client'
/**
 * AI Call Agent — Voice Agents — /call-agent/agents
 *
 * NEW (Voice AI Part 5). Standalone list/create page for independent
 * Voice Agents (own AI provider/model/instructions/personality/voice/
 * Knowledge Base). Nothing here imports workflowsApi or knowledgeApi —
 * see lib/api/callAgent.ts:voiceAgentsApi for the dedicated endpoints.
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Bot, Plus, Trash2, Settings2, Zap, ZapOff } from 'lucide-react'
import { getToken } from '@/lib/api/auth'
import { voiceAgentsApi } from '@/lib/api/callAgent'
import type { VoiceAgent } from '@/types/callAgent'
import { Card, Badge } from '@/components/ui/Card'
import { Button, IconButton } from '@/components/ui/Button'
import { FieldLabel, Input, Textarea } from '@/components/ui/Field'
import { SubPageBar } from '@/components/ui/TopBar'
import { CallAgentNav } from '@/components/callAgent/CallAgentNav'
import { PageLoader, ErrorState, EmptyState, SkeletonGrid } from '@/components/ui/States'
import { Modal } from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/lib/utils/errors'

export default function VoiceAgentsPage() {
  const router = useRouter()
  const qc = useQueryClient()
  const { toast } = useToast()

  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [deleting, setDeleting] = useState<VoiceAgent | null>(null)

  useEffect(() => {
    if (typeof window !== 'undefined' && !getToken()) router.replace('/login')
  }, [router])

  const { data: agents = [], isLoading, error, refetch } = useQuery({
    queryKey: ['voice-agents'],
    queryFn: voiceAgentsApi.list,
  })

  const createMutation = useMutation({
    mutationFn: () => voiceAgentsApi.create({ name: name.trim(), description: description.trim() }),
    onSuccess: (agent) => {
      qc.invalidateQueries({ queryKey: ['voice-agents'] })
      toast('success', 'Voice Agent created.')
      setShowCreate(false)
      setName('')
      setDescription('')
      router.push(`/call-agent/agents/${agent.id}`)
    },
    onError: (e) => toast('error', getErrorMessage(e, 'Could not create the Voice Agent.')),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => voiceAgentsApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['voice-agents'] })
      toast('success', 'Voice Agent deleted.')
      setDeleting(null)
    },
    onError: (e) => toast('error', getErrorMessage(e, 'Could not delete the Voice Agent.')),
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_enabled }: { id: string; is_enabled: boolean }) =>
      voiceAgentsApi.update(id, { is_enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['voice-agents'] }),
    onError: (e) => toast('error', getErrorMessage(e, 'Could not update the Voice Agent.')),
  })

  return (
    <div className="tb2-shell">
      <SubPageBar backHref="/call-agent" crumb="Voice Agents" crumbIcon={<Bot size={13} className="text-cyan-300/70" />} />
      <CallAgentNav />

      <div className="max-w-5xl mx-auto px-3 sm:px-6 py-8 space-y-6">
        <div className="flex items-center justify-between gap-3 tb2-rise">
          <div>
            <h1 className="text-xl font-bold text-white">Voice Agents</h1>
            <p className="text-sm text-white/35 mt-1">
              Create unlimited standalone AI Call Agents — each with its own provider, instructions, voice, and Knowledge Base.
            </p>
          </div>
          <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)} data-tutorial="call-agent-create">New Voice Agent</Button>
        </div>

        {isLoading ? (
          <SkeletonGrid count={3} />
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
            description="Create your first standalone AI Call Agent to get started."
            action={<Button size="sm" icon={<Plus size={13} />} onClick={() => setShowCreate(true)}>New Voice Agent</Button>}
          />
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {agents.map(agent => (
              <Card key={agent.id} className="p-4 space-y-3 tb2-rise">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-white/85 truncate">{agent.name}</p>
                    <p className="text-[11px] text-white/35 truncate mt-0.5">{agent.description || 'No description'}</p>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    {/* NEW — Draft/Published lifecycle status, separate from is_enabled */}
                    <Badge tone={agent.status === 'published' ? 'success' : 'default'}>
                      {agent.status === 'published' ? 'Published' : 'Draft'}
                    </Badge>
                    {agent.is_enabled ? (
                      <Badge tone="success" dot>On</Badge>
                    ) : (
                      <Badge tone="default">Off</Badge>
                    )}
                  </div>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {agent.ai_provider && <Badge tone="accent">{agent.ai_provider}</Badge>}
                  {agent.voice_id && <Badge tone="cyan">{agent.voice_id}</Badge>}
                  <Badge tone="default">{agent.language}</Badge>
                </div>

                <div className="flex items-center gap-2 pt-1">
                  <Button size="sm" icon={<Settings2 size={12} />} onClick={() => router.push(`/call-agent/agents/${agent.id}`)}>
                    Configure
                  </Button>
                  <IconButton
                    aria-label={agent.is_enabled ? 'Disable' : 'Enable'}
                    onClick={() => toggleMutation.mutate({ id: agent.id, is_enabled: !agent.is_enabled })}
                  >
                    {agent.is_enabled ? <ZapOff size={14} /> : <Zap size={14} />}
                  </IconButton>
                  <IconButton aria-label="Delete" variant="danger" onClick={() => setDeleting(agent)}>
                    <Trash2 size={14} />
                  </IconButton>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      {showCreate && (
        <Modal onClose={() => setShowCreate(false)} title="New Voice Agent" subtitle="You can configure everything else after creating it.">
          <div className="space-y-4">
            <div>
              <FieldLabel>Name</FieldLabel>
              <Input value={name} onChange={e => setName(e.target.value)} placeholder="Support Line Agent" autoFocus />
            </div>
            <div>
              <FieldLabel hint="Optional">Description</FieldLabel>
              <Textarea rows={3} value={description} onChange={e => setDescription(e.target.value)} placeholder="What is this agent for?" />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>Cancel</Button>
              <Button
                disabled={!name.trim()}
                loading={createMutation.isPending}
                onClick={() => createMutation.mutate()}
              >
                Create
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {deleting && (
        <Modal onClose={() => setDeleting(null)} title="Delete Voice Agent?" subtitle={deleting.name}>
          <div className="space-y-4">
            <p className="text-sm text-white/50">
              This permanently deletes the agent, its Instructions, and its entire Knowledge Base. Any phone number bound to it will be unbound. This cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setDeleting(null)}>Cancel</Button>
              <Button variant="danger" loading={deleteMutation.isPending} onClick={() => deleteMutation.mutate(deleting.id)}>
                Delete
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
