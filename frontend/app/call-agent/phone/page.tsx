'use client'
/**
 * AI Call Agent — Phone AI Agent mode — /call-agent/phone
 *
 * Phone number connection + verification ONLY. There is no call placement,
 * no telephony session, and no workflow binding here — see
 * backend/app/api/v1/call_agent.py for the exact scope of this part.
 *
 * Follows the same page shape already established by /whatsapp, /telegram,
 * /instagram (SubPageBar + Card list) and the same step-machine pattern
 * already used by Settings > Security's TOTP setup flow (send code ->
 * enter code -> confirm), reusing the existing UI kit and toast/error
 * conventions throughout — no new patterns introduced.
 *
 * MOVED from /call-agent (v92 -> v93) so the AI Call Agent landing page can
 * ask "Web Voice Bubble vs Phone AI Agent" first. This route, every query
 * key, every mutation, and every field below is byte-for-byte the same
 * logic that used to live at /call-agent — only the URL and the back-link
 * target changed. Phone verification still only ever happens on this page.
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Phone, PhoneCall, PhoneOff, Plus, Trash2, RefreshCw, ShieldCheck,
  X, Check, Send, KeyRound, AlertCircle, Settings2, LayoutDashboard,
} from 'lucide-react'
import { getToken } from '@/lib/api/auth'
import { callAgentApi } from '@/lib/api/callAgent'
import type { PhoneNumber, PhoneVerificationMethod } from '@/types/callAgent'
import { Card, Badge } from '@/components/ui/Card'
import { Button, IconButton } from '@/components/ui/Button'
import { FieldLabel, Input, Select } from '@/components/ui/Field'
import { SubPageBar } from '@/components/ui/TopBar'
import { CallAgentNav } from '@/components/callAgent/CallAgentNav'
import { PageLoader, ErrorState, EmptyState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/lib/utils/errors'

const METHOD_LABEL: Record<PhoneVerificationMethod, string> = {
  otp: 'One-time passcode',
  sms: 'SMS text message',
  call: 'Phone call',
}

function statusBadge(number: PhoneNumber) {
  if (!number.is_connected && number.status === 'verified') {
    return <Badge tone="default">Disconnected</Badge>
  }
  switch (number.status) {
    case 'verified':
      return <Badge tone="success" dot>Verified</Badge>
    case 'pending':
      return <Badge tone="warning">Pending</Badge>
    case 'failed':
      return <Badge tone="danger">Failed</Badge>
    case 'expired':
      return <Badge tone="danger">Expired</Badge>
    default:
      return <Badge tone="default">{number.status}</Badge>
  }
}

export default function CallAgentPage() {
  const router = useRouter()
  const qc = useQueryClient()
  const { toast } = useToast()
  const [showAdd, setShowAdd] = useState(false)

  useEffect(() => {
    if (typeof window !== 'undefined' && !getToken()) router.replace('/login')
  }, [router])

  const {
    data: numbers = [], isLoading, error, refetch,
  } = useQuery({ queryKey: ['call-agent', 'phone-numbers'], queryFn: callAgentApi.list })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['call-agent', 'phone-numbers'] })

  const addMutation = useMutation({
    mutationFn: callAgentApi.add,
    onSuccess: () => { invalidate(); setShowAdd(false) },
    onError: (err) => toast('error', getErrorMessage(err, 'Could not add that phone number.')),
  })

  const removeMutation = useMutation({
    mutationFn: callAgentApi.remove,
    onSuccess: () => { toast('success', 'Phone number removed.'); invalidate() },
    onError: (err) => toast('error', getErrorMessage(err, 'Could not remove that phone number.')),
  })

  return (
    <div className="tb2-shell">
      <SubPageBar backHref="/call-agent" crumb="Phone AI Agent" crumbIcon={<Phone size={13} className="text-cyan-300/70" />} />
      <CallAgentNav />

      <div className="max-w-2xl mx-auto px-6 py-10 space-y-6">
        <div className="tb2-rise flex items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-white">Phone Numbers</h1>
            <p className="text-sm text-white/35 mt-1">
              Connect and verify phone numbers before enabling AI Call Agent features.
            </p>
          </div>
          {!showAdd && (
            <div className="flex items-center gap-2">
              <Button
                size="sm" variant="secondary" icon={<LayoutDashboard size={13} />}
                onClick={() => router.push('/call-agent/calls')}
              >
                Calls
              </Button>
              <Button size="sm" icon={<Plus size={13} />} onClick={() => setShowAdd(true)}>
                Add number
              </Button>
            </div>
          )}
        </div>

        {showAdd && (
          <AddPhoneNumberForm
            pending={addMutation.isPending}
            onCancel={() => setShowAdd(false)}
            onSubmit={(phone_number, label) => addMutation.mutate({ phone_number, label })}
          />
        )}

        {isLoading ? (
          <PageLoader />
        ) : error ? (
          <ErrorState
            title="Couldn't load your phone numbers"
            description={getErrorMessage(error, 'Check your connection and that the backend is running.')}
            onRetry={() => refetch()}
          />
        ) : numbers.length === 0 && !showAdd ? (
          <EmptyState
            icon={<Phone size={26} />}
            title="No phone numbers yet"
            description="Add a phone number to start setting up AI Call Agent features."
            action={
              <Button size="sm" icon={<Plus size={13} />} onClick={() => setShowAdd(true)}>
                Add number
              </Button>
            }
          />
        ) : (
          <div className="space-y-3">
            {numbers.map(n => (
              <PhoneNumberCard
                key={n.id}
                number={n}
                onRemove={() => {
                  if (window.confirm(`Remove ${n.phone_number}? This can't be undone.`)) {
                    removeMutation.mutate(n.id)
                  }
                }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function AddPhoneNumberForm({
  pending, onCancel, onSubmit,
}: {
  pending: boolean
  onCancel: () => void
  onSubmit: (phoneNumber: string, label: string) => void
}) {
  const [phoneNumber, setPhoneNumber] = useState('')
  const [label, setLabel] = useState('')

  return (
    <Card className="p-4 space-y-3 tb2-rise">
      <div className="flex items-center gap-2 text-white/50">
        <Phone size={14} />
        <span className="text-xs font-semibold uppercase tracking-wider">Add a phone number</span>
      </div>
      <div>
        <FieldLabel hint="International format">Phone number</FieldLabel>
        <Input
          type="tel"
          value={phoneNumber}
          onChange={e => setPhoneNumber(e.target.value)}
          placeholder="+1 415 555 1234"
          autoFocus
        />
      </div>
      <div>
        <FieldLabel hint="Optional">Label</FieldLabel>
        <Input
          type="text"
          value={label}
          onChange={e => setLabel(e.target.value)}
          placeholder="e.g. Support line"
          maxLength={100}
        />
      </div>
      <div className="flex gap-2">
        <Button
          size="sm"
          loading={pending}
          disabled={phoneNumber.trim().length < 8}
          onClick={() => onSubmit(phoneNumber.trim(), label.trim())}
        >
          Add number
        </Button>
        <Button size="sm" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </Card>
  )
}

type CardStep = 'idle' | 'choose-method' | 'enter-code'

function PhoneNumberCard({
  number, onRemove,
}: {
  number: PhoneNumber
  onRemove: () => void
}) {
  const qc = useQueryClient()
  const router = useRouter()
  const { toast } = useToast()
  const [step, setStep] = useState<CardStep>('idle')
  const [method, setMethod] = useState<PhoneVerificationMethod>('sms')
  const [code, setCode] = useState('')
  const [formError, setFormError] = useState('')

  const invalidate = () => qc.invalidateQueries({ queryKey: ['call-agent', 'phone-numbers'] })

  const sendCodeMutation = useMutation({
    mutationFn: () => callAgentApi.sendCode(number.id, { method }),
    onSuccess: () => {
      setStep('enter-code')
      setFormError('')
      toast('success', `Verification code sent via ${METHOD_LABEL[method].toLowerCase()}.`)
      invalidate()
    },
    onError: (err) => setFormError(getErrorMessage(err, 'Could not send a verification code.')),
  })

  const verifyMutation = useMutation({
    mutationFn: () => callAgentApi.verifyCode(number.id, { code: code.trim() }),
    onSuccess: () => {
      setStep('idle')
      setCode('')
      setFormError('')
      toast('success', 'Phone number verified.')
      invalidate()
    },
    onError: (err) => setFormError(getErrorMessage(err, 'Invalid verification code')),
  })

  const disconnectMutation = useMutation({
    mutationFn: () => callAgentApi.disconnect(number.id),
    onSuccess: () => { toast('success', 'Phone number disconnected.'); invalidate() },
    onError: (err) => toast('error', getErrorMessage(err, 'Could not disconnect that phone number.')),
  })

  const reconnectMutation = useMutation({
    mutationFn: () => callAgentApi.reconnect(number.id),
    onSuccess: () => { toast('success', 'Phone number reconnected.'); invalidate() },
    onError: (err) => toast('error', getErrorMessage(err, 'Could not reconnect that phone number.')),
  })

  const enableMutation = useMutation({
    mutationFn: () => (number.is_enabled ? callAgentApi.disable(number.id) : callAgentApi.enable(number.id)),
    onSuccess: () => invalidate(),
    onError: (err) => toast('error', getErrorMessage(err, 'Could not update AI Call Agent status.')),
  })

  const needsVerification = number.status !== 'verified' || !number.is_connected
  const canReconnect = number.status === 'verified' && !number.is_connected

  return (
    <Card className="p-4 space-y-3 tb2-rise">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center flex-shrink-0">
            <Phone size={16} className="text-cyan-300" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white/85 truncate">{number.phone_number}</p>
            {number.label && <p className="text-[11px] text-white/35 truncate">{number.label}</p>}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {statusBadge(number)}
          <IconButton aria-label="Remove phone number" variant="danger" onClick={onRemove}>
            <Trash2 size={13} />
          </IconButton>
        </div>
      </div>

      {number.last_error && step === 'idle' && (
        <p className="text-[11px] text-red-400/80 flex items-center gap-1.5">
          <AlertCircle size={11} className="flex-shrink-0" />
          {number.last_error}
        </p>
      )}

      {/* ── Actions when idle ── */}
      {step === 'idle' && (
        <div className="flex flex-wrap gap-2 pt-1">
          {needsVerification && !canReconnect && (
            <Button size="sm" icon={<Send size={12} />} onClick={() => setStep('choose-method')}>
              {number.status === 'pending' ? 'Verify number' : 'Verify again'}
            </Button>
          )}
          {canReconnect && (
            <Button
              size="sm"
              icon={<RefreshCw size={12} />}
              loading={reconnectMutation.isPending}
              onClick={() => reconnectMutation.mutate()}
            >
              Reconnect
            </Button>
          )}
          {number.status === 'verified' && number.is_connected && (
            <>
              <Button
                size="sm"
                variant={number.is_enabled ? 'secondary' : 'primary'}
                icon={<ShieldCheck size={12} />}
                loading={enableMutation.isPending}
                onClick={() => enableMutation.mutate()}
              >
                {number.is_enabled ? 'Disable AI Call Agent' : 'Enable AI Call Agent'}
              </Button>
              {number.is_enabled && (
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<Settings2 size={12} />}
                  onClick={() => router.push(`/call-agent/settings/${number.id}`)}
                >
                  Call settings
                </Button>
              )}
              <Button
                size="sm"
                variant="secondary"
                icon={<PhoneOff size={12} />}
                loading={disconnectMutation.isPending}
                onClick={() => disconnectMutation.mutate()}
              >
                Disconnect
              </Button>
            </>
          )}
        </div>
      )}

      {/* ── Step: choose verification method ── */}
      {step === 'choose-method' && (
        <div className="tb2-rise space-y-3 pt-2 border-t border-white/10 mt-1">
          <p className="text-xs text-white/50">How should we send your verification code?</p>
          <Select value={method} onChange={e => setMethod(e.target.value as PhoneVerificationMethod)}>
            <option value="sms">SMS text message</option>
            <option value="otp">One-time passcode</option>
            <option value="call">Phone call</option>
          </Select>
          {formError && <FormErrorBanner message={formError} />}
          <div className="flex gap-2">
            <Button
              size="sm"
              icon={<PhoneCall size={12} />}
              loading={sendCodeMutation.isPending}
              onClick={() => sendCodeMutation.mutate()}
            >
              Send code
            </Button>
            <Button size="sm" variant="secondary" onClick={() => { setStep('idle'); setFormError('') }}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* ── Step: enter code ── */}
      {step === 'enter-code' && (
        <div className="tb2-rise space-y-3 pt-2 border-t border-white/10 mt-1">
          <p className="text-xs text-white/50">
            Enter the code sent via {METHOD_LABEL[method].toLowerCase()}.
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
              maxLength={8}
            />
          </div>
          {formError && <FormErrorBanner message={formError} />}
          <div className="flex gap-2">
            <Button
              size="sm"
              icon={<KeyRound size={12} />}
              loading={verifyMutation.isPending}
              disabled={code.trim().length < 4}
              onClick={() => verifyMutation.mutate()}
            >
              Confirm code
            </Button>
            <Button
              size="sm"
              variant="secondary"
              loading={sendCodeMutation.isPending}
              onClick={() => sendCodeMutation.mutate()}
            >
              Resend code
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => { setStep('idle'); setCode(''); setFormError('') }}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </Card>
  )
}

function FormErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 text-xs text-red-400/90 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
      <X size={13} className="flex-shrink-0 mt-0.5" />
      <span>{message}</span>
    </div>
  )
}
