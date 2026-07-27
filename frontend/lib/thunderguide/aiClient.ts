// ============================================================
// ThunderGuide — AI Tier Client
//
// These features require the user's own Google Gemini API key.
// ThunderGuide never adds a second key-management surface: the
// key used here is either the session-cached copy of a key the
// user pastes once (kept only in sessionStorage, never persisted),
// or it is not available — in which case the caller should route
// the user to the existing /settings/api-keys page to configure
// one first.
//
// Transport: Gemini is called directly from the browser (Google's
// `:generateContent` endpoint already returns permissive CORS
// headers) — the session key never leaves the browser except to
// go straight to Gemini.
// ============================================================
import type { AIProviderId } from './types'

const SESSION_KEY_PREFIX = 'tg_session_key__'

// ============================================================
// ROOT CAUSE FIX — request timeouts for direct browser->provider calls
//
// Gemini is called with a plain fetch() straight from the browser (see
// module header). A plain fetch() has NO timeout of its own: if the
// provider (or the network path to it) stalls, the call just hangs
// indefinitely — the "Generate Chatbot" button stays spinning forever with
// no error and no friendly message, which is worse than a clear failure.
// GENERATION_TIMEOUT_MS below is deliberately generous (Create with AI can
// ask for up to ~7000 output tokens describing a large workflow graph,
// which legitimately takes a while), but it guarantees every direct call
// eventually resolves one way or the other.
// ============================================================
const GENERATION_TIMEOUT_MS = 90_000
const QUICK_TIMEOUT_MS = 20_000 // for lightweight calls like Gemini's model list

class ProviderTimeoutError extends Error {}

function withTimeout(ms: number): { signal: AbortSignal; clear: () => void } {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), ms)
  return { signal: controller.signal, clear: () => clearTimeout(timer) }
}

function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError'
}

function friendlyTimeoutError(label: string): Error {
  return new Error(
    `${label} took too long to respond and the request timed out. This can happen with a longer or more ` +
    `complex description — try again, or narrow the request a little.`
  )
}

export function getSessionKey(provider: AIProviderId): string | null {
  if (typeof window === 'undefined') return null
  return sessionStorage.getItem(SESSION_KEY_PREFIX + provider)
}

export function setSessionKey(provider: AIProviderId, key: string) {
  if (typeof window === 'undefined') return
  sessionStorage.setItem(SESSION_KEY_PREFIX + provider, key)
}

export function clearSessionKey(provider: AIProviderId) {
  if (typeof window === 'undefined') return
  sessionStorage.removeItem(SESSION_KEY_PREFIX + provider)
}

export const PROVIDER_LABELS: Record<AIProviderId, string> = {
  gemini: 'Gemini',
}

export const PROVIDER_DEFAULT_MODEL: Record<AIProviderId, string> = {
  // Gemini intentionally has no static default here: the model actually
  // available to a given API key changes over time (Google periodically
  // retires old model ids from v1beta), so ThunderGuide resolves it
  // dynamically at call time instead. See resolveGeminiModels() below.
  gemini: '',
}

// ============================================================
// Gemini — dynamic model discovery
//
// Root cause of "models/gemini-1.5-flash is not found for API
// version v1beta": ThunderGuide called generateContent with a
// hardcoded model id. Google periodically retires old Gemini
// model ids from the v1beta API, so a hardcoded id eventually
// 404s for some/all keys even though the key itself is fine and
// other Gemini models remain available.
//
// Fix: instead of hardcoding a model, ask the API (with the
// user's own key) which models it currently exposes that support
// generateContent, then pick the best match from a preference
// list, and gracefully fall back through the rest of the list if
// the top pick 404s. This keeps ThunderGuide working as Google
// adds/retires models, with no code changes needed here.
//
// Scope: this only affects ThunderGuide's own browser-side Gemini
// calls. It does not touch the AI Agent / backend Gemini
// integration (backend/app/services/ai_engine.py), which already
// resolves its model from GEMINI_DEFAULT_MODEL server-side and is
// untouched by this fix.
// ============================================================

const GEMINI_API_BASE = 'https://generativelanguage.googleapis.com/v1beta'

// Preference order when multiple compatible models are available.
// Leads with the same model family the backend's working Gemini
// integration defaults to (gemini-2.5-flash), then falls back sensibly.
const GEMINI_MODEL_PREFERENCE = [
  'gemini-2.5-flash',
  'gemini-2.5-pro',
  'gemini-2.5-flash-lite',
  'gemini-2.0-flash',
  'gemini-2.0-flash-lite',
  'gemini-1.5-flash-latest',
  'gemini-1.5-flash',
  'gemini-1.5-pro-latest',
  'gemini-1.5-pro',
]

