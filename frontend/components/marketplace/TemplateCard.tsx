'use client'
import { Clock, Layers, Eye, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import { Card, Badge } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { TemplateIcon } from './icons'
import type { MarketplaceTemplate } from '@/lib/marketplace/types'

const DIFFICULTY_TONE: Record<string, 'success' | 'warning' | 'danger'> = {
  Beginner: 'success',
  Intermediate: 'warning',
  Advanced: 'danger',
}

export function TemplateCard({
  template,
  style,
  onPreview,
  onUse,
  using,
}: {
  template: MarketplaceTemplate
  style?: React.CSSProperties
  onPreview: (t: MarketplaceTemplate) => void
  onUse: (t: MarketplaceTemplate) => void
  using: boolean
}) {
  return (
    <Card hover className="tb2-rise group relative overflow-hidden flex flex-col" style={style}>
      {template.featured && (
        <div className="absolute top-3 right-3 z-10">
          <Badge tone="accent" className="flex items-center gap-1">
            <Sparkles size={8} />Featured
          </Badge>
        </div>
      )}

      <div className="p-5 flex flex-col flex-1">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl tb2-brand-mark flex items-center justify-center flex-shrink-0">
            <TemplateIcon name={template.icon} size={17} className="text-[#a5b4fc]" />
          </div>
          <div className="min-w-0">
            <p className="font-semibold text-sm text-white/90 truncate">{template.name}</p>
            <p className="text-[10px] text-white/30">{template.industry}</p>
          </div>
        </div>

        <p className="text-xs text-white/45 leading-relaxed mb-4 line-clamp-2">
          {template.description}
        </p>

        <div className="flex items-center gap-3 flex-wrap mb-4">
          <Badge tone={DIFFICULTY_TONE[template.difficulty] ?? 'default'}>{template.difficulty}</Badge>
          <span className="flex items-center gap-1 text-[10px] text-white/30">
            <Clock size={9} />{template.setup_time}
          </span>
          <span className="flex items-center gap-1 text-[10px] text-white/30">
            <Layers size={9} />{template.features.length} features
          </span>
        </div>

        <div className="flex flex-wrap gap-1.5 mb-5">
          {template.features.slice(0, 3).map(f => (
            <span
              key={f}
              className="text-[9px] px-2 py-0.5 rounded-full bg-white/[0.04] border border-white/10 text-white/40"
            >
              {f}
            </span>
          ))}
          {template.features.length > 3 && (
            <span className="text-[9px] px-2 py-0.5 text-white/25">
              +{template.features.length - 3} more
            </span>
          )}
        </div>

        <div className="mt-auto flex gap-2">
          <Button
            variant="secondary"
            size="sm"
            className="flex-1"
            icon={<Eye size={12} />}
            onClick={() => onPreview(template)}
          >
            Preview
          </Button>
          <Button
            size="sm"
            className="flex-1"
            loading={using}
            onClick={() => onUse(template)}
          >
            Use Template
          </Button>
        </div>
      </div>
    </Card>
  )
}
