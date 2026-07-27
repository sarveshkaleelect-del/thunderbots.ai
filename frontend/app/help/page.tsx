'use client'
import { useMemo, useState } from 'react'
import Link from 'next/link'
import { ChevronRight, HelpCircle } from 'lucide-react'
import { SubPageBar } from '@/components/ui/TopBar'
import { Footer } from '@/components/ui/Footer'
import { HelpSearch } from '@/components/help/HelpSearch'
import { CategoryGrid } from '@/components/help/CategoryGrid'
import { QuickStartGuide } from '@/components/help/QuickStartGuide'
import { HelpActions } from '@/components/help/HelpActions'
import { CATEGORIES, searchFAQs } from '@/lib/data/helpCenter'

export default function HelpCenterPage() {
  const [query, setQuery] = useState('')
  const results = useMemo(() => (query.trim() ? searchFAQs(query) : []), [query])

  return (
    <div className="tb2-shell flex flex-col min-h-screen">
      <SubPageBar backHref="/dashboard" crumb="Help Center" crumbIcon={<HelpCircle size={13} />} />

      <div className="flex-1 max-w-5xl w-full mx-auto px-6 py-10 space-y-10">
        <div className="space-y-4 tb2-rise">
          <h1 className="text-xl font-bold text-white">How can we help?</h1>
          <p className="text-sm text-white/40 max-w-lg">
            Search our FAQs, browse a category, or reach out to the team directly.
          </p>
          <div className="max-w-lg">
            <HelpSearch value={query} onChange={setQuery} />
          </div>

          {query.trim() && (
            <div className="max-w-lg pt-2 space-y-2">
              {results.length === 0 && <p className="text-xs text-white/30">No FAQs match "{query}".</p>}
              {results.slice(0, 5).map(r => (
                <Link
                  key={r.id}
                  href={`/help/faq?q=${encodeURIComponent(query)}`}
                  className="tb2-glass tb2-glass-hover flex items-center justify-between gap-3 p-3 rounded-xl group"
                >
                  <span className="text-[13px] text-white/70 truncate">{r.question}</span>
                  <ChevronRight size={13} className="text-white/25 group-hover:text-cyan-300 transition-colors flex-shrink-0" />
                </Link>
              ))}
              {results.length > 5 && (
                <Link href={`/help/faq?q=${encodeURIComponent(query)}`} className="text-[11px] text-[#818cf8] hover:text-cyan-300 hover:underline">
                  View all {results.length} results →
                </Link>
              )}
            </div>
          )}
        </div>

        <div>
          <h2 className="text-sm font-bold text-white/70 mb-3">Browse by category</h2>
          <CategoryGrid categories={CATEGORIES} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <QuickStartGuide />
          <div className="space-y-3">
            <h2 className="text-sm font-bold text-white/70">Still need help?</h2>
            <p className="text-[12px] text-white/35 max-w-sm">
              Can't find what you're looking for? Contact support, report a bug, or suggest a feature.
            </p>
            <HelpActions />
          </div>
        </div>

        <div className="pt-2">
          <Link
            href="/help/faq"
            className="text-xs font-semibold text-[#818cf8] hover:text-cyan-300 hover:underline inline-flex items-center gap-1"
          >
            Browse all FAQs <ChevronRight size={12} />
          </Link>
        </div>
      </div>

      <Footer />
    </div>
  )
}
