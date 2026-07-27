'use client'
import { useState, useEffect } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import {
  Instagram, Bot, Check, Copy,
  RefreshCw, Unlink, Power, ShieldCheck, Webhook, Activity, ScrollText,
  CheckCircle2, XCircle, AlertTriangle, Circle, Users, Send, Inbox,
  ExternalLink, LogIn,
} from 'lucide-react'
import { workflowsApi } from '@/lib/api/workflows'
import { instagramApi } from '@/lib/api/instagram'
import { getErrorMessage } from '@/lib/utils/errors'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
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

function CopyRow({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false)
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
          value={value}
          className="tb2-field flex-1 text-xs text-white/70 rounded-lg px-3 py-2.5 outline-none font-mono truncate"
        />
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

const OAUTH_ERROR_MESSAGES: Record<string, string> = {
  missing_state: 'The connection attempt expired. Please try connecting again.',
  missing_code: 'Instagram did not return an authorization code. Please try again.',
  no_linked_instagram_account: 'No Facebook Page with a linked Instagram Business account was found for that login.',
  oauth_exchange_failed: 'Instagram could not confirm the connection. Please try again.',
  unexpected: 'Something went wrong while connecting Instagram. Please try again.',
}

export default function InstagramSettingsPage() {
  const params = useParams()
  const workflowId = String(params.workflowId)
  const router = useRouter()
  const searchParams = useSearchParams()
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

  const { data: account, isLoading } = useQuery({
    queryKey: ['instagram-account', workflowId],
    queryFn: () => instagramApi.get(workflowId),
  })

  const { data: webhookInfo } = useQuery({
    queryKey: ['instagram-webhook-info', workflowId],
    queryFn: () => instagramApi.webhookInfo(workflowId),
    enabled: !!account?.connected,
    retry: false,
  })

  const { data: stats } = useQuery({
    queryKey: ['instagram-stats', workflowId],
    queryFn: () => instagramApi.stats(workflowId),
    enabled: !!account?.connected,
    refetchInterval: 8000,
  })

  const { data: logs } = useQuery({
    queryKey: ['instagram-logs', workflowId],
    queryFn: () => instagramApi.logs(workflowId, 20),
    enabled: !!account?.connected,
  })

  const [notice, setNotice] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  // Handle the redirect back from Meta's OAuth callback (?ig_connected=1 / ?ig_error=...)
  useEffect(() => {
    const connected = searchParams.get('ig_connected')
    const error = searchParams.get('ig_error')
    if (connected) {
      setNotice({ kind: 'ok', text: 'Instagram connected successfully.' })
      invalidate()
      router.replace(`/instagram/${workflowId}`)
    } else if (error) {
      setNotice({ kind: 'err', text: OAUTH_ERROR_MESSAGES[error] || 'Could not connect Instagram.' })
      router.replace(`/instagram/${workflowId}`)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['instagram-account', workflowId] })
    qc.invalidateQueries({ queryKey: ['instagram-webhook-info', workflowId] })
    qc.invalidateQueries({ queryKey: ['instagram-stats', workflowId] })
    qc.invalidateQueries({ queryKey: ['instagram-logs', workflowId] })
  }

  const connectMutation = useMutation({
    mutationFn: () => instagramApi.authorizeUrl(workflowId),
    onSuccess: res => {
      window.location.href = res.authorize_url
    },
    onError: err => setNotice({ kind: 'err', text: getErrorMessage(err, 'Instagram is not configured on this server yet.') }),
  })

  const testMutation = useMutation({
    mutationFn: () => instagramApi.test(workflowId),
    onSuccess: res => {
      invalidate()
      setNotice(
        res.ok
          ? { kind: 'ok', text: `Connected as @${res.ig_username || 'Instagram account'}.` }
          : { kind: 'err', text: res.error || 'Connection test failed.' }
      )
    },
    onError: err => setNotice({ kind: 'err', text: getErrorMessage(err, 'Test connection failed.') }),
  })

  const enableMutation = useMutation({
    mutationFn: () => instagramApi.enable(workflowId),
    onSuccess: invalidate,
    onError: err => setNotice({ kind: 'err', text: getErrorMessage(err, 'Could not enable Instagram.') }),
  })

  const disableMutation = useMutation({
    mutationFn: () => instagramApi.disable(workflowId),
    onSuccess: invalidate,
  })

  const reconnectMutation = useMutation({
    mutationFn: () => instagramApi.reconnect(workflowId),
    onSuccess: res => {
      invalidate()
      if (res.needs_reauth) {
        setNotice({ kind: 'err', text: res.error || 'Your Instagram connection has expired — reconnect below.' })
      } else {
        setNotice({ kind: 'ok', text: res.token_refreshed ? 'Access token refreshed successfully.' : 'Reconnected successfully.' })
      }
    },
    onError: err => setNotice({ kind: 'err', text: getErrorMessage(err, 'Reconnect failed.') }),
  })

  const disconnectMutation = useMutation({
    mutationFn: () => instagramApi.disconnect(workflowId),
    onSuccess: () => {
      invalidate()
      setNotice({ kind: 'ok', text: 'Disconnected. Instagram access has been cleared.' })
    },
  })

  const isConnected = !!account?.connected
  const isExpired = account?.status === 'expired'
  const isLive = isConnected && account?.status === 'connected'
  const notConfigured = isConnected && account?.configured === false

  return (
    <div className="tb2-shell">
      <SubPageBar
        backHref="/instagram"
        crumb={workflow?.name || '…'}
        crumbIcon={<Instagram size={13} className="text-pink-400/70" />}
        right={
          isConnected ? (
            <div className="flex items-center gap-2">
              <HealthDot health={account?.health_status} />
              <span className="text-[11px] text-white/40 capitalize">{account?.status}</span>
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

        {notConfigured && (
          <div className="tb2-rise flex items-start gap-2 p-3 rounded-xl text-xs border bg-amber-500/5 border-amber-500/20 text-amber-300">
            <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
            <span>Instagram isn't configured on this server yet (missing Meta App credentials). Ask an admin to set INSTAGRAM_APP_ID / INSTAGRAM_APP_SECRET.</span>
          </div>
        )}

        {isConnected && (
          <Section icon={<ShieldCheck size={14} />} title="Connection">
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <p className="text-white/25 text-[10px] uppercase tracking-wide mb-0.5">Instagram Username</p>
                <p className="text-white/75">{account?.ig_username ? `@${account.ig_username}` : '—'}</p>
              </div>
              <div>
                <p className="text-white/25 text-[10px] uppercase tracking-wide mb-0.5">Facebook Page</p>
                <p className="text-white/75">{account?.facebook_page_name || '—'}</p>
              </div>
              <div>
                <p className="text-white/25 text-[10px] uppercase tracking-wide mb-0.5">Access Token</p>
                <p className="text-white/75 font-mono">{account?.token_preview || '—'}</p>
              </div>
              <div>
                <p className="text-white/25 text-[10px] uppercase tracking-wide mb-0.5">Token Expires</p>
                <p className={cn('text-white/75', isExpired && 'text-red-300')}>
                  {account?.token_expires_at ? new Date(account.token_expires_at).toLocaleDateString() : '—'}
                </p>
              </div>
            </div>
            {account?.last_error && (
              <div className="flex items-start gap-2 p-2.5 rounded-lg bg-red-500/5 border border-red-500/15 text-[11px] text-red-300">
                <AlertTriangle size={12} className="mt-0.5 flex-shrink-0" />
                {account.last_error}
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
                  if (window.confirm('Disconnect Instagram? Access will be revoked for this bot.')) disconnectMutation.mutate()
                }}
              >
                Disconnect
              </Button>
            </div>
            {isExpired && (
              <Button
                className="w-full"
                loading={connectMutation.isPending}
                icon={!connectMutation.isPending ? <LogIn size={13} /> : undefined}
                onClick={() => connectMutation.mutate()}
              >
                Reconnect via Instagram Login
              </Button>
            )}
          </Section>
        )}

        {isConnected && (
          <Section icon={<Power size={14} />} title="Status">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-white/80 font-medium">{isLive ? 'Bot is live on Instagram' : 'Instagram is disabled'}</p>
                <p className="text-[11px] text-white/30 mt-0.5">
                  {account?.status !== 'connected'
                    ? 'Run Test Connection successfully to enable.'
                    : account?.is_enabled
                    ? 'Incoming DMs are being answered automatically.'
                    : 'Incoming DMs will not be processed until enabled.'}
                </p>
              </div>
              <button
                onClick={() => (account?.is_enabled ? disableMutation.mutate() : enableMutation.mutate())}
                disabled={account?.status !== 'connected' || enableMutation.isPending || disableMutation.isPending}
                className={cn(
                  'relative w-11 h-6 rounded-full transition-colors flex-shrink-0 disabled:opacity-30',
                  account?.is_enabled ? 'bg-emerald-500' : 'bg-white/10'
                )}
              >
                <span
                  className={cn(
                    'absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform',
                    account?.is_enabled ? 'translate-x-5' : 'translate-x-0.5'
                  )}
                />
              </button>
            </div>
          </Section>
        )}

        {isConnected && (
          <Section icon={<Activity size={14} />} title="Health & Message Stats">
            <div className="grid grid-cols-3 gap-2">
              <div className="p-3 rounded-lg bg-white/[0.03] border border-white/[0.07] text-center">
                <Inbox size={13} className="mx-auto text-white/25 mb-1" />
                <p className="text-lg font-bold text-white/85">{stats?.messages_received_count ?? account?.messages_received_count ?? 0}</p>
                <p className="text-[9px] text-white/25 uppercase tracking-wide">Received</p>
              </div>
              <div className="p-3 rounded-lg bg-white/[0.03] border border-white/[0.07] text-center">
                <Send size={13} className="mx-auto text-white/25 mb-1" />
                <p className="text-lg font-bold text-white/85">{stats?.messages_sent_count ?? account?.messages_sent_count ?? 0}</p>
                <p className="text-[9px] text-white/25 uppercase tracking-wide">Sent</p>
              </div>
              <div className="p-3 rounded-lg bg-white/[0.03] border border-white/[0.07] text-center">
                <Users size={13} className="mx-auto text-white/25 mb-1" />
                <p className="text-lg font-bold text-white/85">{stats?.contact_count ?? 0}</p>
                <p className="text-[9px] text-white/25 uppercase tracking-wide">Contacts</p>
              </div>
            </div>
            <div className="flex items-center justify-between text-[11px] text-white/30 pt-1">
              <span>Last sync: {account?.last_sync_at ? new Date(account.last_sync_at).toLocaleString() : '—'}</span>
              <span>Last webhook: {account?.last_webhook_at ? new Date(account.last_webhook_at).toLocaleString() : '—'}</span>
            </div>

            {!!stats?.contacts?.length && (
              <div className="pt-2 border-t border-white/[0.06] space-y-1.5">
                <p className="text-[10px] text-white/25 uppercase tracking-wide">Recent contacts</p>
                {stats.contacts.slice(0, 5).map(c => (
                  <div key={c.igsid} className="flex items-center justify-between text-xs">
                    <span className="text-white/60">{c.username ? `@${c.username}` : c.igsid}</span>
                    <span className="text-white/25">{c.message_count} msgs</span>
                  </div>
                ))}
              </div>
            )}
          </Section>
        )}

        {isConnected && webhookInfo && (
          <Section icon={<Webhook size={14} />} title="Webhook">
            <p className="text-[11px] text-white/30">
              Instagram/Messenger webhooks are registered once per Meta App, not per account. Paste this into your
              Meta App → Webhooks → Instagram configuration, subscribing to{' '}
              <span className="text-white/50 font-mono">messages</span>.
            </p>
            <CopyRow label="Webhook URL (app-wide)" value={webhookInfo.webhook_url} />
            <div className="flex items-center gap-1.5 text-[11px] text-white/30">
              <Circle size={6} className={webhookInfo.verify_token_configured ? 'fill-emerald-400 text-emerald-400' : 'fill-amber-400 text-amber-400'} />
              Verify Token {webhookInfo.verify_token_configured ? 'configured' : 'not set on the server'}
            </div>
            <div className="flex items-center gap-1.5 text-[11px] text-white/30">
              <Circle size={6} className={webhookInfo.app_secret_configured ? 'fill-emerald-400 text-emerald-400' : 'fill-white/20 text-white/20'} />
              App Secret {webhookInfo.app_secret_configured ? 'configured — signatures are validated' : 'not set — signature validation is skipped'}
            </div>
          </Section>
        )}

        {isConnected && !!logs?.length && (
          <Section icon={<ScrollText size={14} />} title="Connection & Webhook Logs">
            <div className="space-y-1.5 max-h-64 overflow-y-auto">
              {logs.map(l => (
                <div key={l.id} className="flex items-start gap-2 text-[11px]">
                  <span
                    className={cn(
                      'mt-1 w-1.5 h-1.5 rounded-full flex-shrink-0',
                      l.level === 'error' ? 'bg-red-400' : l.level === 'warning' ? 'bg-amber-400' : 'bg-white/20'
                    )}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-white/60">{l.message}</p>
                    <p className="text-white/25">{l.event_type} · {new Date(l.created_at).toLocaleString()}</p>
                  </div>
                </div>
              ))}
            </div>
          </Section>
        )}

        {!isConnected && (
          <Section icon={<Instagram size={14} />} title="Connect Instagram">
            <p className="text-[11px] text-white/30">
              Sign in with your Facebook account to connect the Instagram Business account linked to one of your
              Facebook Pages. This bot's Workflow Runtime and Knowledge Base will automatically answer Instagram DMs
              once enabled.
            </p>
            <Button
              className="w-full"
              loading={connectMutation.isPending}
              icon={!connectMutation.isPending ? <Instagram size={13} /> : undefined}
              onClick={() => connectMutation.mutate()}
            >
              Connect Instagram
            </Button>
          </Section>
        )}

        {isLoading && <PageLoader />}

        <Section icon={<Instagram size={14} />} title="What this channel supports">
          <div className="grid grid-cols-2 gap-3 text-[11px] text-white/40">
            <div>
              <p className="text-white/25 uppercase tracking-wide text-[10px] mb-1">Receiving</p>
              <ul className="space-y-0.5">
                <li>Text messages</li>
                <li>Images, videos & attachments <span className="text-white/25">(logged, coming soon)</span></li>
              </ul>
            </div>
            <div>
              <p className="text-white/25 uppercase tracking-wide text-[10px] mb-1">Sending</p>
              <ul className="space-y-0.5">
                <li>Text messages</li>
                <li>Numbered multiple-choice replies</li>
                <li>Images</li>
              </ul>
            </div>
          </div>
          <p className="text-[11px] text-white/25 pt-1 border-t border-white/[0.06]">
            Every message runs through this bot's exact same workflow as your website chat and WhatsApp — Start,
            Text, Multiple Choice, Transition, AI Agent and End nodes all work identically, and every conversation
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
