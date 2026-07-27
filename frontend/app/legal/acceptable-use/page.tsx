import type { Metadata } from 'next'
import { ShieldAlert } from 'lucide-react'
import { LegalLayout, LegalSection } from '@/components/legal/LegalLayout'
import { siteConfig } from '@/lib/siteConfig'

export const metadata: Metadata = {
  title: 'Acceptable Use Policy',
  description: `Rules for acceptable use of ${siteConfig.name}.`,
}

export default function AcceptableUsePage() {
  return (
    <LegalLayout title="Acceptable Use Policy" updated="July 26, 2026" icon={<ShieldAlert size={13} />}>
      <p>
        This Acceptable Use Policy describes prohibited uses of {siteConfig.name}. It is part of, and should be
        read alongside, our <a href="/legal/terms">Terms &amp; Conditions</a>.
      </p>

      <LegalSection title="1. Prohibited Content & Conduct">
        <p>You may not use the Service to build, deploy, or distribute agents, workflows, or content that:</p>
        <ul>
          <li>Is illegal, fraudulent, or facilitates illegal activity.</li>
          <li>Infringes intellectual property, privacy, or publicity rights of others.</li>
          <li>Harasses, threatens, defames, or discriminates against any person or group.</li>
          <li>Distributes malware, spam, or performs unauthorized data scraping or security attacks.</li>
          <li>Impersonates a person or organization in a deceptive or harmful manner.</li>
          <li>Generates or facilitates the exploitation or endangerment of minors.</li>
        </ul>
      </LegalSection>

      <LegalSection title="2. Platform Integrity">
        <ul>
          <li>Do not attempt to bypass rate limits, security controls, or usage tiers.</li>
          <li>Do not reverse-engineer or resell the Service without authorization.</li>
          <li>Do not use the Service to build competing products by scraping or copying our platform.</li>
        </ul>
      </LegalSection>

      <LegalSection title="3. Messaging & WhatsApp Deployments">
        <p>
          Agents deployed to WhatsApp or other messaging channels must comply with the messaging provider&apos;s
          policies (including opt-in and anti-spam requirements) and applicable communications law.
        </p>
      </LegalSection>

      <LegalSection title="4. Enforcement">
        <p>
          Violations of this policy may result in content removal, feature restrictions, suspension, or
          termination of your account, at our discretion and depending on severity.
        </p>
      </LegalSection>

      <LegalSection title="5. Reporting Violations">
        <p>
          If you believe an agent or workflow on {siteConfig.name} violates this policy, please contact{' '}
          <a href={`mailto:${siteConfig.legalEmail}`}>{siteConfig.legalEmail}</a> or use our{' '}
          <a href="/report-bug">Report a Bug</a> page.
        </p>
      </LegalSection>
    </LegalLayout>
  )
}
