'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { MessageCircle, Bot, ChevronRight } from 'lucide-react'
import { workflowsApi } from '@/lib/api/workflows'
import { whatsappApi } from '@/lib/api/whatsapp'
import type { WorkflowListItem } from '@/types'
import { Badge } from '@/components/ui/Card'
import { SubPageBar } from '@/components/ui/TopBar'
import { PageLoader, EmptyState } from '@/components/ui/States'

function StatusPill({ workflowId }: { workflowId: string }) {
  const { data } = useQuery({
    queryKey: ['whatsapp-channel', workflowId],
    queryFn: () => whatsappApi.get(workflowId),
  })

  if (!data || !data.connected) {
    return <Badge tone="default">Not connected</Badge>
  }

  const isLive = data.is_enabled && data.status === 'connected'
  const tone = isLive ? 'success' : data.status === 'error' ? 'danger' : 'warning'

  return <Badge tone={tone} dot={isLive}>{isLive ? 'Live' : data.status}</Badge>
}

export default function WhatsAppIndexPage() {
  const router = useRouter()

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('tb_token')) {
      router.replace('/login')
    }
  }, [router])

  const { data: workflows = [], isLoading } = useQuery({
    queryKey: ['workflows'],
    queryFn: workflowsApi.list,
  })

  return (
    <div className="tb2-shell">
      <SubPageBar crumb="WhatsApp" crumbIcon={<MessageCircle size={13} className="text-emerald-400/70" />} />

      <div className="max-w-2xl mx-auto px-6 py-10 space-y-6">
        <div className="tb2-rise">
          <h1 className="text-xl font-bold text-white">WhatsApp Channel</h1>
          <p className="text-sm text-white/35 mt-1">
            Connect any chatbot to its own WhatsApp Business number via the Meta Cloud API.
          </p>
        </div>

        {isLoading ? (
          <PageLoader />
        ) : workflows.length === 0 ? (
          <EmptyState
            icon={<Bot size={26} />}
            title="No chatbots yet"
            description="Create one from the dashboard first."
          />
        ) : (
          <div className="space-y-2">
            {(workflows as WorkflowListItem[]).map((wf, i) => (
              <button
                key={wf.id}
                onClick={() => router.push(`/whatsapp/${wf.id}`)}
                className="tb2-row tb2-glass tb2-glass-hover w-full flex items-center gap-3 p-4 text-left group tb2-rise"
                style={{ animationDelay: `${Math.min(i, 8) * 30}ms` }}
              >
                <div className="w-9 h-9 rounded-xl tb2-brand-mark flex items-center justify-center flex-shrink-0">
                  <Bot size={16} className="text-[#a5b4fc]" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-white/85 truncate">{wf.name}</p>
                  {wf.description && (
                    <p className="text-[11px] text-white/30 truncate mt-0.5">{wf.description}</p>
                  )}
                </div>
                <StatusPill workflowId={wf.id} />
                <ChevronRight size={14} className="text-white/20 group-hover:text-cyan-300 transition-colors flex-shrink-0" />
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
