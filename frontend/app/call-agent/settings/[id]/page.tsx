'use client'
/**
 * NEW (AI Call Agent — Voice AI Part 3) — /call-agent/settings/[id]
 *
 * Binds a verified + AI-Call-Agent-enabled phone number to a Workflow and
 * configures its call voice/speed/language/recording — the workflow
 * binding Part 2 explicitly left out. Also lets the owner place a test
 * outbound AI call. Its own route, so /call-agent/page.tsx (Part 2) is
 * never touched.
 */
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Settings2, PhoneOutgoing, Mic, Gauge, Languages, Bot,
  MessageSquare, ShieldAlert, BookOpen, Clock, Zap,
} from 'lucide-react'
import { getToken } from '@/lib/api/auth'
import { callAgentApi, voiceAgentsApi } from '@/lib/api/callAgent'
import { workflowsApi } from '@/lib/api/workflows'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { FieldLabel, Input, Select, Textarea } from '@/components/ui/Field'
import { SubPageBar } from '@/components/ui/TopBar'
import { CallAgentNav } from '@/components/callAgent/CallAgentNav'
import { PageLoader, ErrorState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/lib/utils/errors'
import type { BusinessHours, InterruptBehavior, PromptScope } from '@/types/callAgent'

const LANGUAGES = [
  { code: 'en-US', label: 'English (US)' },
  { code: 'en-GB', label: 'English (UK)' },
  { code: 'es-ES', label: 'Spanish' },
  { code: 'fr-FR', label: 'French' },
  { code: 'de-DE', label: 'German' },
  { code: 'pt-BR', label: 'Portuguese (Brazil)' },
  { code: 'hi-IN', label: 'Hindi' },
  { code: 'ja-JP', label: 'Japanese' },
]

const WEEKDAYS: Array<{ key: keyof BusinessHours['days']; label: string }> = [
  { key: 'mon', label: 'Mon' }, { key: 'tue', label: 'Tue' }, { key: 'wed', label: 'Wed' },
  { key: 'thu', label: 'Thu' }, { key: 'fri', label: 'Fri' }, { key: 'sat', label: 'Sat' }, { key: 'sun', label: 'Sun' },
]
const DEFAULT_BUSINESS_HOURS: BusinessHours = {
  enabled: false, timezone: 'UTC',
  days: { mon: { open: '09:00', close: '17:00' }, tue: { open: '09:00', close: '17:00' }, wed: { open: '09:00', close: '17:00' }, thu: { open: '09:00', close: '17:00' }, fri: { open: '09:00', close: '17:00' } },
}

export default function CallSettingsPage() {
  const params = useParams<{ id: string }>()
  const numberId = params.id
  const router = useRouter()
  const qc = useQueryClient()
  const { toast } = useToast()

  useEffect(() => {
    if (typeof window !== 'undefined' && !getToken()) router.replace('/login')
  }, [router])

  const { data: settings, isLoading, error, refetch } = useQuery({
    queryKey: ['call-agent', 'call-settings', numberId],
    queryFn: () => callAgentApi.getCallSettings(numberId),
  })
  const { data: voiceAgents = [] } = useQuery({ queryKey: ['voice-agents'], queryFn: voiceAgentsApi.list })
  const { data: workflows = [] } = useQuery({ queryKey: ['workflows'], queryFn: workflowsApi.list })
  const { data: voiceProviders = [] } = useQuery({ queryKey: ['call-agent', 'voices'], queryFn: callAgentApi.listVoices })

  const [voiceAgentId, setVoiceAgentId] = useState('')
  const [useLegacyWorkflow, setUseLegacyWorkflow] = useState(false)
  const [workflowId, setWorkflowId] = useState('')
  const [voiceProvider, setVoiceProvider] = useState('gemini')
  const [voiceId, setVoiceId] = useState('')
  const [speed, setSpeed] = useState(1.0)
  const [language, setLanguage] = useState('en-US')
  const [recordingEnabled, setRecordingEnabled] = useState(false)
  const [toNumber, setToNumber] = useState('')

  // NEW (Voice AI Part 4) — admin controls
  const [greetingMessage, setGreetingMessage] = useState('')
  const [fallbackPrompt, setFallbackPrompt] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [promptScope, setPromptScope] = useState<PromptScope>('open')
  const [interruptBehavior, setInterruptBehavior] = useState<InterruptBehavior>('interrupt')
  const [businessHours, setBusinessHours] = useState<BusinessHours>(DEFAULT_BUSINESS_HOURS)

  useEffect(() => {
    if (!settings) return
    setVoiceAgentId(settings.voice_agent_id || '')
    setWorkflowId(settings.workflow_id || '')
    setUseLegacyWorkflow(!!settings.workflow_id && !settings.voice_agent_id)
    setVoiceProvider(settings.call_settings.voice_provider || 'gemini')
    setVoiceId(settings.call_settings.voice_id || '')
    setSpeed(settings.call_settings.speed ?? 1.0)
    setLanguage(settings.call_settings.language || 'en-US')
    setRecordingEnabled(!!settings.call_settings.recording_enabled)
    setGreetingMessage(settings.call_settings.greeting_message || '')
    setFallbackPrompt(settings.call_settings.fallback_prompt || '')
    setSystemPrompt(settings.call_settings.system_prompt || '')
    setPromptScope(settings.call_settings.prompt_scope || 'open')
    setInterruptBehavior(settings.call_settings.interrupt_behavior || 'interrupt')
    setBusinessHours(settings.call_settings.business_hours || DEFAULT_BUSINESS_HOURS)
  }, [settings])

  const saveMutation = useMutation({
    mutationFn: () => callAgentApi.updateCallSettings(numberId, {
      voice_agent_id: useLegacyWorkflow ? null : (voiceAgentId || null),
      workflow_id: useLegacyWorkflow ? (workflowId || null) : null,
      voice_provider: voiceProvider,
      voice_id: voiceId || undefined,
      speed,
      language,
      recording_enabled: recordingEnabled,
      greeting_message: greetingMessage,
      fallback_prompt: fallbackPrompt,
      system_prompt: systemPrompt,
      prompt_scope: promptScope,
      interrupt_behavior: interruptBehavior,
      business_hours: businessHours,
    }),
    onSuccess: () => {
      toast('success', 'Call settings saved.')
      qc.invalidateQueries({ queryKey: ['call-agent', 'call-settings', numberId] })
    },
    onError: (err) => toast('error', getErrorMessage(err, 'Could not save call settings.')),
  })

  const callMutation = useMutation({
    mutationFn: () => callAgentApi.placeOutboundCall({ phone_number_id: numberId, to_number: toNumber }),
    onSuccess: (call) => {
      toast('success', `Calling ${call.to_number}…`)
      router.push('/call-agent/calls')
    },
    onError: (err) => toast('error', getErrorMessage(err, 'Could not place that call.')),
  })

  const selectedProvider = voiceProviders.find(p => p.credential_provider === voiceProvider || p.name.toLowerCase().includes(voiceProvider))

  if (isLoading) {
    return (
      <div className="tb2-shell">
        <SubPageBar backHref="/call-agent" crumb="Call settings" crumbIcon={<Settings2 size={13} className="text-cyan-300/70" />} />
        <PageLoader />
      </div>
    )
  }

  if (error) {
    return (
      <div className="tb2-shell">
        <SubPageBar backHref="/call-agent" crumb="Call settings" crumbIcon={<Settings2 size={13} className="text-cyan-300/70" />} />
        <div className="max-w-xl mx-auto px-6 py-10">
          <ErrorState
            title="Couldn't load call settings"
            description={getErrorMessage(error, 'Enable AI Call Agent for this number first.')}
            onRetry={() => refetch()}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="tb2-shell">
      <SubPageBar backHref="/call-agent" crumb="Call settings" crumbIcon={<Settings2 size={13} className="text-cyan-300/70" />} />
      <CallAgentNav />

      <div className="max-w-xl mx-auto px-6 py-10 space-y-6">
        <div className="tb2-rise">
          <h1 className="text-xl font-bold text-white">AI Call Agent settings</h1>
          <p className="text-sm text-white/35 mt-1">
            Choose which Voice Agent answers calls on this number, and how it sounds.
          </p>
        </div>

        <Card className="p-4 space-y-4 tb2-rise">
          {!useLegacyWorkflow ? (
            <div>
              <FieldLabel hint="Its own Instructions, personality & Knowledge Base — see Voice Agents">
                <span className="flex items-center gap-1.5"><Bot size={12} />Voice Agent</span>
              </FieldLabel>
              <Select value={voiceAgentId} onChange={e => setVoiceAgentId(e.target.value)}>
                <option value="">— Not configured —</option>
                {voiceAgents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
              </Select>
              {voiceAgents.length === 0 && (
                <p className="text-[11px] text-white/30 mt-1.5">No Voice Agents yet — create one first.</p>
              )}
            </div>
          ) : (
            <div>
              <FieldLabel hint="Legacy — binds this number to a chatbot Workflow instead of a standalone Voice Agent">
                <span className="flex items-center gap-1.5"><Bot size={12} />Bot / Workflow</span>
              </FieldLabel>
              <Select value={workflowId} onChange={e => setWorkflowId(e.target.value)}>
                <option value="">— Not configured —</option>
                {workflows.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </Select>
            </div>
          )}
          <label className="flex items-center gap-2 text-xs text-white/40 cursor-pointer">
            <input
              type="checkbox" className="accent-cyan-400"
              checked={useLegacyWorkflow}
              onChange={e => setUseLegacyWorkflow(e.target.checked)}
            />
            Use a chatbot Workflow instead of a Voice Agent (legacy)
          </label>

          <div>
            <FieldLabel><span className="flex items-center gap-1.5"><Mic size={12} />AI voice</span></FieldLabel>
            <div className="grid grid-cols-2 gap-2">
              <Select value={voiceProvider} onChange={e => { setVoiceProvider(e.target.value); setVoiceId('') }}>
                {voiceProviders.map(p => (
                  <option key={p.credential_provider} value={p.credential_provider} disabled={!p.configured}>
                    {p.name}{!p.configured ? ' (no API key)' : ''}
                  </option>
                ))}
              </Select>
              <Select value={voiceId} onChange={e => setVoiceId(e.target.value)}>
                <option value="">Default voice</option>
                {selectedProvider?.voices.map(v => (
                  <option key={v.id} value={v.id}>{v.name}</option>
                ))}
              </Select>
            </div>
          </div>

          <div>
            <FieldLabel hint={`${speed.toFixed(2)}x`}>
              <span className="flex items-center gap-1.5"><Gauge size={12} />Voice speed</span>
            </FieldLabel>
            <input
              type="range" min={0.5} max={2.0} step={0.05} value={speed}
              onChange={e => setSpeed(parseFloat(e.target.value))}
              className="w-full accent-cyan-400"
            />
          </div>

          <div>
            <FieldLabel><span className="flex items-center gap-1.5"><Languages size={12} />Language / accent</span></FieldLabel>
            <Select value={language} onChange={e => setLanguage(e.target.value)}>
              {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
            </Select>
          </div>

          <label className="flex items-center gap-2 text-sm text-white/70 cursor-pointer">
            <input
              type="checkbox" checked={recordingEnabled}
              onChange={e => setRecordingEnabled(e.target.checked)}
              className="accent-cyan-400"
            />
            Record calls on this number
          </label>
          {recordingEnabled && (
            <p className="text-[11px] text-amber-400/80">
              Callers should be informed calls may be recorded, per your local laws.
            </p>
          )}

          <Button size="sm" loading={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
            Save settings
          </Button>
        </Card>

        {/* NEW (Voice AI Part 5): Knowledge Base & Instructions now belong
            to the Voice Agent itself, not this phone number — see
            /call-agent/agents/[id]. This keeps a legacy-Workflow number's
            KB selection reachable without duplicating that UI here. */}
        {!useLegacyWorkflow && voiceAgentId && (
          <Card className="p-4 flex items-center justify-between gap-3 tb2-rise">
            <div className="flex items-center gap-2 text-sm text-white/60">
              <BookOpen size={14} className="text-cyan-300/70" />
              Knowledge Base & Instructions are managed on the Voice Agent.
            </div>
            <Button size="sm" variant="secondary" onClick={() => router.push(`/call-agent/agents/${voiceAgentId}`)}>
              Open Voice Agent
            </Button>
          </Card>
        )}

        {/* NEW (Voice AI Part 4) — Admin controls: prompts, interrupt behavior, business hours */}
        <Card className="p-4 space-y-4 tb2-rise">
          <div className="flex items-center gap-2 text-white/50">
            <Settings2 size={14} />
            <span className="text-xs font-semibold uppercase tracking-wider">Admin controls</span>
          </div>

          <div>
            <FieldLabel hint="Spoken the moment the call connects, before anything else">
              <span className="flex items-center gap-1.5"><MessageSquare size={12} />Greeting message</span>
            </FieldLabel>
            <Textarea rows={2} placeholder="Thanks for calling! How can I help you today?"
              value={greetingMessage} onChange={e => setGreetingMessage(e.target.value)} />
          </div>

          <div>
            <FieldLabel hint="Spoken when the AI can't answer, before handing off to a human">
              <span className="flex items-center gap-1.5"><ShieldAlert size={12} />Fallback prompt</span>
            </FieldLabel>
            <Textarea rows={2} placeholder="I'm not able to help with that — let me connect you with a member of our team."
              value={fallbackPrompt} onChange={e => setFallbackPrompt(e.target.value)} />
          </div>

          <div>
            <FieldLabel hint={useLegacyWorkflow ? "Extra persona/instructions layered on top of the bot's own Workflow prompt" : 'Extra persona/instructions layered on top of the Voice Agent\'s own Instructions'}>
              <span className="flex items-center gap-1.5"><Bot size={12} />Call-specific system prompt</span>
            </FieldLabel>
            <Textarea rows={3} placeholder="Speak briefly and confirm the caller's name early in the call."
              value={systemPrompt} onChange={e => setSystemPrompt(e.target.value)} />
          </div>

          <div>
            <FieldLabel hint="Strict: only answers from the selected Knowledge Bases, with a fallback if nothing matches. Open: uses them as extra context.">
              <span className="flex items-center gap-1.5"><BookOpen size={12} />Prompt scope</span>
            </FieldLabel>
            <Select value={promptScope} onChange={e => setPromptScope(e.target.value as PromptScope)}>
              <option value="open">Open — answer normally, use KB when relevant</option>
              <option value="strict">Strict — only answer from Knowledge Base(s)</option>
            </Select>
          </div>

          <div>
            <FieldLabel hint="What happens when the caller starts talking while the AI is speaking">
              <span className="flex items-center gap-1.5"><Zap size={12} />Interrupt behavior</span>
            </FieldLabel>
            <Select value={interruptBehavior} onChange={e => setInterruptBehavior(e.target.value as InterruptBehavior)}>
              <option value="interrupt">Interrupt — stop instantly (barge-in)</option>
              <option value="queue">Queue — finish the sentence, then respond</option>
              <option value="ignore">Ignore — caller's speech never interrupts</option>
            </Select>
          </div>

          <div>
            <FieldLabel hint="Calls outside these hours hear a closed message instead of reaching the AI">
              <span className="flex items-center gap-1.5"><Clock size={12} />Business hours</span>
            </FieldLabel>
            <label className="flex items-center gap-2 text-sm text-white/70 cursor-pointer mb-2">
              <input
                type="checkbox" className="accent-cyan-400"
                checked={businessHours.enabled}
                onChange={e => setBusinessHours(bh => ({ ...bh, enabled: e.target.checked }))}
              />
              Enforce business hours
            </label>
            {businessHours.enabled && (
              <div className="space-y-2">
                <Input
                  placeholder="Timezone (e.g. America/New_York)"
                  value={businessHours.timezone}
                  onChange={e => setBusinessHours(bh => ({ ...bh, timezone: e.target.value }))}
                />
                {WEEKDAYS.map(({ key, label }) => {
                  const day = businessHours.days[key]
                  return (
                    <div key={key} className="flex items-center gap-2">
                      <label className="flex items-center gap-1.5 w-16 text-xs text-white/60 cursor-pointer">
                        <input
                          type="checkbox" className="accent-cyan-400"
                          checked={!!day}
                          onChange={e => setBusinessHours(bh => {
                            const days = { ...bh.days }
                            if (e.target.checked) days[key] = { open: '09:00', close: '17:00' }
                            else delete days[key]
                            return { ...bh, days }
                          })}
                        />
                        {label}
                      </label>
                      <input
                        type="time" disabled={!day} value={day?.open || '09:00'}
                        onChange={e => setBusinessHours(bh => ({ ...bh, days: { ...bh.days, [key]: { open: e.target.value, close: day?.close || '17:00' } } }))}
                        className="bg-white/[0.04] border border-white/10 rounded-md px-2 py-1 text-xs text-white/70 disabled:opacity-30"
                      />
                      <span className="text-white/30 text-xs">–</span>
                      <input
                        type="time" disabled={!day} value={day?.close || '17:00'}
                        onChange={e => setBusinessHours(bh => ({ ...bh, days: { ...bh.days, [key]: { open: day?.open || '09:00', close: e.target.value } } }))}
                        className="bg-white/[0.04] border border-white/10 rounded-md px-2 py-1 text-xs text-white/70 disabled:opacity-30"
                      />
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          <Button size="sm" loading={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
            Save admin controls
          </Button>
        </Card>

        <Card className="p-4 space-y-3 tb2-rise">
          <div className="flex items-center gap-2 text-white/50">
            <PhoneOutgoing size={14} />
            <span className="text-xs font-semibold uppercase tracking-wider">Place a test outbound call</span>
          </div>
          <Input
            type="tel" value={toNumber} onChange={e => setToNumber(e.target.value)}
            placeholder="+1 415 555 1234"
          />
          <Button
            size="sm" variant="secondary" icon={<PhoneOutgoing size={12} />}
            loading={callMutation.isPending}
            disabled={(useLegacyWorkflow ? !workflowId : !voiceAgentId) || toNumber.trim().length < 8}
            onClick={() => callMutation.mutate()}
          >
            Call now
          </Button>
        </Card>
      </div>
    </div>
  )
}
