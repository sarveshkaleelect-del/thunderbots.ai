'use client'
/**
 * AI Call Agent — Voice Agent editor — /call-agent/agents/[id]
 *
 * NEW (Voice AI Part 5). The heart of the standalone Voice Agent product:
 * General, Instructions, Knowledge Base, Text Knowledge Base, Voice, and
 * Advanced all live here as tabs on ONE independent agent — nothing on
 * this page imports workflowsApi, knowledgeApi, or any Builder component.
 * Every field maps 1:1 to backend/app/models/voice_agent.py:VoiceAgent.
 */
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Bot, SlidersHorizontal, ScrollText, BookOpen, FileText, Mic2, Settings2,
  Upload, Plus, Trash2, RefreshCw, CheckCircle2, XCircle, Loader2, HelpCircle,
  PhoneCall, Rocket, Undo2,
} from 'lucide-react'
import { getToken } from '@/lib/api/auth'
import { voiceAgentsApi, callAgentApi } from '@/lib/api/callAgent'
import { settingsApi } from '@/lib/api/settings'
import type { AIProvider } from '@/types'
import type {
  VoiceAgent, VoiceAgentInstructions, VoiceAgentKBDocument, VoiceAgentUpdatePayload,
} from '@/types/callAgent'
import { Card, Badge } from '@/components/ui/Card'
import { Button, IconButton } from '@/components/ui/Button'
import { FieldLabel, Input, Textarea, Select } from '@/components/ui/Field'
import { SubPageBar } from '@/components/ui/TopBar'
import { PageLoader, ErrorState, EmptyState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/lib/utils/errors'
import { cn } from '@/lib/utils/cn'
import { TestVoiceAgentDialog } from '@/components/callAgent/TestVoiceAgentDialog'

type TabId = 'general' | 'instructions' | 'knowledge' | 'text-knowledge' | 'voice' | 'advanced'

const TABS: { id: TabId; label: string; icon: any }[] = [
  { id: 'general', label: 'General', icon: SlidersHorizontal },
  { id: 'instructions', label: 'Instructions', icon: ScrollText },
  { id: 'knowledge', label: 'Knowledge Base', icon: BookOpen },
  { id: 'text-knowledge', label: 'Text Knowledge Base', icon: FileText },
  { id: 'voice', label: 'Voice', icon: Mic2 },
  { id: 'advanced', label: 'Advanced', icon: Settings2 },
]

export default function VoiceAgentEditorPage() {
  const params = useParams<{ id: string }>()
  const agentId = params.id
  const router = useRouter()
  const qc = useQueryClient()
  const { toast } = useToast()
  const [tab, setTab] = useState<TabId>('general')
  const [showTest, setShowTest] = useState(false)

  useEffect(() => {
    if (typeof window !== 'undefined' && !getToken()) router.replace('/login')
  }, [router])

  const { data: agent, isLoading, error, refetch } = useQuery({
    queryKey: ['voice-agent', agentId],
    queryFn: () => voiceAgentsApi.get(agentId),
  })

  const updateMutation = useMutation({
    mutationFn: (payload: VoiceAgentUpdatePayload) => voiceAgentsApi.update(agentId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['voice-agent', agentId] })
      qc.invalidateQueries({ queryKey: ['voice-agents'] })
      toast('success', 'Saved.')
    },
    onError: (e) => toast('error', getErrorMessage(e, 'Could not save changes.')),
  })

  // NEW — Publish / Unpublish (additive; independent of the existing
  // is_enabled On/Off toggle further down the page).
  const publishMutation = useMutation({
    mutationFn: () => voiceAgentsApi.publish(agentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['voice-agent', agentId] })
      qc.invalidateQueries({ queryKey: ['voice-agents'] })
      toast('success', 'Voice Agent published.')
    },
    onError: (e) => toast('error', getErrorMessage(e, 'Could not publish.')),
  })
  const unpublishMutation = useMutation({
    mutationFn: () => voiceAgentsApi.unpublish(agentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['voice-agent', agentId] })
      qc.invalidateQueries({ queryKey: ['voice-agents'] })
      toast('success', 'Voice Agent unpublished — back to draft.')
    },
    onError: (e) => toast('error', getErrorMessage(e, 'Could not unpublish.')),
  })

  return (
    <div className="tb2-shell">
      <SubPageBar
        backHref="/call-agent/agents"
        crumb={agent?.name || 'Voice Agent'}
        crumbIcon={<Bot size={13} className="text-cyan-300/70" />}
        right={agent && (
          <>
            <Badge tone={agent.status === 'published' ? 'success' : 'default'} dot>
              {agent.status === 'published' ? 'Published' : 'Draft'}
            </Badge>
            <Button
              variant="secondary"
              size="sm"
              icon={<PhoneCall size={13} />}
              onClick={() => setShowTest(true)}
            >
              Test
            </Button>
            {agent.status === 'published' ? (
              <Button
                variant="secondary"
                size="sm"
                icon={<Undo2 size={13} />}
                loading={unpublishMutation.isPending}
                onClick={() => unpublishMutation.mutate()}
              >
                Unpublish
              </Button>
            ) : (
              <Button
                variant="primary"
                size="sm"
                icon={<Rocket size={13} />}
                loading={publishMutation.isPending}
                onClick={() => publishMutation.mutate()}
              >
                Publish
              </Button>
            )}
          </>
        )}
      />

      {agent && showTest && (
        <TestVoiceAgentDialog agent={agent} onClose={() => setShowTest(false)} />
      )}

      <div className="max-w-5xl mx-auto px-3 sm:px-6 py-6">
        {isLoading ? (
          <PageLoader />
        ) : error || !agent ? (
          <ErrorState
            title="Couldn't load this Voice Agent"
            description={getErrorMessage(error, 'It may have been deleted.')}
            onRetry={() => refetch()}
          />
        ) : (
          <>
            <div className="tb2-glass flex items-center gap-1 p-1 rounded-2xl overflow-x-auto no-scrollbar mb-6">
              {TABS.map(t => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={cn(
                    'flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-xl whitespace-nowrap transition flex-shrink-0',
                    tab === t.id ? 'bg-white/[0.08] text-white' : 'text-white/40 hover:text-white/75 hover:bg-white/[0.04]'
                  )}
                >
                  <t.icon size={13} />
                  {t.label}
                </button>
              ))}
            </div>

            {tab === 'general' && <GeneralTab agent={agent} onSave={p => updateMutation.mutate(p)} saving={updateMutation.isPending} />}
            {tab === 'instructions' && <InstructionsTab agent={agent} onSave={p => updateMutation.mutate(p)} saving={updateMutation.isPending} />}
            {tab === 'knowledge' && <KnowledgeTab agentId={agentId} kbType="pdf" />}
            {tab === 'text-knowledge' && <KnowledgeTab agentId={agentId} kbType="text" />}
            {tab === 'voice' && <VoiceTab agent={agent} onSave={p => updateMutation.mutate(p)} saving={updateMutation.isPending} />}
            {tab === 'advanced' && <AdvancedTab agent={agent} onSave={p => updateMutation.mutate(p)} saving={updateMutation.isPending} />}
          </>
        )}
      </div>
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────

