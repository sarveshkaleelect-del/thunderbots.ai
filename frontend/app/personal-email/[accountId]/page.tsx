'use client'
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Mail, Inbox, Send, FileEdit, Star, RefreshCw, Search, Sparkles, Clock, ListChecks,
  AlertCircle, Smile, Meh, Frown, ChevronLeft, Unplug, ShieldAlert, BarChart3, Zap,
  CheckSquare, Square, Paperclip, Download, History, BellRing, Send as SendIcon,
} from 'lucide-react'
import { personalEmailApi } from '@/lib/api/personalEmail'
import { SubPageBar } from '@/components/ui/TopBar'
import { Card, Badge } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input, Select } from '@/components/ui/Field'
import { PageLoader, EmptyState, SkeletonRows } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'
import { DraftPanel } from '@/components/personal-email/DraftPanel'
import { DigestModal } from '@/components/personal-email/DigestModal'
import { AnalyticsModal } from '@/components/personal-email/AnalyticsModal'
import { AutoReplyRulesModal } from '@/components/personal-email/AutoReplyRulesModal'
import type { PersonalEmailFolder, PersonalEmailPriority, PersonalEmailSentiment, PersonalEmailDraftStyle } from '@/types/personalEmail'

const FOLDERS: { value: PersonalEmailFolder; label: string; icon: any }[] = [
  { value: 'inbox', label: 'Inbox', icon: Inbox },
  { value: 'sent', label: 'Sent', icon: Send },
  { value: 'drafts', label: 'Drafts', icon: FileEdit },
  { value: 'starred', label: 'Starred', icon: Star },
]

const PRIORITY_TONE: Record<PersonalEmailPriority, 'default' | 'warning' | 'danger'> = {
  low: 'default', medium: 'default', high: 'warning', urgent: 'danger',
}

const SENTIMENT_ICON: Record<PersonalEmailSentiment, any> = {
  positive: Smile, neutral: Meh, negative: Frown,
}

const CATEGORY_TONE: Record<string, 'default' | 'accent' | 'cyan'> = {
  work: 'accent', finance: 'cyan', personal: 'default', promotions: 'default',
  social: 'default', updates: 'default', spam: 'default', other: 'default',
}

function isUnanswered(m: { folder: string; ai_action_required: boolean | null; is_answered: boolean; is_spam: boolean }) {
  return m.folder === 'inbox' && m.ai_action_required && !m.is_answered && !m.is_spam
}

