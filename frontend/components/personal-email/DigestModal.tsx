'use client'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Sparkles, AlertTriangle, ListChecks, Flame } from 'lucide-react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Skeleton } from '@/components/ui/States'
import { personalEmailApi } from '@/lib/api/personalEmail'
import { useToast } from '@/components/ui/Toast'

export function DigestModal({ accountId, onClose }: { accountId: string; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const { data: latest, isLoading } = useQuery({
    queryKey: ['personal-email-digest-latest', accountId],
    queryFn: () => personalEmailApi.latestDigest(accountId),
  })

  const { data: history } = useQuery({
    queryKey: ['personal-email-digest-history', accountId],
    queryFn: () => personalEmailApi.digestHistory(accountId, 7),
  })

  const generateMutation = useMutation({
    mutationFn: () => personalEmailApi.generateDigest(accountId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['personal-email-digest-latest', accountId] })
      queryClient.invalidateQueries({ queryKey: ['personal-email-digest-history', accountId] })
      toast('success', 'Digest generated.')
    },
    onError: (e: any) => toast('error', e?.response?.data?.detail || 'Digest generation failed.'),
  })

  return (
    <Modal onClose={onClose} title="Daily AI Email Digest" subtitle="A short AI summary of what's in your inbox" maxWidth="max-w-lg">
      <div className="space-y-4">
        {isLoading && <Skeleton className="h-24 w-full rounded-xl" />}

        {!isLoading && latest && (
          <div className="tb2-glass rounded-xl p-4 space-y-3">
            <p className="text-[10px] font-semibold text-white/35 uppercase tracking-wide">{latest.digest_date}</p>
            <p className="text-sm text-white/75 leading-relaxed">{latest.summary}</p>
            <div className="flex items-center gap-4 text-xs text-white/40 pt-1">
              <span className="flex items-center gap-1"><ListChecks size={13} /> {latest.total_emails} emails</span>
              <span className="flex items-center gap-1"><Flame size={13} /> {latest.high_priority_count} high priority</span>
              <span>{latest.action_required_count} need action</span>
            </div>
          </div>
        )}

        {!isLoading && !latest && (
          <div className="flex flex-col items-center text-center py-8 gap-2">
            <AlertTriangle size={18} className="text-white/20" />
            <p className="text-sm text-white/40">No digest yet for this account.</p>
          </div>
        )}

        <Button size="sm" icon={<Sparkles size={13} />} loading={generateMutation.isPending} onClick={() => generateMutation.mutate()}>
          Generate today's digest
        </Button>

        {history && history.length > 1 && (
          <div className="pt-2 border-t border-white/[0.06] space-y-2">
            <p className="text-[10px] font-semibold text-white/35 uppercase tracking-wide">History</p>
            {history.slice(1).map(d => (
              <div key={d.id} className="text-xs text-white/40 flex items-center justify-between gap-2">
                <span>{d.digest_date}</span>
                <span className="truncate ml-2 text-white/30">{d.total_emails} emails · {d.high_priority_count} high priority</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </Modal>
  )
}
