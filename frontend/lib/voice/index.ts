'use client'

/**
 * ThunderBots — Voice Responses orchestrator.
 *
 * This is the ONLY module chat surfaces (Test Chat panel, deployed chatbot
 * page) should import for playback. It never touches workflow execution —
 * it is only ever called with text that a bot response has already
 * produced and already rendered.
 *
 * Performance / lazy-load contract:
 *  - The Browser provider dynamically imports `./speechSynthesis` (native
 *    SpeechSynthesis API — no bundle cost) only when actually used.
 *  - Premium providers (Gemini/ElevenLabs/Azure/Google) are never
 *    called from a vendor SDK on the client at all — synthesis happens on
 *    the backend (keeping API keys off the client and heavy SDKs out of
 *    this bundle entirely) and this module just fetches the resulting
 *    audio bytes and plays them with a plain <audio> element.
 *  - This file itself has zero third-party imports, so importing it is
 *    always cheap; it is still recommended callers `import()` it lazily,
 *    matching the existing pattern for Text Only bots.
 */
import type { VoiceGender, VoicePersonality, VoiceProviderId } from '@/types'
import { splitReadyChunks, finalChunk } from './textChunker'

let currentAudio: HTMLAudioElement | null = null
let currentAudioUrl: string | null = null
let browserModulePromise: Promise<typeof import('./speechSynthesis')> | null = null

// The one streaming controller currently allowed to play audio. Only ever
// one at a time — starting a new one (new bot message) or calling
// stopSpeaking() (mute, new user message, unmount) retires the previous one.
let activeStream: SpeechStreamController | null = null

function loadBrowserModule() {
  if (!browserModulePromise) {
    browserModulePromise = import('./speechSynthesis')
  }
  return browserModulePromise
}

/** Plays a single already-synthesized audio blob to completion (or to
 * cancellation). Shared by both the one-shot `speakWithProvider` path and
 * the incremental streaming queue below, so there's exactly one place that
 * owns `<audio>` element lifecycle / object-URL cleanup. */
function playAudioBlob(blob: Blob): Promise<void> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    currentAudio = audio
    currentAudioUrl = url
    const cleanup = () => {
      if (currentAudioUrl === url) {
        try { URL.revokeObjectURL(url) } catch { /* no-op */ }
        currentAudioUrl = null
      }
      if (currentAudio === audio) currentAudio = null
      resolve()
    }
    audio.onended = cleanup
    audio.onerror = cleanup
    audio.play().then(undefined, cleanup)
  })
}

/** Stop whatever is currently playing/speaking, on any provider. Safe to
 * call unconditionally (e.g. on mute, on new message, on unmount). */
export function stopSpeaking(): void {
  if (activeStream) {
    activeStream.stop()
    activeStream = null
  }
  if (currentAudio) {
    try { currentAudio.pause() } catch { /* no-op */ }
    currentAudio = null
  }
  if (currentAudioUrl) {
    try { URL.revokeObjectURL(currentAudioUrl) } catch { /* no-op */ }
    currentAudioUrl = null
  }
  if (browserModulePromise) {
    browserModulePromise.then(mod => mod.cancelSpeech()).catch(() => { /* no-op */ })
  }
}

export interface SpeakOptions {
  text: string
  provider: VoiceProviderId
  voiceId?: string | null
  gender?: VoiceGender
  /** Playback-only styling — never changes the text that's spoken. */
  personality?: VoicePersonality
  /**
   * Resolves to synthesized audio bytes for premium providers. Not called
   * (and not required) when provider === 'browser'. The builder passes a
   * fetcher backed by the authenticated `/voice/synthesize` route; the
   * deployed chatbot passes one backed by the public
   * `/voice/live/{slug}/synthesize` route — this module doesn't care which,
   * it just plays whatever audio comes back.
   */
  fetchAudio?: (args: { provider: VoiceProviderId; voice?: string | null; text: string; personality?: VoicePersonality }) => Promise<Blob>
}

/**
 * Speak text with the given provider. Fire-and-forget safe: never throws,
 * always resolves, and never delays or blocks the caller — always call
 * this only after the text is already rendered on screen.
 */
export async function speakWithProvider(opts: SpeakOptions): Promise<void> {
  stopSpeaking()
  const text = opts.text?.trim()
  if (!text) return

  if (opts.provider === 'browser') {
    try {
      const mod = await loadBrowserModule()
      if (!mod.isVoiceSupported()) return
      await mod.speak(text, { voiceId: opts.voiceId, gender: opts.gender, personality: opts.personality })
    } catch {
      // best-effort — never surfaces as a chat error
    }
    return
  }

  if (!opts.fetchAudio) return
  try {
    // Premium providers that don't support personality tuning simply
    // ignore the field server-side and return default-voice audio —
    // never an error, matching the graceful-fallback requirement.
    const blob = await opts.fetchAudio({ provider: opts.provider, voice: opts.voiceId, text, personality: opts.personality })
    await playAudioBlob(blob)
  } catch {
    // best-effort — voice failure must never crash or block the chatbot
  }
}

