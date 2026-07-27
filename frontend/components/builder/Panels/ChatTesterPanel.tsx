'use client'
import { useEffect, useRef, useState, useCallback, memo } from 'react'
import { useRouter } from 'next/navigation'
import { Send, RefreshCw, Bug, RotateCcw, Volume2, VolumeX, PlayCircle, Loader2, ChevronDown, KeyRound } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useWorkflowStore } from '@/store/workflowStore'
import { WS_URL } from '@/lib/api/client'
import { voiceApi } from '@/lib/api/voice'
import { getErrorMessage } from '@/lib/utils/errors'
import { cn } from '@/lib/utils/cn'
import type { ChatMessage, VoiceProviderId, VoiceProviderInfo, VoiceGender, VoiceOption, VoicePersonality } from '@/types'
import type { SpeechStreamController } from '@/lib/voice'
import { VOICE_PERSONALITIES, DEFAULT_VOICE_PERSONALITY } from '@/lib/voice/personality'
import { useFeatureTutorial } from '@/hooks/useFeatureTutorial'

// Purely cosmetic click-ripple, used on interactive chat-tester controls.
// Spawns a short-lived absolutely-positioned span inside the element that
// was clicked (which must have position:relative + overflow:hidden via
// the `ctp-ripple-host` class) and lets it self-remove after its CSS
// animation finishes. Never calls preventDefault/stopPropagation, so it
// never interferes with the button's real onClick handler or disabled state.
function spawnRipple(e: React.MouseEvent<HTMLElement>) {
  const el = e.currentTarget
  if (el.hasAttribute('disabled')) return
  const rect = el.getBoundingClientRect()
  const size = Math.max(rect.width, rect.height) * 1.4
  const span = document.createElement('span')
  span.className = 'ctp-ripple'
  span.style.width = `${size}px`
  span.style.height = `${size}px`
  span.style.left = `${e.clientX - rect.left - size / 2}px`
  span.style.top = `${e.clientY - rect.top - size / 2}px`
  el.appendChild(span)
  window.setTimeout(() => span.remove(), 600)
}

