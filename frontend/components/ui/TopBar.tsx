'use client'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { LayoutDashboard, BarChart3, MessageCircle, Instagram, Send, Settings, ChevronLeft, Store, ShieldCheck, Users, Sparkles, HelpCircle, Menu, X, Megaphone, Headset, RadioTower, Mail, MoreHorizontal, Phone, ShoppingBag } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import { useIsAdmin } from '@/hooks/useAdmin'
import { SearchTrigger, NotificationsMenu, ThemeMenu, AccountMenu, PopoverPortal, panelCls, usePopover, TB2_DROPDOWN_Z } from './TopBarMenus'
import { Logo } from './Logo'

const CREATE_WITH_AI_HREF = '/create-with-ai'

// Row 1 — primary workspace nav: the tools someone reaches for constantly.
const PRIMARY_NAV_ITEMS = [
  { href: '/dashboard', label: 'Workflows', icon: LayoutDashboard },
  { href: CREATE_WITH_AI_HREF, label: 'Create with AI', icon: Sparkles, highlight: true },
  { href: '/campaigns', label: 'Campaigns', icon: Megaphone },
  { href: '/live-agent', label: 'Live Agent', icon: Headset },
  { href: '/ai-supervisor', label: 'AI Supervisor', icon: RadioTower },
  { href: '/analytics', label: 'Analytics', icon: BarChart3 },
]

// Row 2 — channels + secondary/admin pages. Same routes as before, just
// visually demoted to their own row so row 1 stops competing for space.
const SECONDARY_NAV_ITEMS = [
  { href: '/whatsapp', label: 'WhatsApp', icon: MessageCircle },
  { href: '/instagram', label: 'Instagram', icon: Instagram },
  { href: '/telegram', label: 'Telegram', icon: Send },
  { href: '/call-agent', label: 'AI Call Agent', icon: Phone },
  { href: '/personal-email', label: 'Personal Email AI', icon: Mail },
  { href: '/teams', label: 'Teams', icon: Users },
  { href: '/shop-assistant', label: 'Smart Shop Assistant', icon: ShoppingBag },
  { href: '/marketplace', label: 'Marketplace', icon: Store },
  { href: '/help', label: 'Help', icon: HelpCircle },
  { href: '/settings', label: 'Settings', icon: Settings },
]

export function Brand({ compact }: { compact?: boolean }) {
  return (
    <Link href="/dashboard" className="flex items-center gap-2.5 group">
      <Logo size={compact ? 24 : 28} />
      {!compact && <span className="font-bold text-white tracking-tight">ThunderBots</span>}
    </Link>
  )
}

type NavItem = { href: string; label: string; icon: any; highlight?: boolean }

/** Compact "More" popover for row 2 items when the viewport is too narrow
 *  for the full second row (tablet widths) but wide enough to be past the
 *  mobile hamburger breakpoint. Same popover pattern as Notifications/Theme. */
function MoreNavMenu({ items, pathname }: { items: NavItem[]; pathname: string | null }) {
  const { open, setOpen, triggerRef, panelRef } = usePopover<HTMLDivElement>()
  const active = items.some(item => pathname?.startsWith(item.href))
  return (
    <div className="relative flex-shrink-0" ref={triggerRef}>
      <button
        type="button"
        aria-label="More navigation"
        aria-expanded={open}
        onClick={() => setOpen(o => !o)}
        className={cn(
          'tb2-tab flex items-center gap-1.5 text-xs font-medium pb-0.5 whitespace-nowrap',
          active ? 'tb2-tab-active text-white' : 'text-white/40 hover:text-white/75'
        )}
      >
        <MoreHorizontal size={13} />
        More
      </button>
      <PopoverPortal open={open} triggerRef={triggerRef} panelRef={panelRef} className={cn(panelCls, 'w-56 p-1.5')}>
        {items.map(item => {
          const itemActive = pathname?.startsWith(item.href)
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setOpen(false)}
              className={cn(
                'tb2-row flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs',
                itemActive ? 'bg-white/[0.08] text-white' : 'text-white/70 hover:bg-white/[0.06] hover:text-white'
              )}
            >
              <item.icon size={14} className={itemActive ? 'text-[#a5b4fc]' : 'text-white/40'} />
              {item.label}
            </Link>
          )
        })}
      </PopoverPortal>
    </div>
  )
}

