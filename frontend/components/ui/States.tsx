'use client'
import { CheckCircle2, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import { Logo } from './Logo'

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('tb2-skeleton', className)} />
}

export function SkeletonCard() {
  return (
    <div className="tb2-glass p-5 space-y-3">
      <div className="flex items-center gap-3">
        <Skeleton className="w-9 h-9 rounded-xl" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-3 w-2/3" />
          <Skeleton className="h-2.5 w-1/3" />
        </div>
      </div>
      <Skeleton className="h-2.5 w-full" />
      <Skeleton className="h-2.5 w-4/5" />
    </div>
  )
}

export function SkeletonGrid({ count = 6 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  )
}

export function SkeletonRows({ count = 5 }: { count?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-14 w-full rounded-xl" />
      ))}
    </div>
  )
}

export function PageLoader({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-14 sm:py-24">
      <div className="relative flex items-center justify-center">
        <Logo size={28} className="tb2-logo-pulse" />
        <Loader2 size={14} className="text-[#818cf8] animate-spin absolute -bottom-1.5 -right-1.5" />
      </div>
      {label && <p className="text-xs text-white/30">{label}</p>}
    </div>
  )
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: React.ReactNode
  title: string
  description?: string
  action?: React.ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-14 sm:py-24 px-4 sm:px-6 tb2-rise">
      <div className="tb2-float w-16 h-16 rounded-2xl tb2-brand-mark flex items-center justify-center mb-4 text-[#a5b4fc]">
        {icon}
      </div>
      <p className="text-white/60 font-semibold mb-1">{title}</p>
      {description && <p className="text-white/25 text-sm mb-6 max-w-sm">{description}</p>}
      {action}
    </div>
  )
}

export function SuccessState({
  title = 'All set',
  description,
  action,
}: {
  title?: string
  description?: string
  action?: React.ReactNode
}) {
  return (
    <div className="flex flex-col items-center py-14 sm:py-24 gap-3 text-center px-4 sm:px-6 tb2-rise">
      <div className="w-14 h-14 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
        <CheckCircle2 size={22} className="text-emerald-400" />
      </div>
      <p className="text-white/70 text-sm font-semibold">{title}</p>
      {description && <p className="text-white/25 text-xs max-w-sm">{description}</p>}
      {action}
    </div>
  )
}

export function ErrorState({
  title = "Something didn't load",
  description,
  onRetry,
}: {
  title?: string
  description?: string
  onRetry?: () => void
}) {
  return (
    <div className="flex flex-col items-center py-14 sm:py-24 gap-3 text-center px-4 sm:px-6">
      <div className="w-14 h-14 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-red-400">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
      </div>
      <p className="text-white/50 text-sm font-medium">{title}</p>
      {description && <p className="text-white/25 text-xs max-w-sm">{description}</p>}
      {onRetry && (
        <button onClick={onRetry} className="text-xs text-[#818cf8] hover:text-cyan-300 hover:underline mt-1 transition-colors">
          Try again
        </button>
      )}
    </div>
  )
}
