'use client'
import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import {
  Send, Bot, Check, Copy,
  RefreshCw, Unlink, Power, ShieldCheck, Webhook, Activity,
  CheckCircle2, XCircle, AlertTriangle, Users, Reply, Inbox,
  Eye, EyeOff, ExternalLink, Headset, MessageSquare, UserCheck, XOctagon,
} from 'lucide-react'
import { workflowsApi } from '@/lib/api/workflows'
import { telegramApi } from '@/lib/api/telegram'
import { getErrorMessage } from '@/lib/utils/errors'
import type { TelegramConnectionPayload } from '@/types/telegram'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Field'
import { SubPageBar } from '@/components/ui/TopBar'
import { PageLoader } from '@/components/ui/States'
import { cn } from '@/lib/utils/cn'
import { ConversationsTable } from '@/components/analytics/ConversationsTable'

function Section({
  icon, title, children, right,
}: { icon: React.ReactNode; title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-white/50">
          {icon}
          <span className="text-xs font-semibold uppercase tracking-wider">{title}</span>
        </div>
        {right}
      </div>
      {children}
    </Card>
  )
}

function Field({
  label, value, onChange, placeholder, type = 'text', hint,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  type?: string
  hint?: string
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-[11px] font-medium text-white/40">{label}</label>
      <Input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} />
      {hint && <p className="text-[10px] text-white/25">{hint}</p>}
    </div>
  )
}