// Extracted + memoized: each bubble only re-renders when its own message
// object changes. Previously the entire message list (including markdown
// parsing for every bot message) was re-rendered on every keystroke in
// the input box, because everything lived in one component that shared
// `input` state with the message list JSX.
const MessageBubble = memo(function MessageBubble({
  msg, debugMode, isTyping, onChoiceClick,
}: {
  msg: ChatMessage
  debugMode: boolean
  isTyping: boolean
  onChoiceClick: (label: string) => void
}) {
  return (
    <div className="ctp-msg-in">
      <div className={cn('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
        <div className={cn(
          'max-w-[92%] rounded-2xl text-sm leading-relaxed',
          msg.role === 'user'
            ? 'ctp-bubble-user text-white px-4 py-2.5 rounded-br-sm'
            : msg.role === 'system'
            ? 'text-[10px] text-white/25 italic px-2 py-1'
            : 'ctp-bubble-bot text-white/80 px-4 py-2.5 rounded-bl-sm chat-message'
        )}>
          {msg.role === 'bot' && msg.image?.url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={msg.image.url}
              alt=""
              className="w-full h-auto max-h-56 object-contain rounded-lg mb-2 shadow-lg"
            />
          )}
          {msg.role === 'bot' ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {msg.content || (msg.isStreaming ? '' : '')}
            </ReactMarkdown>
          ) : (
            msg.content
          )}
          {msg.isStreaming && (
            <span className="inline-block w-0.5 h-3.5 ctp-cursor ml-0.5 align-middle rounded-full" />
          )}
        </div>
      </div>

      {/* Debug info */}
      {debugMode && msg.nodeId && (
        <p className={cn(
          'text-[9px] text-white/15 mt-0.5 font-mono',
          msg.role === 'user' ? 'text-right' : 'text-left px-1'
        )}>
          → {msg.nodeId} ({msg.nodeType})
        </p>
      )}

      {/* Citations — sources from the Knowledge Base used to ground this answer */}
      {msg.citations && msg.citations.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-1.5 ml-1">
          {msg.citations.map((c) => (
            <span
              key={c.index}
              title={c.excerpt}
              className="ctp-citation text-[10px] px-2 py-1 rounded-lg bg-white/[0.04] border border-white/10
                         text-white/40 cursor-help hover:text-white/60 hover:border-white/20"
            >
              [{c.index}] {c.source} · {Math.round(c.score * 100)}%
            </span>
          ))}
        </div>
      )}

      {/* Choice buttons */}
      {msg.choices && msg.choices.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-2 ml-1">
          {msg.choices.map((c, i) => (
            <button key={i}
              onClick={() => onChoiceClick(c.label)}
              onMouseDown={spawnRipple}
              disabled={isTyping}
              className="ctp-chip ctp-ripple-host text-xs px-3 py-1.5 rounded-xl border border-[#6366f1]/30
                         text-[#a5b4fc] disabled:opacity-30 disabled:cursor-not-allowed">
              {c.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
})

const GENDERS: { id: VoiceGender; label: string }[] = [
  { id: 'neutral', label: 'Neutral' },
  { id: 'male',    label: 'Male' },
  { id: 'female',  label: 'Female' },
]

/**
 * Voice Responses section for the Test Chat panel. Entirely self-contained
 * and additive: when Enable Voice is OFF (the default) nothing here does
 * anything more than render a toggle — no provider list is fetched until
 * the section is opened, and no speech/TTS module is ever imported until
 * a bot reply actually needs to be spoken or Test Voice is pressed.
 */
function VoiceResponsesSection({
  open, onToggleOpen,
  enabled, onEnabledChange,
  provider, onProviderChange,
  gender, onGenderChange,
  voiceId, onVoiceIdChange,
  personality, onPersonalityChange,
}: {
  open: boolean
  onToggleOpen: () => void
  enabled: boolean
  onEnabledChange: (v: boolean) => void
  provider: VoiceProviderId
  onProviderChange: (v: VoiceProviderId) => void
  gender: VoiceGender
  onGenderChange: (v: VoiceGender) => void
  voiceId: string | null
  onVoiceIdChange: (v: string | null) => void
  personality: VoicePersonality
  onPersonalityChange: (v: VoicePersonality) => void
}) {
  const [providers, setProviders] = useState<VoiceProviderInfo[]>([])
  const [providersLoaded, setProvidersLoaded] = useState(false)
  const [browserVoices, setBrowserVoices] = useState<VoiceOption[]>([])
  const [testing, setTesting] = useState(false)
  const [testMsg, setTestMsg] = useState<{ ok: boolean; text: string } | null>(null)

  // Fetch the provider catalog only once the section is actually opened.
  useEffect(() => {
    if (!open || providersLoaded) return
    setProvidersLoaded(true)
    voiceApi.listProviders().then(setProviders).catch(() => setProviders([
      { id: 'browser', name: 'Browser (Free)', requires_key: false, requires_region: false, configured: true, voices: [] },
    ]))
  }, [open, providersLoaded])

  // Only ever imports the native SpeechSynthesis wrapper when Browser is selected.
  useEffect(() => {
    if (provider !== 'browser') return
    let cancelled = false
    import('@/lib/voice/speechSynthesis').then(mod => mod.whenVoicesReady()).then(voices => {
      if (!cancelled) setBrowserVoices(voices)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [provider])

  const activeProviderVoices: VoiceOption[] =
    provider === 'browser' ? browserVoices : (providers.find(p => p.id === provider)?.voices ?? [])
  const genderFiltered = gender === 'neutral'
    ? activeProviderVoices
    : activeProviderVoices.filter(v => v.gender === gender)
  const voiceChoices = genderFiltered.length > 0 ? genderFiltered : activeProviderVoices

  const handleTestVoice = useCallback(async () => {
    setTesting(true)
    setTestMsg(null)
    const sample = 'This is a test of the ThunderBots voice response system.'
    try {
      if (provider === 'browser') {
        const mod = await import('@/lib/voice/speechSynthesis')
        if (!mod.isVoiceSupported()) {
          setTestMsg({ ok: false, text: 'Browser voice is not supported in this browser.' })
          return
        }
        await mod.speak(sample, { voiceId, gender, personality })
        setTestMsg({ ok: true, text: 'Played' })
      } else {
        const blob = await voiceApi.synthesize({ provider, text: sample, voice: voiceId, personality })
        const url = URL.createObjectURL(blob)
        const audio = new Audio(url)
        await new Promise<void>((resolve) => {
          audio.onended = () => resolve()
          audio.onerror = () => resolve()
          audio.play().then(undefined, () => resolve())
        })
        URL.revokeObjectURL(url)
        setTestMsg({ ok: true, text: 'Played' })
      }
    } catch (err) {
      setTestMsg({ ok: false, text: getErrorMessage(err, 'Voice test failed') })
    } finally {
      setTesting(false)
    }
  }, [provider, voiceId, gender, personality])

  return (
    <div className="border-t border-[#1a1a1a] flex-shrink-0">
      <button
        onClick={onToggleOpen}
        className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-semibold text-white/50 hover:text-white/70 transition"
      >
        <span className="flex items-center gap-1.5">
          {enabled ? <Volume2 size={12} /> : <VolumeX size={12} />}
          Voice Responses
        </span>
        <ChevronDown size={12} className={cn('transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="px-4 pb-3 space-y-2.5 tb-anim-fade-up">
          {/* Enable Voice */}
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-white/45">Enable Voice</span>
            <button
              onClick={() => onEnabledChange(!enabled)}
              className={cn('relative w-8 h-4.5 rounded-full transition-colors flex-shrink-0',
                enabled ? 'bg-[#6366f1]' : 'bg-[#2a2a2a]')}
              style={{ height: 18 }}
            >
              <span className={cn('absolute top-0.5 left-0.5 w-3.5 h-3.5 rounded-full bg-white transition-transform',
                enabled && 'translate-x-3.5')} />
            </button>
          </div>

          {enabled && (
            <>
              {/* Voice Provider */}
              <div>
                <label className="text-[10px] font-semibold text-white/30 uppercase tracking-wider mb-1 block">Voice Provider</label>
                <select
                  value={provider}
                  onChange={(e) => { onProviderChange(e.target.value as VoiceProviderId); onVoiceIdChange(null) }}
                  className="w-full bg-[#141414] text-xs text-white/80 border border-[#242424] rounded-lg px-2.5 py-1.5 outline-none focus:border-[#6366f1]/50"
                >
                  <option value="browser">Browser (Free)</option>
                  {providers.filter(p => p.id !== 'browser').map(p => (
                    <option key={p.id} value={p.id} disabled={!p.configured}>
                      {p.name}{!p.configured ? ' — no API key saved' : ''}
                    </option>
                  ))}
                </select>
              </div>

              {/* Voice (gender filter + auto-detected list) */}
              <div>
                <label className="text-[10px] font-semibold text-white/30 uppercase tracking-wider mb-1 block">Voice</label>
                <div className="flex bg-[#111] rounded-lg p-0.5 border border-[#1a1a1a] mb-1.5">
                  {GENDERS.map(g => (
                    <button
                      key={g.id}
                      onClick={() => { onGenderChange(g.id); onVoiceIdChange(null) }}
                      className={cn('flex-1 py-1 rounded-md text-[10px] font-medium transition',
                        gender === g.id ? 'bg-[#242424] text-white/80' : 'text-white/30 hover:text-white/55')}
                    >
                      {g.label}
                    </button>
                  ))}
                </div>
                <select
                  value={voiceId ?? ''}
                  onChange={(e) => onVoiceIdChange(e.target.value || null)}
                  className="w-full bg-[#141414] text-xs text-white/80 border border-[#242424] rounded-lg px-2.5 py-1.5 outline-none focus:border-[#6366f1]/50"
                >
                  <option value="">Auto-detect</option>
                  {voiceChoices.map(v => (
                    <option key={v.id} value={v.id}>{v.name}</option>
                  ))}
                </select>
              </div>

              {/* Voice Personality — playback style only, never changes bot text */}
              <div>
                <label className="text-[10px] font-semibold text-white/30 uppercase tracking-wider mb-1 block">Voice Personality</label>
                <select
                  value={personality}
                  onChange={(e) => onPersonalityChange(e.target.value as VoicePersonality)}
                  className="w-full bg-[#141414] text-xs text-white/80 border border-[#242424] rounded-lg px-2.5 py-1.5 outline-none focus:border-[#6366f1]/50"
                >
                  {VOICE_PERSONALITIES.map(p => (
                    <option key={p.id} value={p.id}>{p.label} — {p.hint}</option>
                  ))}
                </select>
              </div>

              <button
                onClick={handleTestVoice}
                disabled={testing}
                className="w-full flex items-center justify-center gap-1.5 text-[11px] font-medium px-3 py-2 rounded-lg
                           bg-[#1a1a1a] border border-[#2a2a2a] text-white/60 hover:text-white/85 hover:border-[#3a3a3a]
                           disabled:opacity-50 transition"
              >
                {testing ? <Loader2 size={12} className="animate-spin" /> : <PlayCircle size={12} />}
                Test Voice
              </button>
              {testMsg && (
                <p className={cn('text-[10px]', testMsg.ok ? 'text-emerald-400/80' : 'text-red-400/80')}>
                  {testMsg.text}
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ROOT CAUSE FIX: when an AI Agent node has no usable provider API key, the
// backend already refuses to call the provider at all (it raises before any
// request goes out — see resolve_agent_provider / get_provider_instance in
// app/services/ai_engine.py) and reports one of two specific, stable
// messages through the WS "error" event. Previously the panel rendered that
// as a generic "⚠ Execution error: ..." system bubble, indistinguishable
// from any other failure. Detect these two specific signatures and show a
// dedicated, actionable inline card instead — never a plain error string.
function isMissingApiKeyError(content: string | undefined): boolean {
  if (!content) return false
  const c = content.toLowerCase()
  return (
    (c.includes('api key') && (c.includes('no api key configured') || c.includes('add one in settings'))) ||
    (c.includes('no provider configured') && c.includes('default ai provider'))
  )
}

export function ChatTesterPanel() {
  useFeatureTutorial('ai-chat')
  const router = useRouter()
  const workflowId = useWorkflowStore(s => s.workflowId)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [connected, setConnected] = useState(false)
  const [debugMode, setDebugMode] = useState(false)
  const [isTyping, setIsTyping] = useState(false)
  const [apiKeyRequired, setApiKeyRequired] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const streamIdRef = useRef<string | null>(null)
  // Mirrors `input` without being a render dependency, so sendMessage can
  // stay referentially stable while typing (see sendMessage below).
  const inputValueRef = useRef('')

  // ── Voice Responses (Test Chat only — local to this session, never saved) ──
  const [voiceOpen, setVoiceOpen] = useState(false)
  const [voiceEnabled, setVoiceEnabled] = useState(false)
  const [voiceProvider, setVoiceProvider] = useState<VoiceProviderId>('browser')
  const [voiceGender, setVoiceGender] = useState<VoiceGender>('neutral')
  const [voiceId, setVoiceId] = useState<string | null>(null)
  const [voicePersonality, setVoicePersonality] = useState<VoicePersonality>(DEFAULT_VOICE_PERSONALITY)
  // Read from the WebSocket message handler via a ref so toggling Voice
  // never requires reconnecting or recreating the socket's handlers.
  const voiceConfigRef = useRef({ enabled: false, provider: 'browser' as VoiceProviderId, voiceId: null as string | null, gender: 'neutral' as VoiceGender, personality: DEFAULT_VOICE_PERSONALITY })
  useEffect(() => {
    voiceConfigRef.current = { enabled: voiceEnabled, provider: voiceProvider, voiceId, gender: voiceGender, personality: voicePersonality }
  }, [voiceEnabled, voiceProvider, voiceId, voiceGender, voicePersonality])

  // Fire-and-forget: only ever called after the text is already rendered,
  // so voice generation/playback can never delay chat responses.
  const speakBotMessage = useCallback((text: string) => {
    const cfg = voiceConfigRef.current
    if (!cfg.enabled || !text || !text.trim()) return
    import('@/lib/voice').then(mod => mod.speakWithProvider({
      text,
      provider: cfg.provider,
      voiceId: cfg.voiceId,
      gender: cfg.gender,
      personality: cfg.personality,
      fetchAudio: cfg.provider === 'browser' ? undefined : (args) => voiceApi.synthesize(args),
    })).catch(() => { /* voice is best-effort; never surfaces as a chat error */ })
  }, [])

  // Holds the in-progress incremental speech session for the bot message
  // currently streaming in, if Voice is on. Lets speech start on the first
  // sentence instead of waiting for the whole response to finish.
  const speechStreamRef = useRef<SpeechStreamController | null>(null)

  // Called once per streamed token — cheap no-op unless Voice is enabled.
  const pushSpeechToken = useCallback((token: string) => {
    const cfg = voiceConfigRef.current
    if (!cfg.enabled || !token) return
    if (!speechStreamRef.current) {
      import('@/lib/voice').then(mod => {
        // A token may have already arrived and been dropped between the
        // dynamic import resolving and now only if the stream was already
        // started elsewhere — guard so we never create two overlapping streams.
        if (speechStreamRef.current) return
        speechStreamRef.current = mod.startSpeechStream({
          provider: cfg.provider,
          voiceId: cfg.voiceId,
          gender: cfg.gender,
          personality: cfg.personality,
          fetchAudio: cfg.provider === 'browser' ? undefined : (args) => voiceApi.synthesize(args),
        })
        speechStreamRef.current.push(token)
      }).catch(() => { /* voice is best-effort; never surfaces as a chat error */ })
      return
    }
    speechStreamRef.current.push(token)
  }, [])

  // Called when the streamed response completes — speaks whatever's left
  // buffered (e.g. a final clause with no terminal punctuation).
  const flushSpeechStream = useCallback(() => {
    if (speechStreamRef.current) {
      speechStreamRef.current.flush()
      speechStreamRef.current = null
    }
  }, [])

  const addMessage = (msg: Partial<ChatMessage>): string => {
    const full: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'bot',
      content: '',
      timestamp: new Date(),
      ...msg,
    }
    setMessages(prev => [...prev, full])
    return full.id
  }

  const appendToken = (id: string, token: string) => {
    setMessages(prev =>
      prev.map(m => m.id === id ? { ...m, content: m.content + token, isStreaming: true } : m)
    )
  }

  const finalizeMessage = (id: string, extra: Partial<ChatMessage> = {}) => {
    setMessages(prev =>
      prev.map(m => m.id === id ? { ...m, ...extra, isStreaming: false } : m)
    )
  }

  const connect = useCallback(() => {
    if (!workflowId) return
    wsRef.current?.close()
    setMessages([])
    setConnected(false)
    setIsTyping(false)
    setApiKeyRequired(false)
    streamIdRef.current = null

    const token = typeof window !== 'undefined' ? localStorage.getItem('tb_token') : null
    const url = `${WS_URL}/ws/chat/${workflowId}${token ? `?token=${token}` : ''}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        if (data.type === 'connected') {
          addMessage({ role: 'system', content: `✓ Connected to "${data.workflow}"` })
          return
        }
        if (data.type === 'token') {
          if (!streamIdRef.current) {
            streamIdRef.current = addMessage({ role: 'bot', content: '', isStreaming: true })
            setIsTyping(false)
          }
          appendToken(streamIdRef.current, data.content)
          // Speak incrementally as text streams in — starts on the first
          // complete sentence instead of waiting for the full response.
          pushSpeechToken(data.content)
          return
        }
        if (data.type === 'done') {
          if (streamIdRef.current) {
            const finishedId = streamIdRef.current
            finalizeMessage(finishedId, {
              nodeId: data.next_node_id,
              nodeType: data.node_type,
              citations: data.citations && data.citations.length > 0 ? data.citations : undefined,
            })
            // Text is already rendered — speak whatever's left buffered
            // (already-spoken sentences are not repeated).
            flushSpeechStream()
            streamIdRef.current = null
          }
          setIsTyping(false)
          return
        }
        if (data.type === 'message') {
          setIsTyping(false)
          addMessage({
            role: 'bot',
            content: data.content,
            choices: data.choices,
            image: data.image,
            nodeType: data.node_type,
          })
          speakBotMessage(data.content)
          return
        }
        if (data.type === 'ended') { setIsTyping(false); return }
        if (data.type === 'error') {
          setIsTyping(false)
          streamIdRef.current = null
          speechStreamRef.current?.stop()
          speechStreamRef.current = null
          if (isMissingApiKeyError(data.content)) {
            setApiKeyRequired(true)
          } else {
            addMessage({ role: 'system', content: `⚠ ${data.content}` })
          }
        }
      } catch {
        // ignore parse errors
      }
    }

    // FIX: previously there was no onerror handler at all, so a WebSocket
    // that failed to connect (wrong/unreachable NEXT_PUBLIC_WS_URL, mixed
    // content blocked by the browser on an https page trying ws://, backend
    // down, etc.) surfaced as nothing — the panel just silently stayed
    // "disconnected" with no explanation, which looked identical to "the AI
    // Agent isn't generating a response." This gives the user an actionable
    // message instead of silent failure.
    ws.onerror = () => {
      setIsTyping(false)
      addMessage({
        role: 'system',
        content: '⚠ Could not connect to the chat server. Check that the backend is running and reachable at the configured WebSocket URL (NEXT_PUBLIC_WS_URL).',
      })
    }

    ws.onclose = () => {
      setConnected(false)
      setIsTyping(false)
      streamIdRef.current = null
    }
  }, [workflowId])

  // Reads the current input from a ref (kept in sync by the onChange
  // handler below) instead of depending on `input` state. This keeps
  // sendMessage's identity stable across keystrokes, which in turn lets
  // the memoized MessageBubble list (and the choice buttons that call
  // this function) skip re-rendering while the user is typing.
  const sendMessage = useCallback((text?: string) => {
    const msg = (text ?? inputValueRef.current).trim()
    if (!msg || !wsRef.current || !connected) return
    setApiKeyRequired(false)
    addMessage({ role: 'user', content: msg })
    wsRef.current.send(JSON.stringify({ message: msg }))
    inputValueRef.current = ''
    setInput('')
    setIsTyping(true)
    inputRef.current?.focus()
  }, [connected])

  const onInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    inputValueRef.current = e.target.value
    setInput(e.target.value)
  }, [])

  const reset = useCallback(() => {
    wsRef.current?.send(JSON.stringify({ type: 'reset' }))
    setMessages([])
    setIsTyping(false)
    streamIdRef.current = null
    speechStreamRef.current = null
    import('@/lib/voice').then(mod => mod.stopSpeaking()).catch(() => {})
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping])

  return (
    <div className="ctp-root flex flex-col h-full">
      {/* Header */}
      <div className="ctp-header flex items-center justify-between px-4 py-3 flex-shrink-0">
        <div className="flex items-center gap-2">
          <div className={cn(
            'w-1.5 h-1.5 rounded-full transition-colors duration-300',
            connected ? 'bg-emerald-400 ctp-dot-live' : 'bg-zinc-600'
          )} />
          <span className="text-xs font-semibold ctp-title">Chat Tester</span>
        </div>
        <div className="flex items-center gap-1">
          {connected && (
            <button onClick={reset} title="Reset conversation"
              className="ctp-iconbtn p-1.5 rounded-lg text-white/20 hover:text-white/60">
              <RotateCcw size={12} />
            </button>
          )}
          <button onClick={() => setDebugMode(d => !d)} title="Debug mode"
            className={cn('ctp-iconbtn p-1.5 rounded-lg',
              debugMode ? 'text-[#a5b4fc]' : 'text-white/20 hover:text-white/60')}>
            <Bug size={12} />
          </button>
          <button
            onClick={connect}
            onMouseDown={spawnRipple}
            data-tutorial="chat-start"
            className="ctp-startbtn ctp-ripple-host flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 rounded-lg
                       text-white font-medium"
          >
            <RefreshCw size={11} />
            {connected ? 'Restart' : 'Start'}
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="ctp-scroll flex-1 overflow-y-auto p-3 space-y-3" data-tutorial="chat-messages">
        {!connected && messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center py-10">
            <div className="ctp-emptystate-icon w-10 h-10 rounded-2xl
                            flex items-center justify-center mb-3">
              <Send size={16} className="text-[#a5b4fc]" />
            </div>
            <p className="text-xs text-white/25">Click Start to test your workflow</p>
          </div>
        )}

        {messages.map(msg => (
          <MessageBubble
            key={msg.id}
            msg={msg}
            debugMode={debugMode}
            isTyping={isTyping}
            onChoiceClick={sendMessage}
          />
        ))}

        {/* Typing indicator */}
        {isTyping && (
          <div className="flex justify-start ctp-msg-in">
            <div className="ctp-typing rounded-2xl rounded-bl-sm
                            px-4 py-3 flex gap-1.5">
              {[0, 1, 2].map(i => (
                <div key={i} className="w-1.5 h-1.5 rounded-full ctp-typing-dot"
                  style={{ animationDelay: `${i * 0.15}s` }} />
              ))}
            </div>
          </div>
        )}

        {apiKeyRequired && (
          <div className="flex justify-start ctp-msg-in">
            <div className="ctp-apikey-card w-full max-w-[92%] rounded-2xl rounded-bl-sm border border-[#6366f1]/25 p-4">
              <div className="flex items-start gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-[#6366f1]/15 border border-[#6366f1]/25 flex items-center justify-center flex-shrink-0">
                  <KeyRound size={14} className="text-[#a5b4fc]" />
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-white/90 leading-snug">AI Provider API Key Required</p>
                  <p className="text-[11px] text-white/40 mt-1 leading-relaxed">
                    This AI Agent needs a configured provider API key before it can respond.
                  </p>
                </div>
              </div>
              <div className="flex gap-2 mt-3">
                <button
                  onClick={() => setApiKeyRequired(false)}
                  className="flex-1 text-[11px] font-medium px-3 py-1.5 rounded-lg text-white/50 hover:text-white/80 border border-white/10 hover:bg-white/[0.06] transition"
                >
                  Cancel
                </button>
                <button
                  onClick={() => router.push(`/settings/api-keys?returnTo=${encodeURIComponent('/builder')}`)}
                  onMouseDown={spawnRipple}
                  className="ctp-startbtn ctp-ripple-host flex-1 text-[11px] font-medium px-3 py-1.5 rounded-lg text-white"
                >
                  Add API Key
                </button>
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Voice Responses */}
      <VoiceResponsesSection
        open={voiceOpen}
        onToggleOpen={() => setVoiceOpen(o => !o)}
        enabled={voiceEnabled}
        onEnabledChange={setVoiceEnabled}
        provider={voiceProvider}
        onProviderChange={setVoiceProvider}
        gender={voiceGender}
        onGenderChange={setVoiceGender}
        voiceId={voiceId}
        onVoiceIdChange={setVoiceId}
        personality={voicePersonality}
        onPersonalityChange={setVoicePersonality}
      />

      {/* Input */}
      <div className="ctp-inputbar p-3 flex-shrink-0">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            value={input}
            onChange={onInputChange}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage()}
            placeholder={connected ? 'Type a message…' : 'Start the chat first'}
            disabled={!connected}
            data-tutorial="chat-input"
            className="ctp-input flex-1 text-sm text-white placeholder-white/15
                       rounded-xl px-3.5 py-2.5 outline-none
                       disabled:opacity-40"
          />
          <button
            onClick={() => sendMessage()}
            onMouseDown={spawnRipple}
            disabled={!connected || !input.trim()}
            className="ctp-sendbtn ctp-ripple-host p-2.5 rounded-xl
                       disabled:opacity-30 disabled:cursor-not-allowed text-white flex-shrink-0"
          >
            <Send size={15} />
          </button>
        </div>
      </div>
    </div>
  )
}
