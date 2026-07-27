import type { Metadata } from 'next'
import { Bot } from 'lucide-react'
import { LegalLayout, LegalSection } from '@/components/legal/LegalLayout'
import { siteConfig } from '@/lib/siteConfig'

export const metadata: Metadata = {
  title: 'AI Usage & Limitations',
  description: `How AI is used across ${siteConfig.name}, which model provider powers it, and its limitations.`,
}

export default function AIUsagePage() {
  return (
    <LegalLayout title="AI Usage & Limitations" updated="July 26, 2026" icon={<Bot size={13} />}>
      <p>
        This page explains how {siteConfig.name} uses artificial intelligence across the platform, which
        model provider powers that AI, and the limitations you should keep in mind when relying on
        AI-generated output.
      </p>

      <LegalSection title="1. Our AI Provider">
        <p>
          {siteConfig.name} is exclusively powered by <strong>Google Gemini</strong>. Gemini is the sole
          third-party large language model provider used to power AI Chat, the Workflow Builder&apos;s AI
          nodes, ThunderGuide, Knowledge Base retrieval, the Smart Shop Assistant, the AI Business Advisor,
          AI Customer Insights, AI Calls, and every other AI-powered feature of the Service. We do not use
          OpenAI, Anthropic (Claude), xAI (Grok), DeepSeek, OpenRouter, Ollama, Hugging Face, Together AI, or
          any other model provider to generate content within the Service.
        </p>
      </LegalSection>

      <LegalSection title="2. Where AI Is Used">
        <ul>
          <li><strong>AI Chat &amp; Workflow Builder:</strong> AI nodes generate conversational responses within your workflows.</li>
          <li><strong>ThunderGuide:</strong> an in-Builder AI assistant that helps design workflows and answer how-to questions.</li>
          <li><strong>Knowledge Base:</strong> documents are embedded and retrieved to ground AI responses in your own content.</li>
          <li><strong>Smart Shop Assistant:</strong> AI-assisted product discovery, customer conversations, and reservation handling for your shop.</li>
          <li><strong>AI Business Advisor:</strong> AI-generated summaries and recommendations based on your shop and account activity.</li>
          <li><strong>AI Customer Insights:</strong> AI-assisted analysis of customer and inventory activity within the Smart Shop Assistant.</li>
          <li><strong>AI Calls:</strong> AI-generated voice responses for phone-based agent interactions.</li>
          <li><strong>Analytics:</strong> AI may assist in summarizing usage and conversation trends.</li>
        </ul>
      </LegalSection>

      <LegalSection title="3. Limitations of AI-Generated Output">
        <p>
          AI models, including Google Gemini, can produce responses that are inaccurate, incomplete, outdated,
          or biased. AI-generated content — including chat replies, business recommendations, customer
          insights, call responses, and analytics summaries — is provided for informational purposes only and
          does not constitute legal, medical, financial, or other professional advice. You are responsible for
          reviewing and validating AI-generated output before relying on it, presenting it to customers, or
          using it to make business decisions.
        </p>
      </LegalSection>

      <LegalSection title="4. Your Configuration & Content">
        <p>
          Where a feature requires a Gemini API key, you are responsible for keeping that key valid and for
          any usage or costs incurred against your own Google account. Content you send to Gemini (such as
          chat messages, Knowledge Base documents, or shop data) is subject to Google&apos;s own terms and
          privacy practices. See our <a href="/legal/privacy-policy">Privacy Policy</a> for how we handle data
          before and after it is sent to Gemini.
        </p>
      </LegalSection>

      <LegalSection title="5. No Guarantee of Availability or Accuracy">
        <p>
          We do not guarantee that AI features will be available at all times or that AI-generated output will
          be accurate, complete, or suitable for any particular purpose. See our{' '}
          <a href="/legal/disclaimer">Disclaimer</a> and <a href="/legal/terms">Terms &amp; Conditions</a> for
          the full limitation of liability.
        </p>
      </LegalSection>

      <LegalSection title="6. Changes to This Page">
        <p>
          We may update this page as our AI features or provider relationships change. Material changes will
          be reflected by an updated &quot;Last updated&quot; date above.
        </p>
      </LegalSection>

      <LegalSection title="7. Contact">
        <p>
          Questions about our AI usage? Reach us at{' '}
          <a href={`mailto:${siteConfig.legalEmail}`}>{siteConfig.legalEmail}</a>.
        </p>
      </LegalSection>
    </LegalLayout>
  )
}