/** Sticky glass top bar with the primary nav, laid out across two responsive
 *  rows so it no longer crowds at laptop widths / 100% zoom. Row 1 carries
 *  the primary workspace tools + the right-side actions (search, notifications,
 *  profile, page action). Row 2 carries channels + secondary/admin pages.
 *  Used by dashboard, campaigns, teams, marketplace, live-agent, personal-email, admin. */
export function TopBar({ right }: { right?: React.ReactNode }) {
  const pathname = usePathname()
  // NEW (Admin Dashboard): the Admin link only ever renders for is_admin=True
  // users — a silent 401/network hiccup here just means the link doesn't show,
  // it never breaks the rest of the nav for anyone else.
  const me = useIsAdmin()
  const secondaryNavItems = me.data?.is_admin
    ? [...SECONDARY_NAV_ITEMS, { href: '/admin', label: 'Admin', icon: ShieldCheck }]
    : SECONDARY_NAV_ITEMS
  // Full flat list — used by the mobile drawer, which has no row split.
  const allNavItems = [...PRIMARY_NAV_ITEMS, ...secondaryNavItems]

  // Mobile nav drawer — below md the full nav has nowhere to live, so it
  // was previously simply unreachable on phones/small tablets other than the
  // dashboard link on the logo. This restores those routes on small screens
  // via a standard hamburger + slide-down panel, purely presentational.
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const headerRef = useRef<HTMLElement>(null)
  const [headerBottom, setHeaderBottom] = useState(0)
  useEffect(() => { setMobileNavOpen(false) }, [pathname])
  useEffect(() => {
    if (!mobileNavOpen) return
    const updateBottom = () => setHeaderBottom(headerRef.current?.getBoundingClientRect().bottom ?? 0)
    updateBottom()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMobileNavOpen(false) }
    document.addEventListener('keydown', onKey)
    window.addEventListener('resize', updateBottom)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', updateBottom)
      document.body.style.overflow = ''
    }
  }, [mobileNavOpen])

  return (
    <header ref={headerRef} className="tb2-topbar tb2-topbar-header sticky top-0 z-[100]">
      {/* Row 1 — brand, primary nav, and the fixed-intent right rail
          (search / notifications / profile / page action). */}
      <div className="px-3 sm:px-6 py-3 sm:py-3.5 flex items-center gap-2 sm:gap-4">
        {/* Left: navigation/actions — fixed-intent width, allowed to shrink
            its own nav row (which already scrolls horizontally) but never
            gives up space to the flexible center. */}
        <div className="tb2-topbar-left flex items-center gap-3 sm:gap-7 min-w-0 flex-shrink-0">
          <button
            type="button"
            aria-label={mobileNavOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={mobileNavOpen}
            onClick={() => setMobileNavOpen(o => !o)}
            className="tb2-iconbtn md:hidden flex items-center justify-center w-11 h-11 -ml-1 rounded-xl text-white/50 hover:text-white/85 flex-shrink-0"
          >
            {mobileNavOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
          <Brand />
          <nav className="hidden md:flex items-center gap-5 lg:gap-6 min-w-0 overflow-x-auto no-scrollbar" aria-label="Primary">
            {PRIMARY_NAV_ITEMS.map(item => {
              const active = pathname?.startsWith(item.href)
              const highlighted = item.highlight
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    'tb2-tab flex items-center gap-1.5 text-xs font-medium pb-0.5 whitespace-nowrap',
                    highlighted
                      ? 'tb2-nav-ai-glow px-2.5 py-1 rounded-lg text-[#c7d2fe] hover:text-white'
                      : active ? 'tb2-tab-active text-white' : 'text-white/40 hover:text-white/75'
                  )}
                >
                  <item.icon size={13} className={highlighted ? 'text-[#a5b4fc]' : undefined} />
                  {item.label}
                </Link>
              )
            })}
            {/* Tablet-width fallback: row 2 is hidden below xl, so its routes
                stay reachable here instead of overlapping row 1. */}
            <div className="xl:hidden">
              <MoreNavMenu items={secondaryNavItems} pathname={pathname} />
            </div>
          </nav>
        </div>

        {/* Center: flexible section — absorbs/yields available width so page
            actions (Create with AI / New Workflow) and the search field grow
            or shrink in normal flow instead of overlapping anything. Search
            sits last so its flex:1 expansion only ever consumes the space
            already reserved for this section. */}
        <div className="tb2-topbar-center flex-1 min-w-0 flex items-center justify-end gap-1 sm:gap-2">
          {/* Mobile-only entry point: the full nav (including this item) is
              hidden below md, so Create with AI gets a compact glowing icon
              button here to stay reachable on small screens. */}
          <Link
            href={CREATE_WITH_AI_HREF}
            aria-label="Create with AI"
            className="tb2-nav-ai-glow md:hidden flex items-center justify-center w-11 h-11 sm:w-9 sm:h-9 rounded-xl text-[#a5b4fc] mr-0.5 flex-shrink-0"
          >
            <Sparkles size={15} />
          </Link>
          {right && <div className="flex items-center gap-1 sm:gap-2 flex-shrink-0">{right}</div>}
          {right && <div className="w-px h-5 bg-white/10 mx-1.5 hidden sm:block flex-shrink-0" />}
          <SearchTrigger />
        </div>

        {/* Right: notifications/profile — fixed width, always visible, never
            the flex target that shrinks or gets covered. */}
        <div className="tb2-topbar-right flex items-center gap-0.5 sm:gap-1 flex-shrink-0">
          <NotificationsMenu />
          <ThemeMenu />
          <AccountMenu />
        </div>
      </div>

      {/* Row 2 — channels + secondary/admin pages. Hidden below xl (where
          MoreNavMenu takes over) and below md (where the mobile drawer
          already carries every route). */}
      <nav
        className="tb2-topbar-row2 hidden xl:flex items-center gap-6 px-3 sm:px-6 min-w-0 overflow-x-auto no-scrollbar"
        aria-label="Channels"
      >
        {secondaryNavItems.map(item => {
          const active = pathname?.startsWith(item.href)
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'tb2-tab flex items-center gap-1.5 text-[11px] font-medium py-2 pb-2.5 whitespace-nowrap',
                active ? 'tb2-tab-active text-white' : 'text-white/35 hover:text-white/70'
              )}
            >
              <item.icon size={12} />
              {item.label}
            </Link>
          )
        })}
      </nav>

      {mobileNavOpen && typeof document !== 'undefined' && createPortal(
        <>
          <div
            className="fixed inset-0 bg-black/60 backdrop-blur-sm md:hidden"
            style={{ top: headerBottom, zIndex: TB2_DROPDOWN_Z }}
            onClick={() => setMobileNavOpen(false)}
          />
          <nav
            className="tb2-glass tb2-popover-in p-2 rounded-2xl shadow-2xl md:hidden max-h-[calc(100vh-90px)] overflow-y-auto"
            style={{ position: 'fixed', left: 8, right: 8, top: headerBottom + 4, zIndex: TB2_DROPDOWN_Z + 1 }}
            aria-label="Primary"
          >
            {allNavItems.map(item => {
              const active = pathname?.startsWith(item.href)
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    'flex items-center gap-3 px-3 py-3 rounded-xl text-sm font-medium min-h-[44px]',
                    active ? 'bg-white/[0.08] text-white' : 'text-white/60 hover:bg-white/[0.06] hover:text-white'
                  )}
                >
                  <item.icon size={16} className={active ? 'text-[#a5b4fc]' : 'text-white/35'} />
                  {item.label}
                </Link>
              )
            })}
          </nav>
        </>,
        document.body
      )}
    </header>
  )
}

/** Slim breadcrumb-style header for nested pages (settings, whatsapp detail, api-keys). */
export function SubPageBar({
  backHref = '/dashboard',
  crumb,
  crumbIcon,
  right,
}: {
  backHref?: string
  crumb: string
  crumbIcon?: React.ReactNode
  right?: React.ReactNode
}) {
  return (
    <header className="tb2-topbar sticky top-0 z-20 px-3 sm:px-6 py-3 sm:py-3.5 flex items-center gap-2 sm:gap-4">
      <Link href={backHref} className="tb2-iconbtn text-white/30 hover:text-white/70 transition w-11 h-11 sm:w-9 sm:h-9 flex items-center justify-center flex-shrink-0">
        <ChevronLeft size={16} />
      </Link>
      <Brand compact />
      <span className="text-white/15 hidden sm:inline">/</span>
      <div className="flex items-center gap-1.5 text-sm text-white/50 min-w-0 truncate" data-tutorial="page-header">
        {crumbIcon}
        <span className="truncate">{crumb}</span>
      </div>
      {right && <div className="ml-auto flex items-center gap-2 flex-shrink-0">{right}</div>}
    </header>
  )
}
