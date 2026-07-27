import Link from 'next/link'
import { Compass } from 'lucide-react'
import { Brand } from '@/components/ui/TopBar'
import { Footer } from '@/components/ui/Footer'
import { Button } from '@/components/ui/Button'

export default function NotFound() {
  return (
    <div className="tb2-shell flex flex-col min-h-screen">
      <header className="px-6 py-3.5">
        <Brand />
      </header>

      <div className="flex-1 flex flex-col items-center justify-center text-center px-6 py-16 tb2-rise">
        <div className="tb2-float w-16 h-16 rounded-2xl tb2-brand-mark flex items-center justify-center mb-5 text-[#a5b4fc]">
          <Compass size={26} />
        </div>
        <p className="text-6xl font-bold text-white/90 mb-2">404</p>
        <p className="text-white/60 font-semibold mb-1">Page not found</p>
        <p className="text-white/30 text-sm mb-7 max-w-sm">
          The page you&apos;re looking for doesn&apos;t exist, may have moved, or the link may be broken.
        </p>
        <div className="flex items-center gap-3">
          <Link href="/dashboard">
            <Button variant="primary">Back to Dashboard</Button>
          </Link>
          <Link href="/help">
            <Button variant="secondary">Visit Help Center</Button>
          </Link>
        </div>
      </div>

      <Footer />
    </div>
  )
}
