import { FileText } from 'lucide-react'
import { SubPageBar } from '@/components/ui/TopBar'
import { Footer } from '@/components/ui/Footer'

/**
 * Shared layout for all static legal/informational pages.
 * Purely additive presentation wrapper — reuses the existing SubPageBar +
 * Footer chrome so these pages match the rest of the product visually.
 */
export function LegalLayout({
  title,
  updated,
  icon,
  children,
}: {
  title: string
  updated?: string
  icon?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="tb2-shell flex flex-col min-h-screen">
      <SubPageBar backHref="/dashboard" crumb={title} crumbIcon={icon ?? <FileText size={13} />} />

      <div className="flex-1 max-w-3xl w-full mx-auto px-6 py-10 tb2-rise">
        <h1 className="text-2xl font-bold text-white mb-1.5">{title}</h1>
        {updated && <p className="text-[11px] text-white/30 mb-8">Last updated: {updated}</p>}

        <div className="tb-legal-prose space-y-6 text-[13.5px] leading-relaxed text-white/60">
          {children}
        </div>
      </div>

      <Footer />
    </div>
  )
}

/** Section heading used consistently across legal pages. */
export function LegalSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2.5">
      <h2 className="text-[14.5px] font-bold text-white/85">{title}</h2>
      <div className="space-y-2.5">{children}</div>
    </section>
  )
}
