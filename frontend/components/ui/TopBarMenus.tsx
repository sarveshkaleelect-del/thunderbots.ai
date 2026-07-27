'use client'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  Search, Bell, Palette, User as UserIcon, Check,
  UserCircle2, CreditCard, LogOut, LogIn, UserPlus,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { cn } from '@/lib/utils/cn'
import { IconButton } from './Button'
import { useThemeStore, THEMES } from '@/store/themeStore'
import { clearToken, getToken } from '@/lib/api/auth'

/**
 * Closes the popover on outside click / Escape. Shared by all top-bar menus.
 *
 * `triggerRef` attaches to the button that opens the popover; `panelRef`
 * attaches to the portaled panel itself (see `PopoverPortal` below). Both
 * are checked on outside-click so that clicking inside a panel rendered
 * into document.body — outside the trigger's own DOM subtree — isn't
 * mistaken for an "outside" click and closes the menu incorrectly.
 */
export function usePopover<T extends HTMLElement>() {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<T>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node
      if (triggerRef.current?.contains(target)) return
      if (panelRef.current?.contains(target)) return
      setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return { open, setOpen, triggerRef, panelRef }
}

// max-w clamps the popover to the viewport width (minus a small margin) so
// it can't overflow off the left edge of narrow phone screens — the fixed
// w-52/w-56/w-72 below still apply whenever there's room for them.
// Positioning (top/right) and z-index now come from PopoverPortal's inline
// style, since the panel is portaled to document.body instead of being an
// absolutely-positioned descendant of the header.
export const panelCls = 'tb2-glass tb2-popover-in origin-top-right overflow-hidden rounded-2xl shadow-2xl max-w-[calc(100vw-1.5rem)]'

// Single source of truth for the header's floating-layer z-index tier, per
// the app's z-index system (header 100 / floating panels 200 / dropdowns
// 1000 / tooltips 1100 / modals 2000).
export const TB2_DROPDOWN_Z = 1000

/**
 * Renders a header popover panel into document.body via a portal, fixed-
 * positioned against the trigger element's live bounding rect. This is
 * what actually fixes the clipping/overlap bugs: once the panel is no
 * longer a DOM descendant of the sticky header, the header's own stacking
 * context (needed for its sticky + glass styling) can no longer clip or
 * out-rank it, and it renders above any other floating element on the
 * page (banners, cards, etc.) via one explicit z-index tier.
 */
export function PopoverPortal({
  open,
  triggerRef,
  panelRef,
  className,
  children,
}: {
  open: boolean
  triggerRef: React.RefObject<HTMLElement>
  panelRef: React.RefObject<HTMLDivElement>
  className: string
  children: React.ReactNode
}) {
  const [pos, setPos] = useState<{ top: number; right: number } | null>(null)

  useEffect(() => {
    if (!open || !triggerRef.current) {
      setPos(null)
      return
    }
    const update = () => {
      const r = triggerRef.current!.getBoundingClientRect()
      setPos({ top: r.bottom + 10, right: Math.max(8, window.innerWidth - r.right) })
    }
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [open, triggerRef])

  if (!open || !pos || typeof document === 'undefined') return null

  return createPortal(
    <div
      ref={panelRef}
      className={className}
      style={{ position: 'fixed', top: pos.top, right: pos.right, zIndex: TB2_DROPDOWN_Z }}
    >
      {children}
    </div>,
    document.body
  )
}

/* ── Search ─────────────────────────────────────────────────────── */
export function SearchTrigger() {
  const router = useRouter()
  const [expanded, setExpanded] = useState(false)
  const [query, setQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (expanded) inputRef.current?.focus()
  }, [expanded])

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const q = query.trim()
    if (!q) return
    router.push(`/dashboard?q=${encodeURIComponent(q)}`)
    setExpanded(false)
    setQuery('')
  }

  if (!expanded) {
    return (
      <IconButton aria-label="Search" onClick={() => setExpanded(true)}>
        <Search size={15} />
      </IconButton>
    )
  }

  // Expands in normal flex flow (flex:1, min-w-0, max-w) inside the
  // header's flexible center section, instead of the old absolute overlay
  // — so it grows into reserved space and can never render on top of
  // "Create with AI" / "New Workflow" or any other adjacent control.
  return (
    <form
      onSubmit={submit}
      className="tb2-field flex items-center gap-2 rounded-xl px-3 h-9 flex-1 min-w-0 max-w-[180px] sm:max-w-[256px]"
    >
      <Search size={13} className="text-white/30 flex-shrink-0" />
      <input
        ref={inputRef}
        value={query}
        onChange={e => setQuery(e.target.value)}
        onBlur={() => { if (!query) setExpanded(false) }}
        placeholder="Search workflows…"
        className="bg-transparent outline-none text-xs text-white/85 placeholder:text-white/25 w-full min-w-0"
      />
    </form>
  )
}

