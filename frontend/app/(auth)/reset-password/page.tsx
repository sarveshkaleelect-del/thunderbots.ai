'use client'
import { Suspense, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { AlertCircle, ArrowLeft, CheckCircle2, Eye, EyeOff } from 'lucide-react'
import { authApi } from '@/lib/api/auth'
import { AxiosError } from 'axios'
import { Button } from '@/components/ui/Button'
import { FieldLabel, Input } from '@/components/ui/Field'
import { Logo } from '@/components/ui/Logo'

function ResetPasswordForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const token = searchParams.get('token') || ''

  const [password,        setPassword]        = useState('')
  const [confirmPassword, setConfirmPassword]  = useState('')
  const [showPass,        setShowPass]         = useState(false)
  const [loading,         setLoading]          = useState(false)
  const [error,           setError]            = useState('')
  const [done,            setDone]             = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }
    if (!token) {
      setError('This reset link is missing or malformed. Please request a new one.')
      return
    }

    setLoading(true)
    try {
      await authApi.resetPassword(token, password)
      setDone(true)
    } catch (err) {
      const axErr = err as AxiosError<{ detail?: string }>
      setError(axErr.response?.data?.detail || 'This password reset link is invalid or has expired.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="tb2-shell flex items-center justify-center p-4">
      <div className="w-full max-w-sm tb2-rise">
        <div className="flex items-center gap-2.5 justify-center mb-10">
          <Logo size={32} />
          <span className="text-xl font-bold text-white tracking-tight">ThunderBots</span>
        </div>

        <div className="tb2-glass p-7">
          {done ? (
            <>
              <div className="flex items-center gap-2 mb-1">
                <CheckCircle2 size={16} className="text-[#a5b4fc]" />
                <h1 className="text-lg font-semibold text-white">Password updated</h1>
              </div>
              <p className="text-sm text-white/35 mb-6">
                Your password has been reset. You can now sign in with your new password.
              </p>
              <Button type="button" className="w-full" size="lg" onClick={() => router.push('/login')}>
                Sign in
              </Button>
            </>
          ) : (
            <>
              <h1 className="text-lg font-semibold text-white mb-1">Set a new password</h1>
              <p className="text-sm text-white/35 mb-6">Choose a new password for your account.</p>

              {!token && (
                <div className="flex items-center gap-2 text-xs text-amber-400 bg-amber-500/8 border border-amber-500/20 rounded-xl px-3 py-2.5 mb-4">
                  <AlertCircle size={12} className="flex-shrink-0" />
                  This link is missing its reset token. Request a new link from the sign-in page.
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <FieldLabel>New password</FieldLabel>
                  <div className="relative">
                    <Input
                      type={showPass ? 'text' : 'password'}
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      required
                      autoFocus
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
                </div>

                <div>
                  <FieldLabel>Confirm new password</FieldLabel>
                  <Input
                    type={showPass ? 'text' : 'password'}
                    value={confirmPassword}
                    onChange={e => setConfirmPassword(e.target.value)}
                    required
                    autoComplete="new-password"
                    placeholder="Re-enter your new password"
                  />
                </div>

                {error && (
                  <div className="flex items-center gap-2 text-xs text-red-400 bg-red-500/8 border border-red-500/20 rounded-xl px-3 py-2.5 tb2-rise">
                    <AlertCircle size={12} className="flex-shrink-0" />
                    {error}
                  </div>
                )}

                <Button type="submit" loading={loading} className="w-full" size="lg">
                  Reset password
                </Button>
                <Link
                  href="/login"
                  className="flex items-center gap-1.5 text-xs text-white/35 hover:text-white/70 transition-colors justify-center"
                >
                  <ArrowLeft size={12} /> Back to sign in
                </Link>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  )
}
