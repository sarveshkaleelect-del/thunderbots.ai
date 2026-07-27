'use client'
import { useRouter } from 'next/navigation'
import { LifeBuoy, Bug, Lightbulb } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { useToast } from '@/components/ui/Toast'
import { siteConfig } from '@/lib/siteConfig'

function mailto(subject: string) {
  return `mailto:${siteConfig.supportEmail}?subject=${encodeURIComponent(subject)}`
}

/** Lightweight action row: contact support via mail client, or open the dedicated Report a Bug / Feature Request pages. */
export function HelpActions() {
  const router = useRouter()
  const { toast } = useToast()

  const handleContact = () => {
    window.location.href = mailto('Support request')
    toast('info', 'Opening your email client…')
  }

  return (
    <div className="flex flex-wrap gap-2.5">
      <Button variant="primary" size="md" icon={<LifeBuoy size={14} />} onClick={handleContact}>
        Contact Support
      </Button>
      <Button variant="secondary" size="md" icon={<Bug size={14} />} onClick={() => router.push('/report-bug')}>
        Report Bug
      </Button>
      <Button variant="secondary" size="md" icon={<Lightbulb size={14} />} onClick={() => router.push('/feature-request')}>
        Feature Request
      </Button>
    </div>
  )
}
