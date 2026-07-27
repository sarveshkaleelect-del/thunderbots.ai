'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { UserCircle2, Mail, ShieldCheck, KeyRound, Lock } from 'lucide-react'
import Link from 'next/link'
import { authApi, getToken } from '@/lib/api/auth'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { SubPageBar } from '@/components/ui/TopBar'
import { PageLoader } from '@/components/ui/States'

export default function ProfilePage() {
  const router = useRouter()

  useEffect(() => {
    if (typeof window !== 'undefined' && !getToken()) router.replace('/login')
  }, [router])

  const { data: me, isLoading } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: authApi.me,
    retry: false,
  })

  const initials = me?.name
    ? me.name.trim().split(/\s+/).slice(0, 2).map(p => p[0]?.toUpperCase()).join('')
    : '—'

  return (
    <div className="tb2-shell">
      <SubPageBar crumb="My Profile" crumbIcon={<UserCircle2 size={14} />} />

      <div className="max-w-2xl mx-auto px-6 py-10 space-y-6">
        <h1 className="text-xl font-bold text-white tb2-rise">My Profile</h1>

        {isLoading ? (
          <PageLoader />
        ) : (
          <Card className="tb2-rise p-6 flex items-center gap-4">
            <div className="w-14 h-14 rounded-2xl tb2-brand-mark flex items-center justify-center text-lg font-bold text-[#c7d2fe] flex-shrink-0">
              {initials}
            </div>
            <div className="min-w-0">
              <p className="text-base font-semibold text-white/90 truncate">{me?.name || 'Account'}</p>
              <p className="flex items-center gap-1.5 text-xs text-white/40 mt-1">
                <Mail size={11} />
                {me?.email}
              </p>
              {me?.is_admin && (
                <p className="flex items-center gap-1.5 text-[11px] text-emerald-400/80 mt-1.5">
                  <ShieldCheck size={11} />
                  Administrator
                </p>
              )}
            </div>
          </Card>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Link href="/settings" className="tb2-row tb2-glass tb2-glass-hover flex items-center gap-3 p-4">
            <div className="w-9 h-9 rounded-xl bg-[#6366f1]/15 border border-[#6366f1]/25 flex items-center justify-center flex-shrink-0">
              <UserCircle2 size={16} className="text-[#a5b4fc]" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-white/80">Account Settings</p>
              <p className="text-[11px] text-white/35">Theme, language, defaults</p>
            </div>
          </Link>
          <Link href="/settings/api-keys" className="tb2-row tb2-glass tb2-glass-hover flex items-center gap-3 p-4">
            <div className="w-9 h-9 rounded-xl bg-[#6366f1]/15 border border-[#6366f1]/25 flex items-center justify-center flex-shrink-0">
              <KeyRound size={16} className="text-[#a5b4fc]" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-white/80">API Keys</p>
              <p className="text-[11px] text-white/35">Manage AI provider keys</p>
            </div>
          </Link>
          {/* NEW (Google SSO & 2FA) */}
          <Link href="/settings/security" className="tb2-row tb2-glass tb2-glass-hover flex items-center gap-3 p-4">
            <div className="w-9 h-9 rounded-xl bg-[#6366f1]/15 border border-[#6366f1]/25 flex items-center justify-center flex-shrink-0">
              <Lock size={16} className="text-[#a5b4fc]" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-white/80">Security</p>
              <p className="text-[11px] text-white/35">Google sign-in, two-factor auth</p>
            </div>
          </Link>
        </div>

        <div className="flex justify-end">
          <Button variant="secondary" onClick={() => router.push('/dashboard')}>
            Back to Dashboard
          </Button>
        </div>
      </div>
    </div>
  )
}
