'use client'
import { useEffect, useState } from 'react'
import type { TargetRect } from '@/hooks/useTutorialTarget'
import type { TutorialGesture } from '@/lib/tutorials/types'

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReduced(mq.matches)
    const onChange = () => setReduced(mq.matches)
    mq.addEventListener?.('change', onChange)
    return () => mq.removeEventListener?.('change', onChange)
  }, [])
  return reduced
}

/** Renders a small animated pointer at the edge of the highlighted rect,
 *  nudging in the direction of the gesture being taught. Purely visual —
 *  `pointer-events: none` so it never intercepts the real click/drag. */
export function TutorialPointer({ rect, gesture }: { rect: TargetRect; gesture?: TutorialGesture }) {
  const reducedMotion = usePrefersReducedMotion()

  if (gesture === 'none' || !gesture) return null

  const cx = rect.left + rect.width / 2
  const cy = rect.top + rect.height / 2
  // Sit just inside the bottom-right corner of the highlight by default —
  // reads naturally for click/save/try; drag/drop nudge toward the canvas.
  const isDrag = gesture === 'drag' || gesture === 'drop'
  const left = isDrag ? cx : rect.left + Math.min(rect.width * 0.72, rect.width - 18)
  const top = isDrag ? cy : rect.top + Math.min(rect.height * 0.72, rect.height - 10)

  return (
    <div
      className={reducedMotion ? '' : 'tb-tutorial-pointer-bounce'}
      style={{
        position: 'fixed',
        left,
        top,
        transform: 'translate(-30%, -10%)',
        fontSize: 28,
        lineHeight: 1,
        zIndex: 2147483001,
        pointerEvents: 'none',
        filter: 'drop-shadow(0 2px 6px rgba(0,0,0,0.5))',
        userSelect: 'none',
      }}
      aria-hidden="true"
    >
      {isDrag ? '👆' : '👇'}
    </div>
  )
}
