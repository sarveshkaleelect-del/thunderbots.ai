'use client'
import { useEffect } from 'react'
import Link from 'next/link'
import { ServerCrash } from 'lucide-react'
import { Brand } from '@/components/ui/TopBar'
import { Footer } from '@/components/ui/Footer'
import { Button } from '@/components/ui/Button'
import { siteConfig } from '@/lib/siteConfig'

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error('Unhandled application error:', error)
  }, [error])

  return (
    <div className="tb2-shell flex flex-col min-h-screen">
      <header className="px-6 py-3.5">
        <Brand />
      </header>

      <div className="flex-1 flex flex-col items-center justify-center text-center px-6 py-16 tb2-rise">
        <div className="w-16 h-16 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center mb-5">
          <ServerCrash size={26} className="text-red-400" />
        </div>
        <p className="text-6xl font-bold text-white/90 mb-2">500</p>
        <p className="text-white/60 font-semibold mb-1">Something went wrong</p>
        <p className="text-white/30 text-sm mb-1 max-w-sm">
          An unexpected error occurred on our end. Our team has been notified.
        </p>
        {error.digest && <p className="text-white/15 text-[11px] mb-7">Reference: {error.digest}</p>}
        <div className="flex items-center gap-3 mt-6">
          <Button variant="primary" onClick={reset}>Try again</Button>
          <Link href="/dashboard">
            <Button variant="secondary">Back to Dashboard</Button>
          </Link>
        </div>
        <p className="text-white/20 text-[11px] mt-6">
          Still stuck? Contact <a href={`mailto:${siteConfig.supportEmail}`} className="text-[#818cf8] hover:text-cyan-300 hover:underline">{siteConfig.supportEmail}</a>
        </p>
      </div>

      <Footer />
    </div>
  )
}
