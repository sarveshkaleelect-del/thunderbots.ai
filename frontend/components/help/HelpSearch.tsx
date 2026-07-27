'use client'
import { Search, X } from 'lucide-react'

export function HelpSearch({
  value,
  onChange,
  placeholder = 'Search FAQs…',
}: {
  value: string
  onChange: (val: string) => void
  placeholder?: string
}) {
  return (
    <div className="relative">
      <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/25" />
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="tb2-field w-full text-sm text-white rounded-xl pl-10 pr-9 py-3 outline-none placeholder-white/25"
      />
      {value && (
        <button
          aria-label="Clear search"
          onClick={() => onChange('')}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-white/25 hover:text-white/60 transition-colors"
        >
          <X size={14} />
        </button>
      )}
    </div>
  )
}
