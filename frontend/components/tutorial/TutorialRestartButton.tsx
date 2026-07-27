'use client'
import { HelpCircle } from 'lucide-react'
import { useTutorialStore } from '@/store/tutorialStore'
import type { TutorialConfig } from '@/lib/tutorials/types'

/** Small "?" affordance so a completed tutorial is never truly gone —
 *  the spec's "Restart" requirement. Only rendered when the current page
 *  actually has a tutorial (see TutorialProvider), so it never appears as
 *  a dead button on pages without one yet. */
export function TutorialRestartButton({ config }: { config: TutorialConfig }) {
  const restart = useTutorialStore(s => s.restart)
  const activeFeature = useTutorialStore(s => s.activeFeature)

  if (activeFeature) return null // don't stack a second launcher over a running tutorial

  return (
    <button
      onClick={() => restart(config.featureKey)}
      aria-label={`Restart the ${config.label} tutorial`}
      title={`Restart the ${config.label} tutorial`}
      className="tb-tutorial-restart-btn fixed bottom-5 left-5 w-10 h-10 rounded-full flex items-center justify-center
                 border shadow-lg transition hover:scale-105 active:scale-95"
      style={{
        zIndex: 900,
        background: 'var(--panel)',
        borderColor: 'var(--border)',
        color: 'var(--accent-text)',
      }}
    >
      <HelpCircle size={17} />
    </button>
  )
}
