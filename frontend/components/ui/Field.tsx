'use client'
import { forwardRef } from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils/cn'

export function FieldLabel({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="flex items-center justify-between mb-1.5">
      <label className="block text-[10px] font-semibold text-white/40 uppercase tracking-wider">
        {children}
      </label>
      {hint && <span className="text-[10px] text-white/25">{hint}</span>}
    </div>
  )
}

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...rest }, ref) {
    return (
      <input
        ref={ref}
        className={cn(
          'tb2-field w-full text-sm text-white rounded-xl px-3.5 py-2.5 outline-none min-h-[44px]',
          'placeholder-white/20',
          className
        )}
        {...rest}
      />
    )
  }
)

export const Textarea = forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...rest }, ref) {
    return (
      <textarea
        ref={ref}
        className={cn(
          'tb2-field w-full text-sm text-white rounded-xl px-3.5 py-2.5 outline-none resize-none',
          'placeholder-white/20',
          className
        )}
        {...rest}
      />
    )
  }
)

export const Select = forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, children, ...rest }, ref) {
    return (
      <div className="relative">
        <select
          ref={ref}
          className={cn(
            'tb2-field w-full text-sm text-white rounded-xl pl-3.5 pr-9 py-2.5 outline-none appearance-none cursor-pointer min-h-[44px]',
            className
          )}
          {...rest}
        >
          {children}
        </select>
        <ChevronDown size={13} className="absolute right-3.5 top-1/2 -translate-y-1/2 text-white/30 pointer-events-none" />
      </div>
    )
  }
)
