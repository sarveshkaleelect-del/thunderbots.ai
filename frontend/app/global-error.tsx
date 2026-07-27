'use client'
import { useEffect } from 'react'

/**
 * Catches errors thrown from the root layout itself. Kept intentionally
 * minimal/inline-styled since it cannot rely on globals.css having loaded.
 */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error('Unhandled root layout error:', error)
  }, [error])

  return (
    <html lang="en">
      <body
        style={{
          background: '#080808',
          color: '#fff',
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, sans-serif',
          textAlign: 'center',
          padding: '24px',
        }}
      >
        <p style={{ fontSize: '48px', fontWeight: 700, marginBottom: '8px', opacity: 0.9 }}>500</p>
        <p style={{ fontWeight: 600, marginBottom: '6px', opacity: 0.7 }}>Something went wrong</p>
        <p style={{ fontSize: '13px', opacity: 0.4, marginBottom: '20px', maxWidth: '360px' }}>
          A critical error occurred while loading ThunderBots. Please try again.
        </p>
        <button
          onClick={reset}
          style={{
            background: '#6366f1',
            color: '#fff',
            border: 'none',
            borderRadius: '10px',
            padding: '10px 20px',
            fontSize: '14px',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          Try again
        </button>
      </body>
    </html>
  )
}
