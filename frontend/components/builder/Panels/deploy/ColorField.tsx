'use client'

export function ColorField({
  label, value, onChange, allowNull, onClear,
}: {
  label: string
  value: string | null | undefined
  onChange: (hex: string) => void
  allowNull?: boolean
  onClear?: () => void
}) {
  const hex = value || '#000000'
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <label className="text-[10px] font-semibold text-white/35 uppercase tracking-wider">{label}</label>
        {allowNull && value && (
          <button onClick={onClear} className="text-[10px] text-white/25 hover:text-white/60 transition">Clear</button>
        )}
      </div>
      <div className="flex items-center gap-2 bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg px-2 py-1.5 tb-hover-lift">
        <div className="relative w-6 h-6 rounded-md overflow-hidden flex-shrink-0 border border-[#333]">
          <input
            type="color"
            value={hex}
            onChange={(e) => onChange(e.target.value)}
            className="absolute -top-1 -left-1 w-8 h-8 cursor-pointer border-none p-0"
          />
        </div>
        <input
          type="text"
          value={hex}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
          className="flex-1 min-w-0 bg-transparent text-xs text-white/60 font-mono outline-none"
        />
      </div>
    </div>
  )
}
