'use client'

/**
 * ThunderBots — Voice Responses playback (Browser provider).
 *
 * Intentionally dependency-free: uses the browser's native SpeechSynthesis
 * API only, so enabling Voice Mode with the Browser provider never adds an
 * external library, never increases bundle size for Text Only bots, and
 * never blocks message rendering (text is always shown first; this module
 * is only ever reached via a dynamic import() after the text has already
 * been displayed).
 *
 * This file must never be statically imported from a chat page — it is
 * loaded on demand, only once, only when a bot's Voice Response Mode is
 * "Voice + Text" or "Voice Only", the Browser provider is selected, and
 * the visitor hasn't muted it.
 */

import type { VoiceGender, VoiceOption, VoicePersonality } from '@/types'
import { getPersonalityPreset } from './personality'

export function isVoiceSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

function guessGender(name: string): VoiceGender {
  const n = name.toLowerCase()
  if (/female|woman|girl|zira|samantha|victoria|karen|susan|tessa|moira|fiona|allison|joanna|salli|kimberly/.test(n)) {
    return 'female'
  }
  if (/male|man|boy|david|daniel|alex|fred|thomas|george|james|matthew|justin|joey/.test(n)) {
    return 'male'
  }
  return 'neutral'
}

/**
 * List voices the browser currently has available. May return an empty
 * array on first call in some browsers (voice list loads asynchronously) —
 * callers should use `whenVoicesReady()` if they need a populated list
 * before the user interacts with anything.
 */
export function listBrowserVoices(): VoiceOption[] {
  if (!isVoiceSupported()) return []
  try {
    return window.speechSynthesis.getVoices().map(v => ({
      id: v.voiceURI,
      name: v.name,
      gender: guessGender(v.name),
    }))
  } catch {
    return []
  }
}

/** Resolves once the browser's voice list is populated (or immediately if
 * it already is / voice is unsupported). Never rejects. */
export function whenVoicesReady(): Promise<VoiceOption[]> {
  return new Promise((resolve) => {
    if (!isVoiceSupported()) {
      resolve([])
      return
    }
    const existing = listBrowserVoices()
    if (existing.length > 0) {
      resolve(existing)
      return
    }
    const onChange = () => {
      window.speechSynthesis.removeEventListener('voiceschanged', onChange)
      resolve(listBrowserVoices())
    }
    window.speechSynthesis.addEventListener('voiceschanged', onChange)
    // Fallback in case the event never fires on this browser.
    setTimeout(() => {
      window.speechSynthesis.removeEventListener('voiceschanged', onChange)
      resolve(listBrowserVoices())
    }, 1000)
  })
}

/**
 * Speak the given text in the background.
 * - Never throws: resolves in every case (unsupported, empty, cancelled,
 *   or synthesis error) so callers can fire-and-forget safely.
 * - Utterances are handed to the browser's own queue, so back-to-back
 *   messages play sequentially without any extra queueing logic here.
 */
export function speak(
  text: string,
  opts?: { rate?: number; pitch?: number; voiceId?: string | null; gender?: VoiceGender; personality?: VoicePersonality }
): Promise<void> {
  return new Promise((resolve) => {
    if (!isVoiceSupported() || !text || !text.trim()) {
      resolve()
      return
    }
    try {
      const utterance = new SpeechSynthesisUtterance(text)
      // Voice Personality only ever nudges rate/pitch for playback — an
      // explicit rate/pitch (if a caller ever passes one) always wins.
      const preset = getPersonalityPreset(opts?.personality)
      utterance.rate = opts?.rate ?? preset.rate
      utterance.pitch = opts?.pitch ?? preset.pitch

      const voices = window.speechSynthesis.getVoices()
      let match: SpeechSynthesisVoice | undefined
      if (opts?.voiceId) {
        match = voices.find(v => v.voiceURI === opts.voiceId)
      }
      if (!match && opts?.gender && opts.gender !== 'neutral') {
        match = voices.find(v => guessGender(v.name) === opts.gender)
      }
      if (match) utterance.voice = match

      utterance.onend = () => resolve()
      utterance.onerror = () => resolve()
      window.speechSynthesis.speak(utterance)
    } catch {
      resolve()
    }
  })
}

/** Immediately stop any speech in progress and clear the queue (mute toggle). */
export function cancelSpeech(): void {
  if (!isVoiceSupported()) return
  try {
    window.speechSynthesis.cancel()
  } catch {
    // no-op — nothing to cancel
  }
}