/* ── Notifications ──────────────────────────────────────────────── */
export function NotificationsMenu() {
  const { open, setOpen, triggerRef, panelRef } = usePopover<HTMLDivElement>()

  return (
    <div className="relative" ref={triggerRef}>
      <IconButton aria-label="Notifications" onClick={() => setOpen(o => !o)}>
        <Bell size={15} />
      </IconButton>
      <PopoverPortal open={open} triggerRef={triggerRef} panelRef={panelRef} className={cn(panelCls, 'w-72 p-1.5')}>
        <div className="px-3 py-2.5 flex items-center justify-between border-b border-white/[0.06] mb-1">
          <span className="text-xs font-semibold text-white/70">Notifications</span>
        </div>
        <div className="px-3 py-9 text-center">
          <div className="relative w-10 h-10 mx-auto mb-3">
            <span className="tb2-glow-blob inset-0 bg-[#6366f1]/20 w-10 h-10" />
            <div className="relative w-10 h-10 rounded-full bg-white/[0.05] border border-white/10 flex items-center justify-center">
              <Bell size={15} className="text-white/25" />
            </div>
          </div>
          <p className="text-[11px] text-white/30">You're all caught up</p>
        </div>
      </PopoverPortal>
    </div>
  )
}

/* ── Theme / Appearance ─────────────────────────────────────────── */
const THEME_SWATCH: Record<string, string> = {
  dark: '#6366f1',
  light: '#4f46e5',
  midnight: '#3b82f6',
  thunder: '#7c3aed',
}

export function ThemeMenu() {
  const { open, setOpen, triggerRef, panelRef } = usePopover<HTMLDivElement>()
  const theme = useThemeStore(s => s.theme)
  const setLocalTheme = useThemeStore(s => s.setLocalTheme)

  return (
    <div className="relative" ref={triggerRef}>
      <IconButton aria-label="Appearance" onClick={() => setOpen(o => !o)}>
        <Palette size={15} />
      </IconButton>
      <PopoverPortal open={open} triggerRef={triggerRef} panelRef={panelRef} className={cn(panelCls, 'w-52 p-1.5')}>
        <div className="px-2.5 py-2 text-[10px] font-semibold uppercase tracking-wider text-white/30">
          Appearance
        </div>
        {THEMES.map(t => {
          const active = theme === t.id
          return (
            <button
              key={t.id}
              onClick={() => { setLocalTheme(t.id); setOpen(false) }}
              className={cn(
                'tb2-row w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-left transition-colors',
                active ? 'bg-white/[0.07] text-white' : 'text-white/70 hover:bg-white/[0.06] hover:text-white'
              )}
            >
              <span
                className="w-2 h-2 rounded-full flex-shrink-0"
                style={{ background: THEME_SWATCH[t.id] ?? '#6366f1', boxShadow: active ? `0 0 8px ${THEME_SWATCH[t.id] ?? '#6366f1'}` : undefined }}
              />
              <span className="w-4 text-center">{t.emoji}</span>
              <span className="flex-1">{t.label}</span>
              {active && <Check size={12} className="text-cyan-300" />}
            </button>
          )
        })}
      </PopoverPortal>
    </div>
  )
}

