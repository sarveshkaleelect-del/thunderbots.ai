'use client'
import { usePathname } from 'next/navigation'

/**
 * Wraps route content so navigating between app-shell pages gently
 * rises/fades in instead of popping in place. Purely presentational —
 * keyed by pathname so React remounts (and replays the animation)
 * whenever the route changes. Does not touch the builder canvas,
 * which mounts its own layout and never passes through here for its
 * internal state changes.
 */
export function PageTransition({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()

  // The builder canvas manages its own mount lifecycle and internal
  // state (nodes, viewport, selection) independently of this wrapper.
  // Skip the remount-on-pathname-key behavior there entirely so this
  // purely cosmetic wrapper can never interact with builder state.
  if (pathname?.startsWith('/builder')) {
    return <>{children}</>
  }

  return (
    <div key={pathname} className="tb2-page-transition">
      {children}
    </div>
  )
}
