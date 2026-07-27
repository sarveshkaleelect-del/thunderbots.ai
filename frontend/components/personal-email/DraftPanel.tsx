'use client'
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Sparkles, Pencil, RotateCcw, Languages, Copy, Check, X, Send, Clock, ThumbsUp, ThumbsDown, XCircle } from 'lucide-react'
import { personalEmailApi } from '@/lib/api/personalEmail'
import { Button } from '@/components/ui/Button'
import { Textarea, Select, Input } from '@/components/ui/Field'
import { Badge } from '@/components/ui/Card'
import { useToast } from '@/components/ui/Toast'
import type { PersonalEmailDraft, PersonalEmailDraftStyle } from '@/types/personalEmail'

const STYLES: { value: PersonalEmailDraftStyle; label: string }[] = [
  { value: 'professional', label: 'Professional' },
  { value: 'friendly', label: 'Friendly' },
  { value: 'short', label: 'Short' },
]

const LANGUAGES = [
  'Spanish', 'French', 'German', 'Hindi', 'Marathi', 'Portuguese', 'Japanese', 'Mandarin Chinese', 'Arabic',
]

function sendStatusTone(status: PersonalEmailDraft['send_status']): 'success' | 'warning' | 'danger' | 'accent' | 'default' {
  switch (status) {
    case 'sent': return 'success'
    case 'scheduled': return 'accent'
    case 'sending': return 'warning'
    case 'failed': return 'danger'
    default: return 'default'
  }
}

