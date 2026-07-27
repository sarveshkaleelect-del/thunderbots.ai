import type { Metadata } from 'next'
import { RotateCcw } from 'lucide-react'
import { LegalLayout, LegalSection } from '@/components/legal/LegalLayout'
import { siteConfig } from '@/lib/siteConfig'

export const metadata: Metadata = {
  title: 'Refund & Cancellation Policy',
  description: `${siteConfig.name} refund and subscription cancellation terms.`,
}

export default function RefundPolicyPage() {
  return (
    <LegalLayout title="Refund & Cancellation Policy" updated="July 26, 2026" icon={<RotateCcw size={13} />}>
      <p>
        This policy describes how subscription cancellations and refunds work for {siteConfig.name} paid plans.
      </p>

      <LegalSection title="1. Cancelling Your Subscription">
        <p>
          You can cancel your subscription at any time from your account settings. Cancellation stops future
          billing; you retain access to paid features until the end of your current billing period.
        </p>
      </LegalSection>

      <LegalSection title="2. Refund Eligibility">
        <ul>
          <li>New subscribers may request a full refund within 14 days of their first payment.</li>
          <li>Refunds outside this window are considered on a case-by-case basis (e.g. billing errors, service outages).</li>
          <li>Usage-based charges (e.g. metered AI provider costs already incurred) are non-refundable.</li>
        </ul>
      </LegalSection>

      <LegalSection title="3. How to Request a Refund">
        <p>
          Email <a href={`mailto:${siteConfig.supportEmail}`}>{siteConfig.supportEmail}</a> with your account
          email and reason for the request. We aim to respond within 2 business days.
        </p>
      </LegalSection>

      <LegalSection title="4. Downgrades & Plan Changes">
        <p>
          Downgrading your plan takes effect at the start of your next billing cycle; upgrades take effect
          immediately, with any difference prorated where applicable.
        </p>
      </LegalSection>

      <LegalSection title="5. Changes to This Policy">
        <p>
          We may update this policy from time to time; material changes will be reflected in the &quot;Last
          updated&quot; date above.
        </p>
      </LegalSection>
    </LegalLayout>
  )
}
