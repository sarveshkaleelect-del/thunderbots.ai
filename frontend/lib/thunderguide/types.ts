// ============================================================
// ThunderGuide — shared types
// ============================================================
import type { Node, Edge } from 'reactflow'

export type IssueSeverity = 'critical' | 'warning' | 'info'

export interface WorkflowIssue {
  id: string
  severity: IssueSeverity
  title: string
  description: string
  nodeIds?: string[]
  edgeIds?: string[]
}

export interface ValidationResult {
  valid: boolean
  issues: WorkflowIssue[]
}

export interface WorkflowStats {
  totalNodes: number
  totalEdges: number
  nodesByType: Record<string, number>
  startNodes: number
  endNodes: number
  aiAgentNodes: number
  branchingNodes: number
  avgOutDegree: number
  maxDepth: number
  isolatedNodes: number
  reachableNodes: number
  unreachableNodes: number
}

export interface HealthScoreResult {
  score: number // 0-100
  grade: 'A' | 'B' | 'C' | 'D' | 'F'
  breakdown: { label: string; points: number; max: number }[]
}

export interface OptimizationSuggestion {
  id: string
  title: string
  detail: string
  impact: 'high' | 'medium' | 'low'
}

export type AIProviderId = 'gemini'

// ── Progressive Generation (ThunderGuide "Build Workflow from Prompt") ──
// Ordered stages surfaced to the UI while a workflow is being generated.
// Purely additive/observational — callbacks are fire-and-forget state
// updates and never gate or delay the underlying generation logic.
export type GenerationStage =
  | 'understanding'
  | 'planning'
  | 'choosing'
  | 'building'
  | 'validating'
  | 'optimizing'
  | 'finalizing'

export const GENERATION_STAGE_ORDER: GenerationStage[] = [
  'understanding', 'planning', 'choosing', 'building', 'validating', 'optimizing', 'finalizing',
]

// Real progress percentage for each stage of actual generation — driven
// entirely by the true onStage callbacks below (see aiActions.ts), never
// by an elapsed-time/fake timer. 100 is intentionally never assigned here:
// it's reserved for the moment generation has fully and successfully
// completed (set explicitly by the caller once the generated workflow has
// been validated), so a stalled or failed generation can never read 100%.
export const GENERATION_STAGE_PROGRESS: Record<GenerationStage, number> = {
  understanding: 8,
  planning: 22,
  choosing: 38,
  building: 58,
  validating: 74,
  optimizing: 86,
  finalizing: 95,
}

export const GENERATION_STAGE_LABELS: Record<GenerationStage, string> = {
  understanding: 'Understanding your idea...',
  planning: 'Planning conversation flow...',
  choosing: 'Choosing the best workflow...',
  building: 'Building nodes...',
  validating: 'Validating workflow...',
  optimizing: 'Optimizing chatbot...',
  finalizing: 'Finalizing...',
}

// Emoji shown alongside each stage label in the progress indicator. Kept
// separate from the label text so any consumer that only wants the plain
// label (e.g. a future non-emoji surface) can still use GENERATION_STAGE_LABELS
// unchanged.
export const GENERATION_STAGE_EMOJI: Record<GenerationStage, string> = {
  understanding: '🧠',
  planning: '📋',
  choosing: '🤖',
  building: '🔧',
  validating: '✅',
  optimizing: '⚡',
  finalizing: '🚀',
}

// ── Retry / failure-recovery reporting (purely observational) ───────────
// Surfaced to the UI when an internal generation attempt fails validation
// and ThunderGuide is about to auto-repair and regenerate. Never changes
// the underlying retry behavior in aiActions.ts — it only reports it.
export interface GenerationRetryInfo {
  attempt: number
  maxAttempts: number
  reasons: string[]
}

// ── Generation Meta (Success Screen: timing + confidence inputs) ────────
// Collected once per buildWorkflowFromPrompt() call and handed to the UI
// via an optional onComplete callback — purely observational, exactly like
// onStage/onRetry above. Never influences generation/validation/repair
// behavior; it only reports what already happened.
export interface GenerationMeta {
  /** Wall-clock time from the start of generation through validation + auto-repair, in ms. */
  generationTimeMs: number
  /** How many model calls this generation took (1 = succeeded first try). */
  attemptsUsed: number
  /** attemptsUsed - 1, for convenience. */
  retryCount: number
  /** Whether the winning candidate needed local structural auto-repair. */
  autoRepaired: boolean
  /** Whether every model attempt failed and the static generic-support fallback was used. */
  usedFallback: boolean
  /** Whether the raw prompt was short/keyword-style (from promptIntent.ts). */
  wasShortPrompt: boolean
  /** Recognized domain key, or null if intent wasn't confidently classified. */
  matchedDomain: string | null
}

// ── Language detection (multilingual ThunderGuide) ───────────────────────
export type DetectedLanguage = 'en' | 'hi' | 'mr'

export interface LanguageDetectionResult {
  language: DetectedLanguage
  languageName: string
  isMixed: boolean
  confidence: 'high' | 'medium' | 'low'
}

export interface ThunderGuideGraph {
  nodes: Node[]
  edges: Edge[]
}

// ── Generated Workflow shapes (Build Workflow from Prompt) ──────────────
// Moved here (out of aiActions.ts) so the prompt-understanding, auto-repair,
// and fallback-generation modules can share the exact same shape without a
// circular import back into aiActions.ts, which re-exports these names
// unchanged for every existing consumer.
export type GeneratedNodeType =
  | 'start' | 'text_card' | 'multiple_choice' | 'ai_agent' | 'transition' | 'end'

export interface GeneratedNode {
  type: GeneratedNodeType
  label: string
  data: Record<string, unknown>
}

export interface GeneratedEdge {
  from: number
  to: number
  // Zero-based index into the source Multiple Choice node's "choices" array.
  choiceIndex?: number
}

export interface GeneratedWorkflow {
  nodes: GeneratedNode[]
  edges: GeneratedEdge[]
}

// ── Prompt Understanding (short-prompt expansion) ────────────────────────
export interface PromptExpansionResult {
  /** The fully-expanded requirements description handed to the model. */
  expandedDescription: string
  /** Key of the matched domain profile, or null if nothing matched. */
  matchedDomain: string | null
  /** Heuristic: true if the raw input looked like a short keyword/phrase. */
  wasShortPrompt: boolean
}
