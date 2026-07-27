'use client'
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils/cn'

// Renders through a portal directly under document.body so the overlay's
// `position: fixed` is never affected by any ancestor's CSS (e.g. the
// app-shell's `.tb2-shell > * { position: relative }` rule). React
// context (Toast/QueryClient/Theme) is unaffected — portals only change
// DOM placement, not React tree ownership.
export function Modal({
  onClose,
  title,
  subtitle,
  children,
  maxWidth = 'max-w-md',
}: {
  onClose: () => void
  title?: string
  subtitle?: string
  children: React.ReactNode
  maxWidth?: string
}) {
  // Portals must not run during SSR/hydration (no `document` on the
  // server); flip this after mount so the server and first client render
  // match, then portal on the next render.
  const [mounted, setMounted] = useState(false)
  useEffect(() => { setMounted(true) }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!mounted) return null

  return createPortal(
    <div
      className="tb2-overlay fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-[200] p-3 sm:p-4"
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      {/* max-h + overflow-y-auto keeps tall modal content (long forms, lists)
          scrollable within the viewport instead of clipping off-screen on
          short mobile viewports; responsive padding tightens up below sm. */}
      <div className={cn('tb2-modal tb2-glass w-full p-4 sm:p-6 shadow-2xl max-h-[90vh] overflow-y-auto', maxWidth)}>
        {(title || subtitle) && (
          <div className="flex items-start justify-between mb-4 sm:mb-5 gap-3">
            <div className="min-w-0">
              {title && <h2 className="text-base font-semibold text-white truncate">{title}</h2>}
              {subtitle && <p className="text-xs text-white/35 mt-1">{subtitle}</p>}
            </div>
            <button
              onClick={onClose}
              className="tb2-iconbtn text-white/30 hover:text-white/70 rounded-lg hover:bg-white/[0.06] -mt-1 -mr-1 flex-shrink-0 w-11 h-11 sm:w-8 sm:h-8 flex items-center justify-center"
              aria-label="Close"
            >
              <X size={16} />
            </button>
          </div>
        )}
        {children}
      </div>
    </div>,
    document.body
  )
}
