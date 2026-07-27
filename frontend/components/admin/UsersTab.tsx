'use client'
import { useState } from 'react'
import { Search, Trash2, ShieldCheck, UserX, UserCheck, Users as UsersIcon } from 'lucide-react'
import { Card, Badge } from '@/components/ui/Card'
import { Input } from '@/components/ui/Field'
import { IconButton } from '@/components/ui/Button'
import { SkeletonRows, EmptyState, ErrorState } from '@/components/ui/States'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/lib/utils/errors'
import { useAdminUsers, useSetUserStatus, useDeleteUser } from '@/hooks/useAdmin'

export default function UsersTab() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const { toast } = useToast()

  const { data, isLoading, error, refetch } = useAdminUsers(search, page)
  const setStatus = useSetUserStatus()
  const deleteUser = useDeleteUser()

  const users = data?.users ?? []
  const total = data?.total ?? 0
  const pageSize = data?.page_size ?? 20
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="space-y-4">
      <div className="relative max-w-xs">
        <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/25" />
        <Input
          placeholder="Search users by name or email…"
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(1) }}
          className="pl-9"
        />
      </div>

      {isLoading && <SkeletonRows count={6} />}

      {error && !isLoading && (
        <ErrorState title="Couldn't load users" description={getErrorMessage(error)} onRetry={() => refetch()} />
      )}

      {!isLoading && !error && users.length === 0 && (
        <EmptyState icon={<UsersIcon size={24} />} title="No users found" description={search ? 'Try a different search.' : 'No users on the platform yet.'} />
      )}

      {!isLoading && !error && users.length > 0 && (
        <Card className="p-1.5">
          <div className="divide-y divide-white/[0.05]">
            {users.map(u => (
              <div key={u.id} className="flex items-center gap-3 px-3.5 py-3">
                <div className="w-8 h-8 rounded-lg tb2-brand-mark flex items-center justify-center flex-shrink-0 text-[11px] font-bold text-[#a5b4fc] uppercase">
                  {(u.name || u.email || '?').slice(0, 2)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-white/85 truncate">{u.name || u.email || 'Unknown user'}</p>
                    {u.is_admin && (
                      <Badge tone="accent"><ShieldCheck size={9} className="mr-0.5" />Admin</Badge>
                    )}
                    {!u.is_active && <Badge tone="danger">Disabled</Badge>}
                  </div>
                  <p className="text-[11px] text-white/30 truncate">{u.email}</p>
                </div>
                <p className="text-[10px] text-white/20 hidden sm:block flex-shrink-0">
                  {u.created_at ? new Date(u.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}
                </p>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <IconButton
                    aria-label={u.is_active ? 'Disable user' : 'Enable user'}
                    className={u.is_active ? 'hover:text-amber-400 hover:bg-amber-500/10' : 'hover:text-emerald-400 hover:bg-emerald-500/10'}
                    onClick={() => {
                      setStatus.mutate(
                        { userId: u.id, isActive: !u.is_active },
                        {
                          onSuccess: () => toast('success', u.is_active ? 'User disabled.' : 'User enabled.'),
                          onError: err => toast('error', getErrorMessage(err, 'Could not update user status.')),
                        }
                      )
                    }}
                  >
                    {u.is_active ? <UserX size={13} /> : <UserCheck size={13} />}
                  </IconButton>
                  <IconButton
                    aria-label="Delete user"
                    variant="danger"
                    onClick={() => {
                      if (window.confirm(`Delete "${u.name}"? This removes all of their bots and data — this cannot be undone.`)) {
                        deleteUser.mutate(u.id, {
                          onSuccess: () => toast('success', 'User deleted.'),
                          onError: err => toast('error', getErrorMessage(err, 'Could not delete user.')),
                        })
                      }
                    }}
                  >
                    <Trash2 size={13} />
                  </IconButton>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-white/30 px-1">
          <span>Page {page} of {totalPages} · {total} users</span>
          <div className="flex gap-2">
            <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="disabled:opacity-30 hover:text-white/70">Prev</button>
            <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} className="disabled:opacity-30 hover:text-white/70">Next</button>
          </div>
        </div>
      )}
    </div>
  )
}
