import type { Metadata } from 'next'
import { Info, Zap, Layers, ShieldCheck, Rocket } from 'lucide-react'
import { SubPageBar } from '@/components/ui/TopBar'
import { Footer } from '@/components/ui/Footer'
import { Card } from '@/components/ui/Card'
import { siteConfig } from '@/lib/siteConfig'

export const metadata: Metadata = {
  title: 'About Us',
  description: `Learn about ${siteConfig.name}, the visual AI agent builder and chatbot workflow platform.`,
}

const VALUES = [
  { icon: Layers, title: 'Build visually', text: 'Design agent workflows on a canvas, not in a maze of config files.' },
  { icon: Zap, title: 'Move fast', text: 'From idea to a deployed AI agent in minutes, not sprints.' },
  { icon: ShieldCheck, title: 'Take security seriously', text: 'Regular audits and a security-first engineering culture.' },
  { icon: Rocket, title: 'Scale with you', text: 'From a single workflow to fleets of agents across channels.' },
]

export default function AboutPage() {
  return (
    <div className="tb2-shell flex flex-col min-h-screen">
      <SubPageBar backHref="/dashboard" crumb="About Us" crumbIcon={<Info size={13} />} />

      <div className="flex-1 max-w-4xl w-full mx-auto px-6 py-10 space-y-10 tb2-rise">
        <div className="space-y-3">
          <h1 className="text-2xl font-bold text-white">About {siteConfig.name}</h1>
          <p className="text-sm text-white/50 max-w-2xl leading-relaxed">
            {siteConfig.name} is a visual AI agent builder and chatbot workflow platform, powered by Google
            Gemini. We help teams design, train, and deploy AI agents — backed by their own knowledge bases —
            across WhatsApp and other channels, without stitching together a dozen disconnected tools. Beyond
            AI Chat and the Workflow Builder, the platform includes the Smart Shop Assistant, AI Business
            Advisor, AI Customer Insights, AI Calls, Analytics, Reservations, Product Images, and Team
            Workspace for collaborating with your team.
          </p>
        </div>

        <div>
          <h2 className="text-sm font-bold text-white/70 mb-3">What we care about</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {VALUES.map(v => (
              <Card key={v.title} className="p-5 space-y-2">
                <div className="w-9 h-9 rounded-xl tb2-brand-mark flex items-center justify-center text-[#a5b4fc]">
                  <v.icon size={16} />
                </div>
                <p className="text-sm font-semibold text-white/80">{v.title}</p>
                <p className="text-[12.5px] text-white/40 leading-relaxed">{v.text}</p>
              </Card>
            ))}
          </div>
        </div>

        <Card className="p-6 space-y-2">
          <p className="text-sm font-semibold text-white/80">Get in touch</p>
          <p className="text-[12.5px] text-white/40 leading-relaxed max-w-lg">
            Want to talk to us about a partnership, press inquiry, or just say hello? Visit our{' '}
            <a href="/contact" className="text-[#818cf8] hover:text-cyan-300 hover:underline">Contact page</a> or
            email <a href={`mailto:${siteConfig.supportEmail}`} className="text-[#818cf8] hover:text-cyan-300 hover:underline">{siteConfig.supportEmail}</a>.
          </p>
        </Card>
      </div>

      <Footer />
    </div>
  )
}
