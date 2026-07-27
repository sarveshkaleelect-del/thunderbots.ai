'use client'
import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useParams } from 'next/navigation'
import { Send, RotateCcw, AlertTriangle, Loader2, Bot, Paperclip, Volume2, VolumeX, Headset } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { getErrorMessage } from '@/lib/utils/errors'
import type { BotBranding, DesignConfig, ChatSettings } from '@/types'
import type { SpeechStreamController } from '@/lib/voice'
import VoiceAssistant, { type VoiceBotEventListener } from '@/components/chat/VoiceAssistant'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const WS_URL  = process.env.NEXT_PUBLIC_WS_URL  || 'ws://localhost:8000'

interface ChatMsg {
  id: string
  role: 'user' | 'bot' | 'system' | 'agent'
  content: string
  choices?: { label: string; value: string }[]
  image?: { url: string; filename?: string } | null
  citations?: { index: number; source: string; score: number; excerpt: string }[]
  isStreaming?: boolean
  time?: string
  agentName?: string
}

type LoadState = 'loading' | 'ready' | 'not_found' | 'error'

const DEFAULT_BRANDING: BotBranding = {
  bot_name: 'Chatbot', logo_url: null, avatar_url: null,
  welcome_title: 'Hi there! 👋', welcome_description: "Ask me anything, I'm happy to help.",
  browser_title: null, favicon_url: null, theme_color: '#6366f1', accent_color: '#818cf8',
}
const DEFAULT_DESIGN: DesignConfig = {
  background_color: '#070708', background_gradient: null, background_image: null,
  bot_bubble_color: '#161616', user_bubble_color: '#6366f1',
  font_family: 'Inter, system-ui, sans-serif', font_size: 15, border_radius: 16,
  shadows: true, glassmorphism: false, mode: 'dark',
}
const DEFAULT_CHAT_SETTINGS: ChatSettings = {
  show_bot_logo: true, show_bot_name: true, show_timestamp: false, show_typing_indicator: true,
  show_restart_button: true, show_powered_by: true, enable_sound: false, enable_file_upload: false,
  enable_markdown: true, enable_auto_scroll: true,
  voice: {
    response_mode: 'text_only', enabled: false, provider: 'browser',
    voice_id: null, gender: 'neutral', personality: 'friendly', allow_mute: true, default_state: 'on',
  },
}

function playChime() {
  try {
    const Ctx = window.AudioContext || (window as any).webkitAudioContext
    const ctx = new Ctx()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.setValueAtTime(720, ctx.currentTime)
    gain.gain.setValueAtTime(0.06, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.25)
    osc.connect(gain).connect(ctx.destination)
    osc.start()
    osc.stop(ctx.currentTime + 0.25)
  } catch {
    // audio unsupported/blocked — non-critical
  }
}

/**
 * ThunderBots — Public deployed chatbot page.
 * Fully themed by Deploy Branding / Deploy Page Customization / Deployment
 * Settings — what you configure in the builder's Deploy panel is exactly
 * what ships here (same defaults, same fields).
 */
