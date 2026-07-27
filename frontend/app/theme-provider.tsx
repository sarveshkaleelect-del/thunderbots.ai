'use client'
import { useEffect, useRef } from 'react'
import { useThemeStore, readStoredTheme, type ThemeId } from '@/store/themeStore'
import { settingsApi } from '@/lib/api/settings'

/**
 * Applies the theme instantly on mount (from localStorage, avoiding any
 * flash), then reconciles with the user's saved backend preference once
 * it loads. Backend is the source of truth across devices; localStorage
 * is the source of truth for instant, no-refresh application.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const setLocalTheme = useThemeStore(s => s.setLocalTheme)
  const setHydrated = useThemeStore(s => s.setHydrated)
  const didReconcile = useRef(false)

  useEffect(() => {
    // Instant local application — already applied synchronously by the
    // inline script in <head>, this just syncs the store's state.
    const local = readStoredTheme()
    useThemeStore.setState({ theme: local })
    setHydrated()

    // Reconcile with the user's saved preference (covers first login on
    // a new device / browser where localStorage is empty).
    settingsApi.getPreferences()
      .then(prefs => {
        if (didReconcile.current) return
        didReconcile.current = true
        const remote = prefs?.theme as ThemeId | undefined
        const validThemes: ThemeId[] = ['dark', 'light', 'midnight', 'thunder']
        if (remote && validThemes.includes(remote) && remote !== local) {
          setLocalTheme(remote)
        }
      })
      .catch(() => {
        // Not authenticated yet, or offline — local/default theme stands.
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return <>{children}</>
}
