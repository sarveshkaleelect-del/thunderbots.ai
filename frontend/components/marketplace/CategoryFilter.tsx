'use client'
import { cn } from '@/lib/utils/cn'

export function CategoryFilter({
  categories,
  active,
  onChange,
}: {
  categories: string[]
  active: string | null
  onChange: (c: string | null) => void
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <button
        onClick={() => onChange(null)}
        className={cn(
          'text-xs font-medium px-3.5 py-1.5 rounded-full border transition whitespace-nowrap',
          active === null
            ? 'bg-[#6366f1]/15 border-[#6366f1]/30 text-[#a5b4fc]'
            : 'bg-white/[0.03] border-white/10 text-white/40 hover:text-white/70 hover:border-white/20'
        )}
      >
        All
      </button>
      {categories.map(c => (
        <button
          key={c}
          onClick={() => onChange(c)}
          className={cn(
            'text-xs font-medium px-3.5 py-1.5 rounded-full border transition whitespace-nowrap',
            active === c
              ? 'bg-[#6366f1]/15 border-[#6366f1]/30 text-[#a5b4fc]'
              : 'bg-white/[0.03] border-white/10 text-white/40 hover:text-white/70 hover:border-white/20'
          )}
        >
          {c}
        </button>
      ))}
    </div>
  )
}
