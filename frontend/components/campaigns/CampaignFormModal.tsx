'use client'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Sparkles, Wand2, MessageCircle, Users, Upload, Phone, Tag, FolderPlus,
  ChevronLeft, ChevronRight, Eye,
} from 'lucide-react'
import { campaignsApi } from '@/lib/api/campaigns'
import { getErrorMessage } from '@/lib/utils/errors'
import { useToast } from '@/components/ui/Toast'
import { cn } from '@/lib/utils/cn'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { FieldLabel, Input, Textarea, Select } from '@/components/ui/Field'
import type {
  Campaign, CampaignChannel, CampaignScheduleType, CampaignTemplate, CampaignCreateInput,
  AudienceType, AudienceConfig, AudienceEntry, ConnectedChannel, WhatsAppContactOption,
  ContactGroupSummary, AudienceResolveResult,
} from '@/types/campaigns'

const CHANNELS: { value: CampaignChannel; label: string; future?: boolean }[] = [
  { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'instagram', label: 'Instagram (coming soon)', future: true },
  { value: 'email', label: 'Email (coming soon)', future: true },
]

const AUDIENCE_SOURCES: { value: AudienceType; label: string; icon: any; hint: string }[] = [
  { value: 'contacts', label: 'WhatsApp Contacts', icon: Users, hint: 'Everyone who has already messaged this bot' },
  { value: 'manual', label: 'CSV / Manual Numbers', icon: Upload, hint: 'Import a CSV or type numbers by hand' },
  { value: 'groups', label: 'Contact Groups', icon: FolderPlus, hint: 'A saved list you curated before' },
  { value: 'tags', label: 'Customer Tags', icon: Tag, hint: 'Everyone tagged e.g. "vip" or "mumbai"' },
]

// NEW (Telegram Integration — Part 2): a Telegram campaign may ONLY ever
// target people who have started the bot conversation — there is no
// manual/CSV/tag/group source for Telegram, by design, so there's no way
// to compose an audience of chat_ids ThunderBots hasn't itself seen.
const TELEGRAM_AUDIENCE_SOURCES: { value: AudienceType; label: string; icon: any; hint: string }[] = [
  { value: 'contacts', label: 'Telegram Subscribers', icon: Users, hint: 'Everyone who has started this bot on Telegram' },
]

const STEPS = ['Account', 'Audience', 'Message', 'Preview', 'Send'] as const

function toLocalInputValue(iso?: string | null) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** Minimal CSV parser: first row = headers (phone/name/city/company, any order/case). */
function parseCsv(text: string): AudienceEntry[] {
  const lines = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean)
  if (lines.length === 0) return []
  const split = (line: string) => line.split(',').map(c => c.trim().replace(/^"|"$/g, ''))
  const header = split(lines[0]).map(h => h.toLowerCase())
  const hasHeader = header.some(h => ['phone', 'number', 'identifier', 'name', 'city', 'company'].includes(h))
  const rows = hasHeader ? lines.slice(1) : lines
  const idx = {
    phone: header.indexOf('phone') >= 0 ? header.indexOf('phone') : header.indexOf('number') >= 0 ? header.indexOf('number') : header.indexOf('identifier'),
    name: header.indexOf('name'),
    city: header.indexOf('city'),
    company: header.indexOf('company'),
  }
  return rows.map(line => {
    const cells = split(line)
    if (!hasHeader) return { identifier: cells[0] || '', name: cells[1], city: cells[2], company: cells[3] }
    return {
      identifier: (idx.phone >= 0 ? cells[idx.phone] : cells[0]) || '',
      name: idx.name >= 0 ? cells[idx.name] : undefined,
      city: idx.city >= 0 ? cells[idx.city] : undefined,
      company: idx.company >= 0 ? cells[idx.company] : undefined,
    }
  }).filter(e => e.identifier)
}

