'use client'
import { X, ChevronLeft, ChevronRight, Check } from 'lucide-react'
import type { TargetRect } from '@/hooks/useTutorialTarget'
import type { TutorialStep } from '@/lib/tutorials/types'

const GESTURE_LABEL: Record<string, string> = {
  click: 'Click here', touch: 'Touch here', drag: 'Drag here',
  drop: 'Drop here', save: 'Save here', try: 'Try this', none: '',
}

export function TutorialTooltip({
  rect, step, stepNumber, totalSteps, onNext, onPrevious, onSkip, onFinish,
}: {
  rect: TargetRect
  step: TutorialStep
  stepNumber: number
  totalSteps: number
  onNext: () => void
  onPrevious: () => void
  onSkip: () => void
  onFinish: () => void
}) {
  const isLast = stepNumber === totalSteps

  // Prefer the requested placement; fall back to whichever side has room.
  const spaceBelow = window.innerHeight - (rect.top + rect.height)
  const spaceAbove = rect.top
  const placement = step.placement === 'auto' || !step.placement
    ? (spaceBelow > 160 ? 'bottom' : spaceAbove > 160 ? 'top' : 'bottom')
    : step.placement

  const CARD_WIDTH = 288
  let top: number
  let left = Math.min(Math.max(rect.left + rect.width / 2 - CARD_WIDTH / 2, 12), window.innerWidth - CARD_WIDTH - 12)

  if (placement === 'top') top = rect.top - 12
  else if (placement === 'bottom') top = rect.top + rect.height + 12
  else if (placement === 'left') { top = rect.top; left = Math.max(rect.left - CARD_WIDTH - 16, 12) }
  else { top = rect.top; left = Math.min(rect.left + rect.width + 16, window.innerWidth - CARD_WIDTH - 12) }

  const translateY = placement === 'top' ? '-100%' : '0'

  return (
    <div
      role="dialog"
      aria-label={step.title}
      style={{
        position: 'fixed',
        top,
        left,
        width: CARD_WIDTH,
        transform: `translateY(${translateY})`,
        zIndex: 2147483002,
      }}
      className="tb-tutorial-card rounded-2xl p-4 shadow-2xl border"
    >
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <p className="text-sm font-semibold text-[var(--fg)]">{step.title}</p>
        <button
          onClick={onSkip}
          aria-label="Skip tutorial"
          className="text-[var(--fg)]/35 hover:text-[var(--fg)]/80 transition flex-shrink-0 -mt-0.5 -mr-0.5"
        >
          <X size={14} />
        </button>
      </div>
      <p className="text-[13px] text-[var(--fg)]/60 leading-relaxed">{step.body}</p>
      {step.gesture && step.gesture !== 'none' && (
        <p className="mt-2 text-[11px] font-medium tracking-wide uppercase text-[var(--accent-text)]">
          {GESTURE_LABEL[step.gesture]}
        </p>
      )}

      <div className="flex items-center justify-between mt-3.5">
        <span className="text-[11px] text-[var(--fg)]/30 tabular-nums">{stepNumber} / {totalSteps}</span>
        <div className="flex items-center gap-1.5">
          {stepNumber > 1 && (
            <button
              onClick={onPrevious}
              className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg text-[var(--fg)]/60 hover:text-[var(--fg)] hover:bg-[var(--hover)] transition"
            >
              <ChevronLeft size={12} /> Back
            </button>
          )}
          <button
            onClick={isLast ? onFinish : onNext}
            className="flex items-center gap-1 text-xs font-medium px-3 py-1.5 rounded-lg text-white transition"
            style={{ background: 'var(--accent)' }}
          >
            {isLast ? (<><Check size={12} /> Finish</>) : (<>Next <ChevronRight size={12} /></>)}
          </button>
        </div>
      </div>
    </div>
  )
}
