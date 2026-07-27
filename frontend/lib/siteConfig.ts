// Central, lightweight source of truth for public-facing site metadata.
// Reused by the footer, legal pages, robots.ts, sitemap.ts, and root layout
// metadata so all of them stay in sync from a single place.
import pkg from '../package.json'

export const siteConfig = {
  name: 'ThunderBots',
  tagline: 'Build. Train. Deploy. Scale.',
  description:
    'ThunderBots is a visual AI agent builder and chatbot workflow platform, powered by Google Gemini — design workflows, train agents on your knowledge base, and deploy AI Chat, AI Calls, the Smart Shop Assistant, AI Business Advisor, and more across WhatsApp and beyond.',
  url: process.env.NEXT_PUBLIC_SITE_URL || 'https://thunderbots.app',
  supportEmail: 'thunderbots.ai@gmail.com',
  legalEmail: 'thunderbots.ai@gmail.com',
  version: pkg.version as string,
  twitterHandle: '@thunderbots',
} as const

export const LEGAL_LINKS = [
  { href: '/legal/privacy-policy', label: 'Privacy Policy' },
  { href: '/legal/terms', label: 'Terms & Conditions' },
  { href: '/legal/cookie-policy', label: 'Cookie Policy' },
  { href: '/legal/acceptable-use', label: 'Acceptable Use Policy' },
  { href: '/legal/refund-policy', label: 'Refund & Cancellation Policy' },
  { href: '/legal/disclaimer', label: 'Disclaimer' },
  { href: '/legal/ai-usage', label: 'AI Usage & Limitations' },
] as const

export const COMPANY_LINKS = [
  { href: '/about', label: 'About Us' },
  { href: '/contact', label: 'Contact Us' },
  { href: '/help', label: 'Help Center' },
  { href: '/help/faq', label: 'FAQ' },
] as const

export const FEEDBACK_LINKS = [
  { href: '/report-bug', label: 'Report a Bug' },
  { href: '/feature-request', label: 'Feature Request' },
] as const
