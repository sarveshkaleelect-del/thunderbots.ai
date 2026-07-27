'use client'
import { useState } from 'react'
import {
  Search, Download, ScrollText, CheckCircle2, XCircle, ChevronLeft, ChevronRight, X,
} from 'lucide-react'
import { Card, Badge } from '@/components/ui/Card'
import { Input, Select } from '@/components/ui/Field'
import { Button } from '@/components/ui/Button'
import { SkeletonRows, EmptyState, ErrorState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/lib/utils/errors'
import { useAuditLogs, useAuditLogActions, useAuditLogResourceTypes } from '@/hooks/useAuditLog'
import { auditLogApi } from '@/lib/api/audit'
import type { AuditLogEntry } from '@/types/admin'

function formatAction(action: string) {
  // "auth.login" -> "Auth · Login"
  const [resource, ...rest] = action.split('.')
  const verb = rest.join(' ').replace(/_/g, ' ')
  return `${resource} · ${verb}`
}

function formatDate(iso: string | null) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
  })
}

function DetailDrawer({ entry, onClose }: { entry: AuditLogEntry; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-end bg-black/50" onClick={onClose}>
      <div
        className="w-full max-w-md h-full overflow-y-auto tb2-glass border-l border-white/10 p-5 space-y-4"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white/85">Audit Log Entry</h3>
          <button onClick={onClose} className="text-white/40 hover:text-white/80">
            <X size={16} />
          </button>
        </div>

        <div className="space-y-3 text-xs">
          <Row label="Action" value={formatAction(entry.action)} />
          <Row label="Status">
            <Badge tone={entry.status === 'success' ? 'success' : 'danger'}>{entry.status}</Badge>
          </Row>
          {entry.status_detail && <Row label="Detail" value={entry.status_detail} />}
          <Row label="Actor" value={entry.actor_name || entry.actor_email || 'Unknown'} />
          {entry.actor_email && <Row label="Actor email" value={entry.actor_email} />}
          <Row label="Actor type" value={entry.actor_type} />
          <Row label="Resource" value={entry.resource_type} />
          {entry.target_label && <Row label="Target" value={entry.target_label} />}
          {entry.target_type && <Row label="Target type" value={entry.target_type} />}
          {entry.target_id && <Row label="Target ID" value={entry.target_id} mono />}
          <Row label="IP address" value={entry.ip_address || '—'} mono />
          <Row label="Request ID" value={entry.request_id} mono />
          <Row label="Timestamp" value={formatDate(entry.created_at)} />
          {entry.user_agent && <Row label="User agent" value={entry.user_agent} />}
          {Object.keys(entry.metadata || {}).length > 0 && (
            <div>
              <p className="text-white/30 uppercase tracking-wider text-[10px] font-semibold mb-1.5">Metadata</p>
              <pre className="tb2-field rounded-xl p-3 text-[11px] text-white/60 overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(entry.metadata, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Row({ label, value, mono, children }: { label: string; value?: string; mono?: boolean; children?: React.ReactNode }) {
  return (
    <div>
      <p className="text-white/30 uppercase tracking-wider text-[10px] font-semibold mb-0.5">{label}</p>
      {children ?? <p className={mono ? 'text-white/70 font-mono text-[11px] break-all' : 'text-white/70'}>{value}</p>}
    </div>
  )
}

export default function AuditLogTab() {
  const [search, setSearch] = useState('')
  const [action, setAction] = useState('')
  const [resourceType, setResourceType] = useState('')
  const [statusFilter, setStatusFilter] = useState<'' | 'success' | 'failure'>('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<AuditLogEntry | null>(null)
  const [exporting, setExporting] = useState(false)
  const { toast } = useToast()

  const filters = {
    search,
    action: action || undefined,
    resource_type: resourceType || undefined,
    status: statusFilter || undefined,
    date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
    date_to: dateTo ? new Date(dateTo).toISOString() : undefined,
    page,
    page_size: 25,
  }

  const { data, isLoading, error, refetch } = useAuditLogs(filters)
  const { data: actions = [] } = useAuditLogActions()
  const { data: resourceTypes = [] } = useAuditLogResourceTypes()

  const logs = data?.logs ?? []
  const total = data?.total ?? 0
  const pageSize = data?.page_size ?? 25
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const resetPage = () => setPage(1)

  const handleExport = async () => {
    setExporting(true)
    try {
      await auditLogApi.exportCsv(filters)
      toast('success', 'Audit log exported.')
    } catch (err) {
      toast('error', getErrorMessage(err, 'Could not export audit log.'))
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/25" />
          <Input
            placeholder="Search actor, action, target, IP…"
            value={search}
            onChange={e => { setSearch(e.target.value); resetPage() }}
            className="pl-9"
          />
        </div>

        <Select value={action} onChange={e => { setAction(e.target.value); resetPage() }} className="max-w-[200px]">
          <option value="">All actions</option>
          {actions.map(a => (
            <option key={a} value={a}>{formatAction(a)}</option>
          ))}
        </Select>

        <Select value={resourceType} onChange={e => { setResourceType(e.target.value); resetPage() }} className="max-w-[160px]">
          <option value="">All resources</option>
          {resourceTypes.map(r => (
            <option key={r} value={r}>{r}</option>
          ))}
        </Select>

        <Select value={statusFilter} onChange={e => { setStatusFilter(e.target.value as any); resetPage() }} className="max-w-[140px]">
          <option value="">Any status</option>
          <option value="success">Success</option>
          <option value="failure">Failure</option>
        </Select>

        <Input type="date" value={dateFrom} onChange={e => { setDateFrom(e.target.value); resetPage() }} className="max-w-[150px]" />
        <Input type="date" value={dateTo} onChange={e => { setDateTo(e.target.value); resetPage() }} className="max-w-[150px]" />

        <Button variant="secondary" size="sm" icon={<Download size={13} />} loading={exporting} onClick={handleExport}>
          Export CSV
        </Button>
      </div>

      {isLoading && <SkeletonRows count={8} />}

      {error && !isLoading && (
        <ErrorState title="Couldn't load audit logs" description={getErrorMessage(error)} onRetry={() => refetch()} />
      )}

      {!isLoading && !error && logs.length === 0 && (
        <EmptyState
          icon={<ScrollText size={24} />}
          title="No audit log entries found"
          description={search || action || resourceType || statusFilter ? 'Try different filters.' : 'No activity has been recorded yet.'}
        />
      )}

      {!isLoading && !error && logs.length > 0 && (
        <Card className="p-1.5">
          <div className="divide-y divide-white/[0.05]">
            {logs.map(entry => (
              <button
                key={entry.id}
                onClick={() => setSelected(entry)}
                className="w-full flex items-center gap-3 px-3.5 py-3 text-left hover:bg-white/[0.03] transition-colors"
              >
                <div className="flex-shrink-0">
                  {entry.status === 'success' ? (
                    <CheckCircle2 size={15} className="text-emerald-400" />
                  ) : (
                    <XCircle size={15} className="text-red-400" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-white/85 truncate">{formatAction(entry.action)}</p>
                    {entry.actor_type === 'admin' && <Badge tone="accent">Admin</Badge>}
                  </div>
                  <p className="text-[11px] text-white/30 truncate">
                    {entry.actor_email || entry.actor_name || 'Unknown actor'}
                    {entry.target_label ? ` → ${entry.target_label}` : ''}
                  </p>
                </div>
                <p className="text-[10px] text-white/25 hidden sm:block flex-shrink-0 font-mono">{entry.ip_address || '—'}</p>
                <p className="text-[10px] text-white/20 flex-shrink-0">{formatDate(entry.created_at)}</p>
              </button>
            ))}
          </div>
        </Card>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-white/30 px-1">
          <span>Page {page} of {totalPages} · {total} entries</span>
          <div className="flex items-center gap-2">
            <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="disabled:opacity-30 hover:text-white/70 flex items-center gap-1">
              <ChevronLeft size={12} /> Prev
            </button>
            <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} className="disabled:opacity-30 hover:text-white/70 flex items-center gap-1">
              Next <ChevronRight size={12} />
            </button>
          </div>
        </div>
      )}

      {selected && <DetailDrawer entry={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
