// ============================================================
// ThunderGuide — AI Actions
// High-level prompt construction + parsing for each AI feature.
// ============================================================
import type { Node, Edge } from 'reactflow'
import type { NodeType } from '@/types'
import { callAIProvider, stripCodeFence } from './aiClient'
import type { AIProviderId, GenerationStage, GenerationRetryInfo, GenerationMeta } from './types'
import { computeWorkflowStats, validateWorkflow } from './analyzer'
import { expandPrompt } from './promptIntent'
import { autoRepairWorkflow } from './autoRepair'
import { buildGenericSupportWorkflow } from './genericFallback'
import { detectPromptLanguage, buildLanguageDirective } from './languageDetect'

const VALID_NODE_TYPES: NodeType[] = ['start', 'text_card', 'multiple_choice', 'ai_agent', 'transition', 'end']

function summarizeGraph(nodes: Node[], edges: Edge[]) {
  return {
    nodes: nodes.map(n => ({ id: n.id, type: n.type, data: n.data })),
    edges: edges.map(e => ({ id: e.id, source: e.source, target: e.target })),
    stats: computeWorkflowStats(nodes, edges),
  }
}

interface AIActionArgs {
  provider: AIProviderId
  apiKey: string
  model?: string
}

// ── Build Workflow from Prompt ─────────────────────────────────
// GeneratedNode/GeneratedEdge/GeneratedWorkflow now live in ./types (shared
// with promptIntent.ts, autoRepair.ts, and genericFallback.ts) — re-exported
// here unchanged so every existing import from '@/lib/thunderguide/aiActions'
// keeps working exactly as before.
export type { GeneratedNode, GeneratedEdge, GeneratedWorkflow } from './types'
import type { GeneratedNode, GeneratedEdge, GeneratedWorkflow } from './types'

// Output budget large enough for production-scale graphs (100+ nodes with
// edges/labels still fits well under typical provider output-token ceilings).
// Only this generator's call uses this value — every other ThunderGuide
// action keeps its original, unrelated maxTokens.
const GENERATION_MAX_TOKENS = 7000
const MAX_GENERATION_ATTEMPTS = 3

const BUILD_SYSTEM_PROMPT = `You are ThunderGuide, a workflow-structure generator for the ThunderBots chatbot builder.
Given a plain-English description, output ONLY valid JSON (no markdown, no prose) matching this exact shape:
{
  "nodes": [ { "type": "start|text_card|multiple_choice|ai_agent|transition|end", "label": "string", "data": { ...node-specific fields... } } ],
  "edges": [ { "from": 0, "to": 1, "choiceIndex": 0 } ]
}

Node data shapes:
- text_card: { "content": "string" }
- multiple_choice: { "question": "string", "choices": [{ "label": "string", "value": "string" }] }
- ai_agent: { "systemPrompt": "string", "temperature": 0.7, "maxTokens": 800, "contextWindow": 10, "memoryEnabled": true, "stayOnNode": true }
  (never set a "provider" field — the app resolves each AI Agent to the user's own configured default provider at run time; an explicit value here would override that and must be omitted)
  (never invent a "knowledgeBaseId" — Knowledge Base linking is configured by the user after insertion)
- transition: { "conditions": [] } — use only to gate re-entry into a loop or merge branches back together; keep at most one condition, described only through your node "label" (e.g. "Retry if unresolved")
- end: { "message": "string" }

Sizing — no artificial cap:
- The number of nodes is driven entirely by the description's real scope, not by a fixed target.
- A single clear task may need only a handful of nodes; a request describing a full production
  support flow, multi-department routing, or many distinct scenarios should produce a correspondingly
  large graph — 100+ nodes when the description genuinely calls for that much branching.
- Never pad with filler nodes just to hit a size, and never compress genuinely distinct branches
  together just to stay small.

Multiple Choice branching (critical):
- Every single choice in a multiple_choice node's "choices" array MUST have exactly one outgoing edge
  whose "from" is that node's index and whose "choiceIndex" equals that choice's zero-based position.
- Never omit an edge for a choice, and never give two choices the same choiceIndex.
- Different choices may legitimately lead to the same downstream node (a merge point) — that is fine —
  but each still needs its OWN edge with its OWN choiceIndex. Do not collapse all choices onto one edge.
- Do not add a choiceIndex to edges whose "from" is not a multiple_choice node.

Graph intelligence:
- Nested branches: a choice may lead into another multiple_choice node to narrow down intent further.
- Merge points: separate branches may reconverge on a shared node (e.g. a common ai_agent or end) —
  give each incoming branch its own edge into that shared node.
- Loops: only create a cycle when the description implies retrying or repeating a step, and only when
  a transition node with a condition provides a real exit out of the cycle. Never create a cycle with
  no way out.
- ai_agent placement: use ai_agent nodes wherever the conversation needs open-ended understanding,
  summarization, or generated responses, typically after a branch has narrowed down what the user wants.
- transition nodes: use to gate conditional re-entry or to join branches back together; do not use them
  as a substitute for multiple_choice branching.
- end nodes: every branch must terminate at an end node (or deliberately loop back with a guaranteed
  exit) — never leave a branch dangling with no further connection unless it is an end node.
- Conditional paths and Knowledge Base usage should be reflected in ai_agent "systemPrompt" wording,
  not by inventing new node types or fields outside the shapes above.

Production quality:
- Give every node a short, specific, human-readable "label" describing its role (never generic
  placeholders like "Node 1").
- No orphan nodes (every non-start node has at least one incoming edge).
- No unreachable nodes (every node must be reachable from the start node by following edges).
- No duplicate branches (never emit two edges with the same from/to/choiceIndex).
- No dead-end paths unless the node is intentionally an end node.

Output contract:
- "from"/"to" are zero-based indices into the "nodes" array.
- Always include exactly one "start" node at index 0 and at least one "end" node.
- Output raw JSON only — no markdown fences, no commentary.`