export function CampaignFormModal({
  campaign,
  templates,
  onClose,
  onSaved,
}: {
  campaign?: Campaign | null
  templates: CampaignTemplate[]
  onClose: () => void
  onSaved: () => void
}) {
  const { toast } = useToast()
  const isEdit = !!campaign

  const [step, setStep] = useState(0)

  // Step 0 — Account
  const [channels, setChannels] = useState<ConnectedChannel[]>([])
  const [loadingChannels, setLoadingChannels] = useState(true)
  const [workflowId, setWorkflowId] = useState<string | null>(campaign?.workflow_id ?? null)

  // Step 1 — Audience
  const [audienceType, setAudienceType] = useState<AudienceType>(campaign?.audience_type ?? 'contacts')
  const [contactSearch, setContactSearch] = useState('')
  const [contactOptions, setContactOptions] = useState<WhatsAppContactOption[]>([])
  const [selectedContactIds, setSelectedContactIds] = useState<string[]>(campaign?.audience_config?.contact_ids ?? [])
  const [manualEntries, setManualEntries] = useState<AudienceEntry[]>(campaign?.audience_config?.manual_entries ?? [])
  const [manualText, setManualText] = useState('')
  const [groups, setGroups] = useState<ContactGroupSummary[]>([])
  const [selectedGroupIds, setSelectedGroupIds] = useState<string[]>(campaign?.audience_config?.group_ids ?? [])
  const [availableTags, setAvailableTags] = useState<string[]>([])
  const [selectedTags, setSelectedTags] = useState<string[]>(campaign?.audience_config?.tags ?? [])
  const [audiencePreview, setAudiencePreview] = useState<AudienceResolveResult | null>(null)
  const [resolvingAudience, setResolvingAudience] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Step 2 — Message
  const [name, setName] = useState(campaign?.name ?? '')
  const [channel, setChannel] = useState<CampaignChannel>(campaign?.channel ?? 'whatsapp')
  const [templateId, setTemplateId] = useState<string>(campaign?.template ?? '')
  const [message, setMessage] = useState(campaign?.message ?? '')
  const [aiPrompt, setAiPrompt] = useState(campaign?.ai_prompt ?? '')
  const [improving, setImproving] = useState(false)
  const [generating, setGenerating] = useState(false)

  // Step 4 — Send
  const [scheduleType, setScheduleType] = useState<CampaignScheduleType>(campaign?.schedule_type ?? 'now')
  const [scheduledAt, setScheduledAt] = useState(toLocalInputValue(campaign?.scheduled_at))
  const [saving, setSaving] = useState<'draft' | 'launch' | 'save' | null>(null)

  const audienceConfig: AudienceConfig = useMemo(() => ({
    contact_ids: audienceType === 'contacts' ? selectedContactIds : undefined,
    manual_entries: audienceType === 'manual' ? manualEntries : undefined,
    group_ids: audienceType === 'groups' ? selectedGroupIds : undefined,
    tags: audienceType === 'tags' ? selectedTags : undefined,
  }), [audienceType, selectedContactIds, manualEntries, selectedGroupIds, selectedTags])

  // Load connected accounts for the selected channel (Step 1: Select
  // connected WhatsApp Business account / Telegram bot). Re-runs whenever
  // the channel changes so switching WhatsApp <-> Telegram shows the right
  // list (NEW — Part 2).
  useEffect(() => {
    if (channel !== 'whatsapp' && channel !== 'telegram') { setChannels([]); return }
    setLoadingChannels(true)
    campaignsApi.channels(channel)
      .then(list => {
        setChannels(list)
        if (list.length === 1) setWorkflowId(list[0].workflow_id)
        else if (!list.some(c => c.workflow_id === workflowId)) setWorkflowId(null)
      })
      .catch(err => toast('error', getErrorMessage(err, `Could not load connected ${channel} accounts.`)))
      .finally(() => setLoadingChannels(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channel])

  // Telegram campaigns only ever offer the 'Telegram Subscribers' audience
  // source (see TELEGRAM_AUDIENCE_SOURCES) — keep audienceType in sync if
  // the user had previously picked a WhatsApp-only source before switching
  // the Target Channel to Telegram.
  useEffect(() => {
    if (channel === 'telegram' && audienceType !== 'contacts') setAudienceType('contacts')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channel])

  // Load contacts / groups / tags for the chosen account, as needed per audience source
  useEffect(() => {
    if (!workflowId) return
    if (audienceType === 'contacts') {
      campaignsApi.contacts(workflowId, { channel, search: contactSearch || undefined, page_size: 100 })
        .then(r => setContactOptions(r.contacts))
        .catch(() => {})
    }
    if (audienceType === 'tags' && channel === 'whatsapp') {
      campaignsApi.tags(workflowId).then(setAvailableTags).catch(() => {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId, channel, audienceType, contactSearch])

  useEffect(() => {
    if (audienceType === 'groups') {
      campaignsApi.groups().then(setGroups).catch(() => {})
    }
  }, [audienceType])

  useEffect(() => {
    if (!templateId || isEdit) return
    const tpl = templates.find(t => t.id === templateId)
    if (!tpl) return
    setMessage(tpl.message)
    setAiPrompt(tpl.ai_prompt)
    if (!name) setName(tpl.name)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateId])

  const resolveAudienceNow = async (withMessage?: string) => {
    setResolvingAudience(true)
    try {
      const res = await campaignsApi.resolveAudience({
        workflow_id: workflowId, channel, audience_type: audienceType, audience_config: audienceConfig,
        message: withMessage, sample_size: 15,
      })
      setAudiencePreview(res)
    } catch (err) {
      toast('error', getErrorMessage(err, 'Could not resolve the audience.'))
    } finally {
      setResolvingAudience(false)
    }
  }

  // Recompute audience counts whenever the audience selection changes (Step 2 requirement)
  useEffect(() => {
    if (step !== 1) return
    resolveAudienceNow()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, channel, workflowId, audienceType, selectedContactIds, manualEntries, selectedGroupIds, selectedTags])

  const handleCsvFile = (file: File) => {
    const reader = new FileReader()
    reader.onload = () => {
      const parsed = parseCsv(String(reader.result || ''))
      setManualEntries(prev => [...prev, ...parsed])
      toast('success', `Imported ${parsed.length} contacts from CSV.`)
    }
    reader.readAsText(file)
  }

  const addManualNumbers = () => {
    const entries = manualText.split(/[\n,]/).map(s => s.trim()).filter(Boolean).map(identifier => ({ identifier }))
    if (entries.length === 0) return
    setManualEntries(prev => [...prev, ...entries])
    setManualText('')
  }

  const handleImprove = async () => {
    if (!message.trim()) { toast('info', 'Write a message first so AI has something to improve.'); return }
    setImproving(true)
    try {
      const res = await campaignsApi.aiImprove({ message, ai_prompt: aiPrompt || undefined, channel, campaign_id: campaign?.id })
      setMessage(res.improved_message)
      toast('success', 'Message rewritten by AI.')
    } catch (err) {
      toast('error', getErrorMessage(err, 'Could not improve the message right now.'))
    } finally {
      setImproving(false)
    }
  }

  const handleGenerate = async () => {
    if (!aiPrompt.trim()) { toast('info', 'Describe what the campaign should say, e.g. "Create a Diwali offer for existing customers".'); return }
    setGenerating(true)
    try {
      const res = await campaignsApi.aiGenerate({ ai_prompt: aiPrompt, channel })
      setMessage(res.improved_message)
      toast('success', 'Message generated by AI.')
    } catch (err) {
      toast('error', getErrorMessage(err, 'Could not generate a message right now.'))
    } finally {
      setGenerating(false)
    }
  }

  const buildPayload = (): CampaignCreateInput => ({
    name: name.trim(),
    channel,
    template: templateId || null,
    message,
    ai_prompt: aiPrompt || null,
    audience_type: audienceType,
    audience_config: audienceConfig,
    workflow_id: workflowId || null,
    schedule_type: scheduleType,
    scheduled_at: scheduleType === 'later' && scheduledAt ? new Date(scheduledAt).toISOString() : null,
  })

  const validateStep = (s: number): string | null => {
    if (s === 0 && (channel === 'whatsapp' || channel === 'telegram') && !workflowId) return `Select which connected ${channel === 'telegram' ? 'Telegram bot' : 'WhatsApp Business account'} this campaign should send from.`
    if (s === 1 && (audiencePreview ? audiencePreview.valid === 0 : false)) return 'Your audience has no valid recipients yet. Add contacts, numbers, a group, or a tag.'
    if (s === 2) {
      if (!name.trim()) return 'Give your campaign a name.'
      if (!message.trim()) return 'Write a message, or generate one with AI, for this campaign.'
    }
    if (s === 4 && scheduleType === 'later' && !scheduledAt) return 'Pick a date and time to schedule this campaign.'
    return null
  }

  const goNext = async () => {
    const err = validateStep(step)
    if (err) { toast('info', err); return }
    if (step === 2) await resolveAudienceNow(message) // refresh Step 4 preview with the final message
    setStep(s => Math.min(s + 1, STEPS.length - 1))
  }
  const goBack = () => setStep(s => Math.max(s - 1, 0))

  const handleSave = async (mode: 'draft' | 'launch' | 'save') => {
    const err = validateStep(2) || (scheduleType === 'later' && !scheduledAt ? 'Pick a date and time to schedule this campaign.' : null)
    if (err) { toast('info', err); return }

    setSaving(mode)
    try {
      if (isEdit && campaign) {
        await campaignsApi.update(campaign.id, buildPayload())
        toast('success', 'Campaign updated.')
      } else {
        await campaignsApi.create({ ...buildPayload(), launch: mode === 'launch' })
        toast('success', mode === 'launch' ? 'Campaign launched — sending now.' : 'Campaign saved as draft.')
      }
      onSaved()
    } catch (e) {
      toast('error', getErrorMessage(e, 'Could not save this campaign.'))
    } finally {
      setSaving(null)
    }
  }

  const toggleInList = (list: string[], value: string, setter: (v: string[]) => void) => {
    setter(list.includes(value) ? list.filter(v => v !== value) : [...list, value])
  }

  return (
    <Modal
      onClose={onClose}
      title={isEdit ? 'Edit Campaign' : 'New Campaign'}
      subtitle={isEdit ? campaign?.name : 'Connect an account, pick your audience, and send an AI broadcast'}
      maxWidth="max-w-2xl"
    >
      {/* Step indicator */}
      <div className="flex items-center gap-1.5 mb-5 overflow-x-auto">
        {STEPS.map((label, i) => (
          <button
            key={label}
            type="button"
            onClick={() => i <= step && setStep(i)}
            className={cn(
              'flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-lg whitespace-nowrap flex-shrink-0',
              i === step ? 'bg-[#6366f1]/15 text-[#c7d2fe] border border-[#6366f1]/30'
                : i < step ? 'text-white/50 hover:text-white/80 cursor-pointer' : 'text-white/20 cursor-default'
            )}
          >
            <span className={cn('w-4 h-4 rounded-full flex items-center justify-center text-[9px]', i <= step ? 'bg-[#6366f1]/30' : 'bg-white/10')}>
              {i + 1}
            </span>
            {label}
          </button>
        ))}
      </div>

      <div className="space-y-4 min-h-[280px]">
        {/* Step 0: Account */}
        {step === 0 && (
          <div className="space-y-3">
            <FieldLabel hint="who this campaign sends from">Target Channel</FieldLabel>
            <Select value={channel} onChange={e => setChannel(e.target.value as CampaignChannel)}>
              {CHANNELS.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
            </Select>

            {(channel === 'whatsapp' || channel === 'telegram') && (
              <div>
                <FieldLabel>{channel === 'telegram' ? 'Connected Telegram Bot' : 'Connected WhatsApp Business Account'}</FieldLabel>
                {loadingChannels ? (
                  <p className="text-xs text-white/40">Loading connected {channel === 'telegram' ? 'bots' : 'accounts'}…</p>
                ) : channels.length === 0 ? (
                  <p className="text-xs text-amber-300/80">
                    {channel === 'telegram'
                      ? 'No Telegram bot is connected yet. Connect one from the Telegram settings page first.'
                      : 'No WhatsApp Business account is connected yet. Connect one from the WhatsApp settings page first.'}
                  </p>
                ) : (
                  <div className="space-y-2">
                    {channels.map(ch => (
                      <button
                        key={ch.workflow_id}
                        type="button"
                        onClick={() => setWorkflowId(ch.workflow_id)}
                        className={cn(
                          'w-full flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-xl border text-left',
                          workflowId === ch.workflow_id ? 'bg-[#6366f1]/10 border-[#6366f1]/30' : 'bg-white/[0.03] border-white/10 hover:border-white/20'
                        )}
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          <MessageCircle size={14} className="text-[#a5b4fc] flex-shrink-0" />
                          <div className="min-w-0">
                            <p className="text-xs font-semibold text-white/85 truncate">{ch.bot_name}</p>
                            <p className="text-[10px] text-white/35">
                              {ch.display_phone_number || (ch.bot_username ? `@${ch.bot_username}` : null) || ch.verified_name || 'Not connected'}
                            </p>
                          </div>
                        </div>
                        <span className={cn('text-[10px] px-2 py-0.5 rounded-full border flex-shrink-0',
                          ch.status === 'connected' && ch.is_enabled ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' : 'text-white/30 border-white/10')}>
                          {ch.status === 'connected' && ch.is_enabled ? 'Connected' : ch.status}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Step 1: Audience */}
        {step === 1 && (
          <div className="space-y-3.5">
            <FieldLabel>Select Audience</FieldLabel>
            <div className="grid grid-cols-2 gap-2">
              {(channel === 'telegram' ? TELEGRAM_AUDIENCE_SOURCES : AUDIENCE_SOURCES).map(src => (
                <button
                  key={src.value}
                  type="button"
                  onClick={() => setAudienceType(src.value)}
                  className={cn(
                    'flex items-start gap-2 px-3 py-2.5 rounded-xl border text-left',
                    audienceType === src.value ? 'bg-[#6366f1]/10 border-[#6366f1]/30' : 'bg-white/[0.03] border-white/10 hover:border-white/20'
                  )}
                >
                  <src.icon size={14} className="text-[#a5b4fc] flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-[11px] font-semibold text-white/85">{src.label}</p>
                    <p className="text-[10px] text-white/35 mt-0.5">{src.hint}</p>
                  </div>
                </button>
              ))}
            </div>

            {audienceType === 'contacts' && (
              <div>
                <Input placeholder={channel === 'telegram' ? 'Search subscribers by name or username…' : 'Search contacts by name or number…'} value={contactSearch} onChange={e => setContactSearch(e.target.value)} className="mb-2" />
                <div className="max-h-40 overflow-y-auto space-y-1 rounded-xl border border-white/10 p-2">
                  {contactOptions.length === 0 && <p className="text-[11px] text-white/30 px-1 py-2">{channel === 'telegram' ? 'No subscribers found. Leave unselected to target everyone who has started this bot.' : 'No contacts found. Leave unselected to target everyone who has messaged this bot.'}</p>}
                  {contactOptions.map(c => (
                    <label key={c.id} className="flex items-center gap-2 px-1.5 py-1 rounded-lg hover:bg-white/[0.04] cursor-pointer">
                      <input type="checkbox" checked={selectedContactIds.includes(c.id)} onChange={() => toggleInList(selectedContactIds, c.id, setSelectedContactIds)} />
                      <span className="text-xs text-white/70">{c.name || c.identifier}</span>
                      <span className="text-[10px] text-white/30 ml-auto">{c.identifier}</span>
                    </label>
                  ))}
                </div>
                <p className="text-[10px] text-white/30 mt-1.5">{channel === 'telegram' ? 'Leave all unchecked to target every subscriber who has started this bot on Telegram.' : 'Leave all unchecked to target every opted-in WhatsApp contact.'}</p>
              </div>
            )}

            {audienceType === 'manual' && (
              <div className="space-y-2.5">
                <div className="flex items-center gap-2">
                  <Button type="button" variant="secondary" size="sm" icon={<Upload size={12} />} onClick={() => fileInputRef.current?.click()}>
                    Import CSV
                  </Button>
                  <input ref={fileInputRef} type="file" accept=".csv,text/csv" className="hidden"
                    onChange={e => { const f = e.target.files?.[0]; if (f) handleCsvFile(f); e.currentTarget.value = '' }} />
                  <span className="text-[10px] text-white/30">Columns: phone, name, city, company</span>
                </div>
                <Textarea placeholder={'Or paste numbers, one per line:\n+919812345678\n+919812345679'} rows={3} value={manualText} onChange={e => setManualText(e.target.value)} />
                <Button type="button" variant="secondary" size="sm" icon={<Phone size={12} />} onClick={addManualNumbers}>Add numbers</Button>
                {manualEntries.length > 0 && (
                  <div className="max-h-32 overflow-y-auto rounded-xl border border-white/10 p-2 space-y-1">
                    {manualEntries.map((e, i) => (
                      <div key={i} className="flex items-center justify-between text-[11px] text-white/60 px-1.5 py-1">
                        <span>{e.name ? `${e.name} — ` : ''}{e.identifier}</span>
                        <button type="button" onClick={() => setManualEntries(prev => prev.filter((_, idx) => idx !== i))} className="text-white/25 hover:text-red-400">✕</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {audienceType === 'groups' && (
              <div className="max-h-40 overflow-y-auto space-y-1 rounded-xl border border-white/10 p-2">
                {groups.length === 0 && <p className="text-[11px] text-white/30 px-1 py-2">No contact groups yet. Create one from the Contacts page, or use CSV/Manual instead.</p>}
                {groups.map(g => (
                  <label key={g.id} className="flex items-center gap-2 px-1.5 py-1 rounded-lg hover:bg-white/[0.04] cursor-pointer">
                    <input type="checkbox" checked={selectedGroupIds.includes(g.id)} onChange={() => toggleInList(selectedGroupIds, g.id, setSelectedGroupIds)} />
                    <span className="text-xs text-white/70">{g.name}</span>
                    <span className="text-[10px] text-white/30 ml-auto">{g.member_count} contacts</span>
                  </label>
                ))}
              </div>
            )}

            {audienceType === 'tags' && (
              <div className="flex flex-wrap gap-1.5">
                {availableTags.length === 0 && <p className="text-[11px] text-white/30">No tags found on your contacts yet.</p>}
                {availableTags.map(t => (
                  <button key={t} type="button" onClick={() => toggleInList(selectedTags, t, setSelectedTags)}
                    className={cn('text-[11px] px-2.5 py-1 rounded-full border', selectedTags.includes(t) ? 'bg-[#6366f1]/15 border-[#6366f1]/30 text-[#c7d2fe]' : 'border-white/10 text-white/40 hover:text-white/70')}>
                    {t}
                  </button>
                ))}
              </div>
            )}

            {/* Requirement: show total / valid / invalid / duplicate counts */}
            <div className="grid grid-cols-4 gap-2 pt-2 border-t border-white/[0.06]">
              {[
                { label: 'Total', value: audiencePreview?.total ?? 0, tone: 'text-white/80' },
                { label: 'Valid', value: audiencePreview?.valid ?? 0, tone: 'text-emerald-400' },
                { label: 'Invalid', value: audiencePreview?.invalid ?? 0, tone: 'text-red-400' },
                { label: 'Duplicate', value: audiencePreview?.duplicate ?? 0, tone: 'text-amber-400' },
              ].map(s => (
                <div key={s.label} className="text-center">
                  <p className={cn('text-lg font-bold tabular-nums', s.tone)}>{resolvingAudience ? '…' : s.value}</p>
                  <p className="text-[9px] text-white/25 uppercase tracking-wide mt-0.5">{s.label}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Step 2: Message */}
        {step === 2 && (
          <div className="space-y-4">
            <div>
              <FieldLabel>Campaign Name</FieldLabel>
              <Input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Diwali Weekend Sale" autoFocus />
            </div>

            <div>
              <FieldLabel hint={isEdit ? undefined : 'optional'}>Template</FieldLabel>
              <Select value={templateId} onChange={e => setTemplateId(e.target.value)}>
                <option value="">Custom (blank)</option>
                {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </Select>
            </div>

            <div>
              <FieldLabel hint="tells the AI what the campaign should say">AI Prompt</FieldLabel>
              <Textarea value={aiPrompt} onChange={e => setAiPrompt(e.target.value)} placeholder='e.g. Create a Diwali offer for existing customers' rows={2} />
              <div className="flex items-center gap-2 mt-2">
                <Button type="button" variant="secondary" size="sm" onClick={handleGenerate} loading={generating} icon={<Sparkles size={13} />}>
                  Generate message with AI
                </Button>
                <Button type="button" variant="secondary" size="sm" onClick={handleImprove} loading={improving} icon={<Wand2 size={13} />}>
                  Improve current message
                </Button>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <FieldLabel>Message</FieldLabel>
                <span className="text-[10px] text-white/25">supports {'{{name}}'}, {'{{city}}'}, {'{{company}}'}</span>
              </div>
              <Textarea value={message} onChange={e => setMessage(e.target.value)} placeholder="What should this campaign say to your customers?" rows={5} />
            </div>
          </div>
        )}

        {/* Step 3: Preview */}
        {step === 3 && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <FieldLabel>Preview — exactly what each customer receives</FieldLabel>
              <Button type="button" variant="ghost" size="sm" onClick={() => resolveAudienceNow(message)} loading={resolvingAudience} icon={<Eye size={12} />}>Refresh</Button>
            </div>
            <div className="max-h-72 overflow-y-auto space-y-2.5">
              {(audiencePreview?.sample || []).filter(s => s.valid).map((s, i) => (
                <div key={i} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-[11px] font-semibold text-white/70">{s.name || s.identifier}</span>
                    <span className="text-[10px] text-white/30">{s.identifier}</span>
                  </div>
                  <p className="text-xs text-white/60 whitespace-pre-wrap">{s.preview || message}</p>
                </div>
              ))}
              {(audiencePreview?.sample || []).every(s => !s.valid) && (
                <p className="text-xs text-white/30">No valid recipients to preview yet — go back and check your audience.</p>
              )}
            </div>
            {audiencePreview && audiencePreview.valid > (audiencePreview.sample.filter(s => s.valid).length) && (
              <p className="text-[10px] text-white/25">Showing a sample of {audiencePreview.sample.filter(s => s.valid).length} of {audiencePreview.valid} recipients.</p>
            )}
          </div>
        )}

        {/* Step 4: Send */}
        {step === 4 && (
          <div className="space-y-4">
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 grid grid-cols-3 gap-3">
              <div>
                <p className="text-[10px] text-white/30 uppercase tracking-wide">Recipients</p>
                <p className="text-lg font-bold text-white/85">{audiencePreview?.valid ?? 0}</p>
              </div>
              <div>
                <p className="text-[10px] text-white/30 uppercase tracking-wide">Channel</p>
                <p className="text-sm font-semibold text-white/70 capitalize mt-1.5">{channel}</p>
              </div>
              <div>
                <p className="text-[10px] text-white/30 uppercase tracking-wide">AI Auto-Reply</p>
                <p className="text-sm font-semibold text-emerald-400 mt-1.5">Enabled</p>
              </div>
            </div>

            <div>
              <FieldLabel>Schedule</FieldLabel>
              <div className="flex items-center gap-2 mb-2">
                {(['now', 'later'] as CampaignScheduleType[]).map(opt => (
                  <button key={opt} type="button" onClick={() => setScheduleType(opt)}
                    className={opt === scheduleType ? 'tb2-btn-primary text-white text-xs font-semibold px-3.5 py-2 rounded-xl' : 'bg-white/[0.04] border border-white/10 text-white/60 hover:text-white text-xs font-medium px-3.5 py-2 rounded-xl'}>
                    {opt === 'now' ? 'Send Now' : 'Schedule for Later'}
                  </button>
                ))}
              </div>
              {scheduleType === 'later' && (
                <Input type="datetime-local" value={scheduledAt} onChange={e => setScheduledAt(e.target.value)} />
              )}
            </div>

            <p className="text-[10px] text-white/30">
              After sending, every customer reply is continued automatically by your existing AI Agent — using your Workflow and Knowledge Base — and handed off to a live agent if the AI can&apos;t help.
            </p>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between pt-4 mt-2 border-t border-white/[0.06]">
        <Button variant="ghost" onClick={step === 0 ? onClose : goBack} disabled={!!saving} icon={step > 0 ? <ChevronLeft size={13} /> : undefined}>
          {step === 0 ? 'Cancel' : 'Back'}
        </Button>

        {step < STEPS.length - 1 ? (
          <Button onClick={goNext} icon={<ChevronRight size={13} />}>Next</Button>
        ) : isEdit ? (
          <Button onClick={() => handleSave('save')} loading={saving === 'save'} disabled={!!saving}>Save Changes</Button>
        ) : (
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={() => handleSave('draft')} loading={saving === 'draft'} disabled={!!saving}>Save as Draft</Button>
            <Button onClick={() => handleSave('launch')} loading={saving === 'launch'} disabled={!!saving} icon={<Sparkles size={13} />}>
              {scheduleType === 'later' ? 'Schedule Campaign' : 'Launch Campaign'}
            </Button>
          </div>
        )}
      </div>
    </Modal>
  )
}
