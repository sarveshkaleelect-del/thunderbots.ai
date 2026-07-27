import type { Metadata } from 'next'
import { Lightbulb } from 'lucide-react'
import { SubPageBar } from '@/components/ui/TopBar'
import { Footer } from '@/components/ui/Footer'
import { Card } from '@/components/ui/Card'
import { FeatureRequestForm } from '@/components/help/FeatureRequestForm'
import { siteConfig } from '@/lib/siteConfig'

export const metadata: Metadata = {
  title: 'Feature Request',
  description: `Suggest a feature for ${siteConfig.name}.`,
}

export default function FeatureRequestPage() {
  return (
    <div className="tb2-shell flex flex-col min-h-screen">
      <SubPageBar backHref="/help" crumb="Feature Request" crumbIcon={<Lightbulb size={13} />} />

      <div className="flex-1 max-w-xl w-full mx-auto px-6 py-10 space-y-6 tb2-rise">
        <div className="space-y-2">
          <h1 className="text-xl font-bold text-white">Feature Request</h1>
          <p className="text-sm text-white/40 max-w-md">
            Have an idea that would make ThunderBots better? We&apos;d love to hear it.
          </p>
        </div>
        <Card className="p-6">
          <FeatureRequestForm />
        </Card>
      </div>

      <Footer />
    </div>
  )
}
