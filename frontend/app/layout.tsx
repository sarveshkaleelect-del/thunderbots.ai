import type { Metadata, Viewport } from 'next'
import './globals.css'
import { Providers } from './providers'
import { ThemeProvider } from './theme-provider'
import { PageTransition } from '@/components/ui/PageTransition'
import { ChunkErrorRecovery } from '@/components/ui/ChunkErrorRecovery'
import { TutorialProvider } from '@/components/tutorial/TutorialProvider'
import { siteConfig } from '@/lib/siteConfig'

const TITLE = `${siteConfig.name} — ${siteConfig.tagline}`

export const metadata: Metadata = {
  metadataBase: new URL(siteConfig.url),
  title: {
    default: TITLE,
    template: `%s — ${siteConfig.name}`,
  },
  description: siteConfig.description,
  keywords: [
    'AI agent builder',
    'chatbot workflow platform',
    'visual workflow automation',
    'WhatsApp AI chatbot',
    'knowledge base AI',
    'ThunderBots',
  ],
  icons: {
    icon: '/logo.svg',
    shortcut: '/logo.svg',
    apple: '/logo.svg',
  },
  openGraph: {
    type: 'website',
    siteName: siteConfig.name,
    title: TITLE,
    description: siteConfig.description,
    url: siteConfig.url,
  },
  twitter: {
    card: 'summary_large_image',
    site: siteConfig.twitterHandle,
    title: TITLE,
    description: siteConfig.description,
  },
  robots: {
    index: true,
    follow: true,
  },
}

// MOBILE FIX (v114): app had no viewport export at all, which meant every
// mobile browser (iOS Safari, Chrome/Samsung Internet on Android) rendered
// the page at an assumed ~980px desktop layout width and scaled it down to
// fit — every single responsive/media-query fix elsewhere in the app was
// being neutralized by this. `initial-scale=1` + `width=device-width` fixes
// that at the root. `viewportFit: 'cover'` lets the page extend under the
// iPhone notch/Dynamic Island/home-indicator area so the existing
// `env(safe-area-inset-*)` CSS (tb-safe-top/tb-safe-bottom) actually has
// something to apply padding against. Pinch-zoom is intentionally left
// enabled (no maximumScale/userScalable lock) for accessibility (WCAG 1.4.4) —
// the actual "zoom on tap" annoyance on iOS is solved separately by ensuring
// inputs render at >=16px, not by disabling zoom globally.
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  themeColor: '#080808',
}

// Runs before paint so the correct theme is applied on first frame —
// no flash of the wrong theme, no reliance on React hydration timing.
const THEME_INIT_SCRIPT = `
(function () {
  try {
    var t = window.localStorage.getItem('tb-theme');
    var valid = ['dark', 'light', 'midnight', 'thunder'];
    document.documentElement.setAttribute('data-theme', valid.indexOf(t) !== -1 ? t : 'dark');
  } catch (e) {
    document.documentElement.setAttribute('data-theme', 'dark');
  }
})();
`

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        {/* PERF FIX (v107): fonts were loaded via a render-blocking CSS
            `@import url(fonts.googleapis.com/...)` inside globals.css,
            which forces the browser to fetch+parse that remote stylesheet
            (its own DNS+TLS+HTTP round trip) before it can finish building
            the CSSOM. next/font/google would be the ideal fix, but it
            requires internet access to Google's font CDN at BUILD time —
            unsafe here given this project's own history of Docker
            build-time network issues, and a hard requirement this audit
            shouldn't introduce. Instead: preconnect establishes the DNS+TLS
            connection to both font hosts early (in parallel with everything
            else in <head>), and the stylesheet is loaded as a standard
            non-blocking <link> (with the existing display=swap already in
            the URL) instead of a blocking CSS @import — same fonts, same
            request, just no longer serialized behind the rest of the CSS. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap"
        />
      </head>
      <body className="bg-[var(--bg)] text-white antialiased" suppressHydrationWarning>
        <ChunkErrorRecovery />
        <Providers>
          <ThemeProvider>
            <PageTransition>{children}</PageTransition>
            <TutorialProvider />
          </ThemeProvider>
        </Providers>
      </body>
    </html>
  )
}
