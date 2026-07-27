import type { Metadata } from 'next'
import { Cookie } from 'lucide-react'
import { LegalLayout, LegalSection } from '@/components/legal/LegalLayout'
import { siteConfig } from '@/lib/siteConfig'

export const metadata: Metadata = {
  title: 'Cookie Policy',
  description: `How ${siteConfig.name} uses cookies and similar technologies.`,
}

export default function CookiePolicyPage() {
  return (
    <LegalLayout title="Cookie Policy" updated="July 26, 2026" icon={<Cookie size={13} />}>
      <p>
        This Cookie Policy explains how {siteConfig.name} uses cookies and similar technologies to recognize
        you when you visit the Service, and the choices available to you.
      </p>

      <LegalSection title="1. What Are Cookies">
        <p>
          Cookies are small text files placed on your device that help websites and apps function, remember
          preferences (such as your selected theme), and understand how the Service is used.
        </p>
      </LegalSection>

      <LegalSection title="2. Types of Cookies We Use">
        <ul>
          <li><strong>Essential cookies:</strong> required for authentication, session management, and core platform functionality.</li>
          <li><strong>Preference cookies:</strong> remember settings like your chosen theme or workspace.</li>
          <li><strong>Analytics cookies:</strong> help us understand feature usage so we can improve the Service.</li>
        </ul>
      </LegalSection>

      <LegalSection title="3. Managing Cookies">
        <p>
          Most browsers let you refuse or delete cookies via their settings. Disabling essential cookies may
          prevent parts of the Service, such as sign-in, from working correctly.
        </p>
      </LegalSection>

      <LegalSection title="4. Changes to This Policy">
        <p>
          We may update this Cookie Policy periodically. Material changes will be reflected by an updated
          &quot;Last updated&quot; date above.
        </p>
      </LegalSection>

      <LegalSection title="5. Contact">
        <p>
          Questions? Reach us at <a href={`mailto:${siteConfig.legalEmail}`}>{siteConfig.legalEmail}</a>.
        </p>
      </LegalSection>
    </LegalLayout>
  )
}
