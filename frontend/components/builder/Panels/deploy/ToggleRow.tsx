'use client'

export function ToggleRow({
  label, hint, checked, onChange,
}: {
  label: string
  hint?: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className="w-full flex items-center justify-between gap-3 py-2 group"
    >
      <div className="text-left min-w-0">
        <p className="text-xs text-white/70 group-hover:text-white/90 transition">{label}</p>
        {hint && <p className="text-[10px] text-white/25 mt-0.5">{hint}</p>}
      </div>
      <span
        className={`relative flex-shrink-0 w-8 h-[18px] rounded-full transition-colors duration-150 ${
          checked ? 'bg-[#6366f1]' : 'bg-[#2a2a2a]'
        }`}
      >
        <span
          className={`absolute top-[2px] w-[14px] h-[14px] rounded-full bg-white transition-transform duration-150 ${
            checked ? 'translate-x-[18px]' : 'translate-x-[2px]'
          }`}
        />
      </span>
    </button>
  )
}
