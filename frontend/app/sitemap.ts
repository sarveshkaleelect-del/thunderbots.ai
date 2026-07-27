import type { MetadataRoute } from 'next'
import { siteConfig } from '@/lib/siteConfig'

const PUBLIC_ROUTES = [
  '/about',
  '/contact',
  '/help',
  '/help/faq',
  '/report-bug',
  '/feature-request',
  '/legal/privacy-policy',
  '/legal/terms',
  '/legal/cookie-policy',
  '/legal/acceptable-use',
  '/legal/refund-policy',
  '/legal/disclaimer',
  '/legal/ai-usage',
]

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date()
  return PUBLIC_ROUTES.map(route => ({
    url: `${siteConfig.url}${route}`,
    lastModified,
    changeFrequency: route === '/about' ? 'monthly' : 'yearly',
    priority: route === '/about' ? 0.8 : 0.5,
  }))
}
