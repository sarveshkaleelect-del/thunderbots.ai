'use client'
import { useMemo, useState } from 'react'
import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Lock, KeyRound, Wand2, Lightbulb, MessageSquareText, FileText,
  Gauge, Loader2, AlertCircle, Plus, Copy, Check, ChevronDown, ExternalLink,
} from 'lucide-react'
import { settingsApi } from '@/lib/api/settings'
import { useWorkflowStore } from '@/store/workflowStore'
import { createNode } from '@/lib/utils/nodeFactory'
import { getErrorMessage } from '@/lib/utils/errors'
import { cn } from '@/lib/utils/cn'
import type { AIProvider, UserAPIKey, NodeType } from '@/types'
import type { AIProviderId, GenerationStage } from '@/lib/thunderguide/types'
import {
  PROVIDER_LABELS, getSessionKey, setSessionKey,
} from '@/lib/thunderguide/aiClient'
import {
  buildWorkflowFromPrompt, suggestNextNodes, explainWorkflow,
  generateDocumentation, advancedOptimize, isValidGeneratedWorkflow,
  type GeneratedWorkflow, type NodeSuggestion, type AdvancedSuggestion,
} from '@/lib/thunderguide/aiActions'
import { ThunderGuideProgress } from './ThunderGuideProgress'

const SUPPORTED: AIProviderId[] = ['gemini']

function impactTone(impact: string) {
  if (impact === 'high') return 'text-red-400 border-red-500/25 bg-red-500/10'
  if (impact === 'medium') return 'text-amber-400 border-amber-500/25 bg-amber-500/10'
  return 'text-white/40 border-white/10 bg-white/[0.04]'
}

// ── Locked state ─────────────────────────────────────────────
function LockedAI() {
  return (
    <div className="flex flex-col items-center text-center px-5 py-10">
      <div className="w-14 h-14 rounded-2xl bg-[#6366f1]/10 border border-[#6366f1]/20 flex items-center justify-center mb-4">
        <Lock size={20} className="text-[#a5b4fc]" />
      </div>
      <p className="text-sm font-semibold text-white/80 mb-1.5">AI features are locked</p>
      <p className="text-[11px] text-white/35 leading-relaxed max-w-[240px] mb-5">
        Add your AI Provider API Key to unlock ThunderGuide AI features.
      </p>
      <Link
        href="/settings/api-keys"
        className="flex items-center gap-1.5 text-[11px] font-semibold px-4 py-2.5 rounded-xl
                   bg-[#6366f1] hover:bg-[#5558e8] text-white transition"
      >
        <KeyRound size={12} /> Add API Key
      </Link>
    </div>
  )
}

// ── Session key gate for the selected provider ─────────────────
function SessionKeyGate({ provider, onUnlocked }: { provider: AIProviderId; onUnlocked: () => void }) {
  const [val, setVal] = useState('')
  return (
    <div className="p-3 rounded-xl border border-[#2a2a2a] bg-[#111] space-y-2">
      <p className="text-[10px] text-white/40 leading-relaxed">
        To run {PROVIDER_LABELS[provider]} actions in this session, paste the same key you configured
        in AI Providers. It's kept only in this browser tab and sent directly to {PROVIDER_LABELS[provider]} — never stored on our servers.
      </p>
      <div className="flex gap-2">
        <input
          type="password"
          value={val}
          onChange={e => setVal(e.target.value)}
          placeholder={`${PROVIDER_LABELS[provider]} API key`}
          className="flex-1 bg-[#1a1a1a] text-xs text-white border border-[#2a2a2a] rounded-lg px-3 py-2 outline-none focus:border-[#6366f1]/50 transition font-mono"
        />
        <button
          onClick={() => { if (val.trim()) { setSessionKey(provider, val.trim()); onUnlocked() } }}
          disabled={!val.trim()}
          className="px-3 py-2 rounded-lg text-[11px] font-semibold bg-[#6366f1] hover:bg-[#5558e8] text-white transition disabled:opacity-40"
        >
          Use
        </button>
      </div>
      <Link href="/settings/api-keys" className="inline-flex items-center gap-1 text-[10px] text-[#818cf8]/70 hover:text-cyan-300 transition-colors">
        Manage AI Providers <ExternalLink size={9} />
      </Link>
    </div>
  )
}

// ── Collapsible action card shell ───────────────────────────────
function ActionCard({
  icon: Icon, title, description, children,
}: { icon: React.ElementType; title: string; description: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-xl border border-[#1e1e1e] bg-[#0d0d0d] overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 p-3 text-left hover:bg-[#141414] transition"
      >
        <div className="w-8 h-8 rounded-lg bg-[#6366f1]/10 border border-[#6366f1]/20 flex items-center justify-center flex-shrink-0">
          <Icon size={14} className="text-[#a5b4fc]" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-white/80">{title}</p>
          <p className="text-[10px] text-white/30 truncate">{description}</p>
        </div>
        <ChevronDown size={13} className={cn('text-white/25 transition-transform flex-shrink-0', open && 'rotate-180')} />
      </button>
      {open && <div className="px-3 pb-3 space-y-2.5 tb2-rise">{children}</div>}
    </div>
  )
}

function MarkdownResult({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="rounded-lg border border-[#1e1e1e] bg-[#111]">
      <div className="flex items-center justify-end px-2 py-1.5 border-b border-[#1e1e1e]">
        <button
          onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500) }}
          className="flex items-center gap-1 text-[10px] text-white/35 hover:text-white/70 transition px-1.5 py-0.5"
        >
          {copied ? <Check size={10} className="text-emerald-400" /> : <Copy size={10} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <div className="chat-message p-3 max-h-64 overflow-y-auto text-[11px] text-white/70">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      </div>
    </div>
  )
}

