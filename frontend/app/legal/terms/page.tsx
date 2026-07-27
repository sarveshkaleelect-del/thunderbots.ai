import type { Metadata } from 'next'
import { Scale } from 'lucide-react'
import { LegalLayout, LegalSection } from '@/components/legal/LegalLayout'
import { siteConfig } from '@/lib/siteConfig'

export const metadata: Metadata = {
  title: 'Terms & Conditions',
  description: `The terms that govern your use of ${siteConfig.name}.`,
}

export default function TermsPage() {
  return (
    <LegalLayout title="Terms & Conditions" updated="July 26, 2026" icon={<Scale size={13} />}>
      <p>
        These Terms &amp; Conditions (&quot;Terms&quot;) govern your access to and use of {siteConfig.name},
        including our website, applications, and services (collectively, the &quot;Service&quot;). By creating
        an account or using the Service, you agree to be bound by these Terms.
      </p>

      <LegalSection title="1. Eligibility & Accounts">
        <p>
          You must be at least 16 years old and capable of forming a binding contract to use the Service. You
          are responsible for maintaining the confidentiality of your account credentials and for all activity
          under your account.
        </p>
      </LegalSection>

      <LegalSection title="2. Use of the Service">
        <ul>
          <li>You may build, train, and deploy AI agents and workflows for lawful business or personal purposes.</li>
          <li>You retain ownership of workflows, prompts, and content you upload to the Service.</li>
          <li>You are responsible for the accuracy and legality of the data you connect to Knowledge Bases and agents.</li>
          <li>You must not use the Service to build agents that violate our <a href="/legal/acceptable-use">Acceptable Use Policy</a>.</li>
        </ul>
      </LegalSection>

      <LegalSection title="3. Subscriptions & Billing">
        <p>
          Paid plans are billed in advance on a recurring basis as described at checkout. Fees are
          non-refundable except as set out in our <a href="/legal/refund-policy">Refund &amp; Cancellation Policy</a>.
          We may change pricing with advance notice; continued use after a price change constitutes acceptance.
        </p>
      </LegalSection>

      <LegalSection title="4. Third-Party Integrations">
        <p>
          The Service is powered by Google Gemini as its sole AI model provider, and allows you to connect
          other third-party services such as WhatsApp, Instagram, Telegram, and payment providers. Your use of
          those integrations is subject to the relevant third party&apos;s own terms, and we are not
          responsible for their availability, accuracy, or content. See our{' '}
          <a href="/legal/ai-usage">AI Usage &amp; Limitations</a> page for details on our AI provider.
        </p>
      </LegalSection>

      <LegalSection title="5. Intellectual Property">
        <p>
          The Service, including its software, design, and branding, is owned by {siteConfig.name} and protected
          by intellectual property laws. Nothing in these Terms grants you rights to our trademarks or brand
          assets except as necessary to use the Service as intended.
        </p>
      </LegalSection>

      <LegalSection title="6. Termination">
        <p>
          You may cancel your account at any time from your settings. We may suspend or terminate accounts that
          violate these Terms, our Acceptable Use Policy, or applicable law, with notice where reasonably
          possible.
        </p>
      </LegalSection>

      <LegalSection title="7. Disclaimers & Limitation of Liability">
        <p>
          The Service is provided &quot;as is&quot; without warranties of any kind, to the maximum extent
          permitted by law. See our <a href="/legal/disclaimer">Disclaimer</a> for details. To the extent
          permitted by law, {siteConfig.name} shall not be liable for indirect, incidental, or consequential
          damages arising from your use of the Service.
        </p>
      </LegalSection>

      <LegalSection title="8. Changes to These Terms">
        <p>
          We may update these Terms from time to time. We will notify you of material changes via the Service
          or email. Continued use after changes take effect constitutes acceptance of the revised Terms.
        </p>
      </LegalSection>

      <LegalSection title="9. Governing Law">
        <p>
          These Terms are governed by the laws of the jurisdiction in which {siteConfig.name} is incorporated,
          without regard to conflict-of-law principles, unless otherwise required by applicable local law.
        </p>
      </LegalSection>

      <LegalSection title="10. Contact">
        <p>
          Questions about these Terms? Contact <a href={`mailto:${siteConfig.legalEmail}`}>{siteConfig.legalEmail}</a>.
        </p>
      </LegalSection>
    </LegalLayout>
  )
}
