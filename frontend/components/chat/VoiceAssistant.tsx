'use client'

/**
 * ThunderBots — Voice AI, Part 1: website-based voice assistant.
 *
 * A floating "Talk to AI" bubble that lets a visitor have a spoken
 * back-and-forth with the bot directly in the browser — no phone number,
 * no telephony stack. It is purely an additive input/output surface:
 *
 *   Speech-to-text (browser Web Speech API)
 *        │  finalized transcript
 *        ▼
 *   the SAME `sendMessage` used by the text composer
 *        │  goes over the SAME `/ws/chat/{workflowId}` socket
 *        ▼
 *   the SAME Workflow Runtime → AI Agent → Knowledge Base pipeline
 *        │  tokens/messages, fed in via `listenerRef`
 *        ▼
 *   Text-to-speech (the existing `lib/voice` Voice Responses module)
 *
 * Nothing here touches the Builder, Workflow Engine, Runtime, AI Engine,
 * or Authentication — it only calls the same public chat socket the page
 * already opens, and the same public voice endpoints the page already
 * calls for the Speaker toggle.
 */
import { useCallback, useEffect, useRef, useState, type MutableRefObject } from 'react'
import { Mic, MicOff, Sparkles, X } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { speakWithProvider, stopSpeaking } from '@/lib/voice'
import type { BotBranding, VoiceSettings } from '@/types'

export type VoiceAssistantState =
  | 'idle' | 'listening' | 'thinking' | 'speaking' | 'interrupted' | 'unsupported' | 'denied'
  // ROOT CAUSE FIX: these three states used to all collapse into either
  // 'unsupported' or a silently-swallowed error (see startRecognition's old
  // onerror handler, which ignored everything except not-allowed/
  // service-not-allowed and just let onend blindly retry forever). That
  // meant "no mic on this device", "mic is open in another app/tab", and
  // "the browser's speech-recognition backend is unreachable" all looked
  // identical to the user: the orb just sat there silently, which is what
  // was being reported as generic "Microphone connection error" /
  // "Network connection error" with no explanation and no way to recover
  // short of reloading the page.
  | 'no-mic' | 'mic-busy' | 'insecure-context' | 'network-error' | 'retry-exhausted'

/** Callbacks the host chat page feeds bot events into — only while a voice
 * session is open. Registering/clearing this is the only wiring the host
 * page needs to do; everything else lives in this component. */
export interface VoiceBotEventListener {
  onToken: (text: string) => void
  onMessage: (text: string) => void
  onDone: () => void
  onError: (msg?: string) => void
}

interface VoiceAssistantProps {
  connected: boolean
  sendMessage: (text: string) => void
  branding: BotBranding
  voiceSettings: VoiceSettings
  slug: string
  apiUrl: string
  /** Set by this component while mounted so the host page can route bot
   * events here; the host page owns the ref, this component fills it in. */
  listenerRef: MutableRefObject<VoiceBotEventListener | null>
  /** Set true while a voice session is open so the host page's own
   * Speaker/auto-read pipeline stands down and this component becomes the
   * single source of spoken audio (avoids double-speaking one reply). */
  sessionActiveRef: MutableRefObject<boolean>
}

const MIN_BARGE_IN_CHARS = 3
const INTERRUPT_FLASH_MS = 450
// ROOT CAUSE FIX: onend previously called recognition.start() unconditionally
// whenever the session was still meant to be listening, with no limit. If
// the browser's speech-recognition backend is unreachable (onerror='network')
// or no microphone is available (onerror='audio-capture'), onend still fires
// right after and restarts immediately — producing a tight, silent,
// unbounded restart loop (CPU/battery drain, and on some browsers this trips
// rate limiting which turns transient failures into permanent ones). This
// caps consecutive failures before giving up and surfacing a real error with
// a manual retry instead of spinning forever.
const MAX_CONSECUTIVE_RECOGNITION_FAILURES = 4
const RECOGNITION_RETRY_BACKOFF_MS = 1200