function toValidationShape(nodes: GeneratedNode[], edges: GeneratedEdge[]) {
  const rfNodes = nodes.map((n, i) => ({
    id: String(i),
    type: n.type,
    position: { x: 0, y: 0 },
    data: n.data,
  })) as unknown as Node[]
  const rfEdges = edges.map((e, i) => ({
    id: `v${i}`,
    source: String(e.from),
    target: String(e.to),
  })) as unknown as Edge[]
  return { rfNodes, rfEdges }
}

function multipleChoiceCoverageIssues(nodes: GeneratedNode[], edges: GeneratedEdge[]): string[] {
  const issues: string[] = []
  nodes.forEach((n, i) => {
    if (n.type !== 'multiple_choice') return
    const choices = (n.data as { choices?: Array<{ label?: string }> })?.choices ?? []
    if (!Array.isArray(choices) || choices.length === 0) return

    const outEdges = edges.filter(e => e.from === i)
    const seen = new Set<number>()
    const dupes = new Set<number>()
    outEdges.forEach(e => {
      if (typeof e.choiceIndex !== 'number') return
      if (seen.has(e.choiceIndex)) dupes.add(e.choiceIndex)
      seen.add(e.choiceIndex)
    })

    for (let c = 0; c < choices.length; c++) {
      if (!seen.has(c)) {
        issues.push(
          `Multiple Choice node #${i} ("${n.label}") option ${c + 1} ("${choices[c]?.label ?? ''}") ` +
          `has no outgoing connection tagged with choiceIndex ${c}. Every option needs its own connection.`
        )
      }
    }
    if (dupes.size > 0) {
      issues.push(`Multiple Choice node #${i} ("${n.label}") has more than one outgoing connection sharing the same choiceIndex.`)
    }
  })
  return issues
}

