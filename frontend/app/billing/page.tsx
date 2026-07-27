'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { CreditCard, Sparkles } from 'lucide-react'
import { getToken } from '@/lib/api/auth'
import { Card, Badge } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { SubPageBar } from '@/components/ui/TopBar'

export default function BillingPage() {
  const router = useRouter()

  useEffect(() => {
    if (typeof window !== 'undefined' && !getToken()) router.replace('/login')
  }, [router])

  return (
    <div className="tb2-shell">
      <SubPageBar crumb="Billing" crumbIcon={<CreditCard size={14} />} />

      <div className="max-w-2xl mx-auto px-6 py-10 space-y-6">
        <h1 className="text-xl font-bold text-white tb2-rise">Billing</h1>

        <Card className="tb2-rise p-6 flex items-center gap-4">
          <div className="w-11 h-11 rounded-2xl bg-[#6366f1]/15 border border-[#6366f1]/25 flex items-center justify-center flex-shrink-0">
            <Sparkles size={18} className="text-[#a5b4fc]" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-white/90">Current Plan</p>
            <p className="text-[11px] text-white/35 mt-0.5">You're on the free tier</p>
          </div>
          <Badge tone="default">Free</Badge>
        </Card>

        <Card className="tb2-rise p-6 text-center">
          <p className="text-sm font-semibold text-white/70">Plans & invoices coming soon</p>
          <p className="text-[11px] text-white/30 mt-1.5">
            Upgrade options and billing history will appear here once available.
          </p>
        </Card>

        <div className="flex justify-end">
          <Button variant="secondary" onClick={() => router.push('/dashboard')}>
            Back to Dashboard
          </Button>
        </div>
      </div>
    </div>
  )
}
