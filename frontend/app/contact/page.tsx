import type { Metadata } from 'next'
import { Mail, LifeBuoy, Bug, Lightbulb, HelpCircle } from 'lucide-react'
import { SubPageBar } from '@/components/ui/TopBar'
import { Footer } from '@/components/ui/Footer'
import { Card } from '@/components/ui/Card'
import { siteConfig } from '@/lib/siteConfig'

export const metadata: Metadata = {
  title: 'Contact Us',
  description: `Get in touch with the ${siteConfig.name} team.`,
}

const CONTACT_OPTIONS = [
  {
    icon: LifeBuoy,
    title: 'General Support',
    text: 'Account, billing, or platform questions.',
    href: `mailto:${siteConfig.supportEmail}?subject=${encodeURIComponent('Support request')}`,
    email: siteConfig.supportEmail,
  },
  {
    icon: Bug,
    title: 'Report a Bug',
    text: 'Found something broken? Let us know the details.',
    href: '/report-bug',
    email: null,
  },
  {
    icon: Lightbulb,
    title: 'Feature Request',
    text: 'Suggest an idea to improve the platform.',
    href: '/feature-request',
    email: null,
  },
  {
    icon: HelpCircle,
    title: 'Help Center',
    text: 'Browse guides and frequently asked questions.',
    href: '/help',
    email: null,
  },
]

export default function ContactPage() {
  return (
    <div className="tb2-shell flex flex-col min-h-screen">
      <SubPageBar backHref="/dashboard" crumb="Contact Us" crumbIcon={<Mail size={13} />} />

      <div className="flex-1 max-w-3xl w-full mx-auto px-6 py-10 space-y-8 tb2-rise">
        <div className="space-y-2">
          <h1 className="text-2xl font-bold text-white">Contact Us</h1>
          <p className="text-sm text-white/50 max-w-lg">
            Whichever way you reach out, we&apos;ll get back to you as soon as we can. For urgent account or
            billing issues, email is the fastest path.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {CONTACT_OPTIONS.map(opt => (
            <a key={opt.title} href={opt.href}>
              <Card hover className="p-5 space-y-2 h-full">
                <div className="w-9 h-9 rounded-xl tb2-brand-mark flex items-center justify-center text-[#a5b4fc]">
                  <opt.icon size={16} />
                </div>
                <p className="text-sm font-semibold text-white/80">{opt.title}</p>
                <p className="text-[12.5px] text-white/40 leading-relaxed">{opt.text}</p>
                {opt.email && <p className="text-[12px] text-[#818cf8]">{opt.email}</p>}
              </Card>
            </a>
          ))}
        </div>

        <Card className="p-5">
          <p className="text-[12.5px] text-white/40">
            Support email: <a href={`mailto:${siteConfig.supportEmail}`} className="text-[#818cf8] hover:text-cyan-300 hover:underline">{siteConfig.supportEmail}</a>
            {' · '}Response time: within 2 business days
          </p>
        </Card>
      </div>

      <Footer />
    </div>
  )
}