function dedupeEdges(edges: GeneratedEdge[]): GeneratedEdge[] {
  const seen = new Set<string>()
  return edges.filter(e => {
    const key = `${e.from}->${e.to}:${e.choiceIndex ?? ''}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

/**
 * Runs the free, local validator (analyzer.ts) plus generation-specific
 * checks (Multiple Choice branch coverage, Start/End presence) against a
 * freshly-generated workflow. Returns human-readable issue strings; an
 * empty array means the workflow is safe to hand to the user.
 */
export function validateGeneratedWorkflow(gw: GeneratedWorkflow): string[] {
  const issues: string[] = []

  if (!gw.nodes || gw.nodes.length === 0) {
    return ['No nodes were generated.']
  }
  if (gw.nodes[0]?.type !== 'start') {
    issues.push('The first node must be a Start node at index 0.')
  }
  if (!gw.nodes.some(n => n.type === 'end')) {
    issues.push('The workflow has no End node.')
  }

  issues.push(...multipleChoiceCoverageIssues(gw.nodes, gw.edges))

  const { rfNodes, rfEdges } = toValidationShape(gw.nodes, gw.edges)
  validateWorkflow(rfNodes, rfEdges).issues
    .filter(i => i.severity === 'critical')
    .forEach(i => issues.push(i.description))

  return issues
}

export async function buildWorkflowFromPrompt(
  args: AIActionArgs, description: string,
  onStage?: (stage: GenerationStage) => void,
  onRetry?: (info: GenerationRetryInfo) => void,
  onComplete?: (meta: GenerationMeta) => void,
): Promise<GeneratedWorkflow> {
  // Wall-clock timer for the Success Screen's "Generation Time" — starts
  // here (before anything else runs) and is read only at the three points
  // below where a workflow is actually handed back, so it always covers
  // every retry plus the final validation/auto-repair pass. Purely a
  // measurement; never gates or delays generation itself.
  const now = () => (typeof performance !== 'undefined' ? performance.now() : Date.now())
  const startedAt = now()
  // Stage callbacks are UI notifications only, wrapped defensively so a
  // throwing subscriber (e.g. a UI bug) can never break generation. The one
  // deliberate frame-yield below (see emit) lets the UI paint each stage;
  // it costs at most ~1 frame per stage and only runs when a subscriber is
  // present — negligible next to the multi-second network call itself.
  const emit = async (stage: GenerationStage) => {
    if (!onStage) return
    try { onStage(stage) } catch { /* UI callback errors must never affect generation */ }
    // Yield a single animation frame so the stage actually paints before the
    // next (synchronous) step of generation overwrites it. Only runs when a
    // subscriber is present, and costs at most ~1 frame (~16ms) — negligible
    // next to the multi-second network call this progress is tracking.
    await new Promise<void>(resolve => {
      if (typeof requestAnimationFrame === 'function') requestAnimationFrame(() => resolve())
      else setTimeout(resolve, 0)
    })
  }

  let lastCandidate: GeneratedWorkflow | null = null
  let lastIssues: string[] = []
  let lastRepaired = false

  // ── Prompt Understanding ──────────────────────────────────────
  // Expand the raw text into a complete requirements brief before it ever
  // reaches the model. Short, keyword-style prompts ("restaurant", "banking",
  // "WhatsApp bot") get replaced with a full domain brief with intelligent
  // defaults (recommended branches, an AI Agent + Knowledge Base fallback,
  // guaranteed End nodes); longer prompts are respected as written but still
  // get the same structural-completeness reminder plus any recognizable
  // domain layered in as extra context. See promptIntent.ts. Computed here
  // (rather than after emit('understanding') below) purely so wasShortPrompt/
  // matchedDomain are already available to the finish() meta-reporter below.
  const { expandedDescription, matchedDomain, wasShortPrompt } = expandPrompt(description)

  // Reports timing + confidence-input metadata once, right at whichever
  // return point is actually taken. Wrapped defensively like every other
  // UI callback here — a throwing subscriber can never affect generation.
  const finish = (
    workflow: GeneratedWorkflow,
    extra: { attemptsUsed: number; autoRepaired: boolean; usedFallback: boolean },
  ): GeneratedWorkflow => {
    if (onComplete) {
      try {
        onComplete({
          generationTimeMs: now() - startedAt,
          attemptsUsed: extra.attemptsUsed,
          retryCount: Math.max(0, extra.attemptsUsed - 1),
          autoRepaired: extra.autoRepaired,
          usedFallback: extra.usedFallback,
          wasShortPrompt,
          matchedDomain,
        })
      } catch { /* UI callback errors must never affect generation */ }
    }
    return workflow
  }

  await emit('understanding')

  // ── Automatic Language Detection ───────────────────────────────
  // Local, offline detection of English/Hindi/Marathi (including mixed
  // prompts) from the raw text the person typed — before any expansion —
  // so the language directive reflects what they actually wrote, not the
  // (always-English) domain brief template. See languageDetect.ts.
  const detectedLanguage = detectPromptLanguage(description)
  const languageDirective = buildLanguageDirective(detectedLanguage)
  const systemPromptWithLanguage = `${BUILD_SYSTEM_PROMPT}${languageDirective}`

  for (let attempt = 1; attempt <= MAX_GENERATION_ATTEMPTS; attempt++) {
    const userPrompt = attempt === 1
      ? expandedDescription
      : `${expandedDescription}\n\nYour previous attempt failed validation for these reasons:\n` +
        lastIssues.map(i => `- ${i}`).join('\n') +
        `\nRegenerate the FULL workflow JSON from scratch, fixing every issue above. Output raw JSON only.`

    await emit('planning')
    await emit('choosing')
    await emit('building')

    const raw = await callAIProvider({
      ...args,
      systemPrompt: systemPromptWithLanguage,
      userPrompt,
      maxTokens: GENERATION_MAX_TOKENS,
    })

    let candidate: GeneratedWorkflow
    try {
      candidate = JSON.parse(stripCodeFence(raw)) as GeneratedWorkflow
    } catch {
      lastIssues = ['Output was not valid JSON.']
      if (attempt < MAX_GENERATION_ATTEMPTS && onRetry) {
        try { onRetry({ attempt, maxAttempts: MAX_GENERATION_ATTEMPTS, reasons: lastIssues }) } catch { /* UI callback errors must never affect generation */ }
      }
      continue
    }

    candidate.nodes = (candidate.nodes ?? []).filter(n => VALID_NODE_TYPES.includes(n.type))
    candidate.edges = dedupeEdges(candidate.edges ?? [])

    // Auto-repair: fix locally-fixable gaps (missing End node, a Multiple
    // Choice option with no outgoing edge, out-of-range edges) before
    // validating. Strictly additive/corrective — never rewrites intent.
    // The before/after comparison below is purely observational (feeds the
    // Success Screen's confidence score) and never changes what autoRepair
    // actually does.
    const beforeRepairNodeCount = candidate.nodes.length
    const beforeRepairEdgeCount = candidate.edges.length
    if (candidate.nodes.length > 0) {
      candidate = autoRepairWorkflow(candidate)
    }
    const repairedThisAttempt =
      candidate.nodes.length !== beforeRepairNodeCount || candidate.edges.length !== beforeRepairEdgeCount

    await emit('validating')
    const issues = validateGeneratedWorkflow(candidate)
    if (issues.length === 0) {
      await emit('optimizing')
      await emit('finalizing')
      return finish(candidate, { attemptsUsed: attempt, autoRepaired: repairedThisAttempt, usedFallback: false })
    }

    lastCandidate = candidate
    lastIssues = issues
    lastRepaired = repairedThisAttempt

    // Better Failure Recovery: report exactly why this attempt failed and
    // which retry number is about to run, purely for UI transparency — the
    // retry itself (userPrompt above already includes lastIssues) is
    // unchanged. Never fires on the final attempt (there is no further
    // retry to announce).
    if (attempt < MAX_GENERATION_ATTEMPTS && onRetry) {
      try { onRetry({ attempt, maxAttempts: MAX_GENERATION_ATTEMPTS, reasons: lastIssues }) } catch { /* UI callback errors must never affect generation */ }
    }
  }

  // ROOT CAUSE FIX ("0 Nodes / 0 Connections" imports): this used to fall
  // back to `lastCandidate` after exhausting all retries as long as it had
  // no Multiple Choice coverage problems — but that check is VACUOUSLY TRUE
  // for a candidate with zero (or zero valid-typed) nodes, since there are
  // no multiple_choice nodes to have coverage issues in the first place. A
  // completely empty or fully-filtered-out candidate (e.g. every attempt
  // returned malformed JSON, or nodes with unrecognized "type" values that
  // VALID_NODE_TYPES filtered down to []) was therefore returned as if it
  // were a valid workflow, silently shipping "0 nodes / 0 connections" all
  // the way through workflow creation and into the Builder. The fallback
  // must re-run the SAME full validation used for every attempt — the same
  // bar every earlier attempt was held to — not a narrower one.
  if (lastCandidate && validateGeneratedWorkflow(lastCandidate).length === 0) {
    await emit('optimizing')
    await emit('finalizing')
    return finish(lastCandidate, { attemptsUsed: MAX_GENERATION_ATTEMPTS, autoRepaired: lastRepaired, usedFallback: false })
  }

  // Generic Customer Support fallback: every attempt above went through
  // prompt expansion, generation, local auto-repair, and full validation —
  // and still came up short (a flaky provider response, a domain the brief
  // couldn't resolve, or a model that keeps producing broken graphs). Per
  // requirements, ThunderGuide must never fail or hand back an incomplete
  // workflow here — fall back to a static, correct-by-construction generic
  // Customer Support chatbot instead. No network dependency, always valid.
  await emit('optimizing')
  await emit('finalizing')
  return finish(buildGenericSupportWorkflow(), { attemptsUsed: MAX_GENERATION_ATTEMPTS, autoRepaired: false, usedFallback: true })
}

/**
 * Runtime type guard for anything about to be treated as a GeneratedWorkflow
 * — e.g. read back out of sessionStorage via takePendingImport(), where a
 * TypeScript `as GeneratedWorkflow` cast is a compile-time-only assertion
 * with no actual runtime guarantee. Every consumer that reads .nodes/.edges
 * off a value crossing a serialization boundary (storage, IPC, an older
 * cached schema, a value edited by hand) MUST check this first instead of
 * assuming the shape — this is the defensive guard that prevents the
 * "Cannot read properties of undefined (reading 'reduce')" class of Builder
 * crash regardless of how a malformed value got there.
 */
export function isValidGeneratedWorkflow(value: unknown): value is GeneratedWorkflow {
  if (!value || typeof value !== 'object') return false
  const v = value as Partial<GeneratedWorkflow>
  if (!Array.isArray(v.nodes) || v.nodes.length === 0) return false
  if (!Array.isArray(v.edges)) return false
  if (!v.nodes.every(n => n && typeof n === 'object' && VALID_NODE_TYPES.includes(n.type))) return false
  if (!v.edges.every(e => e && typeof e === 'object' && typeof e.from === 'number' && typeof e.to === 'number')) return false
  if (v.nodes[0]?.type !== 'start') return false
  if (!v.nodes.some(n => n.type === 'end')) return false
  return true
}

// ── AI Node Suggestions ─────────────────────────────────────────
export interface NodeSuggestion { type: NodeType; reason: string }

export async function suggestNextNodes(
  args: AIActionArgs, nodes: Node[], edges: Edge[], focusNodeId?: string | null
): Promise<NodeSuggestion[]> {
  const system = `You are ThunderGuide, a workflow copilot for the ThunderBots chatbot builder.
Given the current workflow graph (JSON) and optionally a focus node, suggest 2-4 sensible next node types to add.
Output ONLY valid JSON: an array of { "type": "start|text_card|multiple_choice|ai_agent|transition|end", "reason": "short one-sentence reason" }.
No markdown, no prose, JSON array only.`

  const userPrompt = JSON.stringify({
    graph: summarizeGraph(nodes, edges),
    focusNodeId: focusNodeId ?? null,
  })

  const raw = await callAIProvider({ ...args, systemPrompt: system, userPrompt, maxTokens: 700 })
  const parsed = JSON.parse(stripCodeFence(raw)) as NodeSuggestion[]
  return parsed.filter(s => VALID_NODE_TYPES.includes(s.type))
}

// ── Explain Workflow ─────────────────────────────────────────────
export async function explainWorkflow(args: AIActionArgs, nodes: Node[], edges: Edge[]): Promise<string> {
  const system = `You are ThunderGuide, a workflow copilot for the ThunderBots chatbot builder.
Explain the given workflow graph (JSON) in plain, friendly English for a non-technical builder.
Describe the conversation flow step by step, mention branch points, and flag anything confusing.
Respond in concise markdown (use short paragraphs and bullet points). No JSON.`

  const userPrompt = JSON.stringify(summarizeGraph(nodes, edges))
  return callAIProvider({ ...args, systemPrompt: system, userPrompt, maxTokens: 1200 })
}

// ── Generate Documentation ────────────────────────────────────────
export async function generateDocumentation(
  args: AIActionArgs, nodes: Node[], edges: Edge[], workflowName: string
): Promise<string> {
  const system = `You are ThunderGuide, a technical writer for the ThunderBots chatbot builder.
Given a workflow graph (JSON) and its name, produce clean markdown documentation with these sections:
# ${workflowName || 'Workflow'} — Documentation
## Overview
## Conversation Flow
## Node Reference (table: Node, Type, Purpose)
## Notes & Edge Cases
Respond in markdown only, no surrounding commentary.`

  const userPrompt = JSON.stringify({ workflowName, graph: summarizeGraph(nodes, edges) })
  return callAIProvider({ ...args, systemPrompt: system, userPrompt, maxTokens: 2000 })
}

// ── Advanced Workflow Optimization ────────────────────────────────
export interface AdvancedSuggestion { title: string; detail: string; impact: 'high' | 'medium' | 'low' }

export async function advancedOptimize(
  args: AIActionArgs, nodes: Node[], edges: Edge[]
): Promise<AdvancedSuggestion[]> {
  const system = `You are ThunderGuide, a senior conversation-design reviewer for the ThunderBots chatbot builder.
Given a workflow graph (JSON), identify deeper UX, conversation-design, and efficiency improvements
that go beyond simple structural rules (e.g. tone consistency, redundant questions, missing fallback
paths, prompt quality for AI Agent nodes, unclear choice labels).
Output ONLY a valid JSON array of { "title": "string", "detail": "string", "impact": "high|medium|low" }.
3-8 suggestions. No markdown, no prose, JSON array only.`

  const userPrompt = JSON.stringify(summarizeGraph(nodes, edges))
  const raw = await callAIProvider({ ...args, systemPrompt: system, userPrompt, maxTokens: 1800 })
  return JSON.parse(stripCodeFence(raw)) as AdvancedSuggestion[]
}
