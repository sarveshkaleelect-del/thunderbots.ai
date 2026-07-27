'use client'
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Zap, ShieldCheck } from 'lucide-react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Input, Select, Textarea, FieldLabel } from '@/components/ui/Field'
import { Badge } from '@/components/ui/Card'
import { Skeleton, EmptyState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'
import { personalEmailApi } from '@/lib/api/personalEmail'
import type { PersonalEmailDraftStyle } from '@/types/personalEmail'

const STYLE_OPTIONS: PersonalEmailDraftStyle[] = ['professional', 'friendly', 'short']

function emptyForm() {
  return {
    name: '', sender_contains: '', subject_contains: '', category: '', priority: '',
    style: 'professional' as PersonalEmailDraftStyle, instructions: '', require_approval: true,
  }
}

export function AutoReplyRulesModal({ accountId, onClose }: { accountId: string; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(emptyForm())

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['personal-email-auto-reply-rules', accountId] })

  const { data: rules, isLoading } = useQuery({
    queryKey: ['personal-email-auto-reply-rules', accountId],
    queryFn: () => personalEmailApi.listAutoReplyRules(accountId),
  })

  const createMutation = useMutation({
    mutationFn: () => personalEmailApi.createAutoReplyRule(accountId, {
      name: form.name,
      sender_contains: form.sender_contains || undefined,
      subject_contains: form.subject_contains || undefined,
      category: (form.category || undefined) as any,
      priority: (form.priority || undefined) as any,
      style: form.style,
      instructions: form.instructions || undefined,
      require_approval: form.require_approval,
    }),
    onSuccess: () => { invalidate(); setShowForm(false); setForm(emptyForm()); toast('success', 'Auto-reply rule created.') },
    onError: (e: any) => toast('error', e?.response?.data?.detail || 'Could not create rule.'),
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => personalEmailApi.toggleAutoReplyRule(id, enabled),
    onSuccess: () => invalidate(),
    onError: () => toast('error', 'Could not update rule.'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => personalEmailApi.deleteAutoReplyRule(id),
    onSuccess: () => { invalidate(); toast('success', 'Rule deleted.') },
    onError: () => toast('error', 'Could not delete rule.'),
  })

  return (
    <Modal onClose={onClose} title="Auto-reply rules" subtitle="Optional — nothing sends automatically unless you turn a rule on" maxWidth="max-w-xl">
      <div className="space-y-4">
        {isLoading && <Skeleton className="h-32 w-full rounded-xl" />}

        {!isLoading && (rules?.length ?? 0) === 0 && !showForm && (
          <EmptyState icon={<Zap size={20} />} title="No auto-reply rules yet" description="Create one to have the AI reply for you when a matching email arrives." />
        )}

        {!isLoading && rules && rules.length > 0 && (
          <div className="space-y-2">
            {rules.map(rule => (
              <div key={rule.id} className="tb2-glass rounded-xl p-3 space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium text-white truncate">{rule.name}</p>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <Badge tone={rule.is_active ? 'success' : 'default'}>{rule.is_active ? 'On' : 'Off'}</Badge>
                    {!rule.require_approval && <Badge tone="warning">Auto-sends</Badge>}
                  </div>
                </div>
                <p className="text-[11px] text-white/35">
                  {[
                    rule.sender_contains && `sender contains "${rule.sender_contains}"`,
                    rule.subject_contains && `subject contains "${rule.subject_contains}"`,
                    rule.category && `category = ${rule.category}`,
                    rule.priority && `priority = ${rule.priority}`,
                  ].filter(Boolean).join(' · ') || 'Matches all inbox emails'}
                </p>
                <div className="flex items-center gap-1.5 pt-1">
                  <Button size="sm" variant="ghost" onClick={() => toggleMutation.mutate({ id: rule.id, enabled: !rule.is_active })} loading={toggleMutation.isPending}>
                    {rule.is_active ? 'Turn off' : 'Turn on'}
                  </Button>
                  <Button size="sm" variant="ghost" icon={<Trash2 size={13} />} onClick={() => deleteMutation.mutate(rule.id)} loading={deleteMutation.isPending}>
                    Delete
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}

        {showForm ? (
          <div className="tb2-glass rounded-xl p-4 space-y-3">
            <div>
              <FieldLabel>Rule name</FieldLabel>
              <Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="e.g. Auto-decline meeting requests" />
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <FieldLabel>Sender contains</FieldLabel>
                <Input value={form.sender_contains} onChange={e => setForm(f => ({ ...f, sender_contains: e.target.value }))} placeholder="optional" />
              </div>
              <div>
                <FieldLabel>Subject contains</FieldLabel>
                <Input value={form.subject_contains} onChange={e => setForm(f => ({ ...f, subject_contains: e.target.value }))} placeholder="optional" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <FieldLabel>Category</FieldLabel>
                <Select value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}>
                  <option value="">Any</option>
                  {['work', 'personal', 'finance', 'promotions', 'social', 'updates', 'other'].map(c => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </Select>
              </div>
              <div>
                <FieldLabel>Priority</FieldLabel>
                <Select value={form.priority} onChange={e => setForm(f => ({ ...f, priority: e.target.value }))}>
                  <option value="">Any</option>
                  {['low', 'medium', 'high', 'urgent'].map(p => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </Select>
              </div>
            </div>
            <div>
              <FieldLabel>Reply style</FieldLabel>
              <Select value={form.style} onChange={e => setForm(f => ({ ...f, style: e.target.value as PersonalEmailDraftStyle }))}>
                {STYLE_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
              </Select>
            </div>
            <div>
              <FieldLabel>Instructions (optional)</FieldLabel>
              <Textarea rows={2} value={form.instructions} onChange={e => setForm(f => ({ ...f, instructions: e.target.value }))} placeholder="e.g. Let them know I'm out of office until Monday." />
            </div>
            <button
              type="button"
              onClick={() => setForm(f => ({ ...f, require_approval: !f.require_approval }))}
              className="flex items-center gap-2 text-xs text-white/55"
            >
              <span className={`w-8 h-4.5 rounded-full transition flex items-center px-0.5 ${form.require_approval ? 'bg-white/10' : 'bg-[#6366f1]'}`}>
                <span className={`w-3.5 h-3.5 rounded-full bg-white transition ${form.require_approval ? '' : 'translate-x-3.5'}`} />
              </span>
              {form.require_approval ? (
                <span className="flex items-center gap-1"><ShieldCheck size={12} /> Require my approval before sending</span>
              ) : (
                <span className="text-amber-300">Sends automatically — no approval step</span>
              )}
            </button>
            <div className="flex items-center gap-1.5 pt-1">
              <Button size="sm" loading={createMutation.isPending} disabled={!form.name.trim()} onClick={() => createMutation.mutate()}>
                Save rule
              </Button>
              <Button size="sm" variant="ghost" onClick={() => { setShowForm(false); setForm(emptyForm()) }}>Cancel</Button>
            </div>
          </div>
        ) : (
          <Button size="sm" variant="secondary" icon={<Plus size={13} />} onClick={() => setShowForm(true)}>
            New rule
          </Button>
        )}
      </div>
    </Modal>
  )
}
