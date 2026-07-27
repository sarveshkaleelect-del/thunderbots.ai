'use client'
import Link from 'next/link'
import { HelpCircle, Mail } from 'lucide-react'
import { siteConfig, LEGAL_LINKS, COMPANY_LINKS, FEEDBACK_LINKS } from '@/lib/siteConfig'
import { Logo } from './Logo'

/** Full footer with legal, company, and feedback links. Purely additive — safe to drop into any page without affecting page logic. */
export function Footer() {
  return (
    <footer className="border-t border-white/[0.06] px-6 py-8 mt-auto">
      <div className="max-w-6xl mx-auto space-y-5">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 text-[11.5px]">
          <FooterColumn title="Legal" links={LEGAL_LINKS} />
          <FooterColumn title="Company" links={COMPANY_LINKS} />
          <FooterColumn title="Feedback" links={FEEDBACK_LINKS} />
          <div className="space-y-2">
            <p className="text-white/25 font-semibold uppercase tracking-wider text-[10px]">Support</p>
            <a
              href={`mailto:${siteConfig.supportEmail}`}
              className="flex items-center gap-1.5 text-white/40 hover:text-white/70 transition-colors"
            >
              <Mail size={12} />
              {siteConfig.supportEmail}
            </a>
          </div>
        </div>

        <div className="pt-5 border-t border-white/[0.06] flex flex-col sm:flex-row items-center justify-between gap-3 text-[11px] text-white/30">
          <span className="flex items-center gap-2">
            <Logo size={16} />
            &copy; {new Date().getFullYear()} {siteConfig.name}. All rights reserved.
          </span>
          <span className="flex items-center gap-4">
            <span className="text-white/20">v{siteConfig.version}</span>
            <Link href="/help" className="flex items-center gap-1.5 hover:text-white/70 transition-colors">
              <HelpCircle size={12} />
              Help Center
            </Link>
          </span>
        </div>
      </div>
    </footer>
  )
}

function FooterColumn({ title, links }: { title: string; links: ReadonlyArray<{ href: string; label: string }> }) {
  return (
    <div className="space-y-2">
      <p className="text-white/25 font-semibold uppercase tracking-wider text-[10px]">{title}</p>
      <nav className="flex flex-col gap-1.5">
        {links.map(link => (
          <Link key={link.href} href={link.href} className="text-white/40 hover:text-white/70 transition-colors">
            {link.label}
          </Link>
        ))}
      </nav>
    </div>
  )
}
