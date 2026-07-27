'use client'
import { forwardRef } from 'react'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils/cn'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md' | 'lg'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  icon?: React.ReactNode
}

const sizeCls: Record<Size, string> = {
  // min-h ensures a >=44px touch target on mobile without changing the
  // visible padding/typography of the button itself.
  sm: 'text-xs px-3 py-1.5 rounded-lg gap-1.5 min-h-[36px] sm:min-h-0',
  md: 'text-sm px-4 py-2.5 rounded-xl gap-2 min-h-[44px] sm:min-h-0',
  lg: 'text-sm px-6 py-3 rounded-xl gap-2 min-h-[44px] sm:min-h-0',
}

const variantCls: Record<Variant, string> = {
  primary: 'tb2-btn-primary text-white font-semibold',
  secondary:
    'tb2-btn-ghost bg-white/[0.04] border border-white/10 text-white/75 hover:text-white hover:bg-white/[0.08] hover:border-white/20 font-medium',
  ghost:
    'tb2-btn-ghost text-white/40 hover:text-white/85 hover:bg-white/[0.06] font-medium',
  danger:
    'tb2-btn-danger bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/15 hover:border-red-500/30 font-medium',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', loading, icon, disabled, className, children, ...rest },
  ref
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        'inline-flex items-center justify-center whitespace-nowrap transition disabled:opacity-45 disabled:cursor-not-allowed',
        sizeCls[size],
        variantCls[variant],
        className
      )}
      {...rest}
    >
      {loading ? <Loader2 size={size === 'sm' ? 12 : 14} className="animate-spin" /> : icon}
      {children}
    </button>
  )
})

export const IconButton = forwardRef<HTMLButtonElement, ButtonProps & { 'aria-label': string }>(
  function IconButton({ className, children, variant = 'ghost', ...rest }, ref) {
    return (
      <button
        ref={ref}
        className={cn(
          // 44x44 minimum touch target on touch/mobile widths (accessibility),
          // stepping back down to the original 36x36 from sm: up where mouse
          // precision makes the larger target unnecessary. Purely a hit-area /
          // spacing change — icon size and visual appearance are unchanged.
          'tb2-iconbtn inline-flex items-center justify-center w-11 h-11 sm:w-9 sm:h-9 rounded-xl',
          variant === 'ghost' && 'text-white/40 hover:text-white/85 hover:bg-white/[0.07]',
          variant === 'danger' && 'text-white/40 hover:text-red-400 hover:bg-red-500/10',
          className
        )}
        {...rest}
      >
        {children}
      </button>
    )
  }
)
