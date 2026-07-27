'use client'
/**
 * AI Call Agent — shared module navigation (NEW, Voice AI Part 5)
 *
 * One tab strip reused by every /call-agent/* page so the module reads as
 * a single standalone product with 12 sections, instead of a scattered
 * set of routes. Knowledge Base / Text Knowledge Base / Instructions are
 * intentionally NOT separate top-level pages here — they are per-Voice-
 * Agent configuration (a Knowledge Base with no agent to belong to is
 * meaningless), so they live as tabs inside /call-agent/agents/[id]
 * instead. Clicking "Voice Agents" is the way in to all three.
 */
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard, Bot, Mic2, MessagesSquare, BarChart3, Code2, Phone, PhoneCall, Settings,
} from 'lucide-react'
import { cn } from '@/lib/utils/cn'

const TABS = [
  { href: '/call-agent', label: 'Dashboard', icon: LayoutDashboard, exact: true },
  { href: '/call-agent/agents', label: 'Voice Agents', icon: Bot },
  { href: '/call-agent/voices', label: 'Voices', icon: Mic2 },
  { href: '/call-agent/conversations', label: 'Conversations', icon: MessagesSquare },
  { href: '/call-agent/analytics', label: 'Analytics', icon: BarChart3 },
  { href: '/call-agent/embed', label: 'Embed', icon: Code2 },
  { href: '/call-agent/phone', label: 'Phone Numbers', icon: Phone },
  { href: '/call-agent/calls', label: 'Calls', icon: PhoneCall },
  { href: '/call-agent/settings', label: 'Settings', icon: Settings },
]

export function CallAgentNav() {
  const pathname = usePathname()
  return (
    <nav className="max-w-6xl mx-auto px-3 sm:px-6 pt-4 sm:pt-5" data-tutorial="call-agent-nav">
      <div className="tb2-glass flex items-center gap-1 p-1 rounded-2xl overflow-x-auto no-scrollbar">
        {TABS.map(tab => {
          const active = tab.exact ? pathname === tab.href : pathname?.startsWith(tab.href)
          const Icon = tab.icon
          return (
            <Link
              key={tab.href}
              href={tab.href}
              data-tutorial={tab.href === '/call-agent/embed' ? 'call-agent-embed' : undefined}
              className={cn(
                'flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-xl whitespace-nowrap transition flex-shrink-0',
                active ? 'bg-white/[0.08] text-white' : 'text-white/40 hover:text-white/75 hover:bg-white/[0.04]'
              )}
            >
              <Icon size={13} />
              {tab.label}
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
