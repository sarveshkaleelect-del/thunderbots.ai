// ============================================================
// AI Chatbot by Prompt — lightweight client-side persistence
//
// Purely additive: no backend endpoints, no new tables. Uses
// sessionStorage for short-lived state (draft prompt, pending
// import) and localStorage for the one durable flag (has the
// user ever generated a chatbot via AI Prompt) that permanently
// disables the Builder reminder.
// ============================================================

const PROMPT_KEY = 'tb_ai_create_prompt_draft'
const PROVIDER_KEY = 'tb_ai_create_provider_draft'
const PENDING_IMPORT_PREFIX = 'tb_ai_pending_import__'
const GENERATED_FLAG = 'tb_ai_chatbot_generated'
const REMINDER_DISMISSED_SESSION_KEY = 'tb_ai_reminder_dismissed_session'

/** Saves the in-progress prompt (+ optional provider) so it survives a
 * round trip to Settings → API Keys and back. */
export function savePromptDraft(prompt: string, provider?: string | null) {
  if (typeof window === 'undefined') return
  sessionStorage.setItem(PROMPT_KEY, prompt)
  if (provider) sessionStorage.setItem(PROVIDER_KEY, provider)
}

export function loadPromptDraft(): { prompt: string; provider: string | null } {
  if (typeof window === 'undefined') return { prompt: '', provider: null }
  return {
    prompt: sessionStorage.getItem(PROMPT_KEY) || '',
    provider: sessionStorage.getItem(PROVIDER_KEY),
  }
}

export function clearPromptDraft() {
  if (typeof window === 'undefined') return
  sessionStorage.removeItem(PROMPT_KEY)
  sessionStorage.removeItem(PROVIDER_KEY)
}

/** Stashes a freshly generated workflow graph, keyed by the newly created
 * workflow's id, so the Builder page can import it once on first load. */
export function setPendingImport(workflowId: string, graph: unknown): boolean {
  if (typeof window === 'undefined') return false
  try {
    sessionStorage.setItem(PENDING_IMPORT_PREFIX + workflowId, JSON.stringify(graph))
    return true
  } catch {
    // Storage full/unavailable (e.g. private-browsing quota, a very large
    // generated graph). ROOT CAUSE FIX: this used to be swallowed entirely,
    // so the caller (create-with-ai/page.tsx) would navigate to the Builder
    // believing the import was queued, and the Builder would open with 0
    // nodes/0 connections — no crash, just a silent empty canvas. Returning
    // false lets the caller keep the user on the Create with AI page and
    // show a clear error instead of ever opening an empty Builder.
    return false
  }
}

/** Reads and clears (one-time) a pending import for this workflow id. */
export function takePendingImport<T = unknown>(workflowId: string): T | null {
  if (typeof window === 'undefined') return null
  const key = PENDING_IMPORT_PREFIX + workflowId
  const raw = sessionStorage.getItem(key)
  if (!raw) return null
  sessionStorage.removeItem(key)
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

export function markChatbotGeneratedViaAI() {
  if (typeof window === 'undefined') return
  localStorage.setItem(GENERATED_FLAG, '1')
}

export function hasGeneratedChatbotViaAI(): boolean {
  if (typeof window === 'undefined') return false
  return localStorage.getItem(GENERATED_FLAG) === '1'
}

export function dismissReminderForSession() {
  if (typeof window === 'undefined') return
  sessionStorage.setItem(REMINDER_DISMISSED_SESSION_KEY, '1')
}

export function isReminderDismissedForSession(): boolean {
  if (typeof window === 'undefined') return false
  return sessionStorage.getItem(REMINDER_DISMISSED_SESSION_KEY) === '1'
}