export default function VoiceAssistant({
  connected, sendMessage, branding, voiceSettings, slug, apiUrl, listenerRef, sessionActiveRef,
}: VoiceAssistantProps) {
  const [open, setOpen] = useState(false)
  const [state, setState] = useState<VoiceAssistantState>('idle')
  const [interim, setInterim] = useState('')
  const [caption, setCaption] = useState('')
  const [micOn, setMicOn] = useState(true)

  const stateRef = useRef<VoiceAssistantState>('idle')
  useEffect(() => { stateRef.current = state }, [state])

  const recognitionRef = useRef<any>(null)
  const requestIdRef = useRef(0)
  const pendingTextRef = useRef('')
  const interruptTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const micOnRef = useRef(true)
  useEffect(() => { micOnRef.current = micOn }, [micOn])
  const consecutiveFailuresRef = useRef(0)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const accent = branding.theme_color || '#6366f1'
  const accent2 = branding.accent_color || '#818cf8'

  // ── Text-to-speech for one bot reply ──────────────────────────────────────
  const speak = useCallback(async (text: string, myId: number) => {
    const trimmed = text.trim()
    if (!trimmed) {
      if (myId === requestIdRef.current && sessionActiveRef.current) setState('listening')
      return
    }
    const provider = voiceSettings?.enabled && voiceSettings.provider !== 'browser' ? voiceSettings.provider : 'browser'
    await speakWithProvider({
      text: trimmed,
      provider,
      voiceId: voiceSettings?.voice_id ?? null,
      gender: voiceSettings?.gender ?? 'neutral',
      personality: voiceSettings?.personality ?? 'friendly',
      fetchAudio: provider === 'browser' ? undefined : async (args: { provider: string; voice?: string | null; text: string; personality?: string }) => {
        const res = await fetch(`${apiUrl}/api/v1/voice/live/${slug}/synthesize`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(args),
        })
        if (!res.ok) throw new Error('Voice request failed')
        return res.blob()
      },
    })
    // If a barge-in superseded this reply (requestId moved on) or the
    // session was closed while speaking, don't clobber whatever state
    // that newer turn has already moved into.
    if (myId !== requestIdRef.current || !sessionActiveRef.current) return
    setCaption('')
    setState('listening')
  }, [voiceSettings, apiUrl, slug, sessionActiveRef])

  // ── Barge-in: user starts talking while the AI is thinking/speaking ──────
  const bargeIn = useCallback(() => {
    stopSpeaking()
    requestIdRef.current += 1
    pendingTextRef.current = ''
    setCaption('')
    setState('interrupted')
    if (interruptTimerRef.current) clearTimeout(interruptTimerRef.current)
    interruptTimerRef.current = setTimeout(() => {
      if (sessionActiveRef.current) setState('listening')
    }, INTERRUPT_FLASH_MS)
  }, [sessionActiveRef])

  // ── A finalized user utterance is ready to send ──────────────────────────
  const handleFinalTranscript = useCallback((text: string) => {
    if (!text.trim() || !connected) return
    setInterim('')
    requestIdRef.current += 1
    pendingTextRef.current = ''
    sendMessage(text.trim())
    setState('thinking')
  }, [connected, sendMessage])

  // ── Register bot-event listener while this component is mounted ─────────
  useEffect(() => {
    listenerRef.current = {
      onToken: (token: string) => {
        pendingTextRef.current += token
        setCaption(pendingTextRef.current)
        if (stateRef.current === 'thinking') setState('speaking')
      },
      onMessage: (text: string) => {
        pendingTextRef.current = text
        setCaption(text)
        setState('speaking')
        speak(text, requestIdRef.current)
      },
      onDone: () => {
        const myId = requestIdRef.current
        const text = pendingTextRef.current
        if (!text.trim()) {
          if (sessionActiveRef.current) setState('listening')
          return
        }
        speak(text, myId)
      },
      onError: () => {
        if (sessionActiveRef.current) setState('listening')
      },
    }
    return () => { listenerRef.current = null }
  }, [listenerRef, sessionActiveRef, speak])

  // ── Speech recognition lifecycle ─────────────────────────────────────────
  const stopRecognition = useCallback(() => {
    const r = recognitionRef.current
    recognitionRef.current = null
    if (r) {
      try { r.onend = null; r.onerror = null; r.onresult = null; r.stop() } catch { /* no-op */ }
    }
  }, [])

  const closeAssistant = useCallback(() => {
    sessionActiveRef.current = false
    stopRecognition()
    stopSpeaking()
    if (interruptTimerRef.current) clearTimeout(interruptTimerRef.current)
    if (retryTimerRef.current) { clearTimeout(retryTimerRef.current); retryTimerRef.current = null }
    consecutiveFailuresRef.current = 0
    requestIdRef.current += 1
    pendingTextRef.current = ''
    setCaption('')
    setInterim('')
    setOpen(false)
    setState('idle')
  }, [sessionActiveRef, stopRecognition])

  const startRecognition = useCallback(() => {
    const SR = (typeof window !== 'undefined') && ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)
    if (!SR) {
      setState('unsupported')
      return
    }
    const recognition = new SR()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = (typeof navigator !== 'undefined' && navigator.language) || 'en-US'

    recognition.onresult = (event: any) => {
      if (!sessionActiveRef.current || !micOnRef.current) return
      let interimText = ''
      let finalText = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const res = event.results[i]
        if (res.isFinal) finalText += res[0].transcript
        else interimText += res[0].transcript
      }

      const currentState = stateRef.current
      if (currentState === 'thinking' || currentState === 'speaking') {
        const candidate = (finalText || interimText).trim()
        if (candidate.length < MIN_BARGE_IN_CHARS) return
        bargeIn()
        setInterim(interimText)
        if (finalText.trim()) handleFinalTranscript(finalText)
        return
      }
      setInterim(interimText)
      if (finalText.trim()) handleFinalTranscript(finalText)
    }

    recognition.onerror = (event: any) => {
      switch (event?.error) {
        case 'not-allowed':
        case 'service-not-allowed':
          // Permission was denied outright, or dismissed without a choice —
          // browsers report both the same way. Either way retrying silently
          // would just re-trigger the same prompt/rejection.
          setState('denied')
          sessionActiveRef.current = false
          recognitionRef.current = null
          return
        case 'audio-capture':
          // No microphone track available — either there's no mic on this
          // device, or it's held exclusively by another app/tab. We can't
          // tell those apart from this error alone, so the message covers
          // both; retrying without the user fixing the underlying cause
          // would just fail again immediately.
          setState('no-mic')
          sessionActiveRef.current = false
          recognitionRef.current = null
          return
        case 'network':
          // The browser's speech-recognition backend (a cloud service, not
          // this site's own connection) couldn't be reached. This used to
          // be silently swallowed and retried instantly forever — now it
          // gets a bounded, backed-off retry with a clear message if it
          // doesn't recover.
          consecutiveFailuresRef.current += 1
          if (consecutiveFailuresRef.current >= MAX_CONSECUTIVE_RECOGNITION_FAILURES) {
            setState('network-error')
            sessionActiveRef.current = false
            recognitionRef.current = null
          }
          return
        case 'no-speech':
        case 'aborted':
          // Not real failures — the user just paused, or we called
          // stop()/start() ourselves (e.g. barge-in). onend below restarts.
          return
        default:
          consecutiveFailuresRef.current += 1
          return
      }
    }

    recognition.onend = () => {
      if (!sessionActiveRef.current || recognitionRef.current !== recognition) return
      if (consecutiveFailuresRef.current >= MAX_CONSECUTIVE_RECOGNITION_FAILURES) {
        setState('network-error')
        sessionActiveRef.current = false
        recognitionRef.current = null
        return
      }
      const restart = () => {
        if (!sessionActiveRef.current || recognitionRef.current !== recognition) return
        try { recognition.start(); consecutiveFailuresRef.current = 0 } catch { /* already starting — ignore */ }
      }
      // Back off once we've seen a failure this cycle so a flaky connection
      // doesn't spin in a tight loop; a clean end-of-utterance restarts
      // immediately as before.
      if (consecutiveFailuresRef.current > 0) {
        if (retryTimerRef.current) clearTimeout(retryTimerRef.current)
        retryTimerRef.current = setTimeout(restart, RECOGNITION_RETRY_BACKOFF_MS)
      } else {
        restart()
      }
    }

    recognitionRef.current = recognition
    consecutiveFailuresRef.current = 0
    try {
      recognition.start()
      setState('listening')
    } catch {
      setState('unsupported')
    }
  }, [bargeIn, handleFinalTranscript, sessionActiveRef])

  const openAssistant = useCallback(async () => {
    setOpen(true)
    setCaption('')
    setInterim('')
    setMicOn(true)
    consecutiveFailuresRef.current = 0

    // ROOT CAUSE FIX: getUserMedia (and SpeechRecognition, which uses it
    // internally) is only available in a secure context. On plain http://
    // (anything other than localhost) the browser doesn't prompt at all —
    // it just rejects immediately, which the old single generic catch below
    // reported as "Microphone blocked" even though the user never got a
    // chance to allow anything. Checking this up front gives the real
    // explanation instead.
    if (typeof window !== 'undefined' && window.isSecureContext === false) {
      setState('insecure-context')
      return
    }
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setState('unsupported')
      return
    }

    sessionActiveRef.current = true
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.getTracks().forEach(t => t.stop())
    } catch (err: any) {
      // ROOT CAUSE FIX: every getUserMedia rejection used to collapse into
      // the same "Microphone blocked" message, whether the user actually
      // denied permission, there's no mic hardware at all, or the mic is
      // already in use by another app/tab — three different problems that
      // need three different instructions to actually fix.
      switch (err?.name) {
        case 'NotFoundError':
        case 'DevicesNotFoundError':
          setState('no-mic')
          break
        case 'NotReadableError':
        case 'TrackStartError':
          setState('mic-busy')
          break
        case 'NotAllowedError':
        case 'PermissionDeniedError':
        case 'SecurityError':
        default:
          setState('denied')
          break
      }
      sessionActiveRef.current = false
      return
    }
    startRecognition()
  }, [sessionActiveRef, startRecognition])

  const toggleMic = useCallback(() => {
    setMicOn((prev: boolean) => {
      const next = !prev
      if (!next && stateRef.current === 'listening') {
        // Pausing the mic mid-turn — keep recognition alive (continuous
        // mode) but stop reacting to results until resumed.
      }
      return next
    })
  }, [])

  // Tapping the orb while the AI is talking is an explicit, non-voice
  // interrupt — same effect as speaking over it.
  const handleOrbClick = useCallback(() => {
    if (state === 'speaking' || state === 'thinking') bargeIn()
  }, [state, bargeIn])

  useEffect(() => () => { closeAssistant() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const stateLabel: Record<VoiceAssistantState, string> = {
    idle: 'Ready', listening: 'Listening…', thinking: 'Thinking…', speaking: 'Speaking…',
    interrupted: 'Got it —', unsupported: 'Not supported here', denied: 'Microphone blocked',
    'no-mic': 'No microphone found', 'mic-busy': 'Microphone in use',
    'insecure-context': 'Secure connection required', 'network-error': 'Connection error',
    'retry-exhausted': 'Still having trouble',
  }
  const isErrorState = state === 'unsupported' || state === 'denied' || state === 'no-mic'
    || state === 'mic-busy' || state === 'insecure-context' || state === 'network-error' || state === 'retry-exhausted'

  return (
    <>
      {!open && (
        <button
          onClick={openAssistant}
          disabled={!connected}
          title="Talk to AI"
          className="tbva-launcher fixed z-50 flex items-center gap-2 pl-3.5 pr-4 py-3 rounded-full
                     text-white text-[13px] font-medium disabled:opacity-40 disabled:cursor-not-allowed min-h-[44px]"
          style={{
            background: `linear-gradient(135deg, ${accent}, ${accent2})`,
            boxShadow: `0 6px 24px ${accent}55`,
            // Fixed-position launcher: bottom/right offsets are computed
            // (not plain Tailwind bottom-5/right-5) so the button clears
            // the iPhone home-indicator / rounded-corner safe area instead
            // of sitting flush against it.
            bottom: 'calc(20px + env(safe-area-inset-bottom, 0px))',
            right: 'calc(20px + env(safe-area-inset-right, 0px))',
          }}
        >
          <span className="tbva-launcher-ring" style={{ borderColor: `${accent2}aa` }} />
          <Mic size={16} />
          <span>Talk to AI</span>
        </button>
      )}

      {open && (
        <div
          className="tbva-panel tb-anim-pop-in fixed z-50 w-[calc(100vw-2.5rem)] max-w-[320px] rounded-3xl overflow-hidden"
          style={{
            bottom: 'calc(20px + env(safe-area-inset-bottom, 0px))',
            right: 'calc(20px + env(safe-area-inset-right, 0px))',
            background: 'linear-gradient(180deg, rgba(20,20,24,0.92), rgba(10,10,13,0.96))',
            border: '1px solid rgba(255,255,255,0.09)',
            boxShadow: `0 20px 60px rgba(0,0,0,0.5), 0 0 0 1px ${accent}22`,
            backdropFilter: 'blur(18px)',
          }}
        >
          <div className="flex items-center justify-between px-4 pt-3.5 pb-1">
            <div className="flex items-center gap-1.5 text-white/80 text-[12px] font-medium">
              <Sparkles size={12} style={{ color: accent2 }} />
              Voice Assistant
            </div>
            <button onClick={closeAssistant} className="tb-hover-lift p-1.5 rounded-lg text-white/40 hover:text-white/80">
              <X size={14} />
            </button>
          </div>

          <div className="flex flex-col items-center px-6 pt-3 pb-5">
            <button
              onClick={handleOrbClick}
              aria-label={state === 'speaking' ? 'Interrupt' : 'Voice assistant status'}
              className="relative w-24 h-24 flex items-center justify-center mb-4"
            >
              {state === 'listening' && (
                <>
                  <span className="tbva-ring" style={{ borderColor: `${accent}66` }} />
                  <span className="tbva-ring tbva-ring-delay" style={{ borderColor: `${accent2}44` }} />
                </>
              )}
              <div
                className={`tbva-orb ${state === 'thinking' ? 'tbva-orb-thinking' : ''} ${state === 'interrupted' ? 'tbva-orb-interrupted' : ''}`}
                style={{ background: `radial-gradient(circle at 35% 30%, ${accent2}, ${accent})` }}
              >
                {state === 'speaking' && (
                  <div className="tbva-bars">
                    {[0, 1, 2, 3, 4].map(i => <span key={i} className="tbva-bar" style={{ animationDelay: `${i * 0.09}s` }} />)}
                  </div>
                )}
                {state === 'listening' && <Mic size={22} className="text-white/90" />}
                {state !== 'speaking' && state !== 'listening' && <Mic size={22} className="text-white/70" />}
              </div>
            </button>

            <p className="text-[12px] font-medium text-white/60 mb-2 h-4">{stateLabel[state]}</p>

            <div className="w-full min-h-[46px] text-center text-[13px] leading-relaxed text-white/85 px-1">
              {state === 'unsupported' && (
                <span className="text-amber-300/80">
                  Voice input isn&apos;t supported in this browser. Try Chrome, Edge, or Safari.
                </span>
              )}
              {state === 'denied' && (
                <span className="text-amber-300/80">
                  Microphone access was blocked. Allow it in your browser&apos;s site settings, then try again.
                </span>
              )}
              {state === 'no-mic' && (
                <span className="text-amber-300/80">
                  No microphone was found. Connect a microphone or check your OS sound settings, then try again.
                </span>
              )}
              {state === 'mic-busy' && (
                <span className="text-amber-300/80">
                  Your microphone is being used by another app or browser tab. Close it, then try again.
                </span>
              )}
              {state === 'insecure-context' && (
                <span className="text-amber-300/80">
                  Voice input needs a secure (https://) connection. Reload this page over HTTPS to use it.
                </span>
              )}
              {(state === 'network-error' || state === 'retry-exhausted') && (
                <span className="text-amber-300/80">
                  Couldn&apos;t reach the voice recognition service. Check your internet connection, then try again.
                </span>
              )}
              {state === 'listening' && (interim ? <span>{interim}</span> : <span className="text-white/35 italic">Say something…</span>)}
              {state === 'thinking' && <span className="text-white/35 italic">Working on it…</span>}
              {(state === 'speaking' || state === 'interrupted') && <span>{caption}</span>}
              {state === 'idle' && <span className="text-white/35 italic">Connecting…</span>}
            </div>
          </div>

          {(state === 'no-mic' || state === 'mic-busy' || state === 'network-error' || state === 'retry-exhausted') && (
            <div className="px-4 pb-3">
              <Button variant="secondary" size="sm" onClick={openAssistant} className="w-full">
                Try again
              </Button>
            </div>
          )}

          <div className="flex items-center justify-between px-4 py-3" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
            <button
              onClick={toggleMic}
              disabled={isErrorState}
              title={micOn ? 'Pause microphone' : 'Resume microphone'}
              className="tb-hover-lift flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-lg text-white/60 hover:text-white/90 disabled:opacity-30"
              style={{ border: '1px solid rgba(255,255,255,0.08)' }}
            >
              {micOn ? <Mic size={13} /> : <MicOff size={13} />}
              {micOn ? 'Mic on' : 'Paused'}
            </button>
            <span className="text-[11px] text-white/25">
              {state === 'speaking' ? 'Tap orb or just speak to interrupt' : 'Speak anytime'}
            </span>
          </div>
        </div>
      )}

      <style jsx global>{`
        .tbva-launcher-ring {
          position: absolute; inset: -4px; border-radius: 9999px; border: 1.5px solid;
          animation: tbvaLauncherPulse 2.4s ease-out infinite;
          pointer-events: none;
        }
        @keyframes tbvaLauncherPulse {
          0% { transform: scale(0.92); opacity: 0.9; }
          70%, 100% { transform: scale(1.35); opacity: 0; }
        }
        .tbva-orb {
          position: relative; width: 64px; height: 64px; border-radius: 9999px;
          display: flex; align-items: center; justify-content: center;
          box-shadow: 0 8px 28px rgba(0,0,0,0.35);
          transition: transform 0.2s ease;
        }
        .tbva-orb-thinking { animation: tbvaThinking 1.1s ease-in-out infinite; }
        @keyframes tbvaThinking {
          0%, 100% { transform: scale(0.94); }
          50% { transform: scale(1.04); }
        }
        .tbva-orb-interrupted { animation: tbvaInterrupt 0.45s ease; }
        @keyframes tbvaInterrupt {
          0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(248,113,113,0.6); }
          50% { transform: scale(0.92); box-shadow: 0 0 0 10px rgba(248,113,113,0); }
          100% { transform: scale(1); }
        }
        .tbva-ring {
          position: absolute; inset: 0; border-radius: 9999px; border: 1.5px solid;
          animation: tbvaRingPulse 1.8s ease-out infinite;
        }
        .tbva-ring-delay { animation-delay: 0.6s; }
        @keyframes tbvaRingPulse {
          0% { transform: scale(0.72); opacity: 0.8; }
          100% { transform: scale(1.45); opacity: 0; }
        }
        .tbva-bars { display: flex; align-items: center; gap: 3px; height: 20px; }
        .tbva-bar {
          width: 3px; height: 6px; border-radius: 2px; background: rgba(255,255,255,0.92);
          animation: tbvaBar 0.9s ease-in-out infinite;
        }
        @keyframes tbvaBar {
          0%, 100% { height: 6px; }
          50% { height: 18px; }
        }
        @media (prefers-reduced-motion: reduce) {
          .tbva-launcher-ring, .tbva-orb-thinking, .tbva-orb-interrupted, .tbva-ring, .tbva-bar { animation: none !important; }
        }
      `}</style>
    </>
  )
}
