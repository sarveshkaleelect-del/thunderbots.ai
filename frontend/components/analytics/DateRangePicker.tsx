'use client'
import { memo, useState } from 'react'
import { Calendar, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import type { DateRange } from '@/hooks/useAnalytics'

const PRESETS: { key: string; label: string }[] = [
  { key: 'today', label: 'Today' },
  { key: '7d', label: '7 days' },
  { key: '30d', label: '30 days' },
  { key: '90d', label: '90 days' },
]

interface DateRangePickerProps {
  value: DateRange
  onChange: (range: DateRange) => void
}

function DateRangePickerImpl({ value, onChange }: DateRangePickerProps) {
  const [showCustom, setShowCustom] = useState(false)
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')

  return (
    <div className="relative flex items-center gap-1 tb2-glass p-1">
      {PRESETS.map(p => (
        <button
          key={p.key}
          onClick={() => { onChange({ key: p.key }); setShowCustom(false) }}
          className={cn(
            'px-3 py-1.5 rounded-lg text-xs font-medium transition',
            value.key === p.key
              ? 'bg-[#6366f1] text-white'
              : 'text-white/40 hover:text-white/70 hover:bg-white/5'
          )}
        >
          {p.label}
        </button>
      ))}
      <button
        onClick={() => setShowCustom(v => !v)}
        className={cn(
          'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition',
          value.key === 'custom'
            ? 'bg-[#6366f1] text-white'
            : 'text-white/40 hover:text-white/70 hover:bg-white/5'
        )}
      >
        <Calendar size={11} /> Custom <ChevronDown size={10} />
      </button>

      {showCustom && (
        <div className="absolute right-0 top-full mt-2 z-30 bg-[#0f0f0f] border border-[#2a2a2a] rounded-xl p-4 shadow-2xl w-64">
          <p className="text-[10px] font-semibold text-white/35 uppercase tracking-wider mb-2">Custom range</p>
          <div className="space-y-2">
            <div>
              <label className="text-[10px] text-white/30">Start</label>
              <input
                type="date"
                value={customStart}
                onChange={e => setCustomStart(e.target.value)}
                className="w-full bg-[#1a1a1a] text-xs text-white border border-[#2a2a2a] rounded-lg px-2.5 py-1.5 outline-none focus:border-[#6366f1]/50 mt-1"
              />
            </div>
            <div>
              <label className="text-[10px] text-white/30">End</label>
              <input
                type="date"
                value={customEnd}
                onChange={e => setCustomEnd(e.target.value)}
                className="w-full bg-[#1a1a1a] text-xs text-white border border-[#2a2a2a] rounded-lg px-2.5 py-1.5 outline-none focus:border-[#6366f1]/50 mt-1"
              />
            </div>
            <button
              disabled={!customStart || !customEnd}
              onClick={() => {
                onChange({
                  key: 'custom',
                  start: new Date(customStart).toISOString(),
                  end: new Date(new Date(customEnd).getTime() + 86_399_000).toISOString(),
                })
                setShowCustom(false)
              }}
              className="w-full py-2 rounded-lg bg-[#6366f1] hover:bg-[#5558e8] text-xs text-white font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed mt-1"
            >
              Apply
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export const DateRangePicker = memo(DateRangePickerImpl)
