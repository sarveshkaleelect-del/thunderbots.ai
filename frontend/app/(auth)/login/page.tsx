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

export default function LoginPage() {
  const router = useRouter()
  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState('')

  // NEW (2FA): once a password or Google credential checks out on an
  // account with TOTP enabled, we hold the short-lived mfa_token here and
  // swap the form for a 6-digit/backup-code prompt instead of navigating
  // away immediately.
  const [mfaToken, setMfaToken] = useState('')
  const [code,      setCode]     = useState('')
  const [verifying, setVerifying] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!email.trim() || !password) {
      setError('Email and password are required')
      return
    }

    setLoading(true)
    try {
      const res = await authApi.login(email.trim(), password)
      if (isMfaRequired(res)) {
        setMfaToken(res.mfa_token)
      } else {
        saveToken(res.access_token)
        router.replace('/dashboard')
      }
    } catch (err) {
      const axErr = err as AxiosError<{ detail?: string }>
      setError(axErr.response?.data?.detail || 'Invalid email or password')
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
      setError(axErr.response?.data?.detail || 'Google sign-in failed. Please try again.')
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
              Enter the 6-digit code from your authenticator app, or a backup code.
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
                <ArrowLeft size={12} /> Back to sign in
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
          <h1 className="text-lg font-semibold text-white mb-1">Welcome back</h1>
          <p className="text-sm text-white/35 mb-6">Sign in to your account</p>

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
              <FieldLabel>Email</FieldLabel>
              <Input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                autoFocus
                autoComplete="email"
                placeholder="you@example.com"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-[10px] font-semibold text-white/40 uppercase tracking-wider">
                  Password
                </label>
                <Link
                  href="/forgot-password"
                  className="text-[11px] text-white/30 hover:text-[#a5b4fc] transition-colors"
                >
                  Forgot password?
                </Link>
              </div>
              <div className="relative">
                <Input
                  type={showPass ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  placeholder="••••••••"
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
            </div>

            {error && (
              <div className="flex items-center gap-2 text-xs text-red-400 bg-red-500/8 border border-red-500/20 rounded-xl px-3 py-2.5 tb2-rise">
                <AlertCircle size={12} className="flex-shrink-0" />
                {error}
              </div>
            )}

            <Button type="submit" loading={loading} className="w-full" size="lg">
              Sign In
            </Button>
          </form>
        </div>

        <p className="text-center text-xs text-white/30 mt-5">
          Don&apos;t have an account?{' '}
          <Link href="/register" className="text-[#a5b4fc] hover:text-cyan-300 transition-colors">
            Sign up
          </Link>
        </p>
      </div>
    </div>
  )
}
