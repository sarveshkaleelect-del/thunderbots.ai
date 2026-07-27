'use client'
/**
 * NEW — Test Voice Agent dialog.
 *
 * Purely additive: does not touch the existing Embed Code, Preview, or
 * Voice Widget anywhere in the app. Lets a builder talk to the agent
 * right inside ThunderBots before publishing it.
 *
 * How it works:
 *  - Microphone capture + live speech-to-text via the browser's native
 *    Web Speech API (SpeechRecognition). No audio is uploaded anywhere;
 *    only the recognized text is sent to the backend.
 *  - Each finished utterance is sent to the new, isolated
 *    `/call-agent/agents/{id}/test-chat` endpoint, which runs it through
 *    the agent's own real instructions/provider/model — the same prompt
 *    composition a real call uses — and returns a text reply.
 *  - The reply is spoken back with the browser's speechSynthesis so this
 *    is a genuine voice conversation, not just a text chat.
 *  - End / Restart controls stop the mic and clear the transcript.
 *
 * Nothing here is persisted: no Call row, no transcript row, no
 * analytics event — testing never pollutes real call history.
 */
import { useEffect, useRef, useState } from 'react'
import { Mic, MicOff, RotateCcw, PhoneOff, Volume2, Loader2, AlertTriangle } from 'lucide-react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Card'
import { voiceAgentsApi } from '@/lib/api/callAgent'
import { getErrorMessage } from '@/lib/utils/errors'
import { cn } from '@/lib/utils/cn'
import type { VoiceAgent, VoiceAgentTestChatTurn } from '@/types/callAgent'

type TurnState = VoiceAgentTestChatTurn & { id: string; pending?: boolean }

// ROOT CAUSE FIX: previously every mic/recognition failure funneled into
// the single generic `errorMsg` string (`Microphone error: ${event.error}`)
// with no distinction between "no mic", "mic in use elsewhere", "browser's
// recognition backend unreachable", or a real permission denial — and
// `onend` restarted recognition unconditionally forever, so an unreachable
// backend just spun silently instead of ever surfacing a real message. See
// the matching fix in VoiceAssistant.tsx for the full rationale.
type CallState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'ended' | 'unsupported'
  | 'no-mic' | 'mic-busy' | 'network-error'

function uid() {
  return Math.random().toString(36).slice(2, 10)
}