export default function PublicChatPage() {
  const params = useParams<{ slug: string }>()
  const slug = params.slug

  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [loadError, setLoadError] = useState<string | null>(null)
  const [workflowId, setWorkflowId] = useState<string | null>(null)
  const [branding, setBranding] = useState<BotBranding>(DEFAULT_BRANDING)
  const [design, setDesign] = useState<DesignConfig>(DEFAULT_DESIGN)
  const [cs, setCs] = useState<ChatSettings>(DEFAULT_CHAT_SETTINGS)

  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [connected, setConnected] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [isTyping, setIsTyping] = useState(false)
  // Voice Responses — end-user-facing control is only ever a mute toggle;
  // the Default Response Mode itself is set per-bot in Bot Settings and
  // never exposed here. Starts unmuted so the admin's chosen mode applies
  // immediately, matching how enable_sound / other defaults behave.
  const [voiceMuted, setVoiceMuted] = useState(false)
  // NEW (Live Agent): tracks whether a human has taken over this
  // conversation, purely for the visitor-facing UI (banner + input hint).
  // The actual handoff state lives server-side (live_agent_handoffs).
  const [humanAgent, setHumanAgent] = useState<string | null>(null)
  const [handoffRequested, setHandoffRequested] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  // ROOT CAUSE FIX (Network connection error): the socket previously had no
  // reconnection logic at all — once it dropped (transient network blip,
  // idle-timeout on a proxy/load balancer, server restart, laptop sleep/wake,
  // switching wifi/cell) the widget stayed dead until the visitor manually
  // reloaded the page. `connected` flipping to false also disables the Voice
  // Assistant launcher, which is why that dead socket surfaced to users as a
  // stuck "Network connection error" with no way to recover. These refs back
  // a bounded exponential-backoff reconnect loop.
  const reconnectAttemptRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const manualCloseRef = useRef(false)
  const MAX_RECONNECT_ATTEMPTS = 8
  const [reconnecting, setReconnecting] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const streamIdRef = useRef<string | null>(null)
  // Root-cause fix: the socket URL never carried session_id even though the
  // backend accepts and resumes one (see chat_ws.py). Without it, every
  // reconnect silently started a brand-new session — context, turn count,
  // and any in-progress handoff were lost, which is especially disruptive
  // for a voice call that reconnects mid-conversation after a network blip.
  const sessionIdRef = useRef<string | null>(null)
  // Lazily-loaded, cached-once voice orchestrator. Never imported until the
  // bot's Response Mode requires it, so Text Only bots never fetch/parse/run it.
  const voiceModuleRef = useRef<Promise<typeof import('@/lib/voice')> | null>(null)
  // NEW (Voice AI, Part 1): the floating "Talk to AI" bubble registers its
  // event handlers here while a voice session is open, and this component
  // forwards bot-socket events to it. `voiceSessionActiveRef` lets the
  // existing Speaker/auto-read pipeline below stand down while a voice
  // session owns spoken output, so a reply is never narrated twice.
  const voiceListenerRef = useRef<VoiceBotEventListener | null>(null)
  const voiceSessionActiveRef = useRef(false)

  const addMessage = (msg: Partial<ChatMsg>): string => {
    const id = crypto.randomUUID()
    const time = new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    setMessages(prev => [...prev, { id, role: 'bot', content: '', time, ...msg }])
    return id
  }
  const appendToken = (id: string, token: string) => {
    setMessages(prev => prev.map(m => m.id === id ? { ...m, content: m.content + token, isStreaming: true } : m))
  }
  const finalize = (id: string, extra: Partial<ChatMsg> = {}) => {
    setMessages(prev => prev.map(m => m.id === id ? { ...m, ...extra, isStreaming: false } : m))
  }

  // ── Voice Responses (optional, additive) ──────────────────────────────────
  // Provider, voice, and Response Mode are configured per-bot in Deploy
  // Settings and deployed with the bot; end users never see any of that,
  // only a Speaker ON/OFF icon — and only if "Allow End Users to Mute" is on.
  const voiceMode = cs.voice?.response_mode ?? 'text_only'
  const voiceEnabledForBot = voiceMode !== 'text_only'
  const allowMute = cs.voice?.allow_mute !== false
  // When end users can't mute, the bot owner's Default State is permanent.
  const effectiveMuted = allowMute ? voiceMuted : cs.voice?.default_state === 'off'
  const voiceActive = voiceEnabledForBot && !effectiveMuted
  // Long-lived WebSocket handlers close over state from connect-time; this
  // ref keeps the mute toggle effective immediately without needing to
  // reconnect or re-create the socket handlers.
  const voiceActiveRef = useRef(voiceActive)
  useEffect(() => { voiceActiveRef.current = voiceActive }, [voiceActive])

  // Apply the bot's configured Default State once, the first time settings
  // load — after that the visitor's own toggle (if allowed) takes over.
  const voiceDefaultAppliedRef = useRef(false)
  useEffect(() => {
    if (loadState !== 'ready' || voiceDefaultAppliedRef.current) return
    voiceDefaultAppliedRef.current = true
    if (allowMute && cs.voice?.default_state === 'off') setVoiceMuted(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadState])

  const loadVoiceModule = useCallback(() => {
    if (!voiceModuleRef.current) {
      voiceModuleRef.current = import('@/lib/voice')
    }
    return voiceModuleRef.current
  }, [])

  // Fire-and-forget: text is already on screen by the time this runs, so
  // voice generation/playback can never delay or block message rendering.
  // Premium providers never leak an API key to the browser — audio bytes
  // are fetched from the public, per-deployment voice endpoint below.
  const speakBotMessage = useCallback((text: string) => {
    if (!voiceActiveRef.current || voiceSessionActiveRef.current || !text || !text.trim()) return
    const voice = cs.voice
    const provider = voice?.provider ?? 'browser'
    loadVoiceModule().then(mod => mod.speakWithProvider({
      text,
      provider,
      voiceId: voice?.voice_id ?? null,
      gender: voice?.gender ?? 'neutral',
      personality: voice?.personality ?? 'friendly',
      fetchAudio: provider === 'browser' ? undefined : async (args) => {
        const res = await fetch(`${API_URL}/api/v1/voice/live/${slug}/synthesize`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(args),
        })
        if (!res.ok) throw new Error('Voice request failed')
        return res.blob()
      },
    })).catch(() => { /* voice is best-effort; never surfaces as a chat error */ })
  }, [loadVoiceModule, cs.voice, slug])

  // Holds the in-progress incremental speech session for the bot message
  // currently streaming in. Lets speech start on the first sentence
  // instead of waiting for the whole response to finish.
  const speechStreamRef = useRef<SpeechStreamController | null>(null)

  const pushSpeechToken = useCallback((token: string) => {
    if (!voiceActiveRef.current || voiceSessionActiveRef.current || !token) return
    const voice = cs.voice
    const provider = voice?.provider ?? 'browser'
    if (!speechStreamRef.current) {
      loadVoiceModule().then(mod => {
        if (speechStreamRef.current) return // guard against a race with a second token
        speechStreamRef.current = mod.startSpeechStream({
          provider,
          voiceId: voice?.voice_id ?? null,
          gender: voice?.gender ?? 'neutral',
          personality: voice?.personality ?? 'friendly',
          fetchAudio: provider === 'browser' ? undefined : async (args) => {
            const res = await fetch(`${API_URL}/api/v1/voice/live/${slug}/synthesize`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(args),
            })
            if (!res.ok) throw new Error('Voice request failed')
            return res.blob()
          },
        })
        speechStreamRef.current.push(token)
      }).catch(() => { /* voice is best-effort; never surfaces as a chat error */ })
      return
    }
    speechStreamRef.current.push(token)
  }, [loadVoiceModule, cs.voice, slug])

  const flushSpeechStream = useCallback(() => {
    if (speechStreamRef.current) {
      speechStreamRef.current.flush()
      speechStreamRef.current = null
    }
  }, [])

  const toggleVoiceMute = useCallback(() => {
    if (!allowMute) return
    setVoiceMuted(prev => {
      const next = !prev
      if (next && voiceModuleRef.current) {
        voiceModuleRef.current.then(mod => mod.stopSpeaking()).catch(() => {})
        speechStreamRef.current = null
      }
      return next
    })
  }, [allowMute])

  // 1. Fetch the deployment config (public endpoint, no auth) — branding, design, settings
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await fetch(`${API_URL}/api/v1/deploy/live/${slug}/config`)
        if (res.status === 404) {
          if (!cancelled) setLoadState('not_found')
          return
        }
        if (!res.ok) {
          const body = await res.json().catch(() => null)
          throw new Error(body?.detail || `Server responded with ${res.status}`)
        }
        const data = await res.json()
        if (cancelled) return
        setWorkflowId(data.workflow_id)
        if (data.branding) setBranding({ ...DEFAULT_BRANDING, ...data.branding })
        if (data.design) setDesign({ ...DEFAULT_DESIGN, ...data.design })
        if (data.chat_settings) setCs({ ...DEFAULT_CHAT_SETTINGS, ...data.chat_settings })
        setLoadState('ready')
      } catch (err) {
        if (cancelled) return
        setLoadError(getErrorMessage(err, 'Could not load this chatbot. The server may be unreachable.'))
        setLoadState('error')
      }
    }
    load()
    return () => { cancelled = true }
  }, [slug])

  // 2. Browser tab title + favicon reflect Deploy Branding
  useEffect(() => {
    if (loadState !== 'ready') return
    document.title = branding.browser_title || branding.bot_name || 'Chatbot'
    if (branding.favicon_url) {
      let link = document.querySelector<HTMLLinkElement>("link[rel~='icon']")
      if (!link) {
        link = document.createElement('link')
        link.rel = 'icon'
        document.head.appendChild(link)
      }
      link.href = branding.favicon_url
    }
  }, [loadState, branding.browser_title, branding.bot_name, branding.favicon_url])

  // Fatal close codes the backend sends when retrying can never succeed
  // (invalid/expired token, workflow not found/unpublished, malformed
  // request) — see backend/app/api/ws/chat_ws.py. Reconnecting after these
  // would just loop forever hitting the same rejection, so we surface a
  // clear message instead of silently retrying.
  const FATAL_CLOSE_CODES = new Set([4001, 4004])

  const scheduleReconnect = useCallback((freshSession: boolean) => {
    if (manualCloseRef.current) return
    if (reconnectAttemptRef.current >= MAX_RECONNECT_ATTEMPTS) {
      setReconnecting(false)
      addMessage({
        role: 'system',
        content: "We're having trouble reconnecting. Check your internet connection, then reload the page to try again.",
      })
      return
    }
    reconnectAttemptRef.current += 1
    setReconnecting(true)
    // Exponential backoff with jitter, capped at 20s, so a brief network
    // hiccup recovers in ~1s while a longer outage doesn't hammer the server.
    const base = Math.min(20_000, 1000 * 2 ** (reconnectAttemptRef.current - 1))
    const delay = base + Math.random() * 300
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
    reconnectTimerRef.current = setTimeout(() => connect(freshSession), delay)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const connect = useCallback((freshSession = false) => {
    if (!workflowId) return
    manualCloseRef.current = false
    if (reconnectTimerRef.current) { clearTimeout(reconnectTimerRef.current); reconnectTimerRef.current = null }
    wsRef.current?.close()
    if (freshSession) setMessages([])
    setConnecting(true)
    streamIdRef.current = null

    if (freshSession) sessionIdRef.current = null
    const qs = sessionIdRef.current ? `?session_id=${encodeURIComponent(sessionIdRef.current)}` : ''
    let ws: WebSocket
    try {
      ws = new WebSocket(`${WS_URL}/ws/chat/${workflowId}${qs}`)
    } catch {
      // Constructing the socket itself threw (e.g. malformed URL, browser
      // blocking mixed-content ws:// from an https:// page) — this is not a
      // transient condition, retrying with the same URL would throw again.
      setConnecting(false)
      addMessage({ role: 'system', content: 'Unable to connect to the chat server. Please try again later.' })
      return
    }
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      setConnecting(false)
      setReconnecting(false)
      reconnectAttemptRef.current = 0
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'connected') {
          if (data.session_id) sessionIdRef.current = data.session_id
          return
        }
        if (data.type === 'token') {
          if (!streamIdRef.current) {
            streamIdRef.current = addMessage({ role: 'bot', isStreaming: true })
            setIsTyping(false)
          }
          appendToken(streamIdRef.current, data.content)
          // Speak incrementally as text streams in — starts on the first
          // complete sentence instead of waiting for the full response.
          pushSpeechToken(data.content)
          // NEW (Voice AI, Part 1): also forward the raw token to an open
          // voice session, independent of the Speaker pipeline above.
          voiceListenerRef.current?.onToken(data.content)
          return
        }
        if (data.type === 'done') {
          if (streamIdRef.current) {
            const finishedId = streamIdRef.current
            finalize(finishedId, {
              citations: data.citations && data.citations.length > 0 ? data.citations : undefined,
            })
            if (cs.enable_sound) playChime()
            // Text is already rendered — speak whatever's left buffered
            // (already-spoken sentences are not repeated).
            flushSpeechStream()
          }
          streamIdRef.current = null
          setIsTyping(false)
          voiceListenerRef.current?.onDone()
          return
        }
        if (data.type === 'message') {
          setIsTyping(false)
          addMessage({ role: 'bot', content: data.content, choices: data.choices, image: data.image })
          if (cs.enable_sound) playChime()
          speakBotMessage(data.content)
          voiceListenerRef.current?.onMessage(data.content)
          return
        }
        if (data.type === 'ended') { setIsTyping(false); return }
        if (data.type === 'error') {
          setIsTyping(false)
          streamIdRef.current = null
          speechStreamRef.current?.stop()
          speechStreamRef.current = null
          addMessage({ role: 'system', content: data.content || 'Something went wrong. Please try again.' })
          voiceListenerRef.current?.onError(data.content)
        }
        // NEW (Live Agent): handoff lifecycle events, pushed on this same
        // socket by services/live_agent_service.py — no second connection.
        if (data.type === 'handoff_queued') {
          setIsTyping(false)
          addMessage({ role: 'system', content: "You're in the queue — a team member will join shortly." })
          return
        }
        if (data.type === 'human_joined') {
          setIsTyping(false)
          setHumanAgent(data.agent_name || 'Agent')
          addMessage({ role: 'system', content: `${data.agent_name || 'A team member'} joined the conversation.` })
          return
        }
        if (data.type === 'human_left') {
          setHumanAgent(null)
          setHandoffRequested(false)
          addMessage({ role: 'system', content: data.closed ? 'The conversation has been closed.' : 'The agent left — you are now chatting with the AI Agent again.' })
          return
        }
        if (data.type === 'agent_message') {
          setIsTyping(false)
          addMessage({ role: 'agent', content: data.content, agentName: data.agent_name })
          if (cs.enable_sound) playChime()
          return
        }
      } catch {
        // ignore malformed frames
      }
    }

    // `onerror` fires (per the WebSocket spec) alongside — and always just
    // before — `onclose` on any failure, with no error detail exposed to
    // JS. Previously this handler alone posted "Lost connection to the chat
    // server", then onclose fired right after and did its own (different)
    // cleanup with no message — so a single failure could show one message
    // with no recovery, and there was no single place deciding whether to
    // retry. All of that now lives in onclose, keyed off the close code;
    // onerror is a no-op observer so we never show a duplicate message.
    ws.onerror = () => { /* handled by onclose, which always follows */ }

    ws.onclose = (event) => {
      const wasConnected = connected
      setConnected(false)
      setConnecting(false)
      setIsTyping(false)
      streamIdRef.current = null
      setHumanAgent(null)
      setHandoffRequested(false)

      if (manualCloseRef.current || wsRef.current !== ws) return // intentional close (unmount/navigate) or superseded by a newer socket

      if (FATAL_CLOSE_CODES.has(event.code)) {
        addMessage({
          role: 'system',
          content: event.code === 4001
            ? 'Your session has expired. Please refresh the page to start a new conversation.'
            : "This chatbot isn't available right now.",
        })
        return
      }

      // Any other close (1006 abnormal/network drop, 1001 going away, 1011
      // server error, a proxy/load-balancer idle timeout, laptop sleep/wake,
      // wifi handoff, etc.) is treated as transient and recoverable.
      if (wasConnected || reconnectAttemptRef.current > 0) {
        addMessage({ role: 'system', content: 'Connection lost. Reconnecting…' })
      }
      scheduleReconnect(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId, cs.enable_sound, connected, scheduleReconnect])

  useEffect(() => {
    if (loadState === 'ready' && workflowId) connect(true)
    return () => {
      manualCloseRef.current = true
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadState, workflowId])

  // Reconnect promptly when the tab regains network/visibility instead of
  // waiting out the current backoff delay — this is what makes "lost wifi
  // for 30s then it came back" feel instant rather than up to 20s late.
  useEffect(() => {
    const tryResume = () => {
      if (manualCloseRef.current) return
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return
      if (reconnectTimerRef.current) { clearTimeout(reconnectTimerRef.current); reconnectTimerRef.current = null }
      reconnectAttemptRef.current = 0
      connect(false)
    }
    const onVisibilityChange = () => { if (document.visibilityState === 'visible') tryResume() }
    window.addEventListener('online', tryResume)
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => {
      window.removeEventListener('online', tryResume)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (cs.enable_auto_scroll) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping, cs.enable_auto_scroll])

  const sendMessage = (text?: string) => {
    const msg = (text ?? input).trim()
    if (!msg) return
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      addMessage({ role: 'system', content: "You're offline — this will send once reconnected." })
      voiceListenerRef.current?.onError('offline')
      return
    }
    addMessage({ role: 'user', content: msg })
    wsRef.current.send(JSON.stringify({ message: msg }))
    setInput('')
    setIsTyping(true)
    inputRef.current?.focus()
  }

  const requestHuman = () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN || handoffRequested || humanAgent) return
    wsRef.current.send(JSON.stringify({ type: 'request_human' }))
    setHandoffRequested(true)
  }

  const handleFilePicked = (file: File) => {
    sendMessage(`📎 ${file.name}`)
    if (fileRef.current) fileRef.current.value = ''
  }

  const restart = () => {
    wsRef.current?.send(JSON.stringify({ type: 'reset' }))
    setMessages([])
    setIsTyping(false)
    streamIdRef.current = null
    speechStreamRef.current = null
    if (voiceModuleRef.current) {
      voiceModuleRef.current.then(mod => mod.stopSpeaking()).catch(() => {})
    }
  }

  const isLight = design.mode === 'light'
  const pageBg = design.background_gradient || design.background_color || (isLight ? '#ffffff' : '#070708')
  const fg = isLight ? '#0a0a0a' : '#ffffff'
  const radius = design.border_radius
  const shadow = design.shadows !== false
  const glass = design.glassmorphism

  const pageStyle: React.CSSProperties = useMemo(() => ({
    background: pageBg,
    backgroundImage: design.background_image ? `url(${design.background_image})` : undefined,
    backgroundSize: 'cover',
    backgroundPosition: 'center',
    color: fg,
    fontFamily: design.font_family,
    fontSize: design.font_size,
  }), [pageBg, design.background_image, fg, design.font_family, design.font_size])

  // ── Loading state ─────────────────────────────────────────────────────────
  if (loadState === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#070708]">
        <Loader2 className="animate-spin text-white/30" size={28} />
      </div>
    )
  }

  // ── Not found ─────────────────────────────────────────────────────────────
  if (loadState === 'not_found') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#070708] px-6">
        <div className="tb-anim-fade-up text-center max-w-sm">
          <div className="w-14 h-14 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center mx-auto mb-5">
            <Bot size={24} className="text-white/30" />
          </div>
          <h1 className="text-lg font-semibold text-white/90 mb-2">This bot isn't published</h1>
          <p className="text-sm text-white/40 leading-relaxed">
            The link may be incorrect, or the owner has unpublished this chatbot. Ask them to check the Deploy panel in their builder.
          </p>
        </div>
      </div>
    )
  }

  // ── Error state ───────────────────────────────────────────────────────────
  if (loadState === 'error') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#070708] px-6">
        <div className="tb-anim-fade-up text-center max-w-sm">
          <div className="w-14 h-14 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center mx-auto mb-5">
            <AlertTriangle size={22} className="text-red-400" />
          </div>
          <h1 className="text-lg font-semibold text-white/90 mb-2">Couldn't load this chatbot</h1>
          <p className="text-sm text-white/40 leading-relaxed">{loadError}</p>
        </div>
      </div>
    )
  }

  const borderCol = isLight ? 'rgba(0,0,0,0.08)' : 'rgba(255,255,255,0.07)'

  // ── Chat UI ───────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen flex flex-col tb-anim-fade-up" style={pageStyle}>
      {/* Header */}
      <header
        className="flex items-center justify-between px-4 sm:px-5 py-3 sm:py-3.5 flex-shrink-0"
        style={{ borderBottom: `1px solid ${borderCol}`, backdropFilter: glass ? 'blur(14px)' : undefined }}
      >
        <div className="flex items-center gap-2.5 min-w-0">
          {cs.show_bot_logo && (branding.logo_url || branding.avatar_url) ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={branding.logo_url || branding.avatar_url || ''}
              alt=""
              className="w-7 h-7 rounded-lg object-cover flex-shrink-0"
              style={{ boxShadow: shadow ? '0 2px 8px rgba(0,0,0,0.25)' : undefined }}
            />
          ) : cs.show_bot_logo ? (
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
              style={{ background: `${branding.theme_color}22`, border: `1px solid ${branding.theme_color}40` }}
            >
              <Bot size={14} style={{ color: branding.accent_color }} />
            </div>
          ) : null}
          <div className="min-w-0">
            {cs.show_bot_name && (
              <p className="text-sm font-semibold leading-tight truncate" style={{ color: fg }}>{branding.bot_name}</p>
            )}
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-emerald-400' : (connecting || reconnecting) ? 'bg-amber-400' : 'bg-zinc-600'}`} />
              <span className="text-[10px] opacity-40">
                {connected ? 'Online' : reconnecting ? 'Reconnecting…' : connecting ? 'Connecting…' : 'Disconnected'}
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          {connected && !humanAgent && (
            <button
              onClick={requestHuman}
              disabled={handoffRequested}
              title={handoffRequested ? 'Waiting for a team member…' : 'Talk to a human'}
              className="tb-hover-lift p-2 rounded-lg opacity-40 hover:opacity-90 transition disabled:opacity-60"
            >
              <Headset size={14} />
            </button>
          )}
          {voiceEnabledForBot && allowMute && (
            <button
              onClick={toggleVoiceMute}
              title={effectiveMuted ? 'Unmute voice' : 'Mute voice'}
              aria-pressed={!effectiveMuted}
              className="tb-hover-lift p-2 rounded-lg opacity-40 hover:opacity-90 transition"
            >
              {effectiveMuted ? <VolumeX size={14} /> : <Volume2 size={14} />}
            </button>
          )}
          {cs.show_restart_button && connected && (
            <button
              onClick={restart}
              title="Restart conversation"
              className="tb-hover-lift p-2 rounded-lg opacity-40 hover:opacity-90 transition"
            >
              <RotateCcw size={14} />
            </button>
          )}
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 sm:px-4 py-5 max-w-2xl w-full mx-auto space-y-4">
        {messages.length === 0 && connecting && (
          <div className="flex justify-center pt-10">
            <Loader2 className="animate-spin opacity-30" size={20} />
          </div>
        )}
        {messages.length === 0 && !connecting && (
          <div className="tb-anim-fade-up text-center pt-10 px-4">
            <p className="text-base font-semibold mb-1.5">{branding.welcome_title}</p>
            <p className="text-sm opacity-55">{branding.welcome_description}</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={msg.id} className="tb-anim-msg-in" style={{ animationDelay: `${Math.min(i, 4) * 25}ms` }}>
            <div className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className="max-w-[85%] sm:max-w-[80%] px-4 py-2.5 text-[15px] leading-relaxed"
                style={
                  msg.role === 'user'
                    ? {
                        background: design.user_bubble_color, color: '#fff',
                        borderRadius: radius, borderBottomRightRadius: 4,
                        boxShadow: shadow ? '0 2px 10px rgba(0,0,0,0.15)' : undefined,
                      }
                    : msg.role === 'system'
                    ? { fontSize: 12, fontStyle: 'italic', color: '#fbbf24bb', padding: '4px 8px' }
                    : {
                        background: design.bot_bubble_color, color: fg,
                        borderRadius: radius, borderBottomLeftRadius: 4,
                        backdropFilter: glass ? 'blur(10px)' : undefined,
                        boxShadow: shadow ? '0 2px 10px rgba(0,0,0,0.12)' : undefined,
                      }
                }
              >
                {msg.role === 'agent' && (
                  <p className="text-[10px] opacity-50 mb-1 font-semibold flex items-center gap-1">
                    <Headset size={10} /> {msg.agentName || 'Agent'}
                  </p>
                )}
                {msg.role === 'bot' && msg.image?.url && (
                  <div className="mb-2 -mx-1">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={msg.image.url}
                      alt={msg.image.filename || ''}
                      className="w-full h-auto max-h-[60vh] object-contain rounded-lg"
                      style={{ borderRadius: Math.max(radius - 4, 0) }}
                    />
                  </div>
                )}
                {msg.role === 'bot' && voiceMode === 'voice_only' ? (
                  <>
                    <span className="inline-flex items-center gap-1.5 opacity-60 text-[13px]">
                      <Volume2 size={12} /> {msg.isStreaming ? 'Speaking…' : 'Voice reply'}
                    </span>
                    {/* Full text stays in the DOM (screen readers, page search,
                        conversation history) even though it isn't shown visually. */}
                    <span className="sr-only">{msg.content}</span>
                  </>
                ) : msg.role === 'bot' ? (
                  cs.enable_markdown
                    ? <div className="chat-message"><ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown></div>
                    : <span style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</span>
                ) : msg.content}
                {msg.isStreaming && <span className="inline-block w-0.5 h-3.5 bg-current opacity-40 ml-0.5 animate-pulse align-middle" />}
              </div>
            </div>
            {cs.show_timestamp && msg.role !== 'system' && (
              <p className={`text-[10px] opacity-30 mt-1 ${msg.role === 'user' ? 'text-right' : 'text-left'}`}>{msg.time}</p>
            )}
            {msg.citations && msg.citations.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {msg.citations.map((c) => (
                  <span
                    key={c.index}
                    title={c.excerpt}
                    className="text-[11px] px-2.5 py-1 rounded-lg border opacity-50 hover:opacity-80 cursor-help transition"
                    style={{ borderColor: borderCol }}
                  >
                    [{c.index}] {c.source} · {Math.round(c.score * 100)}%
                  </span>
                ))}
              </div>
            )}
            {msg.choices && msg.choices.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2.5">
                {msg.choices.map((c, ci) => (
                  <button
                    key={ci}
                    onClick={() => sendMessage(c.label)}
                    disabled={isTyping}
                    className="tb-hover-lift text-sm px-4 py-2 rounded-xl border transition
                               disabled:opacity-30 disabled:cursor-not-allowed"
                    style={{ borderColor: `${branding.theme_color}55`, color: branding.theme_color }}
                  >
                    {c.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}

        {isTyping && cs.show_typing_indicator && (
          <div className="flex justify-start tb-anim-fade-up">
            <div
              className="px-4 py-3 flex gap-1.5"
              style={{ background: design.bot_bubble_color, borderRadius: radius, borderBottomLeftRadius: 4 }}
            >
              {[0, 1, 2].map(i => (
                <span key={i} className="typing-dot w-1.5 h-1.5 rounded-full" style={{ background: `${fg}88` }} />
              ))}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-3 sm:px-4 py-4 flex-shrink-0" style={{ borderTop: `1px solid ${borderCol}` }}>
        <div className="max-w-2xl mx-auto flex gap-2 sm:gap-2.5">
          {cs.enable_file_upload && (
            <>
              <button
                onClick={() => fileRef.current?.click()}
                disabled={!connected}
                className="tb-hover-lift px-3 py-3 rounded-xl opacity-50 hover:opacity-90 transition disabled:opacity-20 flex-shrink-0"
                style={{ border: `1px solid ${borderCol}` }}
                title="Attach a file"
              >
                <Paperclip size={15} />
              </button>
              <input
                ref={fileRef}
                type="file"
                className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFilePicked(f) }}
              />
            </>
          )}
          <input
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && sendMessage()}
            placeholder={connected ? 'Type a message…' : 'Connecting…'}
            disabled={!connected}
            className="flex-1 min-w-0 text-[15px] px-4 py-3 outline-none transition disabled:opacity-50"
            style={{
              background: design.bot_bubble_color, color: fg,
              border: `1px solid ${borderCol}`, borderRadius: Math.max(radius - 4, 6),
            }}
          />
          <button
            onClick={() => sendMessage()}
            disabled={!connected || !input.trim()}
            className="tb-hover-lift px-4 py-3 text-white transition
                       disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center flex-shrink-0"
            style={{ background: branding.theme_color, borderRadius: Math.max(radius - 4, 6) }}
          >
            <Send size={16} />
          </button>
        </div>
        {cs.show_powered_by && (
          <p className="text-center text-[10px] opacity-20 mt-3">Powered by ThunderBots</p>
        )}
      </div>

      {/* NEW (Voice AI, Part 1): floating "Talk to AI" voice bubble — a
          browser-only spoken-conversation surface layered on top of the
          same socket/workflow/AI pipeline the text chat above already
          uses. No phone number, no telephony. */}
      <VoiceAssistant
        connected={connected}
        sendMessage={sendMessage}
        branding={branding}
        voiceSettings={cs.voice}
        slug={slug}
        apiUrl={API_URL}
        listenerRef={voiceListenerRef}
        sessionActiveRef={voiceSessionActiveRef}
      />
    </div>
  )
}
