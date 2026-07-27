/**
 * ThunderBots — Voice Personality presets.
 *
 * Purely a playback concern: these presets only ever adjust HOW a reply is
 * spoken (rate/pitch on the Browser provider, matching hints sent to the
 * backend for premium providers). They never touch the bot's actual text
 * response, workflow execution, or the AI Agent.
 *
 * Kept dependency-free and tiny so importing it never adds bundle weight —
 * safe to import from both the lazily-loaded browser TTS wrapper and the
 * builder's Voice Responses UI.
 */
import type { VoicePersonality } from '@/types'

export const VOICE_PERSONALITIES: { id: VoicePersonality; label: string; hint: string }[] = [
  { id: 'friendly',     label: 'Friendly',     hint: 'Warm and approachable' },
  { id: 'professional', label: 'Professional', hint: 'Clear and steady' },
  { id: 'energetic',    label: 'Energetic',    hint: 'Upbeat and lively' },
  { id: 'calm',         label: 'Calm',         hint: 'Slow and soothing' },
  { id: 'formal',       label: 'Formal',       hint: 'Measured and precise' },
]

export const DEFAULT_VOICE_PERSONALITY: VoicePersonality = 'friendly'

/** rate/pitch are consumed by the browser SpeechSynthesis wrapper only.
 * Values are gentle multipliers/offsets — never extreme enough to make
 * speech sound broken on any voice. */
export const PERSONALITY_PRESETS: Record<VoicePersonality, { rate: number; pitch: number }> = {
  friendly:     { rate: 1.0,  pitch: 1.15 },
  professional: { rate: 1.0,  pitch: 1.0 },
  energetic:    { rate: 1.15, pitch: 1.25 },
  calm:         { rate: 0.88, pitch: 0.9 },
  formal:       { rate: 0.95, pitch: 0.95 },
}

export function getPersonalityPreset(personality?: VoicePersonality | null) {
  return PERSONALITY_PRESETS[personality || DEFAULT_VOICE_PERSONALITY] ?? PERSONALITY_PRESETS.friendly
}
