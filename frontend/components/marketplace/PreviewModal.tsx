'use client'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Loader2 } from 'lucide-react'
import { Modal } from '@/components/ui/Modal'
import { Badge, Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { TemplateIcon } from './icons'
import { marketplaceApi } from '@/lib/marketplace/api'
import type { MarketplaceTemplate } from '@/lib/marketplace/types'

function nodeLabel(n: any): string {
  const t = n?.type as string
  if (t === 'start') return `Start · "${n.data?.welcomeMessage ?? ''}"`
  if (t === 'multiple_choice') return `Menu · ${n.data?.choices?.length ?? 0} options`
  if (t === 'ai_agent') return 'AI Agent · replies using GPT'
  if (t === 'end') return `End · "${n.data?.message ?? ''}"`
  return t ?? 'Node'
}

export function PreviewModal({
  template,
  onClose,
  onUse,
  using,
}: {
  template: MarketplaceTemplate
  onClose: () => void
  onUse: (t: MarketplaceTemplate) => void
  using: boolean
}) {
  const { data, isLoading } = useQuery({
    queryKey: ['marketplace-template-detail', template.id],
    queryFn: () => marketplaceApi.templateDetail(template.id),
  })

  return (
    <Modal onClose={onClose} maxWidth="max-w-lg" title={template.name} subtitle={template.industry}>
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <Badge tone="accent">{template.difficulty}</Badge>
        <Badge tone="default">{template.setup_time} setup</Badge>
        {template.featured && <Badge tone="cyan">Featured</Badge>}
      </div>

      <p className="text-xs text-white/45 leading-relaxed mb-5">{template.description}</p>

      <p className="text-[10px] font-semibold text-white/40 uppercase tracking-wider mb-2">
        Features included
      </p>
      <div className="flex flex-wrap gap-1.5 mb-5">
        {template.features.map(f => (
          <span key={f} className="text-[10px] px-2.5 py-1 rounded-full bg-white/[0.04] border border-white/10 text-white/50">
            {f}
          </span>
        ))}
      </div>

      <p className="text-[10px] font-semibold text-white/40 uppercase tracking-wider mb-2">
        Workflow preview
      </p>
      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 size={18} className="text-[#818cf8] animate-spin" />
        </div>
      ) : (
        <div className="space-y-1.5 mb-6">
          {(data?.preview_nodes ?? []).map((n: any, i: number, arr: any[]) => (
            <div key={n.id} className="flex items-center gap-2">
              <Card className="flex-1 px-3 py-2 flex items-center gap-2">
                <TemplateIcon name={template.icon} size={12} className="text-[#a5b4fc] flex-shrink-0" />
                <span className="text-[11px] text-white/60 truncate">{nodeLabel(n)}</span>
              </Card>
              {i < arr.length - 1 && <ArrowRight size={12} className="text-white/15 flex-shrink-0" />}
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2.5">
        <Button variant="secondary" className="flex-1" onClick={onClose}>Close</Button>
        <Button className="flex-1" loading={using} onClick={() => onUse(template)}>
          Use Template
        </Button>
      </div>
    </Modal>
  )
}
