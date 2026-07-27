import type { MetadataRoute } from 'next'
import { siteConfig } from '@/lib/siteConfig'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: [
          '/dashboard',
          '/builder',
          '/chat',
          '/whatsapp',
          '/analytics',
          '/settings',
          '/admin',
          '/teams',
          '/marketplace',
          '/create-with-ai',
          '/api/',
        ],
      },
    ],
    sitemap: `${siteConfig.url}/sitemap.xml`,
  }
}
