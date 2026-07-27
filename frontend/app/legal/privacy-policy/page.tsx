import type { Metadata } from 'next'
import { ShieldCheck } from 'lucide-react'
import { LegalLayout, LegalSection } from '@/components/legal/LegalLayout'
import { siteConfig } from '@/lib/siteConfig'

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: `How ${siteConfig.name} collects, uses, and protects your data.`,
}

export default function PrivacyPolicyPage() {
  return (
    <LegalLayout title="Privacy Policy" updated="July 26, 2026" icon={<ShieldCheck size={13} />}>
      <p>
        This Privacy Policy explains how {siteConfig.name} (&quot;we&quot;, &quot;us&quot;, or &quot;our&quot;)
        collects, uses, discloses, and safeguards information when you use our visual AI agent builder and
        chatbot workflow platform (the &quot;Service&quot;), including AI Chat, the Workflow Builder,
        Knowledge Base, Smart Shop Assistant, AI Business Advisor, AI Customer Insights, AI Calls, Analytics,
        Reservations, Product Images, and Team Workspace. By using the Service, you agree to the practices
        described here.
      </p>

      <LegalSection title="1. Information We Collect">
        <ul>
          <li><strong>Account information:</strong> name, email address, password hash, and organization details you provide at sign-up.</li>
          <li><strong>Workflow &amp; content data:</strong> workflows, nodes, agent configurations, Knowledge Base documents, and chat/WhatsApp/Telegram/Instagram conversation data you create or connect.</li>
          <li><strong>Voice &amp; call data:</strong> call recordings, transcripts, and phone numbers connected to AI Calls, where that feature is enabled.</li>
          <li><strong>Commerce data:</strong> product listings, product images, orders, and reservations you manage through the Smart Shop Assistant.</li>
          <li><strong>Business &amp; analytics data:</strong> conversation, sales, and usage activity used to generate AI Business Advisor summaries, AI Customer Insights, and Analytics dashboards.</li>
          <li><strong>Team data:</strong> members, roles, and permissions you configure within Team Workspace.</li>
          <li><strong>Usage data:</strong> log data, device/browser information, IP address, and analytics events used to operate and improve the Service.</li>
          <li><strong>Payment data:</strong> billing details are processed by our payment provider; we do not store full card numbers.</li>
        </ul>
      </LegalSection>

      <LegalSection title="2. How We Use Information">
        <ul>
          <li>To provide, operate, and maintain the Service, including running your workflows, AI agents, Smart Shop Assistant, AI Business Advisor, and AI Calls.</li>
          <li>To generate embeddings and power retrieval for your Knowledge Base, and to power AI Chat, AI Customer Insights, and other AI features, using Google Gemini.</li>
          <li>To communicate with you about updates, security notices, and support requests.</li>
          <li>To monitor, detect, and prevent fraud, abuse, and security incidents.</li>
          <li>To improve platform performance, reliability, and features.</li>
        </ul>
      </LegalSection>

      <LegalSection title="3. Third-Party AI Providers">
        <p>
          {siteConfig.name} uses <strong>Google Gemini</strong> as its sole third-party AI model provider for
          embeddings, chat and agent responses, and every other AI-powered feature described in our{' '}
          <a href="/legal/ai-usage">AI Usage &amp; Limitations</a> page. We do not send your content to
          OpenAI, Anthropic (Claude), xAI (Grok), DeepSeek, OpenRouter, Ollama, Hugging Face, Together AI, or
          any other model provider. Content sent to Gemini is subject to Google&apos;s own terms and privacy
          policy, and we recommend reviewing Google&apos;s privacy practices as well.
        </p>
      </LegalSection>

      <LegalSection title="4. Data Sharing">
        <p>
          We do not sell your personal information. We may share data with service providers who help us operate
          the Service (hosting, analytics, email delivery, payment processing), each bound by confidentiality
          obligations, or when required by law, legal process, or to protect the rights and safety of our users.
        </p>
      </LegalSection>

      <LegalSection title="5. Data Retention">
        <p>
          We retain account and workflow data for as long as your account is active or as needed to provide the
          Service. You may request deletion of your account and associated data at any time by contacting{' '}
          <a href={`mailto:${siteConfig.legalEmail}`}>{siteConfig.legalEmail}</a>.
        </p>
      </LegalSection>

      <LegalSection title="6. Security">
        <p>
          We use industry-standard technical and organizational measures — including encryption in transit,
          access controls, and regular audits — to protect your information. No method of transmission or
          storage is completely secure, and we cannot guarantee absolute security.
        </p>
      </LegalSection>

      <LegalSection title="7. Your Rights">
        <ul>
          <li>Access, correct, or export the personal data we hold about you.</li>
          <li>Request deletion of your account and associated data.</li>
          <li>Opt out of non-essential communications at any time.</li>
          <li>Depending on your jurisdiction (e.g. GDPR, CCPA), additional rights may apply.</li>
        </ul>
      </LegalSection>

      <LegalSection title="8. Cookies">
        <p>
          We use cookies and similar technologies as described in our <a href="/legal/cookie-policy">Cookie Policy</a>.
        </p>
      </LegalSection>

      <LegalSection title="9. Children's Privacy">
        <p>The Service is not directed to individuals under 16, and we do not knowingly collect their data.</p>
      </LegalSection>

      <LegalSection title="10. Changes to This Policy">
        <p>
          We may update this Privacy Policy from time to time. Material changes will be communicated via the
          Service or by email. Continued use of the Service after changes take effect constitutes acceptance.
        </p>
      </LegalSection>

      <LegalSection title="11. Contact Us">
        <p>
          Questions about this policy? Reach us at <a href={`mailto:${siteConfig.legalEmail}`}>{siteConfig.legalEmail}</a>{' '}
          or visit our <a href="/contact">Contact page</a>.
        </p>
      </LegalSection>
    </LegalLayout>
  )
}
