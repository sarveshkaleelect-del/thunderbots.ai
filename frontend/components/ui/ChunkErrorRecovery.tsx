'use client'
// ============================================================
// Chunk Load Error Recovery
//
// Part of the Issue 1 root-cause fix (see SimulatorPanel.tsx for the
// render-phase-import() bug that caused the reported error directly).
// This component is a second, independent safety net for the *class* of
// error, not just the one component that happened to surface it: any
// dynamically-imported chunk (code-split route, next/dynamic component,
// or a manual import()) can fail to load if the browser's cached chunk
// map goes stale — most commonly right after a new production deploy
// replaces the .next build output while a user still has the previous
// page open, or on a flaky network mid-request. Next.js does not recover
// from this on its own; the tab is stuck until the user manually
// refreshes.
//
// This listens globally for that failure shape and performs ONE automatic
// reload, guarded by sessionStorage so a genuinely broken chunk can never
// cause a reload loop — after one attempt, if it still fails, it's a real
// error and is left alone (visible in the console / to any error boundary)
// instead of reloading forever.
// ============================================================
import { useEffect } from 'react'

const RELOAD_GUARD_KEY = 'tb-chunk-reload-guard'

function isChunkLoadError(reason: unknown): boolean {
  if (!reason) return false
  const message = reason instanceof Error ? `${reason.name} ${reason.message}` : String(reason)
  return /ChunkLoadError|Loading chunk [\w.-]+ failed/i.test(message)
}

function attemptRecovery() {
  try {
    // Only ever auto-reload once per browser session for this guard —
    // if the reload didn't fix it, don't keep trying.
    if (sessionStorage.getItem(RELOAD_GUARD_KEY)) return
    sessionStorage.setItem(RELOAD_GUARD_KEY, '1')
  } catch {
    // sessionStorage unavailable (private mode, etc.) — skip the guard
    // rather than blocking recovery entirely.
  }
  window.location.reload()
}

export function ChunkErrorRecovery() {
  useEffect(() => {
    const onRejection = (event: PromiseRejectionEvent) => {
      if (isChunkLoadError(event.reason)) attemptRecovery()
    }
    const onError = (event: ErrorEvent) => {
      if (isChunkLoadError(event.error ?? event.message)) attemptRecovery()
    }
    window.addEventListener('unhandledrejection', onRejection)
    window.addEventListener('error', onError)
    return () => {
      window.removeEventListener('unhandledrejection', onRejection)
      window.removeEventListener('error', onError)
    }
  }, [])

  // Clear the guard once the app has been up and stable for a bit, so a
  // later, genuinely new stale-chunk incident (e.g. the next deploy) still
  // gets one fresh auto-recovery attempt instead of being silently skipped
  // forever because of a guard flag from a past session.
  useEffect(() => {
    const t = setTimeout(() => {
      try { sessionStorage.removeItem(RELOAD_GUARD_KEY) } catch { /* ignore */ }
    }, 15000)
    return () => clearTimeout(t)
  }, [])

  return null
}
