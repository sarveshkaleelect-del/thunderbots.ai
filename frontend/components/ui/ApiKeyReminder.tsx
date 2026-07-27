'use client'
import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { KeyRound, X } from 'lucide-react'
import { settingsApi } from '@/lib/api/settings'
import type { UserAPIKey } from '@/types'
import { Button } from './Button'
import { cn } from '@/lib/utils/cn'

const DISMISS_KEY = 'tb-apikey-reminder-dismissed'

function isDismissedThisSession(): boolean {
  if (typeof window === 'undefined') return false
  try { return sessionStorage.getItem(DISMISS_KEY) === '1' } catch { return false }
}

/**
 * Small floating reminder shown on AI-related pages (Workflow Builder,
 * Create with AI — which also covers the Test Chat / Deploy / AI Agent
 * panels living inside the builder) when the user has no configured AI
 * provider API key yet. Purely informational: never blocks the page,
 * never appears inside the chat/test-chat surface itself, and reuses the
 * existing Settings → API Keys page + its `returnTo` redirect for saving.
 *
 * No polling: a single one-shot fetch of the user's keys, cached by
 * react-query. Dismissal is session-only (sessionStorage), and the
 * reminder is skipped entirely once any key exists.
 */
export function ApiKeyReminder() {
  const pathname = usePathname()
  const router = useRouter()
  const [dismissed, setDismissed] = useState(true) // default hidden until we know session state (avoids flash)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setDismissed(isDismissedThisSession())
    setMounted(true)
  }, [])

  const { data: keys, isLoading, isError } = useQuery({
    queryKey: ['api-keys'],
    queryFn: settingsApi.listKeys,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
    refetchInterval: false,
    retry: false,
  })

  const hasKey = isError || (Array.isArray(keys) && (keys as UserAPIKey[]).length > 0)

  if (!mounted || isLoading || hasKey || dismissed) return null

  const handleDismiss = () => {
    try { sessionStorage.setItem(DISMISS_KEY, '1') } catch {}
    setDismissed(true)
  }

  const handleAddKey = () => {
    const returnTo = encodeURIComponent(pathname || '/dashboard')
    router.push(`/settings/api-keys?returnTo=${returnTo}`)
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'tb2-glass tbkr-card tbkr-in fixed top-20 right-5 z-40 w-72 p-4',
        'pointer-events-auto'
      )}
    >
      <div className="tbkr-glow" aria-hidden="true" />
      <button
        aria-label="Dismiss"
        onClick={handleDismiss}
        className="absolute top-2.5 right-2.5 w-6 h-6 rounded-lg flex items-center justify-center text-white/30 hover:text-white/70 hover:bg-white/[0.06] transition"
      >
        <X size={12} />
      </button>

      <div className="flex items-start gap-2.5 pr-4">
        <div className="w-8 h-8 rounded-xl bg-[#6366f1]/15 border border-[#6366f1]/25 flex items-center justify-center flex-shrink-0 mt-0.5">
          <KeyRound size={14} className="text-[#a5b4fc]" />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-semibold text-white/90 leading-snug">
            🔑 AI Provider Not Configured
          </p>
          <p className="text-[11px] text-white/40 mt-1 leading-relaxed">
            Add your API Key to unlock AI features.
          </p>
        </div>
      </div>

      <div className="flex gap-2 mt-3.5">
        <Button size="sm" className="flex-1" onClick={handleAddKey}>
          Add API Key
        </Button>
        <Button size="sm" variant="secondary" onClick={handleDismiss}>
          Dismiss
        </Button>
      </div>
    </div>
  )
}