export default function PersonalEmailAccountPage() {
  const params = useParams<{ accountId: string }>()
  const accountId = params.accountId
  const router = useRouter()
  const queryClient = useQueryClient()
  const { toast } = useToast()

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('tb_token')) {
      router.replace('/login')
    }
  }, [router])

  const [folder, setFolder] = useState<PersonalEmailFolder>('inbox')
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showDigest, setShowDigest] = useState(false)
  // ── Part 2 ──────────────────────────────────────────────────────────────
  const [showAnalytics, setShowAnalytics] = useState(false)
  const [showRules, setShowRules] = useState(false)
  const [unansweredOnly, setUnansweredOnly] = useState(false)
  const [bulkMode, setBulkMode] = useState(false)
  const [bulkSelected, setBulkSelected] = useState<Set<string>>(new Set())
  const [bulkStyle, setBulkStyle] = useState<PersonalEmailDraftStyle>('professional')

  const { data: accountsData } = useQuery({
    queryKey: ['personal-email-accounts'],
    queryFn: personalEmailApi.listAccounts,
  })
  const account = accountsData?.accounts.find(a => a.id === accountId)

  const { data: messagesData, isLoading: messagesLoading } = useQuery({
    queryKey: ['personal-email-messages', accountId, folder, search],
    queryFn: () => personalEmailApi.listMessages(accountId, folder, search || undefined),
    enabled: !!accountId,
  })

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['personal-email-message', selectedId],
    queryFn: () => personalEmailApi.getMessage(selectedId as string),
    enabled: !!selectedId,
  })

  const syncMutation = useMutation({
    mutationFn: () => personalEmailApi.sync(accountId),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['personal-email-messages', accountId] })
      queryClient.invalidateQueries({ queryKey: ['personal-email-accounts'] })
      toast('success', `Synced ${res.synced} emails · ${res.new_messages} new · ${res.analyzed} analyzed.`)
    },
    onError: (e: any) => toast('error', e?.response?.data?.detail || 'Sync failed.'),
  })

  const starMutation = useMutation({
    mutationFn: ({ id, starred }: { id: string; starred: boolean }) =>
      starred ? personalEmailApi.unstar(id) : personalEmailApi.star(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['personal-email-messages', accountId] })
      queryClient.invalidateQueries({ queryKey: ['personal-email-message', selectedId] })
    },
    onError: () => toast('error', 'Could not update star.'),
  })

  const analyzeMutation = useMutation({
    mutationFn: (id: string) => personalEmailApi.analyze(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['personal-email-message', selectedId] })
      queryClient.invalidateQueries({ queryKey: ['personal-email-messages', accountId] })
      toast('success', 'Email re-analyzed.')
    },
    onError: (e: any) => toast('error', e?.response?.data?.detail || 'AI analysis failed.'),
  })

  const disconnectMutation = useMutation({
    mutationFn: () => personalEmailApi.disconnect(accountId),
    onSuccess: () => {
      toast('success', 'Account disconnected.')
      router.push('/personal-email')
    },
    onError: () => toast('error', 'Could not disconnect.'),
  })

  // ── Part 2: bulk reply ────────────────────────────────────────────────
  const bulkReplyMutation = useMutation({
    mutationFn: () => personalEmailApi.bulkReply(accountId, Array.from(bulkSelected), bulkStyle),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['personal-email-messages', accountId] })
      setBulkMode(false)
      setBulkSelected(new Set())
      toast('success', `Generated ${res.drafts.length} reply draft(s). Review and send from each email.`)
    },
    onError: (e: any) => toast('error', e?.response?.data?.detail || 'Bulk reply failed.'),
  })

  // ── Part 2: unanswered reminder ────────────────────────────────────────
  const { data: unansweredList } = useQuery({
    queryKey: ['personal-email-unanswered', accountId],
    queryFn: () => personalEmailApi.unanswered(accountId),
    enabled: !!accountId,
  })

  // ── Part 2: conversation history / thread ──────────────────────────────
  const { data: thread } = useQuery({
    queryKey: ['personal-email-thread', selectedId],
    queryFn: () => personalEmailApi.thread(selectedId as string),
    enabled: !!selectedId,
  })

  // ── Part 2: AI follow-up suggestion for a sent-but-unanswered message ──
  const followUpMutation = useMutation({
    mutationFn: (id: string) => personalEmailApi.generateFollowUp(id),
    onError: (e: any) => toast('error', e?.response?.data?.detail || 'Could not generate a follow-up suggestion.'),
  })

  const toggleBulkSelected = (id: string) => {
    setBulkSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const messages = (messagesData?.messages || []).filter(m => !unansweredOnly || isUnanswered(m))

  return (
    <div className="min-h-screen">
      <SubPageBar
        backHref="/personal-email"
        crumb={account?.email_address || 'Personal Email'}
        crumbIcon={<Mail size={14} />}
        right={
          <>
            {(unansweredList?.length ?? 0) > 0 && (
              <Button size="sm" variant="ghost" icon={<BellRing size={13} />} onClick={() => { setFolder('inbox'); setUnansweredOnly(true); setSelectedId(null) }}>
                {unansweredList!.length} unanswered
              </Button>
            )}
            <Button size="sm" variant="ghost" icon={<Zap size={13} />} onClick={() => setShowRules(true)}>
              Auto-reply rules
            </Button>
            <Button size="sm" variant="ghost" icon={<BarChart3 size={13} />} onClick={() => setShowAnalytics(true)}>
              Analytics
            </Button>
            <Button size="sm" variant="ghost" icon={<Sparkles size={13} />} onClick={() => setShowDigest(true)}>
              Digest
            </Button>
            <Button size="sm" variant="secondary" icon={<RefreshCw size={13} className={syncMutation.isPending ? 'animate-spin' : ''} />} loading={syncMutation.isPending} onClick={() => syncMutation.mutate()}>
              Sync
            </Button>
          </>
        }
      />

      <main className="max-w-6xl mx-auto px-3 sm:px-6 py-4 sm:py-6">
        {account && account.status !== 'connected' && (
          <Card className="p-4 mb-4 flex items-center gap-3">
            <AlertCircle size={16} className="text-amber-400 flex-shrink-0" />
            <p className="text-xs text-white/50 flex-1">
              This account is {account.status}. {account.last_error || 'Reconnect from the accounts list to keep syncing.'}
            </p>
          </Card>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-4">
          {/* ── List column ────────────────────────────────────────────── */}
          <div className={`space-y-3 ${selectedId ? 'hidden lg:block' : ''}`}>
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
              {FOLDERS.map(f => {
                const Icon = f.icon
                return (
                  <button
                    key={f.value}
                    onClick={() => { setFolder(f.value); setSelectedId(null); setUnansweredOnly(false) }}
                    className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border whitespace-nowrap transition ${
                      folder === f.value
                        ? 'bg-[#6366f1]/15 text-[#a5b4fc] border-[#6366f1]/30'
                        : 'bg-white/[0.03] text-white/40 border-white/10 hover:text-white/70'
                    }`}
                  >
                    <Icon size={12} /> {f.label}
                  </button>
                )
              })}
              {folder === 'inbox' && (
                <button
                  onClick={() => setUnansweredOnly(v => !v)}
                  className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border whitespace-nowrap transition ${
                    unansweredOnly
                      ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                      : 'bg-white/[0.03] text-white/40 border-white/10 hover:text-white/70'
                  }`}
                >
                  <BellRing size={12} /> Unanswered
                </button>
              )}
            </div>

            {folder === 'inbox' && messages.length > 0 && (
              <div className="flex items-center justify-between">
                <button
                  onClick={() => { setBulkMode(v => !v); setBulkSelected(new Set()) }}
                  className="text-[11px] text-white/40 hover:text-white/70 flex items-center gap-1"
                >
                  {bulkMode ? <CheckSquare size={12} /> : <Square size={12} />} Bulk reply
                </button>
                {bulkMode && bulkSelected.size > 0 && (
                  <span className="text-[11px] text-white/40">{bulkSelected.size} selected</span>
                )}
              </div>
            )}

            <div className="relative">
              <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/25" />
              <Input placeholder="Search emails…" value={search} onChange={e => setSearch(e.target.value)} className="pl-9" />
            </div>

            {messagesLoading && <SkeletonRows count={6} />}

            {!messagesLoading && messages.length === 0 && (
              <EmptyState icon={<Inbox size={20} />} title="No emails here" description="Try syncing, or check another folder." />
            )}

            <div className="space-y-1.5">
              {messages.map(m => (
                <Card
                  key={m.id}
                  hover
                  onClick={() => bulkMode ? toggleBulkSelected(m.id) : setSelectedId(m.id)}
                  className={`p-3 ${selectedId === m.id ? 'border-[#6366f1]/40' : ''}`}
                >
                  <div className="flex items-start gap-2">
                    {bulkMode && (
                      <button onClick={(e) => { e.stopPropagation(); toggleBulkSelected(m.id) }} className="flex-shrink-0 mt-0.5 text-white/25 hover:text-[#a5b4fc]">
                        {bulkSelected.has(m.id) ? <CheckSquare size={15} className="text-[#a5b4fc]" /> : <Square size={15} />}
                      </button>
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-xs font-semibold text-white truncate flex items-center gap-1.5">
                          {isUnanswered(m) && <span className="w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" />}
                          {m.sender_name || m.sender_email || 'Unknown sender'}
                        </p>
                        {m.ai_priority && <Badge tone={PRIORITY_TONE[m.ai_priority]} className="flex-shrink-0">{m.ai_priority}</Badge>}
                      </div>
                      <p className="text-xs text-white/60 truncate mt-0.5">{m.subject || '(no subject)'}</p>
                      <p className="text-[11px] text-white/30 truncate mt-0.5">{m.ai_summary || m.snippet}</p>
                      <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                        {m.is_spam && <Badge tone="danger"><ShieldAlert size={10} className="mr-0.5" />Spam</Badge>}
                        {!m.is_spam && m.category && <Badge tone={CATEGORY_TONE[m.category] || 'default'}>{m.category}</Badge>}
                        {m.has_attachments && <Paperclip size={11} className="text-white/25" />}
                      </div>
                    </div>
                    {!bulkMode && (
                      <button
                        onClick={(e) => { e.stopPropagation(); starMutation.mutate({ id: m.id, starred: m.is_starred }) }}
                        className="flex-shrink-0 text-white/20 hover:text-amber-400 transition p-1"
                      >
                        <Star size={13} fill={m.is_starred ? 'currentColor' : 'none'} className={m.is_starred ? 'text-amber-400' : ''} />
                      </button>
                    )}
                  </div>
                </Card>
              ))}
            </div>

            {bulkMode && bulkSelected.size > 0 && (
              <div className="tb2-glass rounded-xl p-3 space-y-2 sticky bottom-2">
                <p className="text-[11px] text-white/40">Reply style for {bulkSelected.size} email(s)</p>
                <div className="flex items-center gap-2">
                  <Select value={bulkStyle} onChange={e => setBulkStyle(e.target.value as PersonalEmailDraftStyle)} className="!py-1.5 !text-xs flex-1">
                    <option value="professional">Professional</option>
                    <option value="friendly">Friendly</option>
                    <option value="short">Short</option>
                  </Select>
                  <Button size="sm" icon={<SendIcon size={13} />} loading={bulkReplyMutation.isPending} onClick={() => bulkReplyMutation.mutate()}>
                    Generate drafts
                  </Button>
                </div>
              </div>
            )}
          </div>

          {/* ── Detail column ──────────────────────────────────────────── */}
          <div className={selectedId ? '' : 'hidden lg:block'}>
            {!selectedId && (
              <div className="hidden lg:flex h-full items-center justify-center">
                <EmptyState icon={<Mail size={22} />} title="Select an email" description="Pick an email from the list to see the AI summary and reply drafts." />
              </div>
            )}

            {selectedId && (
              <Card className="p-4 sm:p-5">
                <button onClick={() => setSelectedId(null)} className="lg:hidden flex items-center gap-1 text-xs text-white/40 mb-3">
                  <ChevronLeft size={14} /> Back to list
                </button>

                {detailLoading && <PageLoader label="Loading email…" />}

                {!detailLoading && detail && (
                  <div className="space-y-5">
                    {detail.is_spam && (
                      <div className="rounded-xl p-3 bg-red-500/10 border border-red-500/25 flex items-start gap-2.5">
                        <ShieldAlert size={16} className="text-red-400 flex-shrink-0 mt-0.5" />
                        <div>
                          <p className="text-xs font-semibold text-red-300">Flagged as spam / possible phishing</p>
                          {detail.spam_reason && <p className="text-[11px] text-red-300/70 mt-0.5">{detail.spam_reason}</p>}
                        </div>
                      </div>
                    )}

                    <div>
                      <div className="flex items-start justify-between gap-2">
                        <h2 className="text-base font-semibold text-white">{detail.subject || '(no subject)'}</h2>
                        <button onClick={() => starMutation.mutate({ id: detail.id, starred: detail.is_starred })} className="text-white/25 hover:text-amber-400 transition flex-shrink-0">
                          <Star size={15} fill={detail.is_starred ? 'currentColor' : 'none'} className={detail.is_starred ? 'text-amber-400' : ''} />
                        </button>
                      </div>
                      <p className="text-xs text-white/40 mt-1">
                        {detail.sender_name ? `${detail.sender_name} · ` : ''}{detail.sender_email}
                        {detail.received_at && ` · ${new Date(detail.received_at).toLocaleString()}`}
                      </p>
                      {(detail.category || (detail.labels && detail.labels.length > 0)) && (
                        <div className="flex items-center gap-1.5 flex-wrap mt-2">
                          {detail.category && <Badge tone={CATEGORY_TONE[detail.category] || 'default'}>{detail.category}</Badge>}
                          {detail.labels?.map(l => <Badge key={l} tone="default">{l}</Badge>)}
                        </div>
                      )}
                    </div>

                    {/* AI analysis panel */}
                    <div className="tb2-glass rounded-xl p-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <p className="text-xs font-semibold text-white/50 uppercase tracking-wide flex items-center gap-1.5">
                          <Sparkles size={12} /> AI Analysis
                        </p>
                        <Button size="sm" variant="ghost" onClick={() => analyzeMutation.mutate(detail.id)} loading={analyzeMutation.isPending}>
                          Re-analyze
                        </Button>
                      </div>
                      <p className="text-sm text-white/70 leading-relaxed">{detail.ai_summary || 'Not analyzed yet — sync or re-analyze to generate an AI summary.'}</p>
                      <div className="flex flex-wrap items-center gap-2">
                        {detail.ai_priority && <Badge tone={PRIORITY_TONE[detail.ai_priority]}>{detail.ai_priority} priority</Badge>}
                        {detail.ai_sentiment && (
                          <Badge tone="default">
                            {(() => { const Icon = SENTIMENT_ICON[detail.ai_sentiment]; return <Icon size={10} className="mr-0.5" /> })()}
                            {detail.ai_sentiment}
                          </Badge>
                        )}
                        <Badge tone={detail.ai_action_required ? 'warning' : 'default'}>
                          {detail.ai_action_required ? 'Action required' : 'No action needed'}
                        </Badge>
                        {detail.ai_deadline && (
                          <Badge tone="cyan"><Clock size={10} className="mr-0.5" />{detail.ai_deadline}</Badge>
                        )}
                        {isUnanswered(detail) && <Badge tone="warning"><BellRing size={10} className="mr-0.5" />Awaiting your reply</Badge>}
                      </div>
                      {detail.ai_tasks && detail.ai_tasks.length > 0 && (
                        <div className="pt-1">
                          <p className="text-[10px] font-semibold text-white/35 uppercase tracking-wide mb-1.5 flex items-center gap-1">
                            <ListChecks size={11} /> Tasks detected
                          </p>
                          <ul className="space-y-1">
                            {detail.ai_tasks.map((t, i) => (
                              <li key={i} className="text-xs text-white/55 flex items-start gap-1.5">
                                <span className="text-white/20 mt-0.5">•</span> {t}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>

                    {/* Body */}
                    <div className="tb2-glass rounded-xl p-4">
                      <p className="text-[10px] font-semibold text-white/35 uppercase tracking-wide mb-2">Message</p>
                      <p className="text-sm text-white/60 leading-relaxed whitespace-pre-wrap max-h-64 overflow-y-auto">
                        {detail.body_text || detail.snippet || 'No content available.'}
                      </p>
                    </div>

                    {/* Part 2: attachments */}
                    {detail.has_attachments && detail.attachments && detail.attachments.length > 0 && (
                      <div className="tb2-glass rounded-xl p-4">
                        <p className="text-[10px] font-semibold text-white/35 uppercase tracking-wide mb-2 flex items-center gap-1">
                          <Paperclip size={11} /> Attachments
                        </p>
                        <div className="space-y-1.5">
                          {detail.attachments.map(a => (
                            <button
                              key={a.attachment_id}
                              onClick={() => personalEmailApi.downloadAttachment(detail.id, a.attachment_id, a.filename).catch(() => toast('error', 'Could not download attachment.'))}
                              className="w-full flex items-center justify-between gap-2 text-xs text-white/55 hover:text-white/85 transition px-2.5 py-1.5 rounded-lg bg-white/[0.03]"
                            >
                              <span className="truncate">{a.filename}</span>
                              <Download size={12} className="flex-shrink-0" />
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Part 2: conversation history */}
                    {thread && thread.length > 1 && (
                      <div className="tb2-glass rounded-xl p-4">
                        <p className="text-[10px] font-semibold text-white/35 uppercase tracking-wide mb-2 flex items-center gap-1">
                          <History size={11} /> Conversation history
                        </p>
                        <div className="space-y-2 max-h-56 overflow-y-auto">
                          {thread.map(t => (
                            <button
                              key={t.id}
                              onClick={() => setSelectedId(t.id)}
                              className={`w-full text-left px-2.5 py-1.5 rounded-lg text-xs transition ${
                                t.id === detail.id ? 'bg-[#6366f1]/15 text-[#a5b4fc]' : 'bg-white/[0.03] text-white/50 hover:text-white/80'
                              }`}
                            >
                              <span className="font-medium">{t.folder === 'sent' ? 'You' : (t.sender_name || t.sender_email || 'Unknown')}</span>
                              {t.received_at && <span className="text-white/25"> · {new Date(t.received_at).toLocaleDateString()}</span>}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Part 2: AI follow-up suggestion for sent-but-unanswered messages */}
                    {detail.folder === 'sent' && !detail.is_answered && (
                      <div className="tb2-glass rounded-xl p-4 space-y-2.5">
                        <p className="text-[10px] font-semibold text-white/35 uppercase tracking-wide flex items-center gap-1">
                          <BellRing size={11} /> No reply yet
                        </p>
                        {followUpMutation.data ? (
                          <p className="text-sm text-white/70 leading-relaxed whitespace-pre-wrap">{followUpMutation.data.suggested_content}</p>
                        ) : (
                          <p className="text-xs text-white/40">Generate a short follow-up nudge to send.</p>
                        )}
                        <Button size="sm" variant="secondary" loading={followUpMutation.isPending} onClick={() => followUpMutation.mutate(detail.id)}>
                          {followUpMutation.data ? 'Regenerate suggestion' : 'Suggest a follow-up'}
                        </Button>
                      </div>
                    )}

                    {/* Drafts */}
                    <DraftPanel messageId={detail.id} drafts={detail.drafts || []} />
                  </div>
                )}
              </Card>
            )}
          </div>
        </div>

        {account && (
          <div className="mt-8 flex justify-end">
            <Button size="sm" variant="danger" icon={<Unplug size={13} />} loading={disconnectMutation.isPending} onClick={() => disconnectMutation.mutate()}>
              Disconnect account
            </Button>
          </div>
        )}
      </main>

      {showDigest && <DigestModal accountId={accountId} onClose={() => setShowDigest(false)} />}
      {showAnalytics && <AnalyticsModal accountId={accountId} onClose={() => setShowAnalytics(false)} />}
      {showRules && <AutoReplyRulesModal accountId={accountId} onClose={() => setShowRules(false)} />}
    </div>
  )
}
