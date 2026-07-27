'use client'
import { useEffect, useRef } from 'react'
import { useTutorialStore } from '@/store/tutorialStore'

/**
 * Call this from any component that represents a "feature" a user should
 * only be guided through once — including features that share a route
 * with other panels (e.g. the Knowledge Base / Chat Tester panels inside
 * the Workflow Builder, which mount only while selected).
 *
 * Auto-starts the tutorial the first time this feature is seen. Does
 * nothing if it's already completed, skipped, or in progress.
 */
export function useFeatureTutorial(featureKey: string) {
  const hydrated = useTutorialStore(s => s.hydrated)
  const hydrate = useTutorialStore(s => s.hydrate)
  const start = useTutorialStore(s => s.start)
  const status = useTutorialStore(s => s.getProgress(featureKey).status)
  const startedRef = useRef(false)

  useEffect(() => {
    if (!hydrated) hydrate()
  }, [hydrated, hydrate])

  useEffect(() => {
    if (!hydrated || startedRef.current) return
    if (status !== 'not_started') return
    startedRef.current = true
    // Small delay so the panel's own content has mounted (and real
    // data-tutorial targets exist) before the overlay starts polling.
    const t = window.setTimeout(() => start(featureKey), 500)
    return () => window.clearTimeout(t)
  }, [hydrated, status, start, featureKey])
}
