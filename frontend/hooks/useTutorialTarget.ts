'use client'
import { useEffect, useRef, useState } from 'react'

export interface TargetRect {
  top: number
  left: number
  width: number
  height: number
}

function rectOf(el: Element): TargetRect {
  const r = el.getBoundingClientRect()
  return { top: r.top, left: r.left, width: r.width, height: r.height }
}

/**
 * Selector-based targeting for a single tutorial step.
 *
 * - Polls for `[data-tutorial="<stepId>"]` since the element may not be
 *   mounted yet (e.g. behind another tab/panel, or still loading).
 * - Scrolls it into view once found, if it's off-screen.
 * - Keeps the rect live across scroll/resize so the highlight tracks it.
 * - Reports `notFound` after a short timeout so the caller can skip the
 *   step gracefully instead of hanging forever.
 */
export function useTutorialTarget(stepId: string | null, timeoutMs = 3500) {
  const [rect, setRect] = useState<TargetRect | null>(null)
  const [element, setElement] = useState<Element | null>(null)
  const [notFound, setNotFound] = useState(false)
  const startRef = useRef(Date.now())

  useEffect(() => {
    setRect(null)
    setElement(null)
    setNotFound(false)
    if (!stepId) return
    startRef.current = Date.now()

    let raf = 0
    let cancelled = false

    const tick = () => {
      if (cancelled) return
      const el = document.querySelector(`[data-tutorial="${stepId}"]`)
      if (el) {
        setElement(el)
        const r = el.getBoundingClientRect()
        const inView = r.top >= 0 && r.left >= 0 && r.bottom <= window.innerHeight && r.right <= window.innerWidth
        if (!inView) {
          const prefersReducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
          el.scrollIntoView({ behavior: prefersReducedMotion ? 'auto' : 'smooth', block: 'center', inline: 'center' })
        }
        setRect(rectOf(el))
        return // keep tracking via the resize/scroll listeners below
      }
      if (Date.now() - startRef.current > timeoutMs) {
        setNotFound(true)
        return
      }
      raf = window.requestAnimationFrame(tick)
    }
    raf = window.requestAnimationFrame(tick)

    const onScrollOrResize = () => {
      const el = document.querySelector(`[data-tutorial="${stepId}"]`)
      if (el) setRect(rectOf(el))
    }
    window.addEventListener('scroll', onScrollOrResize, true)
    window.addEventListener('resize', onScrollOrResize)

    return () => {
      cancelled = true
      window.cancelAnimationFrame(raf)
      window.removeEventListener('scroll', onScrollOrResize, true)
      window.removeEventListener('resize', onScrollOrResize)
    }
  }, [stepId, timeoutMs])

  return { rect, element, notFound }
}
