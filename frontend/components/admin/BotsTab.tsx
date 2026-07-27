'use client'
import { useState } from 'react'
import { Search, Trash2, Bot as BotIcon, Globe } from 'lucide-react'
import { Card, Badge } from '@/components/ui/Card'
import { Input } from '@/components/ui/Field'
import { IconButton } from '@/components/ui/Button'
import { SkeletonRows, EmptyState, ErrorState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/lib/utils/errors'
import { useAdminBots, useDeleteBot } from '@/hooks/useAdmin'

export default function BotsTab() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const { toast } = useToast()

  const { data, isLoading, error, refetch } = useAdminBots(search, page)
  const deleteBot = useDeleteBot()

  const bots = data?.bots ?? []
  const total = data?.total ?? 0
  const pageSize = data?.page_size ?? 20
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="space-y-4">
      <div className="relative max-w-xs">
        <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/25" />
        <Input
          placeholder="Search bots by name…"
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(1) }}
          className="pl-9"
        />
      </div>

      {isLoading && <SkeletonRows count={6} />}

      {error && !isLoading && (
        <ErrorState title="Couldn't load bots" description={getErrorMessage(error)} onRetry={() => refetch()} />
      )}

      {!isLoading && !error && bots.length === 0 && (
        <EmptyState icon={<BotIcon size={24} />} title="No bots found" description={search ? 'Try a different search.' : 'No bots on the platform yet.'} />
      )}

      {!isLoading && !error && bots.length > 0 && (
        <Card className="p-1.5">
          <div className="divide-y divide-white/[0.05]">
            {bots.map(b => (
              <div key={b.id} className="flex items-center gap-3 px-3.5 py-3">
                <div className="w-8 h-8 rounded-lg tb2-brand-mark flex items-center justify-center flex-shrink-0">
                  <BotIcon size={13} className="text-[#a5b4fc]" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-white/85 truncate">{b.name}</p>
                  <p className="text-[11px] text-white/30 truncate">{b.owner_email ?? 'Unknown owner'}</p>
                </div>
                <Badge tone={b.status === 'published' ? 'success' : 'default'} dot className="hidden sm:inline-flex">
                  {b.status === 'published' ? <span className="flex items-center gap-1"><Globe size={8} />Live</span> : 'Draft'}
                </Badge>
                <p className="text-[10px] text-white/20 hidden sm:block flex-shrink-0">
                  {b.created_at ? new Date(b.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}
                </p>
                <IconButton
                  aria-label="Delete bot"
                  variant="danger"
                  onClick={() => {
                    if (window.confirm(`Delete "${b.name}"? This removes its workflow, deployment, and conversation history — this cannot be undone.`)) {
                      deleteBot.mutate(b.id, {
                        onSuccess: () => toast('success', 'Bot deleted.'),
                        onError: err => toast('error', getErrorMessage(err, 'Could not delete bot.')),
                      })
                    }
                  }}
                >
                  <Trash2 size={13} />
                </IconButton>
              </div>
            ))}
          </div>
        </Card>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-white/30 px-1">
          <span>Page {page} of {totalPages} · {total} bots</span>
          <div className="flex gap-2">
            <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="disabled:opacity-30 hover:text-white/70">Prev</button>
            <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} className="disabled:opacity-30 hover:text-white/70">Next</button>
          </div>
        </div>
      )}
    </div>
  )
}
