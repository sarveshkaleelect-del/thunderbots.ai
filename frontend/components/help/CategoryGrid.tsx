'use client'
import Link from 'next/link'
import { Card } from '@/components/ui/Card'
import type { HelpCategory } from '@/lib/data/helpCenter'

/** Grid of Help Center categories; each links to the FAQ page pre-filtered to that category. */
export function CategoryGrid({ categories }: { categories: HelpCategory[] }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {categories.map(cat => (
        <Link key={cat.id} href={`/help/faq?category=${cat.id}`}>
          <Card hover className="p-4 h-full flex items-start gap-3">
            <div className="w-9 h-9 rounded-xl bg-[#6366f1]/15 border border-[#6366f1]/25 flex items-center justify-center flex-shrink-0">
              <cat.icon size={16} className="text-[#a5b4fc]" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-white/85">{cat.label}</p>
              <p className="text-[11px] text-white/35 mt-0.5">{cat.description}</p>
            </div>
          </Card>
        </Link>
      ))}
    </div>
  )
}
