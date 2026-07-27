'use client'
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTutorialStore } from '@/store/tutorialStore'
import { findConfigForFeature } from '@/lib/tutorials/registry'
import { useTutorialTarget } from '@/hooks/useTutorialTarget'
import { TutorialPointer } from './TutorialPointer'
import { TutorialTooltip } from './TutorialTooltip'

const HIGHLIGHT_PADDING = 8

function StepRenderer({ featureKey }: { featureKey: string }) {
  const config = findConfigForFeature(featureKey)
  const progress = useTutorialStore(s => s.getProgress(featureKey))
  const setStep = useTutorialStore(s => s.setStep)
  const skip = useTutorialStore(s => s.skip)
  const finish = useTutorialStore(s => s.finish)

  const totalSteps = config?.steps.length ?? 0
  const stepIndex = progress.currentStep
  const step = config?.steps[stepIndex] ?? null

  const { rect, element, notFound } = useTutorialTarget(step?.id ?? null)

  const goNext = () => {
    if (!config) return
    if (stepIndex + 1 >= totalSteps) finish(featureKey, totalSteps)
    else setStep(featureKey, stepIndex + 1, totalSteps)
  }
  const goPrevious = () => {
    if (stepIndex > 0) setStep(featureKey, stepIndex - 1, totalSteps)
  }
  const doSkip = () => skip(featureKey, totalSteps)
  const doFinish = () => finish(featureKey, totalSteps)

  // Element never showed up (e.g. optional/conditional UI, or the user
  // navigated to a different panel) — skip forward instead of hanging.
  useEffect(() => {
    if (notFound) goNext()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notFound])

  // Let the real element's own click naturally advance the tutorial —
  // additive listener, never replaces the app's own handler.
  useEffect(() => {
    if (!element || !step) return
    if (!['click', 'save', 'try'].includes(step.gesture ?? '')) return
    const onClick = () => goNext()
    element.addEventListener('click', onClick)
    return () => element.removeEventListener('click', onClick)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [element, step?.id])

  // Keyboard navigation
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') doSkip()
      else if (e.key === 'ArrowRight' || e.key === 'Enter') goNext()
      else if (e.key === 'ArrowLeft') goPrevious()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stepIndex, featureKey])

  if (!config || !step || !rect) return null

  const highlightRect = {
    top: rect.top - HIGHLIGHT_PADDING,
    left: rect.left - HIGHLIGHT_PADDING,
    width: rect.width + HIGHLIGHT_PADDING * 2,
    height: rect.height + HIGHLIGHT_PADDING * 2,
  }

  return (
    <>
      <div
        className="tb-tutorial-highlight"
        style={{ top: highlightRect.top, left: highlightRect.left, width: highlightRect.width, height: highlightRect.height }}
        aria-hidden="true"
      />
      <TutorialPointer rect={highlightRect} gesture={step.gesture} />
      <TutorialTooltip
        rect={highlightRect}
        step={step}
        stepNumber={stepIndex + 1}
        totalSteps={totalSteps}
        onNext={goNext}
        onPrevious={goPrevious}
        onSkip={doSkip}
        onFinish={doFinish}
      />
    </>
  )
}

/** Mount once, near the root. Renders nothing until a feature tutorial is
 *  active (`useTutorialStore.activeFeature`), then portals the overlay to
 *  `document.body` so it's never affected by any ancestor's stacking
 *  context — same reasoning as components/ui/Modal.tsx. */
export function TutorialOverlay() {
  const activeFeature = useTutorialStore(s => s.activeFeature)
  const [mounted, setMounted] = useState(false)
  useEffect(() => { setMounted(true) }, [])

  if (!mounted || !activeFeature) return null

  return createPortal(<StepRenderer featureKey={activeFeature} />, document.body)
}
