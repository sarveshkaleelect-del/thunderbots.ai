import { apiClient } from './client'
import type { VoicePersonality, VoiceProviderInfo } from '@/types'

/**
 * Voice Responses — builder-side calls only (Test Chat panel, Deploy
 * Settings provider/voice pickers). The deployed public chatbot never uses
 * this client; it calls the public `/voice/live/{slug}/synthesize` endpoint
 * directly with `fetch`, unauthenticated, the same way it already fetches
 * `/deploy/live/{slug}/config`.
 */
export const voiceApi = {
  /** Browser is always included and always configured=true (no key needed). */
  listProviders: () => apiClient.get<VoiceProviderInfo[]>('/voice/providers').then(r => r.data),

  /** Returns an audio Blob (mp3/wav depending on provider). Never used for
   * the 'browser' provider — that path never leaves the client.
   * `personality` is playback styling only — providers that don't support
   * it silently ignore it server-side and return default-voice audio. */
  synthesize: (payload: { provider: string; text: string; voice?: string | null; personality?: VoicePersonality }) =>
    apiClient
      .post('/voice/synthesize', payload, { responseType: 'blob' })
      .then(r => r.data as Blob),
}
