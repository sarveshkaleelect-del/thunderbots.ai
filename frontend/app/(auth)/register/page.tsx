'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Eye, EyeOff, AlertCircle, ShieldCheck, ArrowLeft } from 'lucide-react'
import { authApi, saveToken } from '@/lib/api/auth'
import { isMfaRequired } from '@/types'
import { AxiosError } from 'axios'
import { Button } from '@/components/ui/Button'
import { FieldLabel, Input } from '@/components/ui/Field'
import { Logo } from '@/components/ui/Logo'
import { GoogleSignInButton } from '@/components/auth/GoogleSignInButton'

export default function RegisterPage() {
  const router = useRouter()
  const [name,     setName]     = useState('')
  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState('')

  // NEW (Google SSO & 2FA): "Continue with Google" on this page can land on
  // an *existing* account (e.g. someone who already registered with a
  // password and enabled 2FA, now trying Google for the first time) — so
  // the same mfa_token step used on /login is needed here too.
  const [mfaToken, setMfaToken] = useState('')
  const [code,      setCode]     = useState('')
  const [verifying, setVerifying] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!name.trim()) { setError('Name is required'); return }
    if (password.length < 8) { setError('Password must be at least 8 characters'); return }

    setLoading(true)
    try {
      const res = await authApi.register(name.trim(), email.trim(), password)
      saveToken(res.access_token)
      router.replace('/dashboard')
    } catch (err) {
      const axErr = err as AxiosError<{ detail?: string }>
      setError(axErr.response?.data?.detail || 'Registration failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  // NEW (Google SSO)
  const handleGoogleCredential = async (credential: string) => {
    setError('')
    setLoading(true)
    try {
      const res = await authApi.googleLogin(credential)
      if (isMfaRequired(res)) {
        setMfaToken(res.mfa_token)
      } else {
        saveToken(res.access_token)
        router.replace('/dashboard')
      }
    } catch (err) {
      const axErr = err as AxiosError<{ detail?: string }>
      setError(axErr.response?.data?.detail || 'Google sign-up failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  // NEW (2FA)
  const handleVerify2FA = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!code.trim()) {
      setError('Enter the 6-digit code from your authenticator app')
      return
    }
    setVerifying(true)
    try {
      const res = await authApi.verify2FA(mfaToken, code.trim())
      saveToken(res.access_token)
      router.replace('/dashboard')
    } catch (err) {
      const axErr = err as AxiosError<{ detail?: string }>
      setError(axErr.response?.data?.detail || 'Invalid verification code')
    } finally {
      setVerifying(false)
    }
  }

  if (mfaToken) {
    return (
      <div className="tb2-shell flex items-center justify-center p-4">
        <div className="w-full max-w-sm tb2-rise">
          <div className="flex items-center gap-2.5 justify-center mb-10">
            <Logo size={32} />
            <span className="text-xl font-bold text-white tracking-tight">ThunderBots</span>
          </div>

          <div className="tb2-glass p-7">
            <div className="flex items-center gap-2 mb-1">
              <ShieldCheck size={16} className="text-[#a5b4fc]" />
              <h1 className="text-lg font-semibold text-white">Two-factor verification</h1>
            </div>
            <p className="text-sm text-white/35 mb-6">
              This Google account is linked to an account with 2FA enabled. Enter your code to continue.
            </p>

            <form onSubmit={handleVerify2FA} className="space-y-4">
              <div>
                <FieldLabel>Verification code</FieldLabel>
                <Input
                  type="text"
                  inputMode="numeric"
                  value={code}
                  onChange={e => setCode(e.target.value)}
                  required
                  autoFocus
                  autoComplete="one-time-code"
                  placeholder="123456"
                  maxLength={11}
                />
              </div>

              {error && (
                <div className="flex items-center gap-2 text-xs text-red-400 bg-red-500/8 border border-red-500/20 rounded-xl px-3 py-2.5 tb2-rise">
                  <AlertCircle size={12} className="flex-shrink-0" />
                  {error}
                </div>
              )}

              <Button type="submit" loading={verifying} className="w-full" size="lg">
                Verify
              </Button>
              <button
                type="button"
                onClick={() => { setMfaToken(''); setCode(''); setError('') }}
                className="flex items-center gap-1.5 text-xs text-white/35 hover:text-white/70 transition-colors mx-auto"
              >
                <ArrowLeft size={12} /> Back
              </button>
            </form>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="tb2-shell flex items-center justify-center p-4">
      <div className="w-full max-w-sm tb2-rise">
        <div className="flex items-center gap-2.5 justify-center mb-10">
          <Logo size={32} />
          <span className="text-xl font-bold text-white tracking-tight">ThunderBots</span>
        </div>

        <div className="tb2-glass p-7">
          <h1 className="text-lg font-semibold text-white mb-1">Create your account</h1>
          <p className="text-sm text-white/35 mb-6">Start building AI bots for free</p>

          {/* Google SSO — full-width, modern SaaS-style button. Renders
              nothing at all when NEXT_PUBLIC_GOOGLE_CLIENT_ID isn't set. */}
          <GoogleSignInButton onCredential={handleGoogleCredential} text="continue_with" disabled={loading} />
          <div className="google-sso-divider flex items-center gap-3 my-6 text-[11px] font-medium tracking-wider text-white/25">
            <span className="h-px flex-1 bg-white/10" />
            OR
            <span className="h-px flex-1 bg-white/10" />
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <FieldLabel>Name</FieldLabel>
              <Input
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                required
                autoFocus
                autoComplete="name"
                placeholder="Your name"
              />
            </div>

            <div>
              <FieldLabel>Email</FieldLabel>
              <Input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                autoComplete="email"
                placeholder="you@example.com"
              />
            </div>

            <div>
              <FieldLabel>Password</FieldLabel>
              <div className="relative">
                <Input
                  type={showPass ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  autoComplete="new-password"
                  placeholder="Min 8 characters"
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPass(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-white/25 hover:text-white/60 transition"
                  aria-label={showPass ? 'Hide password' : 'Show password'}
                >
                  {showPass ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
              {password.length > 0 && password.length < 8 && (
                <p className="text-[10px] text-amber-400/70 mt-1">
                  {8 - password.length} more character{8 - password.length !== 1 ? 's' : ''} needed
                </p>
              )}
            </div>

            {error && (
              <div className="flex items-center gap-2 text-xs text-red-400 bg-red-500/8 border border-red-500/20 rounded-xl px-3 py-2.5 tb2-rise">
                <AlertCircle size={12} className="flex-shrink-0" />
                {error}
              </div>
            )}

            <Button type="submit" loading={loading} disabled={password.length < 8} className="w-full" size="lg">
              Create Account
            </Button>
          </form>
        </div>

        <p className="text-center text-xs text-white/30 mt-5">
          Already have an account?{' '}
          <Link href="/login" className="text-[#a5b4fc] hover:text-cyan-300 transition-colors">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
