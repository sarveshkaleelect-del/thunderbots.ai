'use client'
import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import { Card } from '@/components/ui/Card'
import type { FAQEntry } from '@/lib/data/helpCenter'

function FAQItem({
  faq,
  open,
  onToggle,
}: {
  faq: FAQEntry
  open: boolean
  onToggle: () => void
}) {
  return (
    <Card className="overflow-hidden">
      <button
        onClick={onToggle}
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-3 p-4 text-left"
      >
        <span className="text-sm font-semibold text-white/85">{faq.question}</span>
        <ChevronDown
          size={15}
          className={cn('text-white/35 flex-shrink-0 transition-transform duration-200', open && 'rotate-180 text-cyan-300')}
        />
      </button>
      <div
        className={cn(
          'grid transition-all duration-200 ease-out',
          open ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'
        )}
      >
        <div className="overflow-hidden">
          <p className="px-4 pb-4 text-[13px] leading-relaxed text-white/45">{faq.answer}</p>
        </div>
      </div>
    </Card>
  )
}

/** Data-driven FAQ list with per-item expand/collapse and an "expand/collapse all" control. */
export function FAQAccordion({ faqs }: { faqs: FAQEntry[] }) {
  const [openIds, setOpenIds] = useState<Set<string>>(new Set())
  const allOpen = faqs.length > 0 && faqs.every(f => openIds.has(f.id))

  const toggle = (id: string) => {
    setOpenIds(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    setOpenIds(allOpen ? new Set() : new Set(faqs.map(f => f.id)))
  }

  if (faqs.length === 0) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-white/40">No FAQs match your search.</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button
          onClick={toggleAll}
          className="text-[11px] font-semibold text-white/35 hover:text-cyan-300 transition-colors"
        >
          {allOpen ? 'Collapse all' : 'Expand all'}
        </button>
      </div>
      {faqs.map(faq => (
        <FAQItem key={faq.id} faq={faq} open={openIds.has(faq.id)} onToggle={() => toggle(faq.id)} />
      ))}
    </div>
  )
}
