'use client'
import { Suspense, useMemo, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { HelpCircle } from 'lucide-react'
import { SubPageBar } from '@/components/ui/TopBar'
import { Footer } from '@/components/ui/Footer'
import { PageLoader } from '@/components/ui/States'
import { cn } from '@/lib/utils/cn'
import { HelpSearch } from '@/components/help/HelpSearch'
import { FAQAccordion } from '@/components/help/FAQAccordion'
import { CATEGORIES, searchFAQs } from '@/lib/data/helpCenter'

function FAQPageInner() {
  const searchParams = useSearchParams()
  const [query, setQuery] = useState(searchParams.get('q') || '')
  const [categoryId, setCategoryId] = useState<string | undefined>(searchParams.get('category') || undefined)

  const results = useMemo(() => searchFAQs(query, categoryId), [query, categoryId])

  return (
    <div className="tb2-shell flex flex-col min-h-screen">
      <SubPageBar backHref="/help" crumb="FAQ" crumbIcon={<HelpCircle size={13} />} />

      <div className="flex-1 max-w-3xl w-full mx-auto px-6 py-10 space-y-6">
        <h1 className="text-xl font-bold text-white tb2-rise">Frequently Asked Questions</h1>

        <HelpSearch value={query} onChange={setQuery} />

        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setCategoryId(undefined)}
            className={cn(
              'text-[11px] font-semibold px-3 py-1.5 rounded-full border transition-colors',
              !categoryId
                ? 'bg-[#6366f1]/15 border-[#6366f1]/30 text-[#a5b4fc]'
                : 'bg-white/[0.03] border-white/10 text-white/40 hover:text-white/70'
            )}
          >
            All
          </button>
          {CATEGORIES.map(cat => (
            <button
              key={cat.id}
              onClick={() => setCategoryId(cat.id)}
              className={cn(
                'text-[11px] font-semibold px-3 py-1.5 rounded-full border transition-colors',
                categoryId === cat.id
                  ? 'bg-[#6366f1]/15 border-[#6366f1]/30 text-[#a5b4fc]'
                  : 'bg-white/[0.03] border-white/10 text-white/40 hover:text-white/70'
              )}
            >
              {cat.label}
            </button>
          ))}
        </div>

        <p className="text-[11px] text-white/25">
          {results.length} {results.length === 1 ? 'result' : 'results'}
        </p>

        <FAQAccordion faqs={results} />
      </div>

      <Footer />
    </div>
  )
}

export default function FAQPage() {
  return (
    <Suspense fallback={<PageLoader />}>
      <FAQPageInner />
    </Suspense>
  )
}
