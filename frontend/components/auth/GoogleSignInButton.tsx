'use client'
/**
 * NEW (Google SSO)
 *
 * Renders Google's own "Sign in with Google" button via Google Identity
 * Services (https://accounts.google.com/gsi/client), loaded on demand with
 * next/script — no @react-oauth/google or similar package added to
 * package.json. GIS hands back a signed ID token ("credential") through the
 * `callback`, which the caller POSTs to the backend at /api/v1/auth/google
 * for server-side verification (see lib/api/auth.ts -> googleLogin).
 *
 * Renders nothing at all when NEXT_PUBLIC_GOOGLE_CLIENT_ID isn't set, so an
 * install that hasn't configured Google SSO sees no trace of this feature.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import Script from 'next/script'

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string
            callback: (response: { credential: string }) => void
            auto_select?: boolean
            cancel_on_tap_outside?: boolean
          }) => void
          renderButton: (
            parent: HTMLElement,
            options: {
              type?: 'standard' | 'icon'
              theme?: 'outline' | 'filled_black' | 'filled_blue'
              size?: 'small' | 'medium' | 'large'
              shape?: 'rectangular' | 'pill' | 'circle' | 'square'
              text?: 'signin_with' | 'signup_with' | 'continue_with' | 'signin'
              width?: number
              locale?: string
            }
          ) => void
        }
      }
    }
  }
}

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID

interface GoogleSignInButtonProps {
  onCredential: (credential: string) => void
  /** GIS's own button label variants. 'continue_with' renders literally
   *  "Continue with Google" — the wording used as the primary CTA on both
   *  the login and register pages (matches ChatGPT/Notion/Canva/Vercel). */
  text?: 'signin_with' | 'signup_with' | 'continue_with'
  disabled?: boolean
}

export function GoogleSignInButton({ onCredential, text = 'continue_with', disabled }: GoogleSignInButtonProps) {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [scriptReady, setScriptReady] = useState(false)
  // Keep the latest callback in a ref so re-renders of the parent (e.g. an
  // error message appearing) never force us to re-initialize/re-render the
  // Google button, which would otherwise flicker.
  const onCredentialRef = useRef(onCredential)
  onCredentialRef.current = onCredential

  // FIX (full-width layout): Google Identity Services only accepts a fixed
  // pixel `width` for its rendered button — there's no "100%" option. To get
  // a true full-width, responsive button (matching the email/password form
  // and modern SaaS login screens like GitHub/Notion/Vercel), we measure the
  // wrapper's actual content width with ResizeObserver and re-render the GIS
  // button at that exact pixel width whenever the container resizes (window
  // resize, orientation change, etc). GIS caps the rendered width at 400px,
  // which is fine — it just centers within a wider wrapper.
  const [width, setWidth] = useState(320)

  const renderButton = useCallback(() => {
    if (!window.google || !containerRef.current || !GOOGLE_CLIENT_ID) return
    containerRef.current.innerHTML = ''
    window.google.accounts.id.initialize({
      client_id: GOOGLE_CLIENT_ID,
      callback: (response) => onCredentialRef.current(response.credential),
      cancel_on_tap_outside: true,
    })
    window.google.accounts.id.renderButton(containerRef.current, {
      type: 'standard',
      theme: 'outline',
      size: 'large',
      shape: 'rectangular',
      text,
      // GIS hard-caps the rendered button at 400px regardless of what's
      // passed — clamping here just avoids passing a nonsensical value on
      // very wide viewports; the wrapper's `flex justify-center` keeps it
      // centered either way.
      width: Math.min(Math.round(width), 400),
      // Forces the English "Continue with Google" label deterministically,
      // regardless of the visitor's browser/OS locale — required wording
      // per the design spec rather than whatever GIS would auto-translate.
      locale: 'en',
    })
  }, [text, width])

  useEffect(() => {
    if (!wrapperRef.current || typeof ResizeObserver === 'undefined') return
    const el = wrapperRef.current
    const observer = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width
      if (w && Math.abs(w - width) > 1) setWidth(w)
    })
    observer.observe(el)
    setWidth(el.offsetWidth || 320)
    return () => observer.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (scriptReady) renderButton()
  }, [scriptReady, renderButton])

  if (!GOOGLE_CLIENT_ID) return null

  return (
    <>
      <Script
        src="https://accounts.google.com/gsi/client?hl=en"
        strategy="afterInteractive"
        onLoad={() => setScriptReady(true)}
      />
      <div
        ref={wrapperRef}
        className={
          disabled
            ? 'pointer-events-none opacity-50 w-full min-h-[44px] flex justify-center overflow-hidden rounded-xl shadow-sm'
            : 'w-full min-h-[44px] flex justify-center overflow-hidden rounded-xl shadow-sm'
        }
      >
        <div ref={containerRef} className="w-full flex justify-center [&>div]:!w-full [&_iframe]:!w-full" />
      </div>
    </>
  )
}
