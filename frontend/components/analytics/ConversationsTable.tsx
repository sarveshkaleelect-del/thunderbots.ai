'use client'
import { memo, useState, useCallback } from 'react'
import {
  Search, Loader2, Download, ChevronLeft, ChevronRight, Star,
  RotateCcw, X, Bot, User as UserIcon, AlertCircle,
} from 'lucide-react'
import { useConversations, useConversationDetail } from '@/hooks/useAnalytics'
import { analyticsApi } from '@/lib/api/analytics'
import type { ConversationFilters, ConversationListItem } from '@/types/analytics'
import { cn } from '@/lib/utils/cn'

const SOURCE_OPTIONS = [
  { value: '', label: 'All sources' },
  { value: 'website', label: 'Website' },
  { value: 'embed_widget', label: 'Embed Widget' },
  { value: 'direct', label: 'Direct' },
  { value: 'api', label: 'API' },
  { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'telegram', label: 'Telegram' },
]

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'active', label: 'Active' },
  { value: 'ended', label: 'Ended' },
]

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function ConversationDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const { data, isLoading } = useConversationDetail(id)

  const handoffBadge = () => {
    const status = data?.handoff_status
    if (!status || status === 'ai') return null
    const label = status === 'waiting' ? 'Waiting for agent'
      : status === 'active' ? `Human agent${data?.assigned_agent_name ? ` · ${data.assigned_agent_name}` : ''}`
      : status === 'paused' ? 'AI paused'
      : status === 'closed' ? 'Handoff closed'
      : status
    const tone = status === 'active' ? 'bg-[#6366f1]/15 text-[#a5b4fc] border-[#6366f1]/25'
      : status === 'waiting' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
      : 'bg-white/5 text-white/40 border-white/10'
    return (
      <span className={cn('inline-flex items-center text-[9px] px-2 py-0.5 rounded-full uppercase font-medium border', tone)}>
        {label}
      </span>
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg h-full bg-[#0b0b0b] border-l border-[#1a1a1a] flex flex-col animate-slide-up">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#1a1a1a] flex-shrink-0">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white/90 truncate">
              {data?.workflow_name || 'Conversation'}
            </p>
            <p className="text-[10px] text-white/25 truncate">{data?.session_id}</p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {handoffBadge()}
            <button onClick={onClose} className="p-1.5 text-white/30 hover:text-white/70 rounded-lg hover:bg-white/5">
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {isLoading && (
            <div className="flex items-center justify-center py-16">
              <Loader2 size={20} className="text-[#6366f1] animate-spin" />
            </div>
          )}
          {data && (
            <div className="space-y-4">
              {data.satisfaction_rating && (
                <div className="flex items-center gap-1 text-amber-400">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Star key={i} size={12} fill={i < data.satisfaction_rating! ? 'currentColor' : 'none'} />
                  ))}
                </div>
              )}
              {data.messages.map(m => (
                <div key={m.id} className={cn('flex gap-2.5', m.role === 'user' && 'flex-row-reverse')}>
                  <div className={cn(
                    'w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0',
                    m.is_error ? 'bg-rose-500/10' : m.role === 'bot' ? 'bg-[#6366f1]/10' : 'bg-white/5'
                  )}>
                    {m.is_error
                      ? <AlertCircle size={12} className="text-rose-400" />
                      : m.role === 'bot'
                        ? <Bot size={12} className="text-[#818cf8]" />
                        : <UserIcon size={12} className="text-white/40" />}
                  </div>
                  <div className={cn(
                    'max-w-[80%] rounded-2xl px-3.5 py-2.5 text-xs leading-relaxed',
                    m.role === 'user' ? 'bg-[#6366f1]/15 text-white/90' : 'bg-white/5 text-white/70'
                  )}>
                    <p className="whitespace-pre-wrap break-words">{m.content || '(empty)'}</p>
                    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                      {m.provider && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-white/30">{m.provider}</span>
                      )}
                      {m.latency_ms != null && (
                        <span className="text-[9px] text-white/20">{m.latency_ms}ms</span>
                      )}
                      <span className="text-[9px] text-white/20 ml-auto">{fmtDate(m.created_at)}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ConversationsTableImpl({
  fixedWorkflowId, fixedSource, hideSourceFilter, hideExport, title,
}: {
  // NEW (Part 3, all optional/additive): lets a channel-specific page (e.g.
  // the Telegram Settings page) embed this exact same table scoped to one
  // workflow/source, with zero behavior change for the existing,
  // unscoped Analytics Dashboard usage (<ConversationsTable /> with no
  // props keeps working exactly as before).
  fixedWorkflowId?: string
  fixedSource?: string
  hideSourceFilter?: boolean
  hideExport?: boolean
  title?: string
} = {}) {
  const [filters, setFilters] = useState<ConversationFilters>({
    page: 1, page_size: 25, workflow_id: fixedWorkflowId, source: fixedSource,
  })
  const [searchInput, setSearchInput] = useState('')
  const [openId, setOpenId] = useState<string | null>(null)
  const [exporting, setExporting] = useState<'csv' | 'json' | null>(null)

  const { data, isLoading, isFetching } = useConversations(filters)

  const applySearch = useCallback(() => {
    setFilters(f => ({ ...f, search: searchInput.trim() || undefined, page: 1 }))
  }, [searchInput])

  const updateFilter = useCallback((patch: Partial<ConversationFilters>) => {
    setFilters(f => ({ ...f, ...patch, page: 1 }))
  }, [])

  const goToPage = useCallback((page: number) => {
    setFilters(f => ({ ...f, page }))
  }, [])

  const handleExport = useCallback(async (format: 'csv' | 'json') => {
    setExporting(format)
    try {
      await analyticsApi.downloadExport(format, filters)
    } finally {
      setExporting(null)
    }
  }, [filters])

  const clearFilters = useCallback(() => {
    setSearchInput('')
    setFilters({ page: 1, page_size: 25, workflow_id: fixedWorkflowId, source: fixedSource })
  }, [fixedWorkflowId, fixedSource])

  const items = data?.items || []
  const hasClearableFilters = filters.search || (!hideSourceFilter && filters.source) || filters.status

  return (
    <div className="tb2-glass overflow-hidden">
      {/* Toolbar */}
      {title && (
        <div className="px-4 pt-4 text-xs font-semibold uppercase tracking-wider text-white/50">{title}</div>
      )}
      <div className="p-4 border-b border-[#1a1a1a] flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/25" />
          <input
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && applySearch()}
            placeholder="Search messages or session ID…"
            className="w-full bg-[#1a1a1a] text-xs text-white border border-[#2a2a2a] rounded-xl
                       pl-8 pr-3 py-2 outline-none focus:border-[#6366f1]/50 transition placeholder-white/20"
          />
        </div>

        {!hideSourceFilter && (
          <select
            value={filters.source || ''}
            onChange={e => updateFilter({ source: e.target.value || undefined })}
            className="bg-[#1a1a1a] text-xs text-white/70 border border-[#2a2a2a] rounded-xl px-3 py-2 outline-none focus:border-[#6366f1]/50"
          >
            {SOURCE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        )}

        <select
          value={filters.status || ''}
          onChange={e => updateFilter({ status: e.target.value || undefined })}
          className="bg-[#1a1a1a] text-xs text-white/70 border border-[#2a2a2a] rounded-xl px-3 py-2 outline-none focus:border-[#6366f1]/50"
        >
          {STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>

        {hasClearableFilters && (
          <button
            onClick={clearFilters}
            className="flex items-center gap-1 text-[11px] text-white/30 hover:text-white/60 px-2 py-2"
          >
            <RotateCcw size={11} /> Clear
          </button>
        )}

        {!hideExport && (
          <div className="ml-auto flex items-center gap-1.5">
            <button
              onClick={() => handleExport('csv')}
              disabled={exporting !== null}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-[#2a2a2a] text-[11px]
                         text-white/50 hover:text-white/80 hover:border-[#3a3a3a] transition disabled:opacity-40"
            >
              {exporting === 'csv' ? <Loader2 size={11} className="animate-spin" /> : <Download size={11} />} CSV
            </button>
            <button
              onClick={() => handleExport('json')}
              disabled={exporting !== null}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-[#2a2a2a] text-[11px]
                         text-white/50 hover:text-white/80 hover:border-[#3a3a3a] transition disabled:opacity-40"
            >
              {exporting === 'json' ? <Loader2 size={11} className="animate-spin" /> : <Download size={11} />} JSON
            </button>
          </div>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="text-[10px] text-white/25 uppercase tracking-wider">
              <th className="px-4 py-2.5 font-medium">Bot</th>
              <th className="px-4 py-2.5 font-medium">Source</th>
              <th className="px-4 py-2.5 font-medium">Messages</th>
              <th className="px-4 py-2.5 font-medium">Avg Response</th>
              <th className="px-4 py-2.5 font-medium">Rating</th>
              <th className="px-4 py-2.5 font-medium">Status</th>
              <th className="px-4 py-2.5 font-medium">Started</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c: ConversationListItem) => (
              <tr
                key={c.id}
                onClick={() => setOpenId(c.id)}
                className="border-t border-[#141414] hover:bg-white/[0.02] cursor-pointer transition"
              >
                <td className="px-4 py-3">
                  <p className="text-xs text-white/70 font-medium truncate max-w-[160px]">{c.workflow_name}</p>
                  {c.is_returning && <span className="text-[9px] text-sky-400/70">returning visitor</span>}
                </td>
                <td className="px-4 py-3">
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 text-white/40 capitalize">
                    {c.source.replace('_', ' ')}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-white/50 tabular-nums">
                  {c.message_count} {c.error_count > 0 && <span className="text-rose-400">({c.error_count} err)</span>}
                </td>
                <td className="px-4 py-3 text-xs text-white/50 tabular-nums">
                  {c.avg_response_time_ms ? `${Math.round(c.avg_response_time_ms)}ms` : '—'}
                </td>
                <td className="px-4 py-3">
                  {c.satisfaction_rating ? (
                    <span className="flex items-center gap-0.5 text-amber-400 text-[10px]">
                      <Star size={9} fill="currentColor" /> {c.satisfaction_rating}
                    </span>
                  ) : <span className="text-white/15 text-[10px]">—</span>}
                </td>
                <td className="px-4 py-3">
                  <span className={cn(
                    'text-[9px] px-2 py-0.5 rounded-full uppercase font-medium',
                    c.status === 'active'
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      : 'bg-white/4 text-white/25 border border-white/8'
                  )}>
                    {c.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-[11px] text-white/30 whitespace-nowrap">{fmtDate(c.started_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {isLoading && (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={18} className="text-[#6366f1] animate-spin" />
          </div>
        )}
        {!isLoading && items.length === 0 && (
          <div className="flex flex-col items-center py-16 gap-2">
            <p className="text-xs text-white/25">No conversations match these filters</p>
          </div>
        )}
      </div>

      {/* Pagination */}
      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-[#1a1a1a]">
          <p className="text-[11px] text-white/25">
            Page {data.page} of {data.total_pages} · {data.total} total {isFetching && '· refreshing…'}
          </p>
          <div className="flex items-center gap-1">
            <button
              disabled={data.page <= 1}
              onClick={() => goToPage(data.page - 1)}
              className="p-1.5 rounded-lg border border-[#2a2a2a] text-white/40 hover:text-white/70 disabled:opacity-30 disabled:cursor-not-allowed transition"
            >
              <ChevronLeft size={13} />
            </button>
            <button
              disabled={data.page >= data.total_pages}
              onClick={() => goToPage(data.page + 1)}
              className="p-1.5 rounded-lg border border-[#2a2a2a] text-white/40 hover:text-white/70 disabled:opacity-30 disabled:cursor-not-allowed transition"
            >
              <ChevronRight size={13} />
            </button>
          </div>
        </div>
      )}

      {openId && <ConversationDrawer id={openId} onClose={() => setOpenId(null)} />}
    </div>
  )
}

export const ConversationsTable = memo(ConversationsTableImpl)
