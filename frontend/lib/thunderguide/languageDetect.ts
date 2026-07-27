// ============================================================
// ThunderGuide — Prompt Language Detection
//
// Purely local, offline, additive module. Detects whether the person's
// free-text prompt is English, Hindi, or Marathi (including prompts that
// mix Devanagari with English words/brand terms, e.g. "मराठी शाळेसाठी
// chatbot"), so buildWorkflowFromPrompt() (aiActions.ts) can instruct the
// model to generate all user-facing text — labels, greetings, FAQs, AI
// Agent persona wording — in the SAME language the person asked in.
//
// No network calls, no new dependencies. Hindi and Marathi both use the
// Devanagari script, so script detection alone can't tell them apart —
// this uses a small set of characteristic function words/particles that
// reliably differ between the two languages (e.g. Marathi "आहे"/"साठी"
// vs Hindi "है"/"के लिए").
// ============================================================
import type { DetectedLanguage, LanguageDetectionResult } from './types'

const DEVANAGARI_RE = /[\u0900-\u097F]/g
const LATIN_WORD_RE = /[A-Za-z]{2,}/g

// Explicit language-name mentions are the strongest possible signal and
// are checked before any word-marker scoring.
const EXPLICIT_MARATHI_RE = /मराठी|marathi/i
const EXPLICIT_HINDI_RE = /हिंदी|हिन्दी|hindi/i

// Characteristic function words / grammatical particles. These were chosen
// because they are extremely common in ordinary sentences but rarely (or
// never) used the same way in the other language.
const MARATHI_MARKERS = [
  'आहे', 'आहेत', 'आहात', 'साठी', 'तुम्ही', 'तुम्हाला', 'तुझ्या', 'माझ्या',
  'कृपया', 'हवे', 'हवा', 'हवी', 'पाहिजे', 'करा', 'करतो', 'करते', 'च्या',
  'ची', 'चा', 'चे', 'नमस्कार', 'शाळेसाठी', 'बँकेसाठी',
]
const HINDI_MARKERS = [
  'है', 'हैं', 'आप', 'आपको', 'आपका', 'तुम्हारे', 'मेरे', 'कृपया', 'चाहिए',
  'करो', 'करता', 'करती', 'के लिए', 'की', 'का', 'के', 'नमस्ते', 'स्कूल के लिए',
  'बैंक के लिए',
]

function countMarkers(text: string, markers: string[]): number {
  let count = 0
  for (const m of markers) {
    if (text.includes(m)) count++
  }
  return count
}

/**
 * Detects the dominant language of a ThunderGuide prompt: English, Hindi,
 * or Marathi. Also flags prompts that mix scripts/languages (common in
 * real usage, e.g. a Devanagari sentence with an English brand/feature
 * word like "chatbot" or "FAQ") so callers can note that in the model
 * instructions without treating it as an error.
 */
export function detectPromptLanguage(raw: string): LanguageDetectionResult {
  const text = (raw || '').trim()
  const devanagariMatches = text.match(DEVANAGARI_RE) ?? []
  const latinWordMatches = text.match(LATIN_WORD_RE) ?? []

  if (devanagariMatches.length === 0) {
    return { language: 'en', languageName: 'English', isMixed: false, confidence: 'high' }
  }

  const isMixed = latinWordMatches.length > 0

  // Explicit mention of a language name wins outright unless both are
  // mentioned, in which case fall through to marker scoring.
  const mentionsMarathi = EXPLICIT_MARATHI_RE.test(text)
  const mentionsHindi = EXPLICIT_HINDI_RE.test(text)
  if (mentionsMarathi && !mentionsHindi) {
    return { language: 'mr', languageName: 'Marathi (मराठी)', isMixed, confidence: 'high' }
  }
  if (mentionsHindi && !mentionsMarathi) {
    return { language: 'hi', languageName: 'Hindi (हिंदी)', isMixed, confidence: 'high' }
  }

  const marathiScore = countMarkers(text, MARATHI_MARKERS)
  const hindiScore = countMarkers(text, HINDI_MARKERS)

  if (marathiScore === 0 && hindiScore === 0) {
    // Devanagari present but no recognizable function words (e.g. a very
    // short prompt like just "मराठी" already handled above, or a name/noun
    // only). Default to Hindi — the most widely used Devanagari language —
    // but with low confidence so downstream logic can treat it loosely.
    return { language: 'hi', languageName: 'Hindi (हिंदी)', isMixed, confidence: 'low' }
  }

  if (marathiScore > hindiScore) {
    const confidence = marathiScore - hindiScore >= 2 ? 'high' : 'medium'
    return { language: 'mr', languageName: 'Marathi (मराठी)', isMixed, confidence }
  }
  if (hindiScore > marathiScore) {
    const confidence = hindiScore - marathiScore >= 2 ? 'high' : 'medium'
    return { language: 'hi', languageName: 'Hindi (हिंदी)', isMixed, confidence }
  }
  // Tied score: default to Hindi with medium confidence.
  return { language: 'hi', languageName: 'Hindi (हिंदी)', isMixed, confidence: 'medium' }
}

/**
 * Builds the instruction block appended to the AI system prompt so the
 * model generates every piece of user-facing text (labels, greetings,
 * FAQs, AI Agent persona wording, choice text, end messages) in the
 * detected language — while leaving JSON keys/field names/node "type"
 * values untouched (those are part of the app's data contract, not
 * user-facing content).
 */
export function buildLanguageDirective(detected: LanguageDetectionResult): string {
  if (detected.language === 'en') {
    return `\n\nLanguage: write all user-facing text (labels, greetings, questions, choices, FAQ ` +
      `answers, AI Agent persona wording, end messages) in English.`
  }

  const mixedNote = detected.isMixed
    ? ` The request mixes ${detected.languageName} with some English words — that's fine; still ` +
      `write all generated user-facing text in ${detected.languageName}, using natural, ` +
      `commonly-used phrasing (a few widely-understood English terms like "OK" or a brand name may ` +
      `stay as-is if that's how a native speaker would actually write them).`
    : ''

  return `\n\nLanguage: the user wrote their request in ${detected.languageName}. Write ALL ` +
    `user-facing text — every node "label", text_card "content", multiple_choice "question" and ` +
    `"choices" labels, ai_agent "systemPrompt" persona wording, end "message", and any FAQ content — ` +
    `in ${detected.languageName}, using the Devanagari script and natural, conversational phrasing a ` +
    `native speaker would actually use. Do NOT translate JSON keys, field names, or node "type" ` +
    `values — only the natural-language VALUES change language.${mixedNote}`
}

/** Short language tag for display (success screen, summaries, etc). */
export function languageDisplayName(language: DetectedLanguage): string {
  switch (language) {
    case 'mr': return 'Marathi (मराठी)'
    case 'hi': return 'Hindi (हिंदी)'
    default: return 'English'
  }
}