type TabProps = { agent: VoiceAgent; onSave: (p: VoiceAgentUpdatePayload) => void; saving: boolean }

function GeneralTab({ agent, onSave, saving }: TabProps) {
  const [name, setName] = useState(agent.name)
  const [description, setDescription] = useState(agent.description)
  const [provider, setProvider] = useState(agent.ai_provider || '')
  const [model, setModel] = useState(agent.ai_model || '')
  const [personality, setPersonality] = useState(agent.personality)
  const [goals, setGoals] = useState(agent.goals)
  const [welcome, setWelcome] = useState(agent.welcome_message)
  const [fallback, setFallback] = useState(agent.fallback_message)

  const { data: providers = [] } = useQuery({ queryKey: ['providers'], queryFn: settingsApi.listProviders })
  const currentProvider = (providers as AIProvider[]).find(p => p.id === provider)

  return (
    <Card className="p-5 space-y-5">
      <div className="grid sm:grid-cols-2 gap-4">
        <div>
          <FieldLabel>Name</FieldLabel>
          <Input value={name} onChange={e => setName(e.target.value)} />
        </div>
        <div>
          <FieldLabel hint="Optional">Description</FieldLabel>
          <Input value={description} onChange={e => setDescription(e.target.value)} />
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <div>
          <FieldLabel hint="Leave blank to use your default">AI Provider</FieldLabel>
          <Select value={provider} onChange={e => { setProvider(e.target.value); setModel('') }}>
            <option value="">Default</option>
            {providers.map(p => (
              <option key={p.id} value={p.id} disabled={!p.configured && p.requires_key}>
                {p.name}{!p.configured && p.requires_key ? ' (no key)' : ''}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <FieldLabel>Model</FieldLabel>
          <Select value={model} onChange={e => setModel(e.target.value)}>
            <option value="">Default</option>
            {(currentProvider?.models || []).map(m => <option key={m} value={m}>{m}</option>)}
          </Select>
        </div>
      </div>

      <div>
        <FieldLabel hint="How the agent should come across">Personality</FieldLabel>
        <Textarea rows={2} value={personality} onChange={e => setPersonality(e.target.value)} placeholder="Warm, patient, and professional." />
      </div>
      <div>
        <FieldLabel hint="What this agent is trying to accomplish on every call">Goals</FieldLabel>
        <Textarea rows={2} value={goals} onChange={e => setGoals(e.target.value)} placeholder="Answer questions and book appointments." />
      </div>
      <div className="grid sm:grid-cols-2 gap-4">
        <div>
          <FieldLabel>Welcome message</FieldLabel>
          <Textarea rows={2} value={welcome} onChange={e => setWelcome(e.target.value)} />
        </div>
        <div>
          <FieldLabel>Fallback message</FieldLabel>
          <Textarea rows={2} value={fallback} onChange={e => setFallback(e.target.value)} />
        </div>
      </div>

      <div className="flex justify-end">
        <Button
          loading={saving}
          onClick={() => onSave({
            name, description, ai_provider: provider || null, ai_model: model || null,
            personality, goals, welcome_message: welcome, fallback_message: fallback,
          })}
        >
          Save
        </Button>
      </div>
    </Card>
  )
}

const INSTRUCTION_FIELDS: { key: keyof VoiceAgentInstructions; label: string; placeholder: string }[] = [
  { key: 'role', label: 'Role', placeholder: 'You are a front-desk assistant for Acme Dental.' },
  { key: 'behaviour', label: 'Behaviour', placeholder: 'Always confirm the caller\'s name before proceeding.' },
  { key: 'tone', label: 'Tone', placeholder: 'Friendly, concise, never pushy.' },
  { key: 'rules', label: 'Rules', placeholder: 'Never quote prices without checking the price list.' },
  { key: 'business_policies', label: 'Business policies', placeholder: 'Cancellations require 24 hours notice.' },
  { key: 'sales_instructions', label: 'Sales instructions', placeholder: 'Offer the premium plan only if the caller asks about upgrades.' },
  { key: 'appointment_booking_rules', label: 'Appointment booking rules', placeholder: 'Only book Mon-Fri, 9am-5pm.' },
  { key: 'escalation_rules', label: 'Escalation rules', placeholder: 'If the caller is angry or asks for a manager, offer human handoff.' },
  { key: 'response_restrictions', label: 'Response restrictions', placeholder: 'Never give medical or legal advice.' },
]

function InstructionsTab({ agent, onSave, saving }: TabProps) {
  const [instructions, setInstructions] = useState<VoiceAgentInstructions>(agent.instructions || {})

  return (
    <Card className="p-5 space-y-5">
      <p className="text-xs text-white/35">
        This works like a dedicated system prompt for this Voice Agent only — completely separate from any chatbot Workflow.
      </p>
      {INSTRUCTION_FIELDS.map(f => (
        <div key={f.key}>
          <FieldLabel>{f.label}</FieldLabel>
          <Textarea
            rows={2}
            value={instructions[f.key] || ''}
            onChange={e => setInstructions(i => ({ ...i, [f.key]: e.target.value }))}
            placeholder={f.placeholder}
          />
        </div>
      ))}
      <div className="flex justify-end">
        <Button loading={saving} onClick={() => onSave({ instructions })}>Save</Button>
      </div>
    </Card>
  )
}

function VoiceTab({ agent, onSave, saving }: TabProps) {
  const [voiceProvider, setVoiceProvider] = useState(agent.voice_provider || '')
  const [voiceId, setVoiceId] = useState(agent.voice_id || '')
  const [language, setLanguage] = useState(agent.language)
  const [speed, setSpeed] = useState(agent.speaking_speed)

  const { data: providers = [] } = useQuery({ queryKey: ['call-voices'], queryFn: callAgentApi.listVoices })
  const currentProvider = providers.find(p => p.name.toLowerCase() === voiceProvider.toLowerCase())

  return (
    <Card className="p-5 space-y-5">
      <div className="grid sm:grid-cols-2 gap-4">
        <div>
          <FieldLabel>Voice provider</FieldLabel>
          <Select value={voiceProvider} onChange={e => { setVoiceProvider(e.target.value); setVoiceId('') }}>
            <option value="">Default</option>
            {providers.map(p => (
              <option key={p.name} value={p.name} disabled={!p.configured}>
                {p.name}{!p.configured ? ' (no key)' : ''}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <FieldLabel>Voice</FieldLabel>
          <Select value={voiceId} onChange={e => setVoiceId(e.target.value)}>
            <option value="">Default</option>
            {(currentProvider?.voices || []).map(v => <option key={v.id} value={v.id}>{v.name} ({v.gender})</option>)}
          </Select>
        </div>
      </div>
      <div className="grid sm:grid-cols-2 gap-4">
        <div>
          <FieldLabel>Language</FieldLabel>
          <Input value={language} onChange={e => setLanguage(e.target.value)} placeholder="en-US" />
        </div>
        <div>
          <FieldLabel hint={`${speed.toFixed(2)}x`}>Speaking speed</FieldLabel>
          <input
            type="range" min={0.5} max={2} step={0.05} value={speed}
            onChange={e => setSpeed(parseFloat(e.target.value))}
            className="w-full accent-cyan-400"
          />
        </div>
      </div>
      <div className="flex justify-end">
        <Button
          loading={saving}
          onClick={() => onSave({ voice_provider: voiceProvider || null, voice_id: voiceId || null, language, speaking_speed: speed })}
        >
          Save
        </Button>
      </div>
    </Card>
  )
}

function AdvancedTab({ agent, onSave, saving }: TabProps) {
  const [temperature, setTemperature] = useState(agent.temperature)
  const [silence, setSilence] = useState(agent.silence_timeout_seconds)
  const [interrupt, setInterrupt] = useState(agent.interrupt_enabled)
  const [memory, setMemory] = useState(agent.memory_enabled)
  const [history, setHistory] = useState(agent.conversation_history_enabled)
  const [enabled, setEnabled] = useState(agent.is_enabled)

  return (
    <Card className="p-5 space-y-5">
      <div className="grid sm:grid-cols-2 gap-4">
        <div>
          <FieldLabel hint={temperature.toFixed(2)}>Creativity / Temperature</FieldLabel>
          <input type="range" min={0} max={1.5} step={0.05} value={temperature} onChange={e => setTemperature(parseFloat(e.target.value))} className="w-full accent-cyan-400" />
        </div>
        <div>
          <FieldLabel>Silence timeout (seconds)</FieldLabel>
          <Input type="number" min={1} max={60} value={silence} onChange={e => setSilence(parseInt(e.target.value) || 5)} />
        </div>
      </div>

      <div className="space-y-2">
        {[
          { label: 'Interrupt / barge-in — caller can talk over the agent', value: interrupt, set: setInterrupt },
          { label: 'Memory — remember facts across the conversation', value: memory, set: setMemory },
          { label: 'Conversation history — keep prior turns in context', value: history, set: setHistory },
          { label: 'Voice Agent enabled', value: enabled, set: setEnabled },
        ].map(row => (
          <label key={row.label} className="flex items-center gap-2 text-sm text-white/70 cursor-pointer">
            <input type="checkbox" checked={row.value} onChange={e => row.set(e.target.checked)} className="accent-cyan-400" />
            {row.label}
          </label>
        ))}
      </div>

      <div className="flex justify-end">
        <Button
          loading={saving}
          onClick={() => onSave({
            temperature, silence_timeout_seconds: silence, interrupt_enabled: interrupt,
            memory_enabled: memory, conversation_history_enabled: history, is_enabled: enabled,
          })}
        >
          Save
        </Button>
      </div>
    </Card>
  )
}

// ────────────────────────────────────────────────────────────────────────
// Knowledge Base / Text Knowledge Base — shared component, filtered by
// kb_type so the two nav sections show the right documents. FAQ entries
// live under the PDF/Knowledge Base tab alongside file uploads.

function statusIcon(status: VoiceAgentKBDocument['status']) {
  if (status === 'ready') return <CheckCircle2 size={13} className="text-emerald-400" />
  if (status === 'error') return <XCircle size={13} className="text-red-400" />
  return <Loader2 size={13} className="text-amber-400 animate-spin" />
}

function KnowledgeTab({ agentId, kbType }: { agentId: string; kbType: 'pdf' | 'text' }) {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [showTextForm, setShowTextForm] = useState(false)
  const [showFaqForm, setShowFaqForm] = useState(false)
  const [textTitle, setTextTitle] = useState('')
  const [textContent, setTextContent] = useState('')
  const [faqTitle, setFaqTitle] = useState('FAQ')
  const [faqItems, setFaqItems] = useState([{ question: '', answer: '' }])

  const { data: docs = [], isLoading, error, refetch } = useQuery({
    queryKey: ['voice-agent-kb', agentId],
    queryFn: () => voiceAgentsApi.listKnowledge(agentId),
  })

  const relevantDocs = docs.filter(d => (kbType === 'text' ? d.kb_type === 'text' : d.kb_type !== 'text'))

  const invalidate = () => qc.invalidateQueries({ queryKey: ['voice-agent-kb', agentId] })

  const uploadMutation = useMutation({
    mutationFn: (file: File) => voiceAgentsApi.uploadPdf(agentId, file),
    onSuccess: () => { invalidate(); toast('success', 'Uploading and indexing…') },
    onError: (e) => toast('error', getErrorMessage(e, 'Upload failed.')),
  })

  const textMutation = useMutation({
    mutationFn: () => voiceAgentsApi.createText(agentId, textTitle, textContent),
    onSuccess: () => { invalidate(); toast('success', 'Text entry added.'); setShowTextForm(false); setTextTitle(''); setTextContent('') },
    onError: (e) => toast('error', getErrorMessage(e, 'Could not save this text entry.')),
  })

  const faqMutation = useMutation({
    mutationFn: () => voiceAgentsApi.createFaq(agentId, faqTitle, faqItems.filter(i => i.question.trim() && i.answer.trim())),
    onSuccess: () => { invalidate(); toast('success', 'FAQ added.'); setShowFaqForm(false); setFaqTitle('FAQ'); setFaqItems([{ question: '', answer: '' }]) },
    onError: (e) => toast('error', getErrorMessage(e, 'Could not save this FAQ.')),
  })

  const retryMutation = useMutation({
    mutationFn: (docId: string) => voiceAgentsApi.retryDocument(agentId, docId),
    onSuccess: () => invalidate(),
    onError: (e) => toast('error', getErrorMessage(e, 'Retry failed.')),
  })

  const deleteMutation = useMutation({
    mutationFn: (docId: string) => voiceAgentsApi.deleteDocument(agentId, docId),
    onSuccess: () => { invalidate(); toast('success', 'Deleted.') },
    onError: (e) => toast('error', getErrorMessage(e, 'Could not delete this document.')),
  })

  return (
    <div className="space-y-4">
      <Card className="p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-white/85">{kbType === 'text' ? 'Text Knowledge Base' : 'Knowledge Base'}</h3>
            <p className="text-[11px] text-white/35 mt-0.5">
              {kbType === 'text'
                ? 'Paste text directly — completely independent from the chatbot Knowledge Base.'
                : 'Upload PDFs, or add FAQ entries. Independent storage from the chatbot Knowledge Base.'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {kbType === 'pdf' && (
              <>
                <label className="tb2-btn-primary text-white text-xs font-semibold px-3 py-2 rounded-xl cursor-pointer inline-flex items-center gap-1.5">
                  <Upload size={12} />
                  Upload PDF
                  <input
                    type="file" accept=".pdf,.docx,.txt,.md" className="hidden"
                    onChange={e => { const f = e.target.files?.[0]; if (f) uploadMutation.mutate(f); e.target.value = '' }}
                  />
                </label>
                <Button size="sm" variant="secondary" icon={<HelpCircle size={12} />} onClick={() => setShowFaqForm(true)}>Add FAQ</Button>
              </>
            )}
            {kbType === 'text' && (
              <Button size="sm" icon={<Plus size={12} />} onClick={() => setShowTextForm(true)}>Add text</Button>
            )}
          </div>
        </div>

        {showTextForm && (
          <div className="space-y-3 border border-white/10 rounded-xl p-3">
            <Input value={textTitle} onChange={e => setTextTitle(e.target.value)} placeholder="Title (optional)" />
            <Textarea rows={6} value={textContent} onChange={e => setTextContent(e.target.value)} placeholder="Paste text here…" />
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="secondary" onClick={() => setShowTextForm(false)}>Cancel</Button>
              <Button size="sm" disabled={!textContent.trim()} loading={textMutation.isPending} onClick={() => textMutation.mutate()}>Save</Button>
            </div>
          </div>
        )}

        {showFaqForm && (
          <div className="space-y-3 border border-white/10 rounded-xl p-3">
            <Input value={faqTitle} onChange={e => setFaqTitle(e.target.value)} placeholder="FAQ title" />
            {faqItems.map((item, i) => (
              <div key={i} className="grid sm:grid-cols-2 gap-2">
                <Input value={item.question} onChange={e => setFaqItems(items => items.map((it, idx) => idx === i ? { ...it, question: e.target.value } : it))} placeholder="Question" />
                <Input value={item.answer} onChange={e => setFaqItems(items => items.map((it, idx) => idx === i ? { ...it, answer: e.target.value } : it))} placeholder="Answer" />
              </div>
            ))}
            <div className="flex justify-between gap-2">
              <Button size="sm" variant="secondary" icon={<Plus size={12} />} onClick={() => setFaqItems(items => [...items, { question: '', answer: '' }])}>Add row</Button>
              <div className="flex gap-2">
                <Button size="sm" variant="secondary" onClick={() => setShowFaqForm(false)}>Cancel</Button>
                <Button size="sm" loading={faqMutation.isPending} onClick={() => faqMutation.mutate()}>Save</Button>
              </div>
            </div>
          </div>
        )}
      </Card>

      {isLoading ? (
        <PageLoader />
      ) : error ? (
        <ErrorState title="Couldn't load Knowledge Base documents" onRetry={() => refetch()} />
      ) : relevantDocs.length === 0 ? (
        <EmptyState icon={<BookOpen size={22} />} title="Nothing here yet" description="Add a document to get started." />
      ) : (
        <div className="space-y-2">
          {relevantDocs.map(doc => (
            <Card key={doc.id} className="p-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2.5 min-w-0">
                {statusIcon(doc.status)}
                <div className="min-w-0">
                  <p className="text-sm text-white/80 truncate">{doc.title}</p>
                  <p className="text-[10px] text-white/30">
                    {doc.kb_type.toUpperCase()} · {doc.status === 'ready' ? `${doc.chunk_count} chunks` : doc.status}
                    {doc.error_message ? ` — ${doc.error_message}` : ''}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                {doc.status === 'error' && (
                  <IconButton aria-label="Retry" onClick={() => retryMutation.mutate(doc.id)}><RefreshCw size={13} /></IconButton>
                )}
                <IconButton aria-label="Delete" variant="danger" onClick={() => deleteMutation.mutate(doc.id)}><Trash2 size={13} /></IconButton>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
