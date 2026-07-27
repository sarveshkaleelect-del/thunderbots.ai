'use client'
import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import {
  MessageCircle, Bot, Check, Copy,
  RefreshCw, Unlink, Power, ShieldCheck, Webhook, Activity,
  CheckCircle2, XCircle, AlertTriangle, Circle, Users, Send, Inbox,
  Eye, EyeOff, ExternalLink,
} from 'lucide-react'
import { workflowsApi } from '@/lib/api/workflows'
import { whatsappApi } from '@/lib/api/whatsapp'
import { getErrorMessage } from '@/lib/utils/errors'
import type { WhatsAppConnectionPayload } from '@/types/whatsapp'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Field'
import { SubPageBar } from '@/components/ui/TopBar'
import { PageLoader } from '@/components/ui/States'
import { cn } from '@/lib/utils/cn'

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

export default function WhatsAppSettingsPage() {
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
    queryKey: ['whatsapp-channel', workflowId],
    queryFn: () => whatsappApi.get(workflowId),
  })

  const { data: webhookInfo } = useQuery({
    queryKey: ['whatsapp-webhook-info', workflowId],
    queryFn: () => whatsappApi.webhookInfo(workflowId),
    enabled: !!channel?.connected,
    retry: false,
  })

  const { data: stats } = useQuery({
    queryKey: ['whatsapp-stats', workflowId],
    queryFn: () => whatsappApi.stats(workflowId),
    enabled: !!channel?.connected,
    refetchInterval: 8000,
  })

  const [form, setForm] = useState<WhatsAppConnectionPayload>({
    phone_number_id: '', business_account_id: '', access_token: '', verify_token: '', app_secret: '',
  })
  const [editing, setEditing] = useState(false)
  const [notice, setNotice] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['whatsapp-channel', workflowId] })
    qc.invalidateQueries({ queryKey: ['whatsapp-webhook-info', workflowId] })
    qc.invalidateQueries({ queryKey: ['whatsapp-stats', workflowId] })
  }

  const connectMutation = useMutation({
    mutationFn: (payload: WhatsAppConnectionPayload) => whatsappApi.connect(workflowId, payload),
    onSuccess: () => {
      invalidate()
      setEditing(false)
      testMutation.mutate(undefined)
    },
    onError: err => setNotice({ kind: 'err', text: getErrorMessage(err, 'Could not save the connection.') }),
  })

  const testMutation = useMutation({
    mutationFn: () => whatsappApi.test(workflowId),
    onSuccess: res => {
      invalidate()
      setNotice(
        res.ok
          ? { kind: 'ok', text: `Connected to ${res.verified_name || res.display_phone_number || 'WhatsApp'}.` }
          : { kind: 'err', text: res.error || 'Connection test failed.' }
      )
    },
    onError: err => setNotice({ kind: 'err', text: getErrorMessage(err, 'Test connection failed.') }),
  })

  const enableMutation = useMutation({
    mutationFn: () => whatsappApi.enable(workflowId),
    onSuccess: invalidate,
    onError: err => setNotice({ kind: 'err', text: getErrorMessage(err, 'Could not enable WhatsApp.') }),
  })

  const disableMutation = useMutation({
    mutationFn: () => whatsappApi.disable(workflowId),
    onSuccess: invalidate,
  })

  const reconnectMutation = useMutation({
    mutationFn: () => whatsappApi.reconnect(workflowId),
    onSuccess: () => {
      invalidate()
      setNotice({ kind: 'ok', text: 'Reconnected successfully.' })
    },
    onError: err => setNotice({ kind: 'err', text: getErrorMessage(err, 'Reconnect failed.') }),
  })

  const disconnectMutation = useMutation({
    mutationFn: () => whatsappApi.disconnect(workflowId),
    onSuccess: () => {
      invalidate()
      setNotice({ kind: 'ok', text: 'Disconnected. Credentials cleared.' })
    },
  })

  const isConnected = !!channel?.connected
  const isLive = isConnected && channel?.status === 'connected'
  const showForm = !isConnected || editing

  return (
    <div className="tb2-shell">
      <SubPageBar
        backHref="/whatsapp"
        crumb={workflow?.name || '…'}
        crumbIcon={<MessageCircle size={13} className="text-emerald-400/70" />}
        right={
          isConnected ? (
            <div className="flex items-center gap-2">
              <HealthDot health={channel?.health_status} />
              <span className="text-[11px] text-white/40 capitalize">{channel?.status}</span>
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
                <p className="text-white/25 text-[10px] uppercase tracking-wide mb-0.5">Phone Number</p>
                <p className="text-white/75">{channel?.display_phone_number || '—'}</p>
              </div>
              <div>
                <p className="text-white/25 text-[10px] uppercase tracking-wide mb-0.5">Verified Name</p>
                <p className="text-white/75">{channel?.verified_name || '—'}</p>
              </div>
              <div>
                <p className="text-white/25 text-[10px] uppercase tracking-wide mb-0.5">Quality Rating</p>
                <p className="text-white/75">{channel?.quality_rating || '—'}</p>
              </div>
              <div>
                <p className="text-white/25 text-[10px] uppercase tracking-wide mb-0.5">Access Token</p>
                <p className="text-white/75 font-mono">{channel?.access_token_preview || '—'}</p>
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
                onClick={() => testMutation.mutate(undefined)}
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
                  if (window.confirm('Disconnect WhatsApp? Credentials will be cleared.')) disconnectMutation.mutate()
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
                <p className="text-sm text-white/80 font-medium">{isLive ? 'Bot is live on WhatsApp' : 'WhatsApp is disabled'}</p>
                <p className="text-[11px] text-white/30 mt-0.5">
                  {channel?.status !== 'connected'
                    ? 'Run Test Connection successfully to enable.'
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
          <Section icon={<Activity size={14} />} title="Health & Message Stats">
            <div className="grid grid-cols-3 gap-2">
              <div className="p-3 rounded-lg bg-white/[0.03] border border-white/[0.07] text-center">
                <Inbox size={13} className="mx-auto text-white/25 mb-1" />
                <p className="text-lg font-bold text-white/85">{stats?.messages_received_count ?? channel?.messages_received_count ?? 0}</p>
                <p className="text-[9px] text-white/25 uppercase tracking-wide">Received</p>
              </div>
              <div className="p-3 rounded-lg bg-white/[0.03] border border-white/[0.07] text-center">
                <Send size={13} className="mx-auto text-white/25 mb-1" />
                <p className="text-lg font-bold text-white/85">{stats?.messages_sent_count ?? channel?.messages_sent_count ?? 0}</p>
                <p className="text-[9px] text-white/25 uppercase tracking-wide">Sent</p>
              </div>
              <div className="p-3 rounded-lg bg-white/[0.03] border border-white/[0.07] text-center">
                <Users size={13} className="mx-auto text-white/25 mb-1" />
                <p className="text-lg font-bold text-white/85">{stats?.contact_count ?? 0}</p>
                <p className="text-[9px] text-white/25 uppercase tracking-wide">Contacts</p>
              </div>
            </div>
            <div className="flex items-center justify-between text-[11px] text-white/30 pt-1">
              <span>Last sync: {channel?.last_sync_at ? new Date(channel.last_sync_at).toLocaleString() : '—'}</span>
              <span>Last webhook: {channel?.last_webhook_at ? new Date(channel.last_webhook_at).toLocaleString() : '—'}</span>
            </div>

            {!!stats?.contacts?.length && (
              <div className="pt-2 border-t border-white/[0.06] space-y-1.5">
                <p className="text-[10px] text-white/25 uppercase tracking-wide">Recent contacts</p>
                {stats.contacts.slice(0, 5).map(c => (
                  <div key={c.wa_id} className="flex items-center justify-between text-xs">
                    <span className="text-white/60">{c.profile_name || c.wa_id}</span>
                    <span className="text-white/25">{c.message_count} msgs</span>
                  </div>
                ))}
              </div>
            )}
          </Section>
        )}

        {isConnected && !editing && webhookInfo && (
          <Section icon={<Webhook size={14} />} title="Webhook">
            <p className="text-[11px] text-white/30">
              Paste these into your Meta App → WhatsApp → Configuration → Webhook settings, then subscribe to
              the <span className="text-white/50 font-mono">messages</span> field.
            </p>
            <CopyRow label="Webhook URL" value={webhookInfo.webhook_url} />
            <CopyRow label="Verify Token" value={webhookInfo.verify_token} secret />
            <div className="flex items-center gap-1.5 text-[11px] text-white/30">
              <Circle size={6} className={webhookInfo.app_secret_configured ? 'fill-emerald-400 text-emerald-400' : 'fill-white/20 text-white/20'} />
              App Secret {webhookInfo.app_secret_configured ? 'configured — signatures are validated' : 'not set — signature validation is skipped'}
            </div>
          </Section>
        )}

        {showForm && (
          <Section icon={<Bot size={14} />} title={isConnected ? 'Edit Connection' : 'Connect WhatsApp'}>
            <p className="text-[11px] text-white/30">
              Create a Meta App with the WhatsApp product, then paste its credentials below. Find these under
              Meta App Dashboard → WhatsApp → API Setup.
            </p>
            <Field
              label="Phone Number ID"
              value={form.phone_number_id}
              onChange={v => setForm(f => ({ ...f, phone_number_id: v }))}
              placeholder="e.g. 109876543210123"
            />
            <Field
              label="Business Account ID"
              value={form.business_account_id}
              onChange={v => setForm(f => ({ ...f, business_account_id: v }))}
              placeholder="e.g. 123456789012345"
            />
            <Field
              label="Access Token"
              value={form.access_token}
              onChange={v => setForm(f => ({ ...f, access_token: v }))}
              placeholder="Permanent or system-user access token"
              type="password"
            />
            <Field
              label="Verify Token"
              value={form.verify_token}
              onChange={v => setForm(f => ({ ...f, verify_token: v }))}
              placeholder="A secret string you choose, used for webhook verification"
            />
            <Field
              label="App Secret (optional)"
              value={form.app_secret || ''}
              onChange={v => setForm(f => ({ ...f, app_secret: v }))}
              placeholder="Enables webhook signature validation"
              type="password"
              hint="Recommended for production — validates that webhook calls really come from Meta."
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
                  form.phone_number_id.trim() && form.access_token.trim() && form.verify_token.trim()
                    ? connectMutation.mutate(form)
                    : setNotice({ kind: 'err', text: 'Phone Number ID, Access Token and Verify Token are required.' })
                }
              >
                Save & Test Connection
              </Button>
            </div>
          </Section>
        )}

        {isLoading && <PageLoader />}

        <Section icon={<MessageCircle size={14} />} title="What this channel supports">
          <div className="grid grid-cols-2 gap-3 text-[11px] text-white/40">
            <div>
              <p className="text-white/25 uppercase tracking-wide text-[10px] mb-1">Receiving</p>
              <ul className="space-y-0.5">
                <li>Text messages</li>
                <li>Images</li>
                <li>Documents</li>
                <li>Audio / voice notes</li>
                <li>Location</li>
                <li>Shared contacts</li>
              </ul>
            </div>
            <div>
              <p className="text-white/25 uppercase tracking-wide text-[10px] mb-1">Sending</p>
              <ul className="space-y-0.5">
                <li>Text messages</li>
                <li>Reply buttons (≤3 options)</li>
                <li>List / quick replies (&gt;3 options)</li>
                <li>Images</li>
                <li>Documents</li>
              </ul>
            </div>
          </div>
          <p className="text-[11px] text-white/25 pt-1 border-t border-white/[0.06]">
            Every message runs through this bot's exact same workflow as your website chat — Start, Text,
            Multiple Choice, Transition, AI Agent and End nodes all work identically, and every conversation
            appears in{' '}
            <Link href="/analytics" className="text-[#a5b4fc] hover:text-cyan-300 transition-colors inline-flex items-center gap-0.5">
              Analytics <ExternalLink size={9} />
            </Link>.
          </p>
        </Section>
      </div>
    </div>
  )
}
