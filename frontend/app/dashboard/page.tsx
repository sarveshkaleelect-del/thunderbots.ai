'use client'
import { useMemo, useState, useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus, Bot, Trash2, ExternalLink, GitBranch,
  Clock, Database, Globe, Copy, MessageCircle, Instagram, Send, Wand2, Sparkles,
  Search, X, MoreVertical, LayoutGrid, Rocket, PenLine, Store,
} from 'lucide-react'
import { workflowsApi } from '@/lib/api/workflows'
import { cn } from '@/lib/utils/cn'
import { getErrorMessage } from '@/lib/utils/errors'
import type { WorkflowListItem } from '@/types'
import { Button, IconButton } from '@/components/ui/Button'
import { Card, Badge } from '@/components/ui/Card'
import { Modal } from '@/components/ui/Modal'
import { FieldLabel, Input, Textarea } from '@/components/ui/Field'
import { TopBar } from '@/components/ui/TopBar'
import { usePopover } from '@/components/ui/TopBarMenus'
import { Footer } from '@/components/ui/Footer'
import { Skeleton, SkeletonGrid, EmptyState, ErrorState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'

type StatusFilter = 'all' | 'published' | 'draft'

function WorkflowCard({
  workflow,
  onDelete,
  onDuplicate,
  style,
}: {
  workflow: WorkflowListItem
  onDelete: (id: string) => void
  onDuplicate: (id: string) => void
  style?: React.CSSProperties
}) {
  const router = useRouter()
  const isPublished = workflow.status === 'published'
  const { open, setOpen, triggerRef: ref } = usePopover<HTMLDivElement>()

  const go = (path: string) => (e: React.MouseEvent) => {
    e.stopPropagation()
    setOpen(false)
    router.push(path)
  }

  return (
    <Card
      hover
      className="tb2-rise group relative overflow-hidden"
      style={style}
      onClick={() => router.push(`/builder/${workflow.id}`)}
    >
      <div
        className={cn(
          'h-1 w-full',
          isPublished
            ? 'bg-gradient-to-r from-emerald-500/70 via-emerald-400/50 to-cyan-400/40'
            : 'bg-white/[0.06]'
        )}
      />

      <div className="p-5">
        <div className="flex items-start justify-between gap-3 mb-3.5">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-xl tb2-brand-mark flex items-center justify-center flex-shrink-0 transition-transform duration-200 group-hover:scale-105">
              <Bot size={16} className="text-[#a5b4fc]" />
            </div>
            <div className="min-w-0">
              <p className="font-semibold text-sm text-white/90 truncate">{workflow.name}</p>
              {workflow.description && (
                <p className="text-[11px] text-white/30 truncate mt-0.5">{workflow.description}</p>
              )}
            </div>
          </div>

          {/* Kebab action menu — replaces the old always-reflowing 4-icon
              hover row with a single compact trigger + dropdown. Same
              four actions, same handlers, just tidier. */}
          <div className="relative flex-shrink-0" ref={ref}>
            <IconButton
              aria-label="Workflow actions"
              className={cn('transition-opacity', open ? 'opacity-100' : 'opacity-0 group-hover:opacity-100')}
              onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
            >
              <MoreVertical size={14} />
            </IconButton>
            {open && (
              <div className="tb2-glass tb2-popover-in origin-top-right absolute right-0 top-[calc(100%+6px)] z-30 w-44 p-1.5 rounded-2xl shadow-2xl overflow-hidden">
                <button
                  onClick={go(`/builder/${workflow.id}`)}
                  className="tb2-row w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-white/70 hover:bg-white/[0.06] hover:text-white text-left"
                >
                  <ExternalLink size={13} className="text-white/40" /> Open in Builder
                </button>
                <button
                  onClick={go(`/whatsapp/${workflow.id}`)}
                  className="tb2-row w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-white/70 hover:bg-emerald-500/10 hover:text-emerald-300 text-left"
                >
                  <MessageCircle size={13} className="text-white/40" /> WhatsApp Channel
                </button>
                <button
                  onClick={go(`/instagram/${workflow.id}`)}
                  className="tb2-row w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-white/70 hover:bg-pink-500/10 hover:text-pink-300 text-left"
                >
                  <Instagram size={13} className="text-white/40" /> Instagram Channel
                </button>
                <button
                  onClick={go(`/telegram/${workflow.id}`)}
                  className="tb2-row w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-white/70 hover:bg-sky-500/10 hover:text-sky-300 text-left"
                >
                  <Send size={13} className="text-white/40" /> Telegram Channel
                </button>
                <button
                  onClick={e => { e.stopPropagation(); setOpen(false); onDuplicate(workflow.id) }}
                  className="tb2-row w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-white/70 hover:bg-white/[0.06] hover:text-white text-left"
                >
                  <Copy size={13} className="text-white/40" /> Duplicate
                </button>
                <div className="h-px bg-white/[0.06] mx-1 my-1" />
                <button
                  onClick={e => {
                    e.stopPropagation()
                    setOpen(false)
                    if (window.confirm(`Delete "${workflow.name}"? This cannot be undone.`)) {
                      onDelete(workflow.id)
                    }
                  }}
                  className="tb2-row w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-red-400/90 hover:bg-red-500/10 text-left"
                >
                  <Trash2 size={13} /> Delete
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <span className="flex items-center gap-1 text-[10px] text-white/25">
            <GitBranch size={9} />{workflow.node_count ?? 0} nodes
          </span>
          <span className="flex items-center gap-1 text-[10px] text-white/25">
            <Clock size={9} />
            {workflow.updated_at
              ? new Date(workflow.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
              : '—'}
          </span>
          {workflow.knowledge_base_id && (
            <span className="flex items-center gap-1 text-[10px] text-emerald-400/50">
              <Database size={9} />KB
            </span>
          )}
          <Badge tone={isPublished ? 'success' : 'default'} dot className="ml-auto">
            {isPublished ? <span className="flex items-center gap-1"><Globe size={8} />Live</span> : 'Draft'}
          </Badge>
        </div>
      </div>
    </Card>
  )
}

function QuickAction({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="tb2-chip flex-shrink-0 flex items-center gap-2 text-xs font-medium text-white/60 hover:text-white bg-white/[0.03] hover:bg-white/[0.07] border border-white/10 hover:border-white/20 rounded-xl px-3.5 py-2"
    >
      <span className="text-[#a5b4fc]">{icon}</span>
      {label}
    </button>
  )
}

function CreateModal({ onClose, onCreate, loading }: {
  onClose: () => void
  onCreate: (name: string, desc: string) => void
  loading: boolean
}) {
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')

  return (
    <Modal onClose={onClose} title="New Workflow" subtitle="Create an AI bot or agent">
      <div className="space-y-4">
        <div>
          <FieldLabel>Name *</FieldLabel>
          <Input
            autoFocus
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && name.trim() && onCreate(name.trim(), desc.trim())}
            placeholder="Support Bot, FAQ Agent…"
          />
        </div>
        <div>
          <FieldLabel>Description (optional)</FieldLabel>
          <Textarea
            value={desc}
            onChange={e => setDesc(e.target.value)}
            placeholder="What does this bot do?"
            rows={2}
          />
        </div>
        <div className="flex gap-2.5 pt-1">
          <Button variant="secondary" className="flex-1" onClick={onClose}>Cancel</Button>
          <Button
            className="flex-1"
            loading={loading}
            disabled={!name.trim()}
            onClick={() => name.trim() && onCreate(name.trim(), desc.trim())}
          >
            Create
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function DashboardPage() {
  return (
    <Suspense fallback={null}>
      <DashboardPageInner />
    </Suspense>
  )
}

function DashboardPageInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const searchQuery = (searchParams.get('q') || '').trim().toLowerCase()
  const qc = useQueryClient()
  const { toast } = useToast()
  const [showCreate, setShowCreate] = useState(false)
  const [searchInput, setSearchInput] = useState(searchParams.get('q') || '')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')

  // Keep the search box in sync if the ?q= param changes elsewhere
  // (e.g. the top bar's own search trigger).
  useEffect(() => {
    setSearchInput(searchParams.get('q') || '')
  }, [searchParams])

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('tb_token')) {
      router.replace('/login')
    }
  }, [router])

  const { data: workflows = [], isLoading, error, refetch } = useQuery({
    queryKey: ['workflows'],
    queryFn: workflowsApi.list,
    retry: 2,
    retryDelay: 1000,
  })

  const createMutation = useMutation({
    mutationFn: ({ name, desc }: { name: string; desc: string }) =>
      workflowsApi.create(name, desc),
    onSuccess: wf => {
      qc.invalidateQueries({ queryKey: ['workflows'] })
      setShowCreate(false)
      router.push(`/builder/${wf.id}`)
    },
    onError: err => toast('error', getErrorMessage(err, 'Could not create the workflow.')),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => workflowsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['workflows'] })
      toast('success', 'Workflow deleted.')
    },
    onError: err => toast('error', getErrorMessage(err, 'Could not delete the workflow.')),
  })

  const duplicateMutation = useMutation({
    mutationFn: (id: string) => workflowsApi.duplicate(id),
    onSuccess: wf => {
      qc.invalidateQueries({ queryKey: ['workflows'] })
      router.push(`/builder/${wf.id}`)
    },
    onError: err => toast('error', getErrorMessage(err, 'Could not duplicate the workflow.')),
  })

  const allWorkflows = workflows as WorkflowListItem[]
  const searched = searchQuery
    ? allWorkflows.filter(w =>
        w.name.toLowerCase().includes(searchQuery) ||
        (w.description || '').toLowerCase().includes(searchQuery)
      )
    : allWorkflows
  const published = searched.filter(w => w.status === 'published').length
  const drafts    = searched.length - published

  const wfList = useMemo(() => {
    if (statusFilter === 'all') return searched
    if (statusFilter === 'published') return searched.filter(w => w.status === 'published')
    return searched.filter(w => w.status !== 'published')
  }, [searched, statusFilter])

  const submitSearch = (e?: React.FormEvent) => {
    e?.preventDefault()
    const q = searchInput.trim()
    router.push(q ? `/dashboard?q=${encodeURIComponent(q)}` : '/dashboard')
  }

  const clearSearch = () => {
    setSearchInput('')
    router.push('/dashboard')
  }

  return (
    <div className="tb2-shell">
      <TopBar
        right={
          <>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => router.push('/create-with-ai')}
              icon={<Wand2 size={14} />}
            >
              Create with AI
            </Button>
            <Button size="sm" onClick={() => setShowCreate(true)} icon={<Plus size={14} />} data-tutorial="dashboard-new-workflow">
              New Workflow
            </Button>
          </>
        }
      />

      <main className="max-w-[1600px] mx-auto px-6 md:px-10 py-8 md:py-10 w-full">
        {/* ── Hero ─────────────────────────────────────────────── */}
        <Card
          hover
          className="tb2-rise mb-8 relative overflow-hidden cursor-pointer border-[#6366f1]/25 bg-gradient-to-r from-[#6366f1]/[0.08] to-transparent p-6 sm:p-7"
          onClick={() => router.push('/create-with-ai')}
        >
          <span className="tb2-glow-blob -top-10 -right-10 w-40 h-40 bg-[#6366f1]/25" />
          <span className="tb2-glow-blob -bottom-16 left-1/3 w-32 h-32 bg-cyan-400/10" />
          <div className="relative flex flex-col sm:flex-row sm:items-center gap-5">
            <div className="w-12 h-12 sm:w-14 sm:h-14 rounded-2xl bg-[#6366f1]/15 border border-[#6366f1]/25 flex items-center justify-center flex-shrink-0 animate-glow-pulse">
              <Sparkles size={20} className="text-[#a5b4fc]" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-base sm:text-lg font-bold text-white/95 tracking-tight">Create with AI</p>
              <p className="text-xs sm:text-[13px] text-white/40 mt-1 max-w-lg">
                Describe your chatbot in plain English and generate a complete workflow instantly.
              </p>
            </div>
            <Button
              icon={<Wand2 size={14} />}
              className="self-start sm:self-auto flex-shrink-0"
              onClick={e => { e.stopPropagation(); router.push('/create-with-ai') }}
            >
              Generate
            </Button>
          </div>
        </Card>

        {/* ── Quick actions ────────────────────────────────────── */}
        <div className="tb2-rise mb-8 flex items-center gap-2.5 overflow-x-auto pb-1 -mx-1 px-1" style={{ animationDelay: '40ms' }} data-tutorial="dashboard-quick-actions">
          <QuickAction icon={<Plus size={13} />} label="New Workflow" onClick={() => setShowCreate(true)} />
          <QuickAction icon={<Wand2 size={13} />} label="Create with AI" onClick={() => router.push('/create-with-ai')} />
          <QuickAction icon={<Store size={13} />} label="Marketplace" onClick={() => router.push('/marketplace')} />
          <QuickAction icon={<MessageCircle size={13} />} label="WhatsApp" onClick={() => router.push('/whatsapp')} />
          <QuickAction icon={<Instagram size={13} />} label="Instagram" onClick={() => router.push('/instagram')} />
          <QuickAction icon={<Send size={13} />} label="Telegram" onClick={() => router.push('/telegram')} />
        </div>

        {/* ── Stats ────────────────────────────────────────────── */}
        {isLoading ? (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-10">
            {Array.from({ length: 3 }).map((_, i) => (
              <Card key={i} className="p-4 flex items-center gap-3">
                <Skeleton className="w-9 h-9 rounded-xl flex-shrink-0" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-5 w-10" />
                  <Skeleton className="h-2.5 w-16" />
                </div>
              </Card>
            ))}
          </div>
        ) : searched.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-10">
            {[
              { label: 'Total Workflows', value: searched.length, icon: LayoutGrid, tone: 'text-white/80', ring: 'bg-white/[0.06] border-white/10' },
              { label: 'Live',            value: published,       icon: Rocket,     tone: 'text-emerald-400', ring: 'bg-emerald-500/10 border-emerald-500/20' },
              { label: 'Drafts',          value: drafts,          icon: PenLine,    tone: 'text-white/50', ring: 'bg-white/[0.06] border-white/10' },
            ].map((stat, i) => (
              <Card key={stat.label} hover className="tb2-rise p-4 flex items-center gap-3.5" style={{ animationDelay: `${60 + i * 40}ms` }}>
                <div className={cn('w-10 h-10 rounded-xl border flex items-center justify-center flex-shrink-0', stat.ring)}>
                  <stat.icon size={16} className={stat.tone} />
                </div>
                <div>
                  <p className={cn('text-2xl font-bold leading-none', stat.tone)}>{stat.value}</p>
                  <p className="text-[11px] text-white/25 mt-1">{stat.label}</p>
                </div>
              </Card>
            ))}
          </div>
        ) : null}

        {/* ── Header: search + filters ─────────────────────────── */}
        <div className="flex flex-col lg:flex-row lg:items-center gap-3 lg:gap-4 justify-between mb-6">
          <h1 className="text-lg font-bold text-white flex-shrink-0">Workflows</h1>

          <div className="flex flex-col sm:flex-row sm:items-center gap-2.5 lg:flex-1 lg:justify-end">
            <form onSubmit={submitSearch} className="tb2-field flex items-center gap-2 rounded-xl px-3 h-9 w-full sm:w-64 flex-shrink-0" data-tutorial="dashboard-search">
              <Search size={13} className="text-white/30 flex-shrink-0" />
              <input
                value={searchInput}
                onChange={e => setSearchInput(e.target.value)}
                placeholder="Search workflows…"
                className="bg-transparent outline-none text-xs text-white/85 placeholder:text-white/25 w-full"
              />
              {searchInput && (
                <button type="button" onClick={clearSearch} aria-label="Clear search" className="text-white/25 hover:text-white/60 transition flex-shrink-0">
                  <X size={12} />
                </button>
              )}
            </form>

            <div className="flex items-center gap-1.5 flex-shrink-0">
              {([
                ['all', 'All'],
                ['published', 'Live'],
                ['draft', 'Draft'],
              ] as [StatusFilter, string][]).map(([value, label]) => (
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
        </div>

        {searchQuery && (
          <p className="text-xs text-white/35 -mt-4 mb-6">
            Results for <span className="text-white/60">"{searchQuery}"</span>
          </p>
        )}

        {isLoading && <SkeletonGrid count={6} />}

        {error && !isLoading && (
          <ErrorState
            title="Couldn't load your workflows"
            description={getErrorMessage(error, 'Check your connection and that the backend is running.')}
            onRetry={() => refetch()}
          />
        )}

        {!isLoading && !error && searched.length === 0 && searchQuery && (
          <EmptyState
            icon={<Bot size={28} />}
            title="No matching workflows"
            description={`Nothing found for "${searchQuery}"`}
            action={
              <Button variant="secondary" onClick={clearSearch}>
                Clear search
              </Button>
            }
          />
        )}

        {!isLoading && !error && searched.length > 0 && wfList.length === 0 && (
          <EmptyState
            icon={<LayoutGrid size={28} />}
            title="No workflows match this filter"
            description="Try a different status filter to see more workflows."
            action={
              <Button variant="secondary" onClick={() => setStatusFilter('all')}>
                Show all
              </Button>
            }
          />
        )}

        {!isLoading && !error && allWorkflows.length === 0 && !searchQuery && (
          <EmptyState
            icon={<Bot size={28} />}
            title="No workflows yet"
            description="Create your first AI bot to get started"
            action={
              <div className="flex items-center gap-2.5">
                <Button onClick={() => setShowCreate(true)} icon={<Plus size={14} />}>
                  Create Workflow
                </Button>
                <Button variant="secondary" onClick={() => router.push('/create-with-ai')} icon={<Wand2 size={14} />}>
                  Create with AI
                </Button>
              </div>
            }
          />
        )}

        {wfList.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {wfList.map((wf, i) => (
              <WorkflowCard
                key={wf.id}
                workflow={wf}
                style={{ animationDelay: `${Math.min(i, 8) * 35}ms` }}
                onDelete={id => deleteMutation.mutate(id)}
                onDuplicate={id => duplicateMutation.mutate(id)}
              />
            ))}
          </div>
        )}
      </main>

      <Footer />

      {showCreate && (
        <CreateModal
          onClose={() => setShowCreate(false)}
          loading={createMutation.isPending}
          onCreate={(name, desc) => createMutation.mutate({ name, desc })}
        />
      )}
    </div>
  )
}