// ── Incremental (streaming) speech ──────────────────────────────────────────
//
// Lets a caller feed in text as it streams token-by-token from the AI
// response, and starts speaking the first sentence as soon as it's
// available — instead of waiting for the full response to finish.
//
// - Text is chunked at natural sentence boundaries (see ./textChunker), so
//   speech never sounds clipped mid-thought.
// - For premium providers, synthesis of the *next* queued chunk begins the
//   moment that chunk is ready — while the *current* chunk is still
//   playing — so by the time playback reaches the next chunk its audio is
//   usually already fetched, keeping the queue gap-free ("seamless").
// - For the Browser provider, chunks are handed to the native
//   SpeechSynthesis queue in order; the browser itself plays them back to
//   back with no gap logic needed on our side.
// - Nothing here changes what text is rendered — exactly like
//   `speakWithProvider`, this only ever narrates text the chat UI has
//   already displayed.

export interface SpeechStreamOptions {
  provider: VoiceProviderId
  voiceId?: string | null
  gender?: VoiceGender
  personality?: VoicePersonality
  fetchAudio?: (args: { provider: VoiceProviderId; voice?: string | null; text: string; personality?: VoicePersonality }) => Promise<Blob>
}

export interface SpeechStreamController {
  /** Feed in the next streamed text delta (a token, or any partial chunk). */
  push(delta: string): void
  /** Call once the response is fully streamed — speaks whatever's left
   * buffered, punctuation or not. */
  flush(): void
  /** Hard-stop: clears anything still queued and silences playback. */
  stop(): void
}

class SpeechStream implements SpeechStreamController {
  private buffer = ''
  private queue: Array<{ text: string; audioPromise: Promise<Blob | null> | null }> = []
  private draining = false
  private stopped = false

  constructor(private opts: SpeechStreamOptions) {}

  push(delta: string): void {
    if (this.stopped || !delta) return
    this.buffer += delta
    const { ready, rest } = splitReadyChunks(this.buffer)
    this.buffer = rest
    for (const chunk of ready) this.enqueue(chunk)
  }

  flush(): void {
    if (this.stopped) return
    const chunk = finalChunk(this.buffer)
    this.buffer = ''
    if (chunk) this.enqueue(chunk)
  }

  stop(): void {
    this.stopped = true
    this.queue = []
  }

  private enqueue(text: string): void {
    if (this.stopped || !text) return
    const isBrowser = this.opts.provider === 'browser'
    // Prefetch immediately for premium providers so synthesis overlaps
    // with whatever chunk is currently playing, instead of starting only
    // once it's this chunk's turn.
    const audioPromise = isBrowser ? null : this.synthesize(text)
    this.queue.push({ text, audioPromise })
    this.drain()
  }

  private async synthesize(text: string): Promise<Blob | null> {
    if (!this.opts.fetchAudio) return null
    try {
      return await this.opts.fetchAudio({
        provider: this.opts.provider, voice: this.opts.voiceId, text, personality: this.opts.personality,
      })
    } catch {
      return null // this chunk silently loses audio rather than breaking the queue
    }
  }

  private async drain(): Promise<void> {
    if (this.draining || this.stopped) return
    this.draining = true
    try {
      while (!this.stopped) {
        const item = this.queue.shift()
        if (!item) break
        if (this.opts.provider === 'browser') {
          try {
            const mod = await loadBrowserModule()
            if (mod.isVoiceSupported()) {
              await mod.speak(item.text, { voiceId: this.opts.voiceId, gender: this.opts.gender, personality: this.opts.personality })
            }
          } catch { /* best-effort */ }
        } else {
          const blob = await item.audioPromise
          if (blob && !this.stopped) {
            try { await playAudioBlob(blob) } catch { /* best-effort */ }
          }
        }
      }
    } finally {
      this.draining = false
    }
  }
}

/**
 * Starts a new incremental speech session. Retires any previously active
 * session first (mirrors `speakWithProvider`'s stop-before-start behavior),
 * so at most one bot message is ever narrated at a time.
 */
export function startSpeechStream(opts: SpeechStreamOptions): SpeechStreamController {
  stopSpeaking()
  const stream = new SpeechStream(opts)
  activeStream = stream
  return stream
}
