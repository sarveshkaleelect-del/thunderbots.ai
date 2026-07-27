import type { Metadata } from 'next'
import { Bug } from 'lucide-react'
import { SubPageBar } from '@/components/ui/TopBar'
import { Footer } from '@/components/ui/Footer'
import { Card } from '@/components/ui/Card'
import { BugReportForm } from '@/components/help/BugReportForm'
import { siteConfig } from '@/lib/siteConfig'

export const metadata: Metadata = {
  title: 'Report a Bug',
  description: `Report a bug or issue with ${siteConfig.name}.`,
}

export default function ReportBugPage() {
  return (
    <div className="tb2-shell flex flex-col min-h-screen">
      <SubPageBar backHref="/help" crumb="Report a Bug" crumbIcon={<Bug size={13} />} />

      <div className="flex-1 max-w-xl w-full mx-auto px-6 py-10 space-y-6 tb2-rise">
        <div className="space-y-2">
          <h1 className="text-xl font-bold text-white">Report a Bug</h1>
          <p className="text-sm text-white/40 max-w-md">
            Found something not working as expected? Give us the details below and we&apos;ll take a look.
          </p>
        </div>
        <Card className="p-6">
          <BugReportForm />
        </Card>
      </div>

      <Footer />
    </div>
  )
}