export function ThunderGuideAITools() {
  const nodes = useWorkflowStore(s => s.nodes)
  const edges = useWorkflowStore(s => s.edges)
  const workflowName = useWorkflowStore(s => s.workflowName)
  const addNode = useWorkflowStore(s => s.addNode)
  const selectedNodeId = useWorkflowStore(s => s.selectedNodeId)

  const { data: providers = [] } = useQuery({ queryKey: ['providers'], queryFn: settingsApi.listProviders })
  const { data: keys = [] } = useQuery({ queryKey: ['api-keys'], queryFn: settingsApi.listKeys })

  const validConfigured = useMemo(() => {
    const byProvider = Object.fromEntries((keys as UserAPIKey[]).map(k => [k.provider, k]))
    return SUPPORTED.filter(p => {
      const k = byProvider[p]
      const providerMeta = (providers as AIProvider[]).find(pr => pr.id === p)
      return !!k && (k.is_valid || providerMeta?.configured)
    })
  }, [keys, providers])

  const [selectedProvider, setSelectedProvider] = useState<AIProviderId | null>(null)
  const activeProvider = selectedProvider ?? validConfigured[0] ?? null
  const [sessionUnlockedTick, setSessionUnlockedTick] = useState(0)
  const hasSessionKey = activeProvider ? !!getSessionKey(activeProvider) : false

  if (validConfigured.length === 0) return <LockedAI />

  const args = activeProvider
    ? { provider: activeProvider, apiKey: getSessionKey(activeProvider) || '' }
    : null

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-[#1e1e1e] space-y-2.5">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold text-white/40 uppercase tracking-wider">Provider</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {SUPPORTED.map(p => {
            const configured = validConfigured.includes(p)
            return (
              <button
                key={p}
                disabled={!configured}
                onClick={() => setSelectedProvider(p)}
                className={cn(
                  'text-[10px] px-2.5 py-1.5 rounded-lg border transition font-medium',
                  activeProvider === p
                    ? 'bg-[#6366f1]/20 border-[#6366f1]/40 text-[#a5b4fc]'
                    : configured
                    ? 'bg-white/[0.03] border-white/10 text-white/50 hover:text-white/80 hover:border-white/20'
                    : 'bg-white/[0.02] border-white/5 text-white/15 cursor-not-allowed'
                )}
              >
                {PROVIDER_LABELS[p]}
              </button>
            )
          })}
        </div>
        {activeProvider && !hasSessionKey && (
          <SessionKeyGate provider={activeProvider} onUnlocked={() => setSessionUnlockedTick(t => t + 1)} />
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
        {activeProvider && hasSessionKey && args && (
          <>
            <BuildFromPromptCard args={args} onInsert={(gw) => insertGeneratedWorkflow(gw, nodes, addNode)} />
            <SuggestNodesCard args={args} nodes={nodes} edges={edges} focusNodeId={selectedNodeId} onAdd={(t) => addNode(createNode(t, nextPosition(nodes)))} />
            <ExplainWorkflowCard args={args} nodes={nodes} edges={edges} />
            <GenerateDocsCard args={args} nodes={nodes} edges={edges} workflowName={workflowName} />
            <AdvancedOptimizeCard args={args} nodes={nodes} edges={edges} />
          </>
        )}
        {activeProvider && !hasSessionKey && (
          <p className="text-center text-[11px] text-white/20 py-6">
            Enter your session key above to run AI actions.
          </p>
        )}
      </div>
    </div>
  )
}