export function TestVoiceAgentDialog({
  agent,
  onClose,
}: {
  agent: VoiceAgent
  onClose: () => void
}) {
  const [turns, setTurns] = useState<TurnState[]>([])
  const [interim, setInterim] = useState('')
  const [state, setState] = useState<CallState>('idle')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const recognitionRef = useRef<any>(null)
  const shouldListenRef = useRef(false)
  const turnsRef = useRef<TurnState[]>([])
  const transcriptEndRef = useRef<HTMLDivElement>(null)
  const consecutiveFailuresRef = useRef(0)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const MAX_CONSECUTIVE_FAILURES = 4
  const RETRY_BACKOFF_MS = 1200

  useEffect(() => { turnsRef.current = turns }, [turns])
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns, interim])

  // ── Setup: SpeechRecognition + start the conversation with the agent's
  //     own welcome message, exactly like a real call would open. ────────
  useEffect(() => {
    const SR: any = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SR) {
      setState('unsupported')
      return
    }
    const recognition = new SR()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = agent.language || 'en-US'

    recognition.onresult = (event: any) => {
      let finalText = ''
      let interimText = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript
        if (event.results[i].isFinal) finalText += transcript
        else interimText += transcript
      }
      setInterim(interimText)
      if (finalText.trim()) {
        setInterim('')
        void handleUserUtterance(finalText.trim())
      }
    }
    recognition.onerror = (event: any) => {
      switch (event.error) {
        case 'no-speech':
        case 'aborted':
          return
        case 'not-allowed':
        case 'service-not-allowed':
          setErrorMsg('Microphone access was blocked. Allow it in your browser\u2019s site settings and restart the call.')
          shouldListenRef.current = false
          setState('idle')
          return
        case 'audio-capture':
          setErrorMsg('No microphone was found. Connect one or check your OS sound settings, then restart the call.')
          shouldListenRef.current = false
          setState('no-mic')
          return
        case 'network':
          consecutiveFailuresRef.current += 1
          if (consecutiveFailuresRef.current >= MAX_CONSECUTIVE_FAILURES) {
            setErrorMsg('Couldn\u2019t reach the voice recognition service. Check your internet connection, then restart the call.')
            shouldListenRef.current = false
            setState('network-error')
          }
          return
        default:
          consecutiveFailuresRef.current += 1
          return
      }
    }
    recognition.onend = () => {
      // Browsers stop recognition after a pause — restart automatically
      // while the call is still meant to be listening. ROOT CAUSE FIX: this
      // used to restart unconditionally and instantly no matter how many
      // times it had just failed, which turned an unreachable recognition
      // backend into a silent, unbounded, instant restart loop instead of
      // ever giving up and telling the user. Now it backs off after a
      // failure and stops retrying (with a clear message) past the cap.
      if (!shouldListenRef.current) return
      if (consecutiveFailuresRef.current >= MAX_CONSECUTIVE_FAILURES) return
      const restart = () => {
        if (!shouldListenRef.current) return
        try { recognition.start(); consecutiveFailuresRef.current = 0 } catch { /* already running */ }
      }
      if (consecutiveFailuresRef.current > 0) {
        if (retryTimerRef.current) clearTimeout(retryTimerRef.current)
        retryTimerRef.current = setTimeout(restart, RETRY_BACKOFF_MS)
      } else {
        restart()
      }
    }
    recognitionRef.current = recognition

    void openWithWelcome()

    return () => {
      shouldListenRef.current = false
      if (retryTimerRef.current) { clearTimeout(retryTimerRef.current); retryTimerRef.current = null }
      try { recognition.stop() } catch {}
      window.speechSynthesis?.cancel()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function openWithWelcome() {
    setState('thinking')
    try {
      const res = await voiceAgentsApi.testChat(agent.id, [])
      await speak(res.content)
      setTurns([{ id: uid(), role: 'assistant', content: res.content }])
      startListening()
    } catch (e) {
      setErrorMsg(getErrorMessage(e, "Couldn't reach the Voice Agent."))
      setState('idle')
    }
  }

  function startListening() {
    if (state === 'unsupported') return
    shouldListenRef.current = true
    setState('listening')
    try { recognitionRef.current?.start() } catch { /* already running */ }
  }

  function stopListening() {
    shouldListenRef.current = false
    try { recognitionRef.current?.stop() } catch {}
  }

  async function speak(text: string) {
    if (!window.speechSynthesis) return
    setState('speaking')
    await new Promise<void>((resolve) => {
      const utter = new SpeechSynthesisUtterance(text)
      utter.rate = agent.speaking_speed || 1
      utter.lang = agent.language || 'en-US'
      utter.onend = () => resolve()
      utter.onerror = () => resolve()
      window.speechSynthesis.speak(utter)
    })
  }

  async function handleUserUtterance(text: string) {
    stopListening()
    setState('thinking')
    const userTurn: TurnState = { id: uid(), role: 'user', content: text }
    const history = [...turnsRef.current, userTurn]
    setTurns(history)

    try {
      const res = await voiceAgentsApi.testChat(
        agent.id,
        history.map(t => ({ role: t.role, content: t.content }))
      )
      setTurns(prev => [...prev, { id: uid(), role: 'assistant', content: res.content }])
      await speak(res.content)
      if (state !== 'ended') startListening()
    } catch (e) {
      setErrorMsg(getErrorMessage(e, "Couldn't reach the Voice Agent."))
      setState('idle')
    }
  }

  function handleEnd() {
    shouldListenRef.current = false
    if (retryTimerRef.current) { clearTimeout(retryTimerRef.current); retryTimerRef.current = null }
    try { recognitionRef.current?.stop() } catch {}
    window.speechSynthesis?.cancel()
    setState('ended')
  }

  function handleRestart() {
    window.speechSynthesis?.cancel()
    if (retryTimerRef.current) { clearTimeout(retryTimerRef.current); retryTimerRef.current = null }
    consecutiveFailuresRef.current = 0
    setTurns([])
    setInterim('')
    setErrorMsg(null)
    void openWithWelcome()
  }

  const statusLabel: Record<CallState, string> = {
    idle: 'Connecting…',
    listening: 'Listening',
    thinking: 'Thinking…',
    speaking: 'Speaking',
    ended: 'Call ended',
    unsupported: 'Mic not supported in this browser',
    'no-mic': 'No microphone found',
    'mic-busy': 'Microphone in use elsewhere',
    'network-error': 'Connection error',
  }
  const isErrorState = state === 'unsupported' || state === 'no-mic' || state === 'mic-busy' || state === 'network-error'

  return (
    <Modal onClose={onClose} title="Test Voice Agent" subtitle={agent.name} maxWidth="max-w-lg">
      <div className="flex items-center justify-between mb-3">
        <Badge tone={state === 'listening' ? 'success' : state === 'speaking' ? 'accent' : isErrorState ? 'danger' : 'default'}>
          {statusLabel[state]}
        </Badge>
        {state === 'thinking' && <Loader2 size={14} className="animate-spin text-white/40" />}
      </div>

      {state === 'unsupported' && (
        <div className="flex items-start gap-2 text-xs text-amber-300/90 bg-amber-500/10 border border-amber-500/20 rounded-xl p-3 mb-3">
          <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
          <span>Your browser doesn't support in-browser microphone speech recognition. Try Chrome or Edge on desktop.</span>
        </div>
      )}

      {errorMsg && (
        <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl p-3 mb-3">
          {errorMsg}
        </div>
      )}

      <div className="tb2-glass rounded-2xl p-3 h-72 overflow-y-auto flex flex-col gap-2 mb-4">
        {turns.length === 0 && !isErrorState && (
          <div className="m-auto text-xs text-white/30">Say hello — the transcript will appear here live.</div>
        )}
        {turns.map(t => (
          <div
            key={t.id}
            className={cn(
              'max-w-[85%] text-xs sm:text-sm rounded-2xl px-3 py-2 leading-relaxed',
              t.role === 'assistant'
                ? 'self-start bg-white/[0.06] text-white/85'
                : 'self-end bg-cyan-500/15 text-cyan-100'
            )}
          >
            {t.content}
          </div>
        ))}
        {interim && (
          <div className="self-end max-w-[85%] text-xs sm:text-sm rounded-2xl px-3 py-2 leading-relaxed bg-cyan-500/5 text-cyan-200/50 italic">
            {interim}
          </div>
        )}
        <div ref={transcriptEndRef} />
      </div>

      <div className="flex items-center justify-center gap-3">
        {state === 'no-mic' || state === 'mic-busy' || state === 'network-error' ? (
          <Button variant="secondary" size="md" icon={<RotateCcw size={14} />} onClick={handleRestart}>
            Try again
          </Button>
        ) : state !== 'ended' ? (
          <>
            <div
              className={cn(
                'w-11 h-11 rounded-full flex items-center justify-center flex-shrink-0',
                state === 'listening' && 'bg-emerald-500/20 text-emerald-300',
                state === 'speaking' && 'bg-[#818cf8]/20 text-[#818cf8]',
                (state === 'thinking' || state === 'idle') && 'bg-white/[0.06] text-white/30',
                state === 'unsupported' && 'bg-white/[0.06] text-white/20'
              )}
            >
              {state === 'speaking' ? <Volume2 size={18} /> : state === 'listening' ? <Mic size={18} /> : <MicOff size={18} />}
            </div>
            <Button variant="danger" size="md" icon={<PhoneOff size={14} />} onClick={handleEnd} disabled={state === 'unsupported'}>
              End
            </Button>
          </>
        ) : (
          <Button variant="secondary" size="md" icon={<RotateCcw size={14} />} onClick={handleRestart}>
            Restart conversation
          </Button>
        )}
      </div>
    </Modal>
  )
}
