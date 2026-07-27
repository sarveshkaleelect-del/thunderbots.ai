// ============================================================
// ThunderGuide — Generation Summary
//
// Purely presentational, purely local. Derives every field shown on the
// final Success Screen (Industry, Language, AI Provider, Total Nodes,
// Estimated Complexity, Generation Time, AI Confidence) from data
// ThunderGuide already has after a successful generation — no new network
// calls, no change to the generated workflow itself, no change to
// generation/validation/repair logic. All calculations are deterministic
// and run in well under a millisecond.
// ============================================================
import type { GeneratedWorkflow, GenerationMeta } from './types'
import type { AIProviderId, LanguageDetectionResult } from './types'
import { classifyIntent } from './promptIntent'
import { PROVIDER_LABELS } from './aiClient'

export type ComplexityLabel = 'Simple' | 'Moderate' | 'Advanced' | 'Complex'

/**
 * Rough, deterministic complexity estimate from graph size alone — no AI
 * call, so it's instant and always available on the success screen.
 * Thresholds are intentionally generous since ThunderBots workflows can
 * legitimately run to 100+ nodes for large support flows.
 */
export function estimateComplexity(nodeCount: number): ComplexityLabel {
  if (nodeCount <= 6) return 'Simple'
  if (nodeCount <= 15) return 'Moderate'
  if (nodeCount <= 30) return 'Advanced'
  return 'Complex'
}

// ── Generation Time ───────────────────────────────────────────────────
/** Formats a millisecond duration as "4.8 seconds" / "12.4 seconds". */
export function formatGenerationTime(ms: number): string {
  const seconds = Math.max(0, ms) / 1000
  const rounded = Math.round(seconds * 10) / 10
  return `${rounded.toFixed(1)} second${rounded === 1 ? '' : 's'}`
}

// ── AI Confidence Score ────────────────────────────────────────────────
export type ConfidenceLabel = 'Excellent' | 'High' | 'Good' | 'Review Recommended'

export interface ConfidenceResult {
  score: number
  label: ConfidenceLabel
  /** 🟢 / 🟡 / 🔴 — reflects the score tier, not just a fixed green dot. */
  emoji: string
  /** True if the generation relied on any assumption ThunderGuide made for the person. */
  assumptionsMade: boolean
}

function confidenceLabelFor(score: number): ConfidenceLabel {
  if (score >= 95) return 'Excellent'
  if (score >= 85) return 'High'
  if (score >= 70) return 'Good'
  return 'Review Recommended'
}

function confidenceEmojiFor(score: number): string {
  if (score >= 85) return '🟢'
  if (score >= 70) return '🟡'
  return '🔴'
}

/**
 * Deterministic, local 0–100 confidence estimate. Every input is something
 * ThunderGuide already knows after generation completes — no extra model
 * call, no new dependency. Factors, each reducing confidence from a 100
 * baseline:
 *  - Prompt clarity: a short/keyword-style prompt required ThunderGuide to
 *    fill in scope itself rather than the person specifying it.
 *  - Intent recognition: no recognized domain meant a generic brief was used.
 *  - Retry count: each internal regeneration means the model's first
 *    attempt(s) failed local validation.
 *  - Auto-repair usage: the winning candidate needed structural patching
 *    (a missing End node, an uncovered Multiple Choice option, etc).
 *  - Fallback usage: every model attempt failed outright and the static
 *    generic Customer Support workflow was used instead — a large hit.
 *  - Workflow completeness / required node coverage: a very thin graph, or
 *    one missing an AI Agent fallback, suggests the result may need review.
 */
export function computeConfidence(meta: GenerationMeta, workflow: GeneratedWorkflow): ConfidenceResult {
  let score = 100
  let assumptionsMade = false

  if (meta.usedFallback) {
    // The static generic-support workflow was used — none of the person's
    // specific requirements made it into this graph.
    score -= 35
    assumptionsMade = true
  } else {
    if (meta.wasShortPrompt) {
      score -= 6
      assumptionsMade = true
    }
    if (!meta.matchedDomain) {
      score -= 10
      assumptionsMade = true
    }
    if (meta.retryCount > 0) {
      score -= Math.min(14, meta.retryCount * 7)
    }
    if (meta.autoRepaired) {
      score -= 6
      assumptionsMade = true
    }
  }

  const nodeCount = workflow.nodes.length
  const hasAiAgent = workflow.nodes.some(n => n.type === 'ai_agent')
  const hasMultipleChoice = workflow.nodes.some(n => n.type === 'multiple_choice')

  if (nodeCount < 4) score -= 8
  if (!hasAiAgent) score -= 5
  if (!hasMultipleChoice && nodeCount > 3) score -= 3

  score = Math.max(0, Math.min(100, Math.round(score)))

  return {
    score,
    label: confidenceLabelFor(score),
    emoji: confidenceEmojiFor(score),
    assumptionsMade,
  }
}

export interface GenerationSummary {
  industry: string
  languageName: string
  aiProvider: string
  totalNodes: number
  totalEdges: number
  complexity: ComplexityLabel
  generationTimeLabel: string
  confidence: ConfidenceResult
}

/**
 * Builds the summary shown on ThunderGuide's final success screen. `prompt`
 * is the raw text the person typed (used only to classify the industry —
 * the same local classifier expandPrompt() already uses internally).
 */
export function buildGenerationSummary(
  prompt: string,
  provider: AIProviderId,
  detectedLanguage: LanguageDetectionResult,
  workflow: GeneratedWorkflow,
  meta: GenerationMeta,
): GenerationSummary {
  const match = classifyIntent(prompt)
  return {
    industry: match?.profile.label ?? 'General / Custom',
    languageName: detectedLanguage.languageName,
    aiProvider: PROVIDER_LABELS[provider],
    totalNodes: workflow.nodes.length,
    totalEdges: workflow.edges.length,
    complexity: estimateComplexity(workflow.nodes.length),
    generationTimeLabel: formatGenerationTime(meta.generationTimeMs),
    confidence: computeConfidence(meta, workflow),
  }
}
