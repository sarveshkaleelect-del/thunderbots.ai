'use client'
import { useEffect, useMemo, useState } from 'react'
import dynamic from 'next/dynamic'
import { useRouter } from 'next/navigation'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus, Megaphone, Send, CheckCircle2, XCircle, Reply, LayoutGrid, Bot, HeartHandshake, QrCode,
  Users, ScanLine, Percent, Clock, Activity,
} from 'lucide-react'
import { campaignsApi } from '@/lib/api/campaigns'
import { getErrorMessage } from '@/lib/utils/errors'
import { cn } from '@/lib/utils/cn'
import type { Campaign, CampaignStatus } from '@/types/campaigns'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { TopBar } from '@/components/ui/TopBar'
import { Footer } from '@/components/ui/Footer'
import { SkeletonGrid, EmptyState, ErrorState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'
import { CampaignCard } from '@/components/campaigns/CampaignCard'
// PERF FIX (v107): these 4 modals (CampaignFormModal alone is 630+ lines)
// are only ever rendered after a user explicitly clicks to open one — never
// on initial page load. Lazy-loading them keeps that weight out of the
// campaigns page's initial bundle; each is fetched once, on first open.
const CampaignFormModal = dynamic(
  () => import('@/components/campaigns/CampaignFormModal').then(m => m.CampaignFormModal),
  { ssr: false },
)
const CampaignHistoryModal = dynamic(
  () => import('@/components/campaigns/CampaignHistoryModal').then(m => m.CampaignHistoryModal),
  { ssr: false },
)
const CampaignRecipientsModal = dynamic(
  () => import('@/components/campaigns/CampaignRecipientsModal').then(m => m.CampaignRecipientsModal),
  { ssr: false },
)
const QRMarketingModal = dynamic(
  () => import('@/components/campaigns/QRMarketingModal').then(m => m.QRMarketingModal),
  { ssr: false },
)
import { SubscriberGrowthCard } from '@/components/campaigns/SubscriberGrowthCard'
import { CampaignPerformanceCard } from '@/components/campaigns/CampaignPerformanceCard'
import { BroadcastHistoryCard } from '@/components/campaigns/BroadcastHistoryCard'

type StatusFilter = 'all' | CampaignStatus

const STATUS_FILTERS: [StatusFilter, string][] = [
  ['all', 'All'],
  ['draft', 'Draft'],
  ['scheduled', 'Scheduled'],
  ['active', 'Active'],
  ['paused', 'Paused'],
  ['completed', 'Completed'],
]

export default function CampaignsPage() {
  const router = useRouter()
  const qc = useQueryClient()
  const { toast } = useToast()

  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<Campaign | null>(null)
  const [historyFor, setHistoryFor] = useState<Campaign | null>(null)
  const [progressFor, setProgressFor] = useState<Campaign | null>(null)
  const [showQRMarketing, setShowQRMarketing] = useState(false)

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('tb_token')) {
      router.replace('/login')
    }
  }, [router])

  const { data: campaigns = [], isLoading, error, refetch } = useQuery({
    queryKey: ['campaigns'],
    queryFn: () => campaignsApi.list(),
  })

  const { data: overview } = useQuery({
    queryKey: ['campaigns-analytics-overview'],
    queryFn: campaignsApi.analyticsOverview,
  })

  const { data: templates = [] } = useQuery({
    queryKey: ['campaign-templates'],
    queryFn: campaignsApi.templates,
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['campaigns'] })
    qc.invalidateQueries({ queryKey: ['campaigns-analytics-overview'] })
  }

  const deleteMutation = useMutation({
    mutationFn: (id: string) => campaignsApi.delete(id),
    onSuccess: () => { invalidate(); toast('success', 'Campaign deleted.') },
    onError: err => toast('error', getErrorMessage(err, 'Could not delete this campaign.')),
  })

  const duplicateMutation = useMutation({
    mutationFn: (id: string) => campaignsApi.duplicate(id),
    onSuccess: () => { invalidate(); toast('success', 'Campaign duplicated.') },
    onError: err => toast('error', getErrorMessage(err, 'Could not duplicate this campaign.')),
  })

  const pauseMutation = useMutation({
    mutationFn: (id: string) => campaignsApi.pause(id),
    onSuccess: () => { invalidate(); toast('success', 'Campaign paused.') },
    onError: err => toast('error', getErrorMessage(err, 'Could not pause this campaign.')),
  })

  const resumeMutation = useMutation({
    mutationFn: (id: string) => campaignsApi.resume(id),
    onSuccess: () => { invalidate(); toast('success', 'Campaign resumed.') },
    onError: err => toast('error', getErrorMessage(err, 'Could not resume this campaign.')),
  })

  const list = campaigns as Campaign[]
  const filtered = useMemo(
    () => statusFilter === 'all' ? list : list.filter(c => c.status === statusFilter),
    [list, statusFilter]
  )

  const closeForm = () => { setShowForm(false); setEditing(null) }
  const openCreate = () => { setEditing(null); setShowForm(true) }
  const openEdit = (c: Campaign) => { setEditing(c); setShowForm(true) }

  const statCards = [
    { label: 'Sent', value: overview?.sent ?? 0, icon: Send, tone: 'text-white/80', ring: 'bg-white/[0.06] border-white/10' },
    { label: 'Delivered', value: overview?.delivered ?? 0, icon: CheckCircle2, tone: 'text-emerald-400', ring: 'bg-emerald-500/10 border-emerald-500/20' },
    { label: 'Failed', value: overview?.failed ?? 0, icon: XCircle, tone: 'text-red-400', ring: 'bg-red-500/10 border-red-500/20' },
    { label: 'Replied', value: overview?.replied ?? 0, icon: Reply, tone: 'text-cyan-300', ring: 'bg-cyan-500/10 border-cyan-500/20' },
    { label: 'AI Resolved', value: overview?.ai_resolved ?? 0, icon: Bot, tone: 'text-[#a5b4fc]', ring: 'bg-[#6366f1]/10 border-[#6366f1]/20' },
    { label: 'Human Handoff', value: overview?.escalated ?? 0, icon: HeartHandshake, tone: 'text-amber-400', ring: 'bg-amber-500/10 border-amber-500/20' },
    { label: 'Subscribers', value: overview?.subscribers ?? 0, icon: Users, tone: 'text-indigo-300', ring: 'bg-indigo-500/10 border-indigo-500/20' },
    { label: 'QR Scans', value: overview?.qr_scans ?? 0, icon: QrCode, tone: 'text-emerald-300', ring: 'bg-emerald-500/10 border-emerald-500/20' },
    { label: 'Unique QR Scans', value: overview?.unique_qr_scans ?? 0, icon: ScanLine, tone: 'text-teal-300', ring: 'bg-teal-500/10 border-teal-500/20' },
    { label: 'Conversion Rate', value: `${overview?.conversion_rate ?? 0}%`, icon: Percent, tone: 'text-fuchsia-300', ring: 'bg-fuchsia-500/10 border-fuchsia-500/20' },
  ]

  const activeCampaigns = useMemo(() => list.filter(c => c.status === 'active').slice(0, 3), [list])
  const scheduledCampaigns = useMemo(() => list.filter(c => c.status === 'scheduled').slice(0, 3), [list])
  const recentCampaigns = useMemo(
    () => [...list].sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at)).slice(0, 3),
    [list]
  )

  return (
    <div className="tb2-shell">
      <TopBar
        right={
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" onClick={() => setShowQRMarketing(true)} icon={<QrCode size={14} />}>
              QR Marketing
            </Button>
            <Button size="sm" onClick={openCreate} icon={<Plus size={14} />}>
              New Campaign
            </Button>
          </div>
        }
      />

      <main className="max-w-[1600px] mx-auto px-6 md:px-10 py-8 md:py-10 w-full">
        <div className="tb2-rise mb-8 flex items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-[#6366f1]/15 border border-[#6366f1]/25 flex items-center justify-center flex-shrink-0">
            <Megaphone size={20} className="text-[#a5b4fc]" />
          </div>
          <div>
            <h1 className="text-lg sm:text-xl font-bold text-white">AI Campaign Manager</h1>
            <p className="text-xs sm:text-[13px] text-white/40 mt-0.5">
              Create and manage AI-powered marketing campaigns across WhatsApp, Telegram, and future channels.
            </p>
          </div>
        </div>

        {/* QR Marketing section */}
        <Card hover onClick={() => setShowQRMarketing(true)} className="tb2-rise mb-8 p-5 flex items-center gap-4 cursor-pointer" style={{ animationDelay: '40ms' }}>
          <div className="w-11 h-11 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center flex-shrink-0">
            <QrCode size={18} className="text-emerald-400" />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-bold text-white">QR Marketing</h2>
            <p className="text-xs text-white/40 mt-0.5">
              Generate a scannable QR code for each connected channel — print it at your shop entrance, cash counter, or bills to turn walk-in customers into permanent Telegram &amp; WhatsApp subscribers.
            </p>
          </div>
          <Button size="sm" variant="secondary" icon={<QrCode size={13} />}>Open</Button>
        </Card>

        {/* Analytics */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-8">
          {statCards.map((s, i) => (
            <Card key={s.label} hover className="tb2-rise p-4 flex items-center gap-3.5" style={{ animationDelay: `${60 + i * 40}ms` }}>
              <div className={cn('w-10 h-10 rounded-xl border flex items-center justify-center flex-shrink-0', s.ring)}>
                <s.icon size={16} className={s.tone} />
              </div>
              <div>
                <p className={cn('text-2xl font-bold leading-none', s.tone)}>{s.value}</p>
                <p className="text-[11px] text-white/25 mt-1">{s.label}</p>
              </div>
            </Card>
          ))}
        </div>

        {/* Subscriber Growth + Campaign Performance (NEW — Part 3) */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          <div className="lg:col-span-2">
            <SubscriberGrowthCard />
          </div>
          <CampaignPerformanceCard campaigns={list} />
        </div>

        {/* Broadcast History (NEW — Part 3) */}
        <div className="mb-8">
          <BroadcastHistoryCard />
        </div>

        {/* Active / Scheduled / Recent Campaigns (NEW — Part 3) */}
        {(activeCampaigns.length > 0 || scheduledCampaigns.length > 0) && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
            {activeCampaigns.length > 0 && (
              <Card className="tb2-rise p-5">
                <div className="flex items-center gap-2.5 mb-4">
                  <div className="w-8 h-8 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center flex-shrink-0">
                    <Activity size={14} className="text-emerald-400" />
                  </div>
                  <h3 className="text-sm font-bold text-white">Active Campaigns</h3>
                </div>
                <div className="space-y-2">
                  {activeCampaigns.map(c => (
                    <div key={c.id} className="flex items-center justify-between px-3 py-2 rounded-xl bg-white/[0.02] border border-white/[0.05]">
                      <p className="text-xs font-medium text-white/85 truncate">{c.name}</p>
                      <p className="text-[11px] text-white/30 flex-shrink-0 ml-3">{c.sent_count} sent</p>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {scheduledCampaigns.length > 0 && (
              <Card className="tb2-rise p-5">
                <div className="flex items-center gap-2.5 mb-4">
                  <div className="w-8 h-8 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center flex-shrink-0">
                    <Clock size={14} className="text-cyan-300" />
                  </div>
                  <h3 className="text-sm font-bold text-white">Scheduled Campaigns</h3>
                </div>
                <div className="space-y-2">
                  {scheduledCampaigns.map(c => (
                    <div key={c.id} className="flex items-center justify-between px-3 py-2 rounded-xl bg-white/[0.02] border border-white/[0.05]">
                      <p className="text-xs font-medium text-white/85 truncate">{c.name}</p>
                      <p className="text-[11px] text-white/30 flex-shrink-0 ml-3">
                        {c.scheduled_at ? new Date(c.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                      </p>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
        )}

        {recentCampaigns.length > 0 && (
          <Card className="tb2-rise p-5 mb-8">
            <div className="flex items-center gap-2.5 mb-4">
              <div className="w-8 h-8 rounded-xl bg-white/[0.06] border border-white/10 flex items-center justify-center flex-shrink-0">
                <Megaphone size={14} className="text-white/60" />
              </div>
              <h3 className="text-sm font-bold text-white">Recent Campaigns</h3>
            </div>
            <div className="space-y-2">
              {recentCampaigns.map(c => (
                <div key={c.id} className="flex items-center justify-between px-3 py-2 rounded-xl bg-white/[0.02] border border-white/[0.05]">
                  <p className="text-xs font-medium text-white/85 truncate">{c.name}</p>
                  <p className="text-[11px] text-white/30 flex-shrink-0 ml-3 capitalize">{c.status}</p>
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* Filters */}
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between mb-6">
          <h2 className="text-sm font-bold text-white/80 flex-shrink-0">Campaigns</h2>
          <div className="flex items-center gap-1.5 flex-wrap">
            {STATUS_FILTERS.map(([value, label]) => (
              <button
                key={value}
                onClick={() => setStatusFilter(value)}
                className={cn(
                  'tb2-chip text-xs font-medium px-3 py-1.5 rounded-lg border',
                  statusFilter === value
                    ? 'bg-[#6366f1]/15 border-[#6366f1]/30 text-[#c7d2fe]'
                    : 'bg-transparent border-white/10 text-white/40 hover:text-white/70 hover:border-white/20'
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {isLoading && <SkeletonGrid count={6} />}

        {error && !isLoading && (
          <ErrorState
            title="Couldn't load your campaigns"
            description={getErrorMessage(error, 'Check your connection and that the backend is running.')}
            onRetry={() => refetch()}
          />
        )}

        {!isLoading && !error && list.length === 0 && (
          <EmptyState
            icon={<Megaphone size={28} />}
            title="No campaigns yet"
            description="Create your first AI-powered marketing campaign to reach your customers."
            action={
              <Button onClick={openCreate} icon={<Plus size={14} />}>
                New Campaign
              </Button>
            }
          />
        )}

        {!isLoading && !error && list.length > 0 && filtered.length === 0 && (
          <EmptyState
            icon={<LayoutGrid size={28} />}
            title="No campaigns match this filter"
            description="Try a different status filter to see more campaigns."
            action={
              <Button variant="secondary" onClick={() => setStatusFilter('all')}>
                Show all
              </Button>
            }
          />
        )}

        {filtered.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filtered.map((c, i) => (
              <CampaignCard
                key={c.id}
                campaign={c}
                style={{ animationDelay: `${Math.min(i, 8) * 35}ms` }}
                onEdit={() => openEdit(c)}
                onDuplicate={() => duplicateMutation.mutate(c.id)}
                onDelete={() => deleteMutation.mutate(c.id)}
                onPause={() => pauseMutation.mutate(c.id)}
                onResume={() => resumeMutation.mutate(c.id)}
                onHistory={() => setHistoryFor(c)}
                onProgress={() => setProgressFor(c)}
              />
            ))}
          </div>
        )}
      </main>

      <Footer />

      {showForm && (
        <CampaignFormModal
          campaign={editing}
          templates={templates}
          onClose={closeForm}
          onSaved={() => { closeForm(); invalidate() }}
        />
      )}

      {historyFor && (
        <CampaignHistoryModal campaign={historyFor} onClose={() => setHistoryFor(null)} />
      )}

      {progressFor && (
        <CampaignRecipientsModal campaign={progressFor} onClose={() => setProgressFor(null)} />
      )}

      {showQRMarketing && (
        <QRMarketingModal onClose={() => setShowQRMarketing(false)} />
      )}
    </div>
  )
}
