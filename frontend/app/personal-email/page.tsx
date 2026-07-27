'use client'
import { useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Mail, Plus, ChevronRight, ShieldCheck, AlertTriangle } from 'lucide-react'
import { personalEmailApi } from '@/lib/api/personalEmail'
import { TopBar } from '@/components/ui/TopBar'
import { Card, Badge } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { PageLoader, EmptyState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'
import type { PersonalEmailStatus } from '@/types/personalEmail'

function statusTone(status: PersonalEmailStatus) {
  if (status === 'connected') return 'success' as const
  if (status === 'disconnected') return 'default' as const
  return 'danger' as const
}

export default function PersonalEmailIndexPage() {
  return (
    <Suspense fallback={null}>
      <PersonalEmailIndexPageInner />
    </Suspense>
  )
}

function PersonalEmailIndexPageInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const queryClient = useQueryClient()
  const { toast } = useToast()

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('tb_token')) {
      router.replace('/login')
    }
  }, [router])

  useEffect(() => {
    const connected = searchParams.get('pe_connected')
    const error = searchParams.get('pe_error')
    if (connected) {
      toast('success', 'Gmail account connected.')
      queryClient.invalidateQueries({ queryKey: ['personal-email-accounts'] })
      router.replace('/personal-email')
    } else if (error) {
      toast('error', `Couldn't connect Gmail: ${error.replace(/_/g, ' ')}`)
      router.replace('/personal-email')
    }
  }, [searchParams, toast, queryClient, router])

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['personal-email-accounts'],
    queryFn: personalEmailApi.listAccounts,
  })

  const handleConnect = async () => {
    try {
      const { authorize_url } = await personalEmailApi.authorizeUrl('gmail')
      window.location.href = authorize_url
    } catch (e: any) {
      toast('error', e?.response?.data?.detail || 'Gmail integration is not configured on this server yet.')
    }
  }

  return (
    <div className="min-h-screen">
      <TopBar />
      <main className="max-w-4xl mx-auto px-3 sm:px-6 py-6 sm:py-10">
        <div className="flex items-center justify-between gap-3 mb-6">
          <div>
            <h1 className="text-lg sm:text-xl font-semibold text-white flex items-center gap-2">
              <Mail size={20} className="text-[#a5b4fc]" />
              Personal Email AI Assistant
            </h1>
            <p className="text-xs sm:text-sm text-white/35 mt-1">
              Connect your own inbox — AI reads, summarizes, organizes, and drafts replies. Separate from the
              customer-support Email Channel.
            </p>
          </div>
          <Button onClick={handleConnect} icon={<Plus size={15} />}>
            Connect Gmail
          </Button>
        </div>

        {isLoading && <PageLoader label="Loading connected accounts…" />}

        {isError && (
          <Card className="p-5 flex items-center gap-3">
            <AlertTriangle size={16} className="text-red-400 flex-shrink-0" />
            <p className="text-sm text-white/60">Couldn't load your connected accounts.</p>
            <Button variant="ghost" size="sm" onClick={() => refetch()}>Retry</Button>
          </Card>
        )}

        {!isLoading && !isError && data && data.accounts.length === 0 && (
          <EmptyState
            icon={<Mail size={24} />}
            title="No mailbox connected yet"
            description="Connect your personal Gmail account to let AI summarize, prioritize, and draft replies for you. We never send anything on your behalf."
            action={
              <Button onClick={handleConnect} icon={<Plus size={15} />}>
                Connect Gmail
              </Button>
            }
          />
        )}

        {!isLoading && !isError && data && data.accounts.length > 0 && (
          <div className="space-y-3">
            {data.accounts.map(account => (
              <Card
                key={account.id}
                hover
                onClick={() => router.push(`/personal-email/${account.id}`)}
                className="p-4 sm:p-5 flex items-center gap-4"
              >
                <div className="w-10 h-10 rounded-xl bg-white/[0.05] flex items-center justify-center flex-shrink-0">
                  <Mail size={18} className="text-[#a5b4fc]" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-white truncate">{account.email_address}</p>
                  <p className="text-xs text-white/35 mt-0.5 truncate">
                    {account.provider === 'gmail' ? 'Gmail' : 'Outlook'} · Last synced{' '}
                    {account.last_sync_at ? new Date(account.last_sync_at).toLocaleString() : 'never'}
                  </p>
                </div>
                <Badge tone={statusTone(account.status)} dot={account.status === 'connected'}>
                  {account.status}
                </Badge>
                <ChevronRight size={16} className="text-white/20 flex-shrink-0" />
              </Card>
            ))}
          </div>
        )}

        {!isLoading && !isError && data && !data.configured && (
          <Card className="p-4 mt-6 flex items-center gap-3">
            <ShieldCheck size={16} className="text-amber-400 flex-shrink-0" />
            <p className="text-xs text-white/40">
              Gmail OAuth isn't configured on this server yet — an admin needs to set GMAIL_CLIENT_ID /
              GMAIL_CLIENT_SECRET before accounts can be connected.
            </p>
          </Card>
        )}
      </main>
    </div>
  )
}
