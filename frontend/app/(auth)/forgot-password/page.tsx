'use client'
import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { AlertCircle, ArrowLeft, MailCheck } from 'lucide-react'
import { authApi } from '@/lib/api/auth'
import { AxiosError } from 'axios'
import { Button } from '@/components/ui/Button'
import { FieldLabel, Input } from '@/components/ui/Field'
import { Logo } from '@/components/ui/Logo'

export default function ForgotPasswordPage() {
  const router = useRouter()
  const [email,   setEmail]   = useState('')
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')
  // The backend always returns the same generic response regardless of
  // whether the email matches an account (prevents enumeration) — so the
  // frontend shows the same "check your email" state either way, never a
  // "this account doesn't exist" error.
  const [sent, setSent] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!email.trim()) {
      setError('Enter your email address')
      return
    }
    setLoading(true)
    try {
      await authApi.forgotPassword(email.trim())
      setSent(true)
    } catch (err) {
      const axErr = err as AxiosError<{ detail?: string }>
      setError(axErr.response?.data?.detail || 'Something went wrong. Please try again.')
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
          {sent ? (
            <>
              <div className="flex items-center gap-2 mb-1">
                <MailCheck size={16} className="text-[#a5b4fc]" />
                <h1 className="text-lg font-semibold text-white">Check your email</h1>
              </div>
              <p className="text-sm text-white/35 mb-6">
                If an account exists for <span className="text-white/60">{email.trim()}</span>, we&apos;ve
                sent a link to reset your password. It expires in 30 minutes.
              </p>
              <Button type="button" className="w-full" size="lg" onClick={() => router.push('/login')}>
                Back to sign in
              </Button>
            </>
          ) : (
            <>
              <h1 className="text-lg font-semibold text-white mb-1">Reset your password</h1>
              <p className="text-sm text-white/35 mb-6">
                Enter your email and we&apos;ll send you a link to get back into your account.
              </p>

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

                {error && (
                  <div className="flex items-center gap-2 text-xs text-red-400 bg-red-500/8 border border-red-500/20 rounded-xl px-3 py-2.5 tb2-rise">
                    <AlertCircle size={12} className="flex-shrink-0" />
                    {error}
                  </div>
                )}

                <Button type="submit" loading={loading} className="w-full" size="lg">
                  Send reset link
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
