'use client'
/**
 * NEW (Google SSO & 2FA) — Settings > Security
 *
 * Google section is read-only status, intentionally not an interactive
 * "connect" button here: linking happens automatically, server-side, the
 * first time someone completes "Sign in with Google" on /login using the
 * same email as their ThunderBots account (see backend POST /auth/google).
 * A button on this page that re-ran that same public endpoint could let a
 * signed-in session get silently re-pointed at whatever Google account the
 * browser happens to authenticate next — so we don't offer that here.
 *
 * TOTP 2FA is a three-step, fully reversible setup:
 *   1) POST /2fa/setup   -> secret + QR (not yet active)
 *   2) POST /2fa/enable  -> confirms one code, activates, returns backup codes
 *   3) user acknowledges the backup codes (shown exactly once)
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useRouter } from 'next/navigation'
import {
  ShieldCheck, ShieldOff, Chrome, KeyRound, Copy, Check, RefreshCw, AlertCircle,
  Monitor, Smartphone, Tablet, HelpCircle, MapPin, LogOut, X,
} from 'lucide-react'
import { authApi, clearToken } from '@/lib/api/auth'
import { getErrorMessage } from '@/lib/utils/errors'
import type { UserSession } from '@/types'
import { Card, Badge } from '@/components/ui/Card'
import { Button, IconButton } from '@/components/ui/Button'
import { FieldLabel, Input } from '@/components/ui/Field'
import { SubPageBar } from '@/components/ui/TopBar'
import { PageLoader, ErrorState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'

type SetupStep = 'idle' | 'scan' | 'backup-codes' | 'disabling' | 'regenerating'

export default function SecurityPage() {
  const qc = useQueryClient()
  const router = useRouter()
  const { toast } = useToast()

  const { data: me, isLoading: loadingMe } = useQuery({ queryKey: ['auth', 'me'], queryFn: authApi.me })
  const {
    data: status, isLoading: loadingStatus, error: statusError, refetch: refetchStatus,
  } = useQuery({ queryKey: ['auth', '2fa-status'], queryFn: authApi.get2FAStatus })

  // NEW (Active Sessions & Device Management — Phase 2)
  const {
    data: sessions = [], isLoading: loadingSessions, error: sessionsError, refetch: refetchSessions,
  } = useQuery({ queryKey: ['auth', 'sessions'], queryFn: authApi.listSessions })

  const revokeSessionMutation = useMutation({
    mutationFn: (sessionId: string) => authApi.revokeSession(sessionId),
    onSuccess: () => {
      toast('success', 'Device signed out.')
      qc.invalidateQueries({ queryKey: ['auth', 'sessions'] })
    },
    onError: (err) => toast('error', getErrorMessage(err, 'Could not sign out that device.')),
  })

  const revokeOthersMutation = useMutation({
    mutationFn: authApi.revokeOtherSessions,
    onSuccess: () => {
      toast('success', "You've been signed out of all other devices.")
      qc.invalidateQueries({ queryKey: ['auth', 'sessions'] })
    },
    onError: (err) => toast('error', getErrorMessage(err, 'Could not sign out other devices.')),
  })

  const logoutAllMutation = useMutation({
    mutationFn: authApi.logoutAllDevices,
    onSuccess: () => {
      // This also revokes the current session — the token this browser is
      // holding stops working immediately, so clear it and send the user
      // back to /login exactly like a normal logout.
      clearToken()
      router.push('/login')
    },
    onError: (err) => toast('error', getErrorMessage(err, 'Could not log out of all devices.')),
  })

  const [step, setStep] = useState<SetupStep>('idle')
  const [setupData, setSetupData] = useState<{ secret: string; qr_code_svg: string } | null>(null)
  const [backupCodes, setBackupCodes] = useState<string[]>([])
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [copied, setCopied] = useState(false)
  const [formError, setFormError] = useState('')

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['auth', '2fa-status'] })
    qc.invalidateQueries({ queryKey: ['auth', 'me'] })
  }

  const setupMutation = useMutation({
    mutationFn: authApi.setup2FA,
    onSuccess: (data) => { setSetupData(data); setStep('scan'); setFormError('') },
    onError: (err) => toast('error', getErrorMessage(err, 'Could not start 2FA setup.')),
  })

  const enableMutation = useMutation({
    mutationFn: () => authApi.enable2FA(code.trim()),
    onSuccess: (data) => {
      setBackupCodes(data.backup_codes)
      setStep('backup-codes')
      setCode('')
      setFormError('')
      refresh()
    },
    onError: (err) => setFormError(getErrorMessage(err, 'Invalid verification code')),
  })

  const disableMutation = useMutation({
    mutationFn: () => authApi.disable2FA({ password: password || undefined, code: code || undefined }),
    onSuccess: () => {
      toast('success', 'Two-factor authentication has been disabled.')
      setStep('idle'); setPassword(''); setCode(''); setFormError('')
      refresh()
    },
    onError: (err) => setFormError(getErrorMessage(err, 'Incorrect password or code')),
  })

  const regenerateMutation = useMutation({
    mutationFn: () => authApi.regenerateBackupCodes(code.trim()),
    onSuccess: (data) => {
      setBackupCodes(data.backup_codes)
      setStep('backup-codes')
      setCode('')
      setFormError('')
      refresh()
    },
    onError: (err) => setFormError(getErrorMessage(err, 'Invalid verification code')),
  })

  const closeBackupCodes = () => {
    setStep('idle')
    setSetupData(null)
    setBackupCodes([])
  }

  const copyBackupCodes = async () => {
    try {
      await navigator.clipboard.writeText(backupCodes.join('\n'))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast('error', 'Could not copy to clipboard — select and copy the codes manually.')
    }
  }

  const loading = loadingMe || loadingStatus

  return (
    <div className="tb2-shell">
      <SubPageBar crumb="Security" crumbIcon={<ShieldCheck size={14} />} />

      <div className="max-w-2xl mx-auto px-6 py-10 space-y-6">
        <h1 className="text-xl font-bold text-white tb2-rise">Security</h1>

        {loading ? (
          <PageLoader />
        ) : statusError ? (
          <ErrorState
            title="Couldn't load your security settings"
            description={getErrorMessage(statusError, 'Check your connection and that the backend is running.')}
            onRetry={() => refetchStatus()}
          />
        ) : (
          <>
            {/* ── Google Sign-In status ── */}
            <Card className="p-4 space-y-3">
              <div className="flex items-center gap-2 text-white/50">
                <Chrome size={14} />
                <span className="text-xs font-semibold uppercase tracking-wider">Google Sign-In</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm text-white/70">
                    {me?.google_linked ? 'Linked to your Google account' : 'Not linked'}
                  </p>
                  <p className="text-[11px] text-white/35 mt-0.5">
                    {me?.google_linked
                      ? `You can sign in with Google using ${me?.email}.`
                      : `Sign in with Google using ${me?.email} on the login page to link it automatically.`}
                  </p>
                </div>
                <Badge tone={me?.google_linked ? 'success' : 'default'}>
                  {me?.google_linked ? 'Connected' : 'Not connected'}
                </Badge>
              </div>
            </Card>

            {/* ── TOTP 2FA ── */}
            <Card className="p-4 space-y-3">
              <div className="flex items-center gap-2 text-white/50">
                <KeyRound size={14} />
                <span className="text-xs font-semibold uppercase tracking-wider">Two-Factor Authentication</span>
              </div>

              {status?.enabled ? (
                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm text-white/70">Enabled</p>
                      <p className="text-[11px] text-white/35 mt-0.5">
                        {status.backup_codes_remaining} backup code{status.backup_codes_remaining !== 1 ? 's' : ''} remaining
                      </p>
                    </div>
                    <Badge tone="success" dot>Active</Badge>
                  </div>

                  <div className="flex flex-wrap gap-2 pt-1">
                    <Button
                      variant="secondary"
                      size="sm"
                      icon={<RefreshCw size={12} />}
                      onClick={() => { setStep('regenerating'); setFormError('') }}
                    >
                      Regenerate backup codes
                    </Button>
                    <Button
                      variant="danger"
                      size="sm"
                      icon={<ShieldOff size={12} />}
                      onClick={() => { setStep('disabling'); setFormError('') }}
                    >
                      Disable 2FA
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white/70">Not enabled</p>
                    <p className="text-[11px] text-white/35 mt-0.5">
                      Add an authenticator app (Google Authenticator, Authy, 1Password…) for an extra layer of protection.
                    </p>
                  </div>
                  <Button
                    size="sm"
                    loading={setupMutation.isPending}
                    onClick={() => setupMutation.mutate()}
                  >
                    Enable 2FA
                  </Button>
                </div>
              )}

              {/* Step: scan QR + confirm code */}
              {step === 'scan' && setupData && (
                <div className="tb2-rise space-y-3 pt-2 border-t border-white/10 mt-1">
                  <p className="text-xs text-white/50">
                    Scan this QR code with your authenticator app, then enter the 6-digit code it shows.
                  </p>
                  <div
                    className="bg-white rounded-xl p-3 w-fit mx-auto [&_svg]:w-40 [&_svg]:h-40"
                    dangerouslySetInnerHTML={{ __html: setupData.qr_code_svg }}
                  />
                  <p className="text-[11px] text-white/35 text-center break-all">
                    Can&apos;t scan? Enter manually: <span className="text-white/60 font-mono">{setupData.secret}</span>
                  </p>
                  <div>
                    <FieldLabel>Verification code</FieldLabel>
                    <Input
                      type="text"
                      inputMode="numeric"
                      value={code}
                      onChange={e => setCode(e.target.value)}
                      placeholder="123456"
                      autoFocus
                      maxLength={6}
                    />
                  </div>
                  {formError && <FormErrorBanner message={formError} />}
                  <div className="flex gap-2">
                    <Button
                      loading={enableMutation.isPending}
                      disabled={code.trim().length < 6}
                      onClick={() => enableMutation.mutate()}
                    >
                      Confirm &amp; Enable
                    </Button>
                    <Button variant="secondary" onClick={() => { setStep('idle'); setSetupData(null); setCode(''); setFormError('') }}>
                      Cancel
                    </Button>
                  </div>
                </div>
              )}

              {/* Step: disable */}
              {step === 'disabling' && (
                <div className="tb2-rise space-y-3 pt-2 border-t border-white/10 mt-1">
                  <p className="text-xs text-white/50">
                    Confirm with {me?.has_password ? 'your password or ' : ''}a verification code to disable 2FA.
                  </p>
                  {me?.has_password && (
                    <div>
                      <FieldLabel>Password</FieldLabel>
                      <Input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" />
                    </div>
                  )}
                  <div>
                    <FieldLabel>{me?.has_password ? 'Or verification code' : 'Verification code'}</FieldLabel>
                    <Input type="text" inputMode="numeric" value={code} onChange={e => setCode(e.target.value)} placeholder="123456" />
                  </div>
                  {formError && <FormErrorBanner message={formError} />}
                  <div className="flex gap-2">
                    <Button
                      variant="danger"
                      loading={disableMutation.isPending}
                      disabled={!password && !code}
                      onClick={() => disableMutation.mutate()}
                    >
                      Disable 2FA
                    </Button>
                    <Button variant="secondary" onClick={() => { setStep('idle'); setPassword(''); setCode(''); setFormError('') }}>
                      Cancel
                    </Button>
                  </div>
                </div>
              )}

              {/* Step: regenerate backup codes */}
              {step === 'regenerating' && (
                <div className="tb2-rise space-y-3 pt-2 border-t border-white/10 mt-1">
                  <p className="text-xs text-white/50">
                    Enter a current code to generate a fresh set of backup codes. Your old backup codes will stop working.
                  </p>
                  <div>
                    <FieldLabel>Verification code</FieldLabel>
                    <Input type="text" inputMode="numeric" value={code} onChange={e => setCode(e.target.value)} placeholder="123456" autoFocus />
                  </div>
                  {formError && <FormErrorBanner message={formError} />}
                  <div className="flex gap-2">
                    <Button
                      loading={regenerateMutation.isPending}
                      disabled={code.trim().length < 6}
                      onClick={() => regenerateMutation.mutate()}
                    >
                      Generate new codes
                    </Button>
                    <Button variant="secondary" onClick={() => { setStep('idle'); setCode(''); setFormError('') }}>
                      Cancel
                    </Button>
                  </div>
                </div>
              )}

              {/* Step: show backup codes (from enable or regenerate) */}
              {step === 'backup-codes' && (
                <div className="tb2-rise space-y-3 pt-2 border-t border-white/10 mt-1">
                  <p className="text-xs text-white/70 font-medium">Save your backup codes</p>
                  <p className="text-[11px] text-white/35">
                    Each code can be used once if you lose access to your authenticator app. Store them somewhere safe — they won&apos;t be shown again.
                  </p>
                  <div className="grid grid-cols-2 gap-2 bg-black/20 border border-white/10 rounded-xl p-3 font-mono text-xs text-white/80">
                    {backupCodes.map(c => <div key={c}>{c}</div>)}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      icon={copied ? <Check size={12} /> : <Copy size={12} />}
                      onClick={copyBackupCodes}
                    >
                      {copied ? 'Copied' : 'Copy codes'}
                    </Button>
                    <Button size="sm" onClick={closeBackupCodes}>
                      I&apos;ve saved these codes
                    </Button>
                  </div>
                </div>
              )}
            </Card>

            {/* ── Active Sessions & Device Management (NEW — Phase 2) ── */}
            <Card className="p-4 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-white/50">
                  <Monitor size={14} />
                  <span className="text-xs font-semibold uppercase tracking-wider">Active Sessions</span>
                </div>
                {sessions.length > 1 && (
                  <button
                    className="text-[11px] font-medium text-white/40 hover:text-white/70 transition-colors"
                    disabled={revokeOthersMutation.isPending}
                    onClick={() => {
                      if (window.confirm('Sign out every other device? Devices currently logged in elsewhere will need to log in again.')) {
                        revokeOthersMutation.mutate()
                      }
                    }}
                  >
                    Log out other devices
                  </button>
                )}
              </div>

              {loadingSessions ? (
                <PageLoader />
              ) : sessionsError ? (
                <ErrorState
                  title="Couldn't load your sessions"
                  description={getErrorMessage(sessionsError, 'Check your connection and that the backend is running.')}
                  onRetry={() => refetchSessions()}
                />
              ) : sessions.length === 0 ? (
                <p className="text-xs text-white/35">No active sessions found.</p>
              ) : (
                <div className="space-y-2">
                  {sessions.map((s: UserSession) => (
                    <SessionRow
                      key={s.id}
                      session={s}
                      revoking={revokeSessionMutation.isPending && revokeSessionMutation.variables === s.id}
                      onRevoke={() => {
                        if (window.confirm(`Sign out "${s.device_name}"? That device will be logged out immediately.`)) {
                          revokeSessionMutation.mutate(s.id)
                        }
                      }}
                    />
                  ))}
                </div>
              )}

              <div className="pt-2 border-t border-white/10 mt-1">
                <Button
                  variant="danger"
                  size="sm"
                  icon={<LogOut size={12} />}
                  loading={logoutAllMutation.isPending}
                  onClick={() => {
                    if (window.confirm("Log out of all devices, including this one? You'll need to log in again everywhere.")) {
                      logoutAllMutation.mutate()
                    }
                  }}
                >
                  Log out of all devices
                </Button>
              </div>
            </Card>
          </>
        )}
      </div>
    </div>
  )
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  const diffSeconds = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (diffSeconds < 60) return 'Active now'
  const diffMinutes = Math.floor(diffSeconds / 60)
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  const diffHours = Math.floor(diffMinutes / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 30) return `${diffDays}d ago`
  return new Date(iso).toLocaleDateString()
}

