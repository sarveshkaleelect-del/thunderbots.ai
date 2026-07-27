/**
 * ThunderBots — streaming text chunker (Voice Responses).
 *
 * Pure functions only, no side effects. Used to decide when enough of a
 * streaming AI response has accumulated to speak a natural-sounding chunk,
 * instead of waiting for the entire response to finish.
 *
 * Strategy:
 *  1. Prefer full sentences — split on `.`/`!`/`?`/`…` followed by
 *     whitespace, so speech always breaks at a natural pause.
 *  2. If a single "sentence" grows unreasonably long with no terminal
 *     punctuation (long unpunctuated runs, lists, etc.), fall back to
 *     cutting at the last word boundary once a soft length cap is hit —
 *     never mid-word — so voice playback isn't stalled waiting on a
 *     sentence that may never end.
 */

/** Once a buffered, not-yet-spoken chunk reaches this many characters
 * without terminal punctuation, cut it at the last space instead of
 * continuing to wait. Keeps latency bounded for long unpunctuated text. */
export const SOFT_MAX_CHUNK_CHARS = 160

/** Matches a run of text ending in sentence-terminal punctuation (optionally
 * followed by a closing quote/paren) and at least one whitespace character —
 * the whitespace confirms the sentence is actually finished, not just an
 * ellipsis mid-word or a decimal point. */
const SENTENCE_RE = /^([\s\S]*?[.!?…]+(?:["'）)\]]*))\s+/

export interface ChunkSplitResult {
  /** Zero or more chunks that are ready to be spoken now, in order. */
  ready: string[]
  /** Remaining buffered text that isn't ready yet — keep accumulating it. */
  rest: string
}

/**
 * Extracts every complete sentence currently available at the start of
 * `buffer`, then (only if what's left is already past the soft cap)
 * additionally cuts a word-boundary-safe chunk from the remainder so
 * speech doesn't stall indefinitely on unpunctuated text.
 */
export function splitReadyChunks(buffer: string): ChunkSplitResult {
  const ready: string[] = []
  let rest = buffer

  // 1) Pull out every finished sentence, in order.
  let match: RegExpExecArray | null
  while ((match = SENTENCE_RE.exec(rest))) {
    const chunk = match[1].trim()
    if (chunk) ready.push(chunk)
    rest = rest.slice(match[0].length)
  }

  // 2) Soft cap fallback for long unpunctuated remainders.
  while (rest.length > SOFT_MAX_CHUNK_CHARS) {
    const cutAt = rest.lastIndexOf(' ', SOFT_MAX_CHUNK_CHARS)
    if (cutAt <= 0) break // no safe word boundary yet — keep waiting
    const chunk = rest.slice(0, cutAt).trim()
    if (chunk) ready.push(chunk)
    rest = rest.slice(cutAt).trimStart()
  }

  return { ready, rest }
}

/** Final flush at end-of-stream — whatever's left is spoken as-is,
 * punctuation or not (e.g. a short reply with no terminal punctuation). */
export function finalChunk(buffer: string): string | null {
  const trimmed = buffer.trim()
  return trimmed ? trimmed : null
}
