'use client'
import { createContext, useCallback, useContext, useRef, useState } from 'react'
import { CheckCircle2, XCircle, Info, AlertTriangle, X } from 'lucide-react'
import { cn } from '@/lib/utils/cn'

type ToastKind = 'success' | 'error' | 'info' | 'warning'
interface ToastItem { id: number; kind: ToastKind; message: string; leaving?: boolean }

const KIND_META: Record<ToastKind, { icon: any; cls: string; bar: string }> = {
  success: { icon: CheckCircle2, cls: 'text-emerald-400', bar: 'bg-emerald-400' },
  error: { icon: XCircle, cls: 'text-red-400', bar: 'bg-red-400' },
  info: { icon: Info, cls: 'text-cyan-300', bar: 'bg-cyan-300' },
  warning: { icon: AlertTriangle, cls: 'text-amber-400', bar: 'bg-amber-400' },
}

const ToastContext = createContext<{ toast: (kind: ToastKind, message: string) => void } | null>(null)

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const idRef = useRef(0)

  const remove = useCallback((id: number) => {
    setItems(list => list.map(t => (t.id === id ? { ...t, leaving: true } : t)))
    setTimeout(() => setItems(list => list.filter(t => t.id !== id)), 160)
  }, [])

  const toast = useCallback((kind: ToastKind, message: string) => {
    const id = ++idRef.current
    setItems(list => [...list, { id, kind, message }])
    setTimeout(() => remove(id), 3800)
  }, [remove])

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 sm:bottom-5 left-3 right-3 sm:left-auto sm:right-5 z-[100] flex flex-col gap-2 items-stretch sm:items-end pointer-events-none">
        {items.map(t => {
          const { icon: Icon, cls, bar } = KIND_META[t.kind]
          return (
            <div
              key={t.id}
              className={cn(
                'tb2-glass relative overflow-hidden pointer-events-auto flex items-center gap-2.5 pl-4 pr-2.5 py-3 rounded-xl shadow-2xl w-full sm:w-auto sm:max-w-sm',
                t.leaving ? 'tb2-toast-out' : 'tb2-toast-in'
              )}
            >
              <span className={cn('absolute left-0 top-0 bottom-0 w-[3px]', bar)} />
              <Icon size={15} className={cn('flex-shrink-0', cls)} />
              <p className="text-xs text-white/85 leading-snug">{t.message}</p>
              <button
                onClick={() => remove(t.id)}
                className="ml-1 text-white/25 hover:text-white/60 transition flex-shrink-0 rounded-md hover:bg-white/[0.06] p-1 -mr-1"
                aria-label="Dismiss"
              >
                <X size={12} />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    // Safe no-op fallback if provider isn't mounted yet, so callers never crash.
    return { toast: (_kind: ToastKind, _message: string) => {} }
  }
  return ctx
}