interface GeminiModelCacheEntry { resolvedAt: number; candidates: string[] }
const geminiModelCache = new Map<string, GeminiModelCacheEntry>()
const GEMINI_CACHE_TTL_MS = 30 * 60 * 1000 // 30 minutes

class GeminiApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

function stripModelPrefix(name: string): string {
  return name.startsWith('models/') ? name.slice('models/'.length) : name
}

/** Ranks a discovered model id against GEMINI_MODEL_PREFERENCE (lower = better). */
function rankGeminiModel(id: string): number {
  const idx = GEMINI_MODEL_PREFERENCE.indexOf(id)
  if (idx !== -1) return idx
  // Unknown-but-supported models: mildly prefer "flash" (cheaper/faster)
  // over "pro", ranked after every explicitly known-good model.
  return GEMINI_MODEL_PREFERENCE.length + (id.includes('flash') ? 0 : 1)
}

/** Queries the user's own key for which Gemini models currently support generateContent. */
async function listCompatibleGeminiModels(apiKey: string): Promise<string[]> {
  const { signal, clear } = withTimeout(QUICK_TIMEOUT_MS)
  let res: Response
  try {
    res = await fetch(`${GEMINI_API_BASE}/models?key=${apiKey}`, { signal })
  } catch (err) {
    if (isAbortError(err)) throw new ProviderTimeoutError('Gemini model list request timed out')
    throw err
  } finally {
    clear()
  }
  if (!res.ok) {
    throw new GeminiApiError(await extractError(res), res.status)
  }
  const data = await res.json()
  const models: Array<{ name?: string; supportedGenerationMethods?: string[] }> = data?.models ?? []
  const compatible = models
    .filter(m => m.supportedGenerationMethods?.includes('generateContent'))
    .map(m => stripModelPrefix(m.name ?? ''))
    .filter(Boolean)
  compatible.sort((a, b) => rankGeminiModel(a) - rankGeminiModel(b))
  return compatible
}

/**
 * Resolves the list of Gemini models currently available to this API key
 * (best-first), caching the result for the session so ThunderGuide doesn't
 * re-list models on every action.
 */
async function resolveGeminiModels(apiKey: string, forceRefresh = false): Promise<string[]> {
  const cached = geminiModelCache.get(apiKey)
  if (!forceRefresh && cached && Date.now() - cached.resolvedAt < GEMINI_CACHE_TTL_MS) {
    return cached.candidates
  }
  const candidates = await listCompatibleGeminiModels(apiKey)
  geminiModelCache.set(apiKey, { resolvedAt: Date.now(), candidates })
  return candidates
}

function isModelNotFoundError(err: unknown): boolean {
  return err instanceof GeminiApiError && (err.status === 404 || /not found|not supported/i.test(err.message))
}

function isAuthError(err: unknown): boolean {
  return err instanceof GeminiApiError && (err.status === 400 || err.status === 401 || err.status === 403)
}

// ROOT CAUSE FIX — Gemini rate-limit (429) and provider-outage (502/503/504)
// responses used to fall through to the same generic "had trouble reaching
// Gemini" message as any other unclassified failure, indistinguishable from
// a genuine bug. Classifying them explicitly gives actionable feedback for
// these two common, provider-side failure modes.
function isRateLimitError(err: unknown): boolean {
  return err instanceof GeminiApiError && (err.status === 429 || /rate.?limit|quota/i.test(err.message))
}

function isUnavailableError(err: unknown): boolean {
  return err instanceof GeminiApiError &&
    (err.status === 502 || err.status === 503 || err.status === 504 ||
      /unavailable|overloaded/i.test(err.message))
}