function DraftCard({ draft, messageId }: { draft: PersonalEmailDraft; messageId: string }) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [editing, setEditing] = useState(false)
  const [content, setContent] = useState(draft.content)
  const [copied, setCopied] = useState(false)
  const [language, setLanguage] = useState(LANGUAGES[0])
  const [scheduling, setScheduling] = useState(false)
  const [scheduleAt, setScheduleAt] = useState('')

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['personal-email-message', messageId] })

  const saveMutation = useMutation({
    mutationFn: () => personalEmailApi.editDraft(draft.id, content),
    onSuccess: () => { setEditing(false); invalidate(); toast('success', 'Draft saved.') },
    onError: () => toast('error', 'Could not save the draft.'),
  })

  const regenMutation = useMutation({
    mutationFn: () => personalEmailApi.regenerateDraft(draft.id),
    onSuccess: (updated) => { setContent(updated.content); invalidate(); toast('success', 'Draft regenerated.') },
    onError: () => toast('error', 'Could not regenerate the draft.'),
  })

  const translateMutation = useMutation({
    mutationFn: () => personalEmailApi.translateDraft(draft.id, language),
    onSuccess: (updated) => { setContent(updated.content); invalidate(); toast('success', `Translated to ${language}.`) },
    onError: () => toast('error', 'Translation failed.'),
  })

  // ── Part 2: send / schedule / approval workflow ─────────────────────────
  const sendMutation = useMutation({
    mutationFn: () => personalEmailApi.sendDraft(draft.id),
    onSuccess: () => { invalidate(); toast('success', 'Email sent.') },
    onError: (e: any) => toast('error', e?.response?.data?.detail || 'Could not send email. The account may need to be reconnected.'),
  })

  const scheduleMutation = useMutation({
    mutationFn: () => personalEmailApi.scheduleDraft(draft.id, new Date(scheduleAt).toISOString()),
    onSuccess: () => { setScheduling(false); invalidate(); toast('success', 'Send scheduled.') },
    onError: (e: any) => toast('error', e?.response?.data?.detail || 'Could not schedule this draft.'),
  })

  const cancelScheduleMutation = useMutation({
    mutationFn: () => personalEmailApi.cancelScheduledDraft(draft.id),
    onSuccess: () => { invalidate(); toast('success', 'Scheduled send cancelled.') },
    onError: () => toast('error', 'Could not cancel the scheduled send.'),
  })

  const approveMutation = useMutation({
    mutationFn: () => personalEmailApi.approveDraft(draft.id),
    onSuccess: () => { invalidate(); toast('success', 'Draft approved.') },
    onError: () => toast('error', 'Could not approve this draft.'),
  })

  const rejectMutation = useMutation({
    mutationFn: () => personalEmailApi.rejectDraft(draft.id),
    onSuccess: () => { invalidate(); toast('success', 'Draft rejected.') },
    onError: () => toast('error', 'Could not reject this draft.'),
  })

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      toast('error', 'Could not copy to clipboard.')
    }
  }

  const busy = saveMutation.isPending || regenMutation.isPending || translateMutation.isPending
  const sendBusy = sendMutation.isPending || scheduleMutation.isPending || cancelScheduleMutation.isPending
    || approveMutation.isPending || rejectMutation.isPending
  const pendingApproval = draft.approval_status === 'pending'
  const isSent = draft.send_status === 'sent'
  const isScheduled = draft.send_status === 'scheduled'

  return (
    <div className="tb2-glass rounded-xl p-3.5 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Badge tone="accent">{STYLES.find(s => s.value === draft.style)?.label || draft.style}</Badge>
          {draft.send_status !== 'draft' && (
            <Badge tone={sendStatusTone(draft.send_status)}>
              {draft.send_status === 'sent' ? 'Sent' : draft.send_status === 'scheduled' ? 'Scheduled' : draft.send_status === 'failed' ? 'Failed' : 'Sending'}
            </Badge>
          )}
          {pendingApproval && <Badge tone="warning">Awaiting approval</Badge>}
        </div>
        {draft.is_edited && <span className="text-[10px] text-white/25">Edited</span>}
      </div>

      {editing ? (
        <Textarea rows={6} value={content} onChange={e => setContent(e.target.value)} disabled={busy} />
      ) : (
        <p className="text-sm text-white/70 leading-relaxed whitespace-pre-wrap">{content}</p>
      )}

      {isSent && draft.sent_at && (
        <p className="text-[11px] text-white/35">Sent {new Date(draft.sent_at).toLocaleString()}</p>
      )}
      {isScheduled && draft.scheduled_at && (
        <p className="text-[11px] text-[#a5b4fc]">Scheduled for {new Date(draft.scheduled_at).toLocaleString()}</p>
      )}
      {draft.send_status === 'failed' && draft.send_error && (
        <p className="text-[11px] text-red-400">{draft.send_error}</p>
      )}

      {!isSent && (
        <div className="flex flex-wrap items-center gap-1.5">
          {editing ? (
            <>
              <Button size="sm" variant="secondary" icon={<Check size={13} />} loading={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
                Save
              </Button>
              <Button size="sm" variant="ghost" icon={<X size={13} />} onClick={() => { setEditing(false); setContent(draft.content) }}>
                Cancel
              </Button>
            </>
          ) : (
            <>
              <Button size="sm" variant="ghost" icon={<Pencil size={13} />} onClick={() => setEditing(true)} disabled={busy || sendBusy}>
                Edit
              </Button>
              <Button size="sm" variant="ghost" icon={<RotateCcw size={13} />} loading={regenMutation.isPending} onClick={() => regenMutation.mutate()} disabled={busy || sendBusy}>
                Regenerate
              </Button>
              <Button size="sm" variant="ghost" icon={copied ? <Check size={13} /> : <Copy size={13} />} onClick={handleCopy} disabled={busy || sendBusy}>
                {copied ? 'Copied' : 'Copy'}
              </Button>
            </>
          )}
        </div>
      )}

      {!editing && !isSent && (
        <div className="flex items-center gap-2 pt-1">
          <Select value={language} onChange={e => setLanguage(e.target.value)} disabled={busy || sendBusy} className="!py-1.5 !text-xs">
            {LANGUAGES.map(l => <option key={l} value={l}>{l}</option>)}
          </Select>
          <Button size="sm" variant="ghost" icon={<Languages size={13} />} loading={translateMutation.isPending} onClick={() => translateMutation.mutate()} disabled={busy || sendBusy}>
            Translate
          </Button>
        </div>
      )}

      {/* ── Part 2: reply approval workflow ── */}
      {pendingApproval && !isSent && (
        <div className="flex items-center gap-1.5 pt-2 border-t border-white/10">
          <Button size="sm" variant="secondary" icon={<ThumbsUp size={13} />} loading={approveMutation.isPending} onClick={() => approveMutation.mutate()} disabled={sendBusy}>
            Approve
          </Button>
          <Button size="sm" variant="ghost" icon={<ThumbsDown size={13} />} loading={rejectMutation.isPending} onClick={() => rejectMutation.mutate()} disabled={sendBusy}>
            Reject
          </Button>
        </div>
      )}

      {/* ── Part 2: one-click send / schedule send ── */}
      {!editing && !isSent && !pendingApproval && (
        <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t border-white/10">
          {isScheduled ? (
            <Button size="sm" variant="ghost" icon={<XCircle size={13} />} loading={cancelScheduleMutation.isPending} onClick={() => cancelScheduleMutation.mutate()} disabled={sendBusy}>
              Cancel scheduled send
            </Button>
          ) : scheduling ? (
            <>
              <Input
                type="datetime-local"
                value={scheduleAt}
                onChange={e => setScheduleAt(e.target.value)}
                className="!py-1.5 !text-xs !w-auto"
              />
              <Button size="sm" variant="secondary" icon={<Clock size={13} />} loading={scheduleMutation.isPending} disabled={!scheduleAt || sendBusy} onClick={() => scheduleMutation.mutate()}>
                Confirm
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setScheduling(false)} disabled={sendBusy}>Cancel</Button>
            </>
          ) : (
            <>
              <Button size="sm" variant="primary" icon={<Send size={13} />} loading={sendMutation.isPending} onClick={() => sendMutation.mutate()} disabled={sendBusy}>
                Send
              </Button>
              <Button size="sm" variant="ghost" icon={<Clock size={13} />} onClick={() => setScheduling(true)} disabled={sendBusy}>
                Schedule send
              </Button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

export function DraftPanel({ messageId, drafts }: { messageId: string; drafts: PersonalEmailDraft[] }) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [selectedStyles, setSelectedStyles] = useState<PersonalEmailDraftStyle[]>(['professional', 'friendly', 'short'])

  const generateMutation = useMutation({
    mutationFn: () => personalEmailApi.generateDrafts(messageId, selectedStyles),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['personal-email-message', messageId] })
      toast('success', 'Reply drafts generated.')
    },
    onError: (e: any) => toast('error', e?.response?.data?.detail || 'Draft generation failed.'),
  })

  const toggleStyle = (style: PersonalEmailDraftStyle) => {
    setSelectedStyles(prev => prev.includes(style) ? prev.filter(s => s !== style) : [...prev, style])
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold text-white/50 uppercase tracking-wide">AI Reply Drafts</p>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {STYLES.map(s => (
          <button
            key={s.value}
            onClick={() => toggleStyle(s.value)}
            className={`text-[11px] px-2.5 py-1 rounded-full border transition ${
              selectedStyles.includes(s.value)
                ? 'bg-[#6366f1]/15 text-[#a5b4fc] border-[#6366f1]/30'
                : 'bg-white/[0.03] text-white/35 border-white/10 hover:text-white/60'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      <Button
        size="sm"
        icon={<Sparkles size={13} />}
        loading={generateMutation.isPending}
        disabled={selectedStyles.length === 0}
        onClick={() => generateMutation.mutate()}
      >
        Generate drafts
      </Button>

      {drafts.length > 0 && (
        <div className="space-y-3 pt-1">
          {drafts.map(d => <DraftCard key={d.id} draft={d} messageId={messageId} />)}
        </div>
      )}
    </div>
  )
}