function DeviceIcon({ deviceType }: { deviceType: UserSession['device_type'] }) {
  const size = 16
  if (deviceType === 'mobile') return <Smartphone size={size} />
  if (deviceType === 'tablet') return <Tablet size={size} />
  if (deviceType === 'desktop') return <Monitor size={size} />
  return <HelpCircle size={size} />
}

function SessionRow({
  session, revoking, onRevoke,
}: { session: UserSession; revoking: boolean; onRevoke: () => void }) {
  return (
    <div className="flex items-center gap-3 p-3 rounded-xl bg-white/[0.02] border border-white/10 tb2-row">
      <div className="w-8 h-8 rounded-lg bg-white/[0.05] border border-white/10 flex items-center justify-center flex-shrink-0 text-white/50">
        <DeviceIcon deviceType={session.device_type} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm text-white/75 truncate">{session.device_name}</p>
          {session.is_current && <Badge tone="success" dot>This device</Badge>}
        </div>
        <p className="text-[11px] text-white/35 mt-0.5 flex items-center gap-1 flex-wrap">
          <span>{relativeTime(session.last_active_at)}</span>
          <span className="opacity-40">·</span>
          {session.location ? (
            <span className="flex items-center gap-0.5"><MapPin size={10} />{session.location}</span>
          ) : (
            <span>{session.ip_address}</span>
          )}
        </p>
      </div>
      {!session.is_current && (
        <IconButton
          aria-label={`Sign out ${session.device_name}`}
          onClick={onRevoke}
          disabled={revoking}
          className="flex-shrink-0"
        >
          {revoking ? <RefreshCw size={13} className="animate-spin" /> : <X size={14} />}
        </IconButton>
      )}
    </div>
  )
}

function FormErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 text-xs text-red-400 bg-red-500/8 border border-red-500/20 rounded-xl px-3 py-2.5">
      <AlertCircle size={12} className="flex-shrink-0" />
      {message}
    </div>
  )
}