async function generateWithGeminiModel(
  apiKey: string, model: string, systemPrompt: string, userPrompt: string, maxTokens: number
): Promise<string> {
  const { signal, clear } = withTimeout(GENERATION_TIMEOUT_MS)
  let res: Response
  try {
    res = await fetch(
      `${GEMINI_API_BASE}/models/${model}:generateContent?key=${apiKey}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          systemInstruction: { parts: [{ text: systemPrompt }] },
          contents: [{ role: 'user', parts: [{ text: userPrompt }] }],
          generationConfig: { maxOutputTokens: maxTokens },
        }),
        signal,
      }
    )
  } catch (err) {
    if (isAbortError(err)) throw new ProviderTimeoutError('Gemini generation request timed out')
    throw err
  } finally {
    clear()
  }
  if (!res.ok) {
    throw new GeminiApiError(await extractError(res), res.status)
  }
  const data = await res.json()
  return data.candidates?.[0]?.content?.parts?.map((p: { text?: string }) => p.text ?? '').join('') ?? ''
}

const GEMINI_FRIENDLY_NO_MODEL =
  "ThunderGuide couldn't find a Gemini model that works with your API key right now. " +
  'Double-check your Gemini API key in Settings, or try again in a few minutes.'
const GEMINI_FRIENDLY_AUTH =
  'ThunderGuide could not authenticate with Gemini using your API key. ' +
  'Please check that your Gemini API key in Settings is correct and active.'
const GEMINI_FRIENDLY_GENERIC =
  'ThunderGuide had trouble reaching Gemini just now. Please try again in a moment.'
const GEMINI_FRIENDLY_RATE_LIMIT =
  'Gemini is rate-limiting requests on your account right now. Please wait a moment and try again.'
const GEMINI_FRIENDLY_UNAVAILABLE =
  'Gemini appears to be temporarily unavailable right now. Please try again shortly.'

/**
 * Calls Gemini with automatic model discovery + graceful fallback.
 * Never surfaces the raw provider error text to the caller — always a
 * friendly, actionable message instead.
 */
async function callGemini(
  apiKey: string, explicitModel: string | undefined,
  systemPrompt: string, userPrompt: string, maxTokens: number
): Promise<string> {
  // Respect an explicitly requested model first (e.g. a future per-call
  // override), but still fall back to auto-detected models if it 404s.
  const tryOrder: string[] = []
  if (explicitModel) tryOrder.push(explicitModel)

  try {
    const discovered = await resolveGeminiModels(apiKey)
    for (const m of discovered) {
      if (!tryOrder.includes(m)) tryOrder.push(m)
    }
  } catch (err) {
    if (isAuthError(err)) throw new Error(GEMINI_FRIENDLY_AUTH)
    // Listing failed for a non-auth reason (e.g. transient network blip);
    // fall through and still try any explicit model we already queued.
  }

  if (tryOrder.length === 0) {
    throw new Error(GEMINI_FRIENDLY_NO_MODEL)
  }

  let lastErr: unknown = null
  for (const candidate of tryOrder) {
    try {
      return await generateWithGeminiModel(apiKey, candidate, systemPrompt, userPrompt, maxTokens)
    } catch (err) {
      lastErr = err
      if (err instanceof ProviderTimeoutError) throw friendlyTimeoutError('Gemini')
      if (isAuthError(err)) throw new Error(GEMINI_FRIENDLY_AUTH)
      if (isRateLimitError(err)) throw new Error(GEMINI_FRIENDLY_RATE_LIMIT)
      if (isUnavailableError(err)) throw new Error(GEMINI_FRIENDLY_UNAVAILABLE)
      if (isModelNotFoundError(err)) {
        // Stale/unsupported model id — drop the cached list so the next
        // ThunderGuide call re-detects from scratch, then keep trying the
        // remaining candidates within this same request.
        geminiModelCache.delete(apiKey)
        continue
      }
      // Non-model, non-auth error (e.g. an unclassified provider response):
      // stop trying further models for this request rather than masking a
      // real issue.
      break
    }
  }
  if (lastErr === null || isModelNotFoundError(lastErr)) {
    throw new Error(GEMINI_FRIENDLY_NO_MODEL)
  }
  throw new Error(GEMINI_FRIENDLY_GENERIC)
}

interface CallOptions {
  provider: AIProviderId
  apiKey: string
  model?: string
  systemPrompt: string
  userPrompt: string
  maxTokens?: number
}

/**
 * Calls Gemini's chat/completions API directly from the browser.
 */
export async function callAIProvider({
  provider, apiKey, model, systemPrompt, userPrompt, maxTokens = 1500,
}: CallOptions): Promise<string> {
  if (provider !== 'gemini') {
    throw new Error('Unsupported provider')
  }
  // No hardcoded model id: discover what this key can actually use, and
  // fall back gracefully. See callGemini() for details.
  return callGemini(apiKey, model, systemPrompt, userPrompt, maxTokens)
}

async function extractError(res: Response): Promise<string> {
  try {
    const data = await res.json()
    return data?.error?.message || data?.message || `Request failed (${res.status})`
  } catch {
    return `Request failed (${res.status})`
  }
}

/** Strips markdown code fences so JSON.parse works on model output. */
export function stripCodeFence(text: string): string {
  return text.trim().replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/, '').trim()
}