function CopyRow({ label, value, secret = false }: { label: string; value: string; secret?: boolean }) {
  const [copied, setCopied] = useState(false)
  const [show, setShow] = useState(!secret)
  const copy = () => {
    navigator.clipboard.writeText(value)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <div className="space-y-1.5">
      <label className="text-[11px] font-medium text-white/40">{label}</label>
      <div className="flex items-center gap-1.5">
        <input
          readOnly
          value={show ? value : '•'.repeat(Math.min(value.length, 32))}
          className="tb2-field flex-1 text-xs text-white/70 rounded-lg px-3 py-2.5 outline-none font-mono truncate"
        />
        {secret && (
          <button
            onClick={() => setShow(s => !s)}
            className="tb2-iconbtn p-2.5 text-white/30 hover:text-white/60 rounded-lg hover:bg-white/[0.06] transition flex-shrink-0"
          >
            {show ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
        )}
        <button
          onClick={copy}
          className="tb2-iconbtn p-2.5 text-white/30 hover:text-white/60 rounded-lg hover:bg-white/[0.06] transition flex-shrink-0"
        >
          {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
        </button>
      </div>
    </div>
  )
}

function HealthDot({ health }: { health?: string }) {
  const map: Record<string, string> = {
    healthy: 'bg-emerald-400 tb2-pulse-dot',
    degraded: 'bg-amber-400',
    error: 'bg-red-400',
    unknown: 'bg-white/20',
  }
  return <span className={`inline-block w-2 h-2 rounded-full ${map[health || 'unknown']}`} />
}

function statusLabel(status?: string) {
  if (status === 'invalid_token') return 'Invalid token'
  return status || 'disconnected'
}

export default function TelegramSettingsPage() {
  const params = useParams()
  const workflowId = String(params.workflowId)
  const router = useRouter()
  const qc = useQueryClient()

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('tb_token')) {
      router.replace('/login')
    }
  }, [router])

  const { data: workflow } = useQuery({
    queryKey: ['workflow', workflowId],
    queryFn: () => workflowsApi.get(workflowId),
  })

  const { data: channel, isLoading } = useQuery({
    queryKey: ['telegram-channel', workflowId],
    queryFn: () => telegramApi.get(workflowId),
  })

  const { data: webhookInfo } = useQuery({
    queryKey: ['telegram-webhook-info', workflowId],
    queryFn: () => telegramApi.webhookInfo(workflowId),
    enabled: !!channel?.connected,
    retry: false,
  })

  const { data: stats } = useQuery({
    queryKey: ['telegram-stats', workflowId],
    queryFn: () => telegramApi.stats(workflowId),
    enabled: !!channel?.connected,
    refetchInterval: 8000,
  })

  const { data: tgAnalytics } = useQuery({
    queryKey: ['telegram-analytics', workflowId],
    queryFn: () => telegramApi.analytics(workflowId),
    enabled: !!channel?.connected,
    refetchInterval: 15000,
  })

  const [form, setForm] = useState<TelegramConnectionPayload>({ bot_token: '' })
  const [editing, setEditing] = useState(false)
  const [notice, setNotice] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['telegram-channel', workflowId] })
    qc.invalidateQueries({ queryKey: ['telegram-webhook-info', workflowId] })
    qc.invalidateQueries({ queryKey: ['telegram-stats', workflowId] })
    qc.invalidateQueries({ queryKey: ['telegram-analytics', workflowId] })
  }

  const connectMutation = useMutation({
    mutationFn: (payload: TelegramConnectionPayload) => telegramApi.connect(workflowId, payload),
    onSuccess: data => {
      invalidate()
      setEditing(false)
      setForm({ bot_token: '' })
      setNotice(
        data.status === 'connected'
          ? { kind: 'ok', text: `Connected to @${data.bot_username || 'your bot'}.` }
          : { kind: 'err', text: data.last_error || 'Could not verify this bot token.' }
      )
    },
    onError: err => setNotice({ kind: 'err', text: getErrorMessage(err, 'Could not save the connection.') }),
  })

  const testMutation = useMutation({
    mutationFn: () => telegramApi.test(workflowId),
    onSuccess: res => {
      invalidate()
      setNotice(
        res.ok
          ? { kind: 'ok', text: `Connected to @${res.bot_username || 'your bot'}.` }
          : { kind: 'err', text: res.error || 'Connection test failed.' }
      )
    },
    onError: err => setNotice({ kind: 'err', text: getErrorMessage(err, 'Test connection failed.') }),
  })

  const enableMutation = useMutation({
    mutationFn: () => telegramApi.enable(workflowId),
    onSuccess: invalidate,
    onError: err => setNotice({ kind: 'err', text: getErrorMessage(err, 'Could not enable Telegram.') }),
  })

  const disableMutation = useMutation({
    mutationFn: () => telegramApi.disable(workflowId),
    onSuccess: invalidate,
  })

  const reconnectMutation = useMutation({
    mutationFn: () => telegramApi.reconnect(workflowId),
    onSuccess: () => {
      invalidate()
      setNotice({ kind: 'ok', text: 'Reconnected successfully.' })
    },
    onError: err => setNotice({ kind: 'err', text: getErrorMessage(err, 'Reconnect failed.') }),
  })

  const disconnectMutation = useMutation({
    mutationFn: () => telegramApi.disconnect(workflowId),
    onSuccess: () => {
      invalidate()
      setNotice({ kind: 'ok', text: 'Disconnected. Bot token cleared.' })
    },
  })

  const isConnected = !!channel?.connected
  const isLive = isConnected && channel?.status === 'connected'
  const showForm = !isConnected || editing

  return (
    <div className="tb2-shell">
      <SubPageBar
        backHref="/telegram"
        crumb={workflow?.name || '…'}
        crumbIcon={<Send size={13} className="text-sky-400/70" />}
        right={
          isConnected ? (
            <div className="flex items-center gap-2">
              <HealthDot health={channel?.health_status} />
              <span className="text-[11px] text-white/40 capitalize">{statusLabel(channel?.status)}</span>
            </div>
          ) : undefined
        }
      />

      <div className="max-w-2xl mx-auto px-6 py-10 space-y-5">
        {notice && (
          <div
            className={cn(
              'tb2-rise flex items-start gap-2 p-3 rounded-xl text-xs border',
              notice.kind === 'ok'
                ? 'bg-emerald-500/5 border-emerald-500/20 text-emerald-300'
                : 'bg-red-500/5 border-red-500/20 text-red-300'
            )}
          >
            {notice.kind === 'ok' ? <CheckCircle2 size={14} className="mt-0.5 flex-shrink-0" /> : <XCircle size={14} className="mt-0.5 flex-shrink-0" />}
            <span>{notice.text}</span>
          </div>
        )}

        {isConnected && !editing && (
          <Section
            icon={<ShieldCheck size={14} />}
            title="Connection"
            right={
              <button
                onClick={() => setEditing(true)}
                className="text-[11px] text-white/35 hover:text-cyan-300 transition px-2 py-1 rounded-md hover:bg-white/[0.06]"
              >
                Edit
              </button>
            }
          >
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <p className="text-white/25 text-[10px] uppercase tracking-wide mb-0.5">Bot Username</p>
                <p className="text-white/75">{channel?.bot_username ? `@${channel.bot_username}` : '—'}</p>
              </div>
              <div>
                <p className="text-white/25 text-[10px] uppercase tracking-wide mb-0.5">Bot Name</p>
                <p className="text-white/75">{channel?.bot_first_name || '—'}</p>
              </div>
              <div>
                <p className="text-white/25 text-[10px] uppercase tracking-wide mb-0.5">Status</p>
                <p className="text-white/75 capitalize">{statusLabel(channel?.status)}</p>
              </div>
              <div>
                <p className="text-white/25 text-[10px] uppercase tracking-wide mb-0.5">Webhook</p>
                <p className="text-white/75">{channel?.webhook_registered ? 'Registered' : 'Not registered'}</p>
              </div>
            </div>
            {channel?.last_error && (
              <div className="flex items-start gap-2 p-2.5 rounded-lg bg-red-500/5 border border-red-500/15 text-[11px] text-red-300">
                <AlertTriangle size={12} className="mt-0.5 flex-shrink-0" />
                {channel.last_error}
              </div>
            )}
            <div className="flex items-center gap-2 pt-1">
              <Button
                variant="secondary"
                size="sm"
                className="flex-1"
                loading={testMutation.isPending}
                icon={!testMutation.isPending ? <ShieldCheck size={12} /> : undefined}
                onClick={() => testMutation.mutate()}
              >
                Test Connection
              </Button>
              <Button
                variant="secondary"
                size="sm"
                className="flex-1"
                loading={reconnectMutation.isPending}
                icon={!reconnectMutation.isPending ? <RefreshCw size={12} /> : undefined}
                onClick={() => reconnectMutation.mutate()}
              >
                Reconnect
              </Button>
              <Button
                variant="danger"
                size="sm"
                className="flex-1"
                loading={disconnectMutation.isPending}
                icon={!disconnectMutation.isPending ? <Unlink size={12} /> : undefined}
                onClick={() => {
                  if (window.confirm('Disconnect Telegram? The bot token will be cleared.')) disconnectMutation.mutate()
                }}
              >
                Disconnect
              </Button>
            </div>
          </Section>
        )}

        {isConnected && !editing && (
          <Section icon={<Power size={14} />} title="Status">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-white/80 font-medium">{isLive ? 'Bot is live on Telegram' : 'Telegram is disabled'}</p>
                <p className="text-[11px] text-white/30 mt-0.5">
                  {channel?.status !== 'connected'
                    ? 'Connect a valid bot token to enable.'
                    : channel?.is_enabled
                    ? 'Incoming messages are being answered automatically.'
                    : 'Incoming messages will not be processed until enabled.'}
                </p>
              </div>
              <button
                onClick={() => (channel?.is_enabled ? disableMutation.mutate() : enableMutation.mutate())}
                disabled={channel?.status !== 'connected' || enableMutation.isPending || disableMutation.isPending}
                className={cn(
                  'relative w-11 h-6 rounded-full transition-colors flex-shrink-0 disabled:opacity-30',
                  channel?.is_enabled ? 'bg-emerald-500' : 'bg-white/10'
                )}
              >
                <span
                  className={cn(
                    'absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform',
                    channel?.is_enabled ? 'translate-x-5' : 'translate-x-0.5'
                  )}
                />
              </button>
            </div>
          </Section>
        )}

        {isConnected && !editing && (
          <Section icon={<Activity size={14} />} title="Health & Subscriber Stats">
            <div className="grid grid-cols-3 gap-2">
              <div className="p-3 rounded-lg bg-white/[0.03] border border-white/[0.07] text-center">
                <Inbox size={13} className="mx-auto text-white/25 mb-1" />
                <p className="text-lg font-bold text-white/85">{stats?.messages_received_count ?? channel?.messages_received_count ?? 0}</p>
                <p className="text-[9px] text-white/25 uppercase tracking-wide">Received</p>
              </div>
              <div className="p-3 rounded-lg bg-white/[0.03] border border-white/[0.07] text-center">
                <Reply size={13} className="mx-auto text-white/25 mb-1" />
                <p className="text-lg font-bold text-white/85">{stats?.messages_sent_count ?? channel?.messages_sent_count ?? 0}</p>
                <p className="text-[9px] text-white/25 uppercase tracking-wide">Sent</p>
              </div>
              <div className="p-3 rounded-lg bg-white/[0.03] border border-white/[0.07] text-center">
                <Users size={13} className="mx-auto text-white/25 mb-1" />
                <p className="text-lg font-bold text-white/85">{stats?.subscriber_count ?? channel?.subscriber_count ?? 0}</p>
                <p className="text-[9px] text-white/25 uppercase tracking-wide">Subscribers</p>
              </div>
            </div>
            <div className="flex items-center justify-between text-[11px] text-white/30 pt-1">
              <span>Last sync: {channel?.last_sync_at ? new Date(channel.last_sync_at).toLocaleString() : '—'}</span>
              <span>Last webhook: {channel?.last_webhook_at ? new Date(channel.last_webhook_at).toLocaleString() : '—'}</span>
            </div>

            {!!stats?.subscribers?.length && (
              <div className="pt-2 border-t border-white/[0.06] space-y-1.5">
                <p className="text-[10px] text-white/25 uppercase tracking-wide">Recent subscribers</p>
                {stats.subscribers.slice(0, 5).map(s => (
                  <div key={s.chat_id} className="flex items-center justify-between text-xs">
                    <span className="text-white/60">{s.username ? `@${s.username}` : s.first_name || s.chat_id}</span>
                    <span className="text-white/25">{s.message_count} msgs</span>
                  </div>
                ))}
              </div>
            )}
          </Section>
        )}

        {isConnected && !editing && tgAnalytics && (
          <Section icon={<Headset size={14} />} title="AI Agent & Human Handoff" right={
            <Link href="/live-agent" className="text-[11px] text-[#a5b4fc] hover:text-cyan-300 transition-colors inline-flex items-center gap-0.5">
              Live Agent <ExternalLink size={9} />
            </Link>
          }>
            <p className="text-[11px] text-white/30">
              Every Telegram reply continues through this bot's AI Agent automatically. If the AI can't
              answer, or a subscriber asks for a human (e.g. sends "/agent"), the conversation is handed off
              to your Live Agent team.
            </p>
            <div className="grid grid-cols-3 gap-2">
              <div className="p-3 rounded-lg bg-white/[0.03] border border-white/[0.07] text-center">
                <MessageSquare size={13} className="mx-auto text-white/25 mb-1" />
                <p className="text-lg font-bold text-white/85">{tgAnalytics.active_conversations}</p>
                <p className="text-[9px] text-white/25 uppercase tracking-wide">Active</p>
              </div>
              <div className="p-3 rounded-lg bg-white/[0.03] border border-white/[0.07] text-center">
                <Bot size={13} className="mx-auto text-emerald-400/70 mb-1" />
                <p className="text-lg font-bold text-white/85">{tgAnalytics.ai_resolved}</p>
                <p className="text-[9px] text-white/25 uppercase tracking-wide">AI Resolved</p>
              </div>
              <div className="p-3 rounded-lg bg-white/[0.03] border border-white/[0.07] text-center">
                <UserCheck size={13} className="mx-auto text-[#a5b4fc] mb-1" />
                <p className="text-lg font-bold text-white/85">{tgAnalytics.human_handoff}</p>
                <p className="text-[9px] text-white/25 uppercase tracking-wide">Human Handoff</p>
              </div>
              <div className="p-3 rounded-lg bg-white/[0.03] border border-white/[0.07] text-center">
                <Reply size={13} className="mx-auto text-white/25 mb-1" />
                <p className="text-lg font-bold text-white/85">{tgAnalytics.replies}</p>
                <p className="text-[9px] text-white/25 uppercase tracking-wide">Replies</p>
              </div>
              <div className="p-3 rounded-lg bg-white/[0.03] border border-white/[0.07] text-center">
                <XOctagon size={13} className="mx-auto text-red-400/70 mb-1" />
                <p className="text-lg font-bold text-white/85">{tgAnalytics.failed_deliveries}</p>
                <p className="text-[9px] text-white/25 uppercase tracking-wide">Failed Deliveries</p>
              </div>
            </div>
          </Section>
        )}

        {isConnected && !editing && (
          <Section icon={<MessageSquare size={14} />} title="Conversation Timeline">
            <p className="text-[11px] text-white/30 -mt-1">
              Full history for every Telegram conversation on this bot — search by message content or
              session, and filter by active/ended. Open a conversation to see the AI Agent and Live Agent
              (human handoff) status alongside its full message timeline.
            </p>
            <div className="-mx-4 -mb-3">
              <ConversationsTable
                fixedWorkflowId={workflowId}
                fixedSource="telegram"
                hideSourceFilter
                hideExport
              />
            </div>
          </Section>
        )}


        {isConnected && !editing && webhookInfo && (
          <Section icon={<Webhook size={14} />} title="Webhook">
            <p className="text-[11px] text-white/30">
              ThunderBots registers this webhook with Telegram automatically when you connect or reconnect —
              there's nothing to paste anywhere else.
            </p>
            <CopyRow label="Webhook URL" value={webhookInfo.webhook_url} />
            <div className="flex items-center gap-1.5 text-[11px] text-white/30">
              <span className={cn('inline-block w-1.5 h-1.5 rounded-full', webhookInfo.webhook_registered ? 'bg-emerald-400' : 'bg-white/20')} />
              {webhookInfo.webhook_registered ? 'Registered with Telegram' : 'Not currently registered'}
            </div>
          </Section>
        )}

        {showForm && (
          <Section icon={<Bot size={14} />} title={isConnected ? 'Edit Connection' : 'Connect Telegram'}>
            <p className="text-[11px] text-white/30">
              Create a bot with{' '}
              <a href="https://t.me/BotFather" target="_blank" rel="noreferrer" className="text-[#a5b4fc] hover:text-cyan-300 transition-colors">
                @BotFather
              </a>{' '}
              on Telegram, then paste the bot token it gives you below.
            </p>
            <Field
              label="Bot Token"
              value={form.bot_token}
              onChange={v => setForm(f => ({ ...f, bot_token: v }))}
              placeholder="e.g. 123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
              type="password"
            />
            <div className="flex gap-2 pt-1">
              {isConnected && (
                <Button variant="secondary" className="flex-1" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
              )}
              <Button
                className="flex-1"
                loading={connectMutation.isPending}
                onClick={() =>
                  form.bot_token.trim()
                    ? connectMutation.mutate(form)
                    : setNotice({ kind: 'err', text: 'Bot token is required.' })
                }
              >
                Save & Connect
              </Button>
            </div>
          </Section>
        )}

        {isLoading && <PageLoader />}

        <Section icon={<Send size={14} />} title="What this channel supports">
          <div className="grid grid-cols-2 gap-3 text-[11px] text-white/40">
            <div>
              <p className="text-white/25 uppercase tracking-wide text-[10px] mb-1">Receiving</p>
              <ul className="space-y-0.5">
                <li>Text messages</li>
                <li>/start conversations</li>
              </ul>
            </div>
            <div>
              <p className="text-white/25 uppercase tracking-wide text-[10px] mb-1">Sending</p>
              <ul className="space-y-0.5">
                <li>Text replies</li>
                <li>Only to subscribers who messaged the bot first</li>
              </ul>
            </div>
          </div>
          <p className="text-[11px] text-white/25 pt-1 border-t border-white/[0.06]">
            Every message runs through this bot's exact same workflow as your website chat — Start, Text,
            Multiple Choice, Transition, AI Agent and End nodes all work identically, and every conversation
            appears in{' '}
            <Link href="/analytics" className="text-[#a5b4fc] hover:text-cyan-300 transition-colors inline-flex items-center gap-0.5">
              Analytics <ExternalLink size={9} />
            </Link>. Only people who have started a conversation with your bot are ever tracked as subscribers —
            ThunderBots never sends to anyone who hasn't messaged the bot first.
          </p>
        </Section>
      </div>
    </div>
  )
}