function nextPosition(nodes: { position: { x: number; y: number } }[]) {
  const maxY = nodes.length ? Math.max(...nodes.map(n => n.position.y)) : 0
  return { x: 400, y: maxY + 180 }
}

// Balanced layered layout: depth = distance from a start node, computed via
// BFS over the generated (index-based) edges. Nodes at the same depth are
// spread out evenly on the X axis so large graphs (including 100+ node
// workflows) stay readable instead of stacking into a thin zig-zag column.
function computeLayeredPositions(
  nodeCount: number,
  edges: GeneratedWorkflow['edges'],
  startIndices: number[]
): { x: number; y: number }[] {
  const NODE_W = 260
  const ROW_H = 170

  const outBy = new Map<number, number[]>()
  for (let i = 0; i < nodeCount; i++) outBy.set(i, [])
  edges.forEach(e => {
    if (outBy.has(e.from)) outBy.get(e.from)!.push(e.to)
  })

  const depth = new Array<number>(nodeCount).fill(-1)
  const queue: number[] = []
  const roots = startIndices.length ? startIndices : [0]
  roots.forEach(r => { if (depth[r] === -1) { depth[r] = 0; queue.push(r) } })

  while (queue.length) {
    const cur = queue.shift()!
    for (const next of outBy.get(cur) ?? []) {
      if (depth[next] === -1) {
        depth[next] = depth[cur] + 1
        queue.push(next)
      }
    }
  }
  // Any node unreached by BFS (shouldn't happen post-validation, but stay
  // defensive) still needs a row — place it just past the deepest level.
  const maxKnownDepth = Math.max(0, ...depth.filter(d => d !== -1))
  for (let i = 0; i < nodeCount; i++) {
    if (depth[i] === -1) depth[i] = maxKnownDepth + 1
  }

  const rows = new Map<number, number[]>()
  for (let i = 0; i < nodeCount; i++) {
    const d = depth[i]
    if (!rows.has(d)) rows.set(d, [])
    rows.get(d)!.push(i)
  }

  const positions = new Array<{ x: number; y: number }>(nodeCount)
  rows.forEach((indices, d) => {
    const rowWidth = (indices.length - 1) * NODE_W
    const startX = 500 - rowWidth / 2
    indices.forEach((nodeIdx, col) => {
      positions[nodeIdx] = { x: startX + col * NODE_W, y: d * ROW_H }
    })
  })
  return positions
}

function insertGeneratedWorkflow(
  gw: GeneratedWorkflow,
  existingNodes: { position: { x: number; y: number } }[],
  addNode: (n: ReturnType<typeof createNode>) => void
) {
  // DEFENSIVE VALIDATION: same guard used at the pending-import boundary
  // (usePendingAIImport.ts). buildWorkflowFromPrompt already guarantees a
  // valid shape today, but this is the last line of defense between any
  // future upstream regression and a live crash reading .reduce/.forEach
  // off an undefined nodes/edges array — never assume the shape here.
  if (!isValidGeneratedWorkflow(gw)) {
    console.error('Refused to insert invalid AI-generated workflow into canvas:', gw)
    return
  }
  const baseY = existingNodes.length ? Math.max(...existingNodes.map(n => n.position.y)) + 180 : 100
  const startIndices = gw.nodes.reduce<number[]>((acc, n, i) => (n.type === 'start' ? [...acc, i] : acc), [])
  const layout = computeLayeredPositions(gw.nodes.length, gw.edges, startIndices)

  const idByIndex: string[] = []
  gw.nodes.forEach((n, i) => {
    const pos = layout[i] ?? { x: 400, y: 0 }
    const node = createNode(n.type, { x: pos.x, y: baseY + pos.y }, {
      label: n.label,
      ...(n.data as Record<string, unknown>),
    })
    idByIndex[i] = node.id
    addNode(node)
  })

  // Edges are appended directly to the store to avoid extra undo snapshots per edge.
  // Multiple Choice sources carry a sourceHandle of `choice_<index>` so each option
  // renders and connects from its own port on the node — never collapsing every
  // option onto a single shared connection.
  const store = useWorkflowStore
  const newEdges = gw.edges
    .filter(e => idByIndex[e.from] && idByIndex[e.to])
    .map(e => {
      const fromNode = gw.nodes[e.from]
      const sourceHandle = fromNode?.type === 'multiple_choice' && typeof e.choiceIndex === 'number'
        ? `choice_${e.choiceIndex}`
        : undefined
      return {
        id: `tg_edge_${idByIndex[e.from]}_${idByIndex[e.to]}_${e.choiceIndex ?? ''}`,
        source: idByIndex[e.from],
        target: idByIndex[e.to],
        ...(sourceHandle ? { sourceHandle } : {}),
        type: 'thunder',
        data: {},
      }
    })
  store.setState(s => ({ edges: [...s.edges, ...newEdges], isDirty: true }))
}

