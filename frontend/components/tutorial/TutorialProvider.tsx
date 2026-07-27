'use client'
import { useEffect, useRef } from 'react'
import { usePathname } from 'next/navigation'
import { useTutorialStore } from '@/store/tutorialStore'
import { findConfigForPath } from '@/lib/tutorials/registry'
import { TutorialOverlay } from './TutorialOverlay'
import { TutorialRestartButton } from './TutorialRestartButton'

/** Mounted once near the app root. Handles the "automatic" half of the
 *  tutorial system: page-level features (Dashboard, Workflow Builder,
 *  Shop Assistant, AI Calls, ...) that are keyed off the route. Panel-
 *  scoped features (Knowledge Base, AI Chat inside the Builder) trigger
 *  themselves via useFeatureTutorial in their own component instead. */
export function TutorialProvider() {
  const pathname = usePathname()
  const hydrated = useTutorialStore(s => s.hydrated)
  const hydrate = useTutorialStore(s => s.hydrate)
  const activeFeature = useTutorialStore(s => s.activeFeature)
  const start = useTutorialStore(s => s.start)
  const getProgress = useTutorialStore(s => s.getProgress)
  const triedForPath = useRef<string | null>(null)

  useEffect(() => {
    if (!hydrated) hydrate()
  }, [hydrated, hydrate])

  useEffect(() => {
    if (!hydrated || !pathname) return
    if (activeFeature) return // one tutorial at a time
    if (triedForPath.current === pathname) return

    const config = findConfigForPath(pathname)
    if (!config || config.paths.length === 0) return // panel-scoped, not path-driven

    triedForPath.current = pathname
    const progress = getProgress(config.featureKey)
    if (progress.status !== 'not_started') return

    // Let the page finish its first render before polling for elements.
    const t = window.setTimeout(() => start(config.featureKey), 700)
    return () => window.clearTimeout(t)
  }, [hydrated, pathname, activeFeature, start, getProgress])

  const pageConfig = pathname ? findConfigForPath(pathname) : null

  return (
    <>
      {pageConfig && pageConfig.paths.length > 0 && <TutorialRestartButton config={pageConfig} />}
      <TutorialOverlay />
    </>
  )
}
