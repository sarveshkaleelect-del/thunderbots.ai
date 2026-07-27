'use client'
import { cloneElement, useId, useRef, useState } from 'react'
import { cn } from '@/lib/utils/cn'

type Side = 'top' | 'bottom' | 'left' | 'right'

const sideCls: Record<Side, string> = {
  top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
  bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
  left: 'right-full top-1/2 -translate-y-1/2 mr-2',
  right: 'left-full top-1/2 -translate-y-1/2 ml-2',
}

const arrowCls: Record<Side, string> = {
  top: 'top-full left-1/2 -translate-x-1/2 -mt-[3px] border-t-0 border-l-0',
  bottom: 'bottom-full left-1/2 -translate-x-1/2 -mb-[3px] border-b-0 border-r-0',
  left: 'left-full top-1/2 -translate-y-1/2 -ml-[3px] border-b-0 border-l-0',
  right: 'right-full top-1/2 -translate-y-1/2 -mr-[3px] border-t-0 border-r-0',
}

/**
 * Lightweight, dependency-free tooltip. Shares the app-shell glass
 * surface + accent tokens so it reads as part of the same design
 * system as Card/Modal/Toast. Purely additive — no existing component
 * is required to use it.
 */
export function Tooltip({
  content,
  children,
  side = 'top',
  delay = 300,
  className,
}: {
  content: React.ReactNode
  children: React.ReactElement
  side?: Side
  delay?: number
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const id = useId()

  const show = () => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setOpen(true), delay)
  }
  const hide = () => {
    if (timerRef.current) clearTimeout(timerRef.current)
    setOpen(false)
  }

  if (!content) return children

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {cloneElement(children, { 'aria-describedby': open ? id : undefined } as any)}
      {open && (
        <span
          role="tooltip"
          id={id}
          className={cn(
            'tb2-tooltip pointer-events-none absolute z-[70] whitespace-nowrap',
            'text-[11px] font-medium px-2.5 py-1.5 rounded-lg',
            sideCls[side],
            className
          )}
        >
          {content}
          <span className={cn('tb2-tooltip-arrow absolute w-[7px] h-[7px] rotate-45', arrowCls[side])} />
        </span>
      )}
    </span>
  )
}