// ── Build Workflow from Prompt ─────────────────────────────────
function BuildFromPromptCard({ args, onInsert }: {
  args: { provider: AIProviderId; apiKey: string }
  onInsert: (gw: GeneratedWorkflow) => void
}) {
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<GeneratedWorkflow | null>(null)
  const [stage, setStage] = useState<GenerationStage | null>(null)

  const run = async () => {
    if (!prompt.trim()) return
    setLoading(true); setError(null); setResult(null); setStage(null)
    try {
      const gw = await buildWorkflowFromPrompt(args, prompt.trim(), setStage)
      setResult(gw)
    } catch (e) {
      setError(getErrorMessage(e, 'Could not generate a workflow.'))
    } finally {
      setLoading(false)
      setStage(null)
    }
  }

  return (
    <ActionCard icon={Wand2} title="Build Workflow from Prompt" description="Generate nodes & connections from a description">
      <textarea
        value={prompt}
        onChange={e => setPrompt(e.target.value)}
        placeholder="e.g. A support bot that greets the user, asks if they need billing or technical help, then routes to an AI agent for each"
        rows={3}
        className="w-full bg-[#1a1a1a] text-xs text-white border border-[#2a2a2a] rounded-lg px-3 py-2 outline-none focus:border-[#6366f1]/50 transition resize-none placeholder-white/20"
      />
      <button
        onClick={run}
        disabled={loading || !prompt.trim()}
        className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg text-[11px] font-semibold bg-[#6366f1] hover:bg-[#5558e8] text-white transition disabled:opacity-40"
      >
        {loading ? <Loader2 size={11} className="animate-spin" /> : <Wand2 size={11} />}
        Generate
      </button>
      {loading && <ThunderGuideProgress stage={stage} />}
      {error && (
        <div className="flex items-start gap-2 px-2.5 py-2 rounded-lg bg-red-500/10 border border-red-500/20">
          <AlertCircle size={11} className="text-red-400 mt-0.5 flex-shrink-0" />
          <p className="text-[10px] text-red-300 leading-snug">{error}</p>
        </div>
      )}
      {result && (
        <div className="p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20 space-y-2">
          <p className="text-[11px] text-emerald-300">
            Generated {result.nodes.length} nodes and {result.edges.length} connections.
          </p>
          <button
            onClick={() => { onInsert(result); setResult(null); setPrompt('') }}
            className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-[11px] font-semibold bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-300 transition"
          >
            <Plus size={11} /> Insert into canvas
          </button>
        </div>
      )}
    </ActionCard>
  )
}

// ── AI Node Suggestions ─────────────────────────────────────────
function SuggestNodesCard({ args, nodes, edges, focusNodeId, onAdd }: {
  args: { provider: AIProviderId; apiKey: string }
  nodes: Parameters<typeof suggestNextNodes>[1]
  edges: Parameters<typeof suggestNextNodes>[2]
  focusNodeId: string | null
  onAdd: (type: NodeType) => void
}) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [suggestions, setSuggestions] = useState<NodeSuggestion[] | null>(null)

  const run = async () => {
    setLoading(true); setError(null)
    try {
      setSuggestions(await suggestNextNodes(args, nodes, edges, focusNodeId))
    } catch (e) {
      setError(getErrorMessage(e, 'Could not fetch suggestions.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <ActionCard icon={Lightbulb} title="AI Node Suggestions" description="Get suggested next nodes for your flow">
      <button
        onClick={run}
        disabled={loading}
        className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg text-[11px] font-semibold bg-[#6366f1] hover:bg-[#5558e8] text-white transition disabled:opacity-40"
      >
        {loading ? <Loader2 size={11} className="animate-spin" /> : <Lightbulb size={11} />}
        Suggest Nodes
      </button>
      {error && <p className="text-[10px] text-red-300">{error}</p>}
      {suggestions?.map((s, i) => (
        <div key={i} className="flex items-center gap-2 p-2 rounded-lg border border-[#1e1e1e] bg-[#111]">
          <div className="flex-1 min-w-0">
            <p className="text-[11px] font-semibold text-white/70 capitalize">{s.type.replace('_', ' ')}</p>
            <p className="text-[10px] text-white/30 leading-snug">{s.reason}</p>
          </div>
          <button onClick={() => onAdd(s.type)} className="p-1.5 text-[#818cf8] hover:text-cyan-300 transition flex-shrink-0">
            <Plus size={13} />
          </button>
        </div>
      ))}
    </ActionCard>
  )
}

// ── Explain Workflow ─────────────────────────────────────────────
function ExplainWorkflowCard({ args, nodes, edges }: {
  args: { provider: AIProviderId; apiKey: string }
  nodes: Parameters<typeof explainWorkflow>[1]
  edges: Parameters<typeof explainWorkflow>[2]
}) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [text, setText] = useState<string | null>(null)

  const run = async () => {
    setLoading(true); setError(null)
    try { setText(await explainWorkflow(args, nodes, edges)) }
    catch (e) { setError(getErrorMessage(e, 'Could not explain this workflow.')) }
    finally { setLoading(false) }
  }

  return (
    <ActionCard icon={MessageSquareText} title="Explain Workflow" description="Plain-English walkthrough of your flow">
      <button
        onClick={run}
        disabled={loading}
        className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg text-[11px] font-semibold bg-[#6366f1] hover:bg-[#5558e8] text-white transition disabled:opacity-40"
      >
        {loading ? <Loader2 size={11} className="animate-spin" /> : <MessageSquareText size={11} />}
        Explain
      </button>
      {error && <p className="text-[10px] text-red-300">{error}</p>}
      {text && <MarkdownResult text={text} />}
    </ActionCard>
  )
}

// ── Generate Documentation ────────────────────────────────────────
function GenerateDocsCard({ args, nodes, edges, workflowName }: {
  args: { provider: AIProviderId; apiKey: string }
  nodes: Parameters<typeof generateDocumentation>[1]
  edges: Parameters<typeof generateDocumentation>[2]
  workflowName: string
}) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [text, setText] = useState<string | null>(null)

  const run = async () => {
    setLoading(true); setError(null)
    try { setText(await generateDocumentation(args, nodes, edges, workflowName)) }
    catch (e) { setError(getErrorMessage(e, 'Could not generate documentation.')) }
    finally { setLoading(false) }
  }

  const download = () => {
    if (!text) return
    const blob = new Blob([text], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${workflowName || 'workflow'}-docs.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <ActionCard icon={FileText} title="Generate Documentation" description="Export a markdown spec of this workflow">
      <button
        onClick={run}
        disabled={loading}
        className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg text-[11px] font-semibold bg-[#6366f1] hover:bg-[#5558e8] text-white transition disabled:opacity-40"
      >
        {loading ? <Loader2 size={11} className="animate-spin" /> : <FileText size={11} />}
        Generate Docs
      </button>
      {error && <p className="text-[10px] text-red-300">{error}</p>}
      {text && (
        <>
          <MarkdownResult text={text} />
          <button
            onClick={download}
            className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-[11px] font-semibold border border-white/10 text-white/60 hover:text-white/90 hover:border-white/20 transition"
          >
            Download .md
          </button>
        </>
      )}
    </ActionCard>
  )
}

// ── Advanced Optimization ──────────────────────────────────────────
function AdvancedOptimizeCard({ args, nodes, edges }: {
  args: { provider: AIProviderId; apiKey: string }
  nodes: Parameters<typeof advancedOptimize>[1]
  edges: Parameters<typeof advancedOptimize>[2]
}) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [suggestions, setSuggestions] = useState<AdvancedSuggestion[] | null>(null)

  const run = async () => {
    setLoading(true); setError(null)
    try { setSuggestions(await advancedOptimize(args, nodes, edges)) }
    catch (e) { setError(getErrorMessage(e, 'Could not analyze this workflow.')) }
    finally { setLoading(false) }
  }

  return (
    <ActionCard icon={Gauge} title="Advanced Optimization" description="Deeper AI-powered UX & design review">
      <button
        onClick={run}
        disabled={loading}
        className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg text-[11px] font-semibold bg-[#6366f1] hover:bg-[#5558e8] text-white transition disabled:opacity-40"
      >
        {loading ? <Loader2 size={11} className="animate-spin" /> : <Gauge size={11} />}
        Analyze
      </button>
      {error && <p className="text-[10px] text-red-300">{error}</p>}
      {suggestions?.map((s, i) => (
        <div key={i} className="p-2.5 rounded-lg border border-[#1e1e1e] bg-[#111] space-y-1">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] font-semibold text-white/75">{s.title}</p>
            <span className={cn('text-[9px] px-1.5 py-0.5 rounded-full border font-semibold uppercase flex-shrink-0', impactTone(s.impact))}>
              {s.impact}
            </span>
          </div>
          <p className="text-[10px] text-white/35 leading-snug">{s.detail}</p>
        </div>
      ))}
    </ActionCard>
  )
}