/* ── Account ─────────────────────────────────────────────────────── */
export function AccountMenu() {
  const { open, setOpen, triggerRef, panelRef } = usePopover<HTMLDivElement>()
  const router = useRouter()

  const { data: me, isError, isLoading } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      const { authApi } = await import('@/lib/api/auth')
      return authApi.me()
    },
    enabled: typeof window !== 'undefined' && !!getToken(),
    staleTime: 60_000,
    retry: false,
  })

  const loggedIn = !!getToken() && !isError && !!me

  const handleLogout = () => {
    // NEW (Active Sessions & Device Management): best-effort — revokes this
    // session's UserSession row server-side so it immediately drops off the
    // account's active-sessions list instead of lingering there (revoked
    // only when it naturally expires) until then. Fire-and-forget: the
    // client-side token clear + redirect below always happens regardless
    // of whether this network call succeeds.
    import('@/lib/api/auth').then(({ authApi }) => {
      authApi.logout().catch(() => {})
    })
    clearToken()
    setOpen(false)
    router.push('/login')
  }

  const initials = me?.name
    ? me.name.trim().split(/\s+/).slice(0, 2).map(p => p[0]?.toUpperCase()).join('')
    : null

  return (
    <div className="relative" ref={triggerRef}>
      <IconButton aria-label="Account" onClick={() => setOpen(o => !o)} className={cn(loggedIn && 'text-white/70')}>
        {loggedIn && initials ? (
          <span className="w-6 h-6 rounded-full tb2-brand-mark ring-1 ring-white/10 flex items-center justify-center text-[10px] font-bold text-[#c7d2fe]">
            {initials}
          </span>
        ) : (
          <UserIcon size={15} />
        )}
      </IconButton>

      <PopoverPortal open={open} triggerRef={triggerRef} panelRef={panelRef} className={cn(panelCls, 'w-56 p-1.5')}>
        {!isLoading && loggedIn ? (
          <>
            <div className="px-3 py-2.5 mb-0.5 flex items-center gap-2.5">
              {initials && (
                <span className="w-8 h-8 rounded-full tb2-brand-mark ring-1 ring-white/10 flex items-center justify-center text-[11px] font-bold text-[#c7d2fe] flex-shrink-0">
                  {initials}
                </span>
              )}
              <div className="min-w-0">
                <p className="text-xs font-semibold text-white/85 truncate">{me?.name || 'Account'}</p>
                <p className="text-[11px] text-white/35 truncate">{me?.email}</p>
              </div>
            </div>
            <div className="h-px bg-white/[0.06] mx-1 mb-1" />
            <MenuLink href="/profile" icon={<UserCircle2 size={14} />} onClick={() => setOpen(false)}>
              My Profile
            </MenuLink>
            <MenuLink href="/billing" icon={<CreditCard size={14} />} onClick={() => setOpen(false)}>
              Billing
            </MenuLink>
            <div className="h-px bg-white/[0.06] mx-1 my-1" />
            <button
              onClick={handleLogout}
              className="tb2-row w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-red-400/90 hover:bg-red-500/10 text-left"
            >
              <LogOut size={14} />
              Logout
            </button>
          </>
        ) : (
          <>
            <div className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-white/30">
              Account
            </div>
            <MenuLink href="/login" icon={<LogIn size={14} />} onClick={() => setOpen(false)}>
              Sign In
            </MenuLink>
            <MenuLink href="/register" icon={<UserPlus size={14} />} onClick={() => setOpen(false)}>
              Sign Up
            </MenuLink>
            <div className="h-px bg-white/[0.06] mx-1 my-1" />
            <MenuLink href="/login" icon={<GoogleGlyph />} onClick={() => setOpen(false)}>
              Continue with Google
            </MenuLink>
          </>
        )}
      </PopoverPortal>
    </div>
  )
}

function MenuLink({ href, icon, children, onClick }: {
  href: string
  icon: React.ReactNode
  children: React.ReactNode
  onClick?: () => void
}) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className="tb2-row flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs text-white/70 hover:bg-white/[0.06] hover:text-white"
    >
      <span className="text-white/40">{icon}</span>
      {children}
    </Link>
  )
}

function GoogleGlyph() {
  return (
    <svg width="14" height="14" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.4 0 6.4 1.2 8.8 3.5l6.5-6.5C35.3 2.6 30 0.5 24 0.5 14.9 0.5 7.1 5.7 3.4 13.3l7.6 5.9C12.8 13.1 17.9 9.5 24 9.5z"/>
      <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.6c-.5 3-2.2 5.5-4.7 7.2l7.3 5.7c4.3-4 6.8-9.8 6.8-17.4z"/>
      <path fill="#FBBC05" d="M11 19.2 3.4 13.3C1.8 16.5.9 20.1.9 24s.9 7.5 2.5 10.7l7.7-6c-.9-2.7-.9-5.7.1-9.5z"/>
      <path fill="#34A853" d="M24 47.5c6 0 11.3-2 15.1-5.4l-7.3-5.7c-2 1.4-4.7 2.2-7.8 2.2-6.1 0-11.2-3.6-13.1-8.6l-7.7 6C7.1 42.3 14.9 47.5 24 47.5z"/>
    </svg>
  )
}
