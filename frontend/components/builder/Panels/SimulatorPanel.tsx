'use client'
// ============================================================
// AI Conversation Simulator panel
//
// Runs ONLY when the user clicks "Run AI Simulation" — never
// automatically. The heavy analysis module (lib/simulator/engine)
// is dynamically imported on click, so it costs nothing until used
// and never affects Builder load time, canvas rendering, or chatbot
// runtime performance. The latest result is cached (by the engine
// module) until the workflow's nodes/edges actually change.
// ============================================================
import { useCallback, useEffect, useState } from 'react'
import {
  Sparkles, Loader2, Check, Circle, AlertTriangle, XCircle, CheckCircle2,
  ChevronDown, ListChecks, GitBranch as GitBranchIcon,
} from 'lucide-react'
import { useWorkflowStore } from '@/store/workflowStore'
import { cn } from '@/lib/utils/cn'
import { SIMULATION_STAGE_ORDER, SIMULATION_STAGE_LABELS, type SimulationStage, type SimulationReport } from '@/lib/simulator/types'

// ============================================================
// ROOT CAUSE (Issue 1 — "Loading chunk ... simulator_engine_ts failed
// (error: http://localhost:3000/_next/undefined)"):
//
// The previous code called `import('@/lib/simulator/engine')` directly
// inside a `useMemo` callback. useMemo runs during the RENDER phase, not
// after commit — so that dynamic import fired on every render pass,
// including React 18 StrictMode's intentional double-render in dev and,
// critically, during Fast Refresh: when the dev server recompiles this
// module, Next/webpack swaps the client chunk registry out from under any
// import() call that was already in flight from a stale render. The old
// promise then resolves against a chunk id the new registry doesn't
// recognize, and webpack's runtime builds the script src by concatenating
// its public path with a chunk-id lookup that comes back `undefined` —
// exactly the broken "/_next/undefined" URL in the error. The same race
// can happen on a plain browser refresh if the render fires before the
// module graph has settled.
//
// Fix: only ever import the engine from inside a `useEffect` (i.e. after
// commit, never during render), with an `ignore` flag so a stale response
// from a superseded effect run is never applied, and a small retry loop so
// a transient ChunkLoadError (slow network, chunk requested mid-redeploy)
// self-heals instead of surfacing to the user. A stable webpackChunkName
// keeps the chunk's filename/id consistent across dev and production
// builds instead of relying on webpack's auto-derived name.
// ============================================================
type SimulatorEngineModule = typeof import('@/lib/simulator/engine')

function loadSimulatorEngineChunk(retriesLeft = 2): Promise<SimulatorEngineModule> {
  return import(
    /* webpackChunkName: "simulator_engine" */
    '@/lib/simulator/engine'
  ).catch((err: unknown) => {
    const isChunkError = err instanceof Error && /Loading chunk|ChunkLoadError/i.test(err.message + err.name)
    if (isChunkError && retriesLeft > 0) {
      // A previous chunk request can fail transiently right after a new
      // deploy/dev-recompile swaps the chunk map. Wait briefly and retry
      // with a fresh import() against the now-current registry, rather
      // than propagating a spurious failure to the user.
      return new Promise<SimulatorEngineModule>((resolve, reject) => {
        setTimeout(() => {
          loadSimulatorEngineChunk(retriesLeft - 1).then(resolve, reject)
        }, 300)
      })
    }
    throw err
  })
}

function StageProgress({ stage }: { stage: SimulationStage | null }) {
  if (!stage) return null
  const currentIndex = SIMULATION_STAGE_ORDER.indexOf(stage)
  return (
    <div className="rounded-lg border border-[#2a2a2a] bg-[#111] p-2.5 space-y-1.5">
      {SIMULATION_STAGE_ORDER.map((s, i) => {
        const done = i < currentIndex
        const active = i === currentIndex
        return (
          <div key={s} className="flex items-center gap-2">
            {done && <Check size={11} className="text-emerald-400 flex-shrink-0" />}
            {active && <Loader2 size={11} className="text-[#a5b4fc] animate-spin flex-shrink-0" />}
            {!done && !active && <Circle size={6} className="text-white/15 flex-shrink-0 mx-[2.5px]" />}
            <span className={cn(
              'text-[10.5px] leading-none transition-colors',
              done && 'text-white/35',
              active && 'text-white/85 font-medium',
              !done && !active && 'text-white/20'
            )}>
              {SIMULATION_STAGE_LABELS[s]}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function MetricCard({ label, value, tone }: { label: string; value: string; tone?: 'good' | 'warn' | 'bad' }) {
  const color = tone === 'good' ? 'text-emerald-400' : tone === 'bad' ? 'text-red-400' : tone === 'warn' ? 'text-amber-400' : 'text-white/85'
  return (
    <div className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2.5">
      <p className="text-[9px] uppercase tracking-wider text-white/30 font-semibold mb-0.5">{label}</p>
      <p className={cn('text-base font-semibold', color)}>{value}</p>
    </div>
  )
}

function Section({ title, icon, count, children, defaultOpen }: {
  title: string; icon: React.ReactNode; count: number; children: React.ReactNode; defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(!!defaultOpen)
  if (count === 0) return null
  return (
    <div className="border-t border-[#1a1a1a] pt-2.5">
      <button onClick={() => setOpen(o => !o)} className="w-full flex items-center justify-between text-left">
        <span className="flex items-center gap-1.5 text-[11px] font-semibold text-white/60">
          {icon} {title}
          <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-white/40">{count}</span>
        </span>
        <ChevronDown size={12} className={cn('text-white/30 transition-transform', open && 'rotate-180')} />
      </button>
      {open && <div className="mt-2 space-y-1.5">{children}</div>}
    </div>
  )
}

/** Turns whatever the simulator engine actually threw into an accurate,
 * specific message — instead of one hardcoded generic string regardless
 * of cause. Falls back to the real error's own message so nothing is
 * ever silently swallowed. */
function describeSimulationError(err: unknown): string {
  const message = err instanceof Error ? err.message : String(err)

  if (err instanceof Error && err.name === 'SimulationError') return message
  if (/call stack/i.test(message)) {
    return 'This workflow is too large or too deeply branched for the simulator to trace safely. Simplify branching or add exit conditions and try again.'
  }
  if (/circular|unserializable/i.test(message)) {
    return "One of your nodes has data the simulator can't read (likely a corrupted field). Check recently edited nodes and try again."
  }
  return message ? `Simulation failed: ${message}` : 'Simulation failed to complete. Please try again.'
}

const READINESS_STYLE: Record<SimulationReport['deploymentReadiness'], { label: string; color: string; Icon: typeof CheckCircle2 }> = {
  ready:            { label: 'Ready to Deploy',        color: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10', Icon: CheckCircle2 },
  needs_attention:  { label: 'Needs Attention',        color: 'text-amber-400 border-amber-500/30 bg-amber-500/10',       Icon: AlertTriangle },
  not_ready:        { label: 'Not Ready',              color: 'text-red-400 border-red-500/30 bg-red-500/10',            Icon: XCircle },
}

export function SimulatorPanel() {
  const workflowId = useWorkflowStore(s => s.workflowId)
  const nodes = useWorkflowStore(s => s.nodes)
  const edges = useWorkflowStore(s => s.edges)

  const [running, setRunning] = useState(false)
  const [stage, setStage] = useState<SimulationStage | null>(null)
  const [report, setReport] = useState<SimulationReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [fromCache, setFromCache] = useState(false)

  // Show a cached result (if the workflow hasn't changed since the last run)
  // without doing any work — purely a read, never triggers a run. Runs in an
  // effect (after commit) rather than during render — see the root-cause
  // note above loadSimulatorEngineChunk for why a render-phase import() here
  // was the actual cause of the chunk-loading failures.
  useEffect(() => {
    if (report || running) return
    let ignore = false
    loadSimulatorEngineChunk().then(mod => {
      if (ignore) return
      const cached = mod.getCachedReport(workflowId, nodes, edges)
      if (cached) { setReport(cached); setFromCache(true) }
    }).catch(() => { /* best-effort cache read only */ })
    return () => { ignore = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId])

  const runSimulation = useCallback(async () => {
    setRunning(true)
    setError(null)
    setFromCache(false)
    setStage('understanding')
    try {
      const mod = await loadSimulatorEngineChunk()
      const result = await mod.runSimulation(workflowId, nodes, edges, setStage)
      mod.setCachedReport(workflowId, nodes, edges, result)
      setReport(result)
    } catch (err) {
      console.error('AI Conversation Simulator failed:', err)
      setError(describeSimulationError(err))
    } finally {
      setRunning(false)
      setStage(null)
    }
  }, [workflowId, nodes, edges])

  const readiness = report ? READINESS_STYLE[report.deploymentReadiness] : null

  return (
    <div className="flex flex-col h-full bg-[#090909]">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[#1a1a1a] flex-shrink-0">
        <Sparkles size={13} className="text-[#a5b4fc]" />
        <span className="text-xs font-semibold text-white/60">AI Conversation Simulator</span>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <p className="text-[11px] text-white/35 leading-relaxed">
          Simulates conversations through this workflow and checks coverage, branches,
          and dead ends before you deploy. Runs only when you click below — never automatically.
        </p>

        <button
          onClick={runSimulation}
          disabled={running || !nodes.length}
          className="w-full flex items-center justify-center gap-2 text-[12px] font-medium px-3 py-2.5 rounded-xl
                     bg-gradient-to-r from-[#6366f1] to-[#8b5cf6] hover:from-[#5558e8] hover:to-[#7c4fe0]
                     disabled:opacity-40 disabled:cursor-not-allowed text-white transition shadow-lg shadow-[#6366f1]/10"
        >
          {running ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
          {running ? 'Running Simulation…' : '✨ Run AI Simulation'}
        </button>

        {!nodes.length && (
          <p className="text-[10px] text-white/25 text-center">Add nodes to your workflow first.</p>
        )}

        {running && <StageProgress stage={stage} />}

        {error && (
          <p className="text-[11px] text-red-400/80 bg-red-500/5 border border-red-500/20 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        {report && !running && (
          <div className="space-y-4 tb-anim-fade-up">
            {fromCache && (
              <p className="text-[9.5px] text-white/25 italic">
                Showing cached results from {new Date(report.generatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} — rerun after changing the workflow.
              </p>
            )}

            {readiness && (
              <div className={cn('flex items-center gap-2 rounded-lg border px-3 py-2', readiness.color)}>
                <readiness.Icon size={14} className="flex-shrink-0" />
                <span className="text-[11.5px] font-medium">{report.readinessLabel}</span>
              </div>
            )}

            <div className="grid grid-cols-2 gap-2">
              <MetricCard label="Success Rate" value={`${report.successRate}%`} tone={report.successRate >= 85 ? 'good' : report.successRate >= 50 ? 'warn' : 'bad'} />
              <MetricCard label="Conversations Tested" value={String(report.conversationsTested)} />
              <MetricCard label="Workflow Coverage" value={`${report.workflowCoverage}%`} tone={report.workflowCoverage >= 90 ? 'good' : report.workflowCoverage >= 60 ? 'warn' : 'bad'} />
              <MetricCard label="Unreachable Nodes" value={String(report.unreachableNodes.length)} tone={report.unreachableNodes.length === 0 ? 'good' : 'bad'} />
            </div>

            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-lg bg-[#0d0d0d] border border-[#1e1e1e] py-2">
                <p className="text-[9px] text-white/30 uppercase tracking-wider">End Nodes</p>
                <p className="text-sm font-semibold text-white/80">{report.endNodesCount}</p>
              </div>
              <div className="rounded-lg bg-[#0d0d0d] border border-[#1e1e1e] py-2">
                <p className="text-[9px] text-white/30 uppercase tracking-wider">AI Agent Paths</p>
                <p className="text-sm font-semibold text-white/80">{report.aiAgentNodesCount}</p>
              </div>
              <div className="rounded-lg bg-[#0d0d0d] border border-[#1e1e1e] py-2">
                <p className="text-[9px] text-white/30 uppercase tracking-wider">Choice Branches</p>
                <p className="text-sm font-semibold text-white/80">{report.multipleChoiceNodesCount}</p>
              </div>
            </div>

            <div className="rounded-lg bg-[#0d0d0d] border border-[#1e1e1e] px-3 py-2 flex items-center justify-between">
              <span className="text-[10.5px] text-white/40">Knowledge Base Usage</span>
              <span className={cn('text-[10.5px] font-medium', report.knowledgeBaseUsage.enabled ? 'text-emerald-400' : 'text-white/25')}>
                {report.knowledgeBaseUsage.enabled ? `${report.knowledgeBaseUsage.nodeCount} AI Agent node(s)` : 'Not used'}
              </span>
            </div>

            <Section title="Unreachable Nodes" icon={<AlertTriangle size={11} className="text-amber-400" />} count={report.unreachableNodes.length}>
              {report.unreachableNodes.map(n => (
                <div key={n.id} className="text-[10.5px] text-white/50 px-2.5 py-1.5 rounded-lg bg-white/[0.03] border border-white/5">
                  <span className="text-white/25">{n.type}</span> — {n.label}
                </div>
              ))}
            </Section>

            <Section title="Dead-End Paths" icon={<XCircle size={11} className="text-red-400" />} count={report.deadEndPaths.length}>
              {report.deadEndPaths.map((d, i) => (
                <div key={i} className="text-[10.5px] text-white/50 px-2.5 py-1.5 rounded-lg bg-white/[0.03] border border-white/5">
                  <span className="text-white/70">{d.node.label}</span>
                  <p className="text-white/30 text-[10px] mt-0.5">{d.reason}</p>
                </div>
              ))}
            </Section>

            <Section title="Missing Transitions" icon={<GitBranchIcon size={11} className="text-amber-400" />} count={report.missingTransitions.length}>
              {report.missingTransitions.map((m, i) => (
                <div key={i} className="text-[10.5px] text-white/50 px-2.5 py-1.5 rounded-lg bg-white/[0.03] border border-white/5">
                  <span className="text-white/70">{m.node.label}</span>
                  <p className="text-white/30 text-[10px] mt-0.5">{m.issue}</p>
                </div>
              ))}
            </Section>

            <Section title="Confusing Options" icon={<ListChecks size={11} className="text-amber-400" />} count={report.confusingOptions.length}>
              {report.confusingOptions.map((c, i) => (
                <div key={i} className="text-[10.5px] text-white/50 px-2.5 py-1.5 rounded-lg bg-white/[0.03] border border-white/5">
                  <span className="text-white/70">{c.node.label}</span>
                  <p className="text-white/30 text-[10px] mt-0.5">{c.issue}</p>
                </div>
              ))}
            </Section>

            <Section title="Failed Paths" icon={<XCircle size={11} className="text-red-400" />} count={report.failedPaths.length}>
              {report.failedPaths.map((f, i) => (
                <div key={i} className="text-[10.5px] text-white/50 px-2.5 py-1.5 rounded-lg bg-white/[0.03] border border-white/5">
                  <p className="text-white/60 truncate">{f.path.map(p => p.label).join(' → ') || '(empty path)'}</p>
                  <p className="text-white/30 text-[10px] mt-0.5">{f.reason}</p>
                </div>
              ))}
            </Section>

            <div className="border-t border-[#1a1a1a] pt-2.5">
              <p className="text-[11px] font-semibold text-white/60 mb-1.5 flex items-center gap-1.5">
                <Sparkles size={11} className="text-[#a5b4fc]" /> AI Suggestions
              </p>
              <ul className="space-y-1.5">
                {report.aiSuggestions.map((s, i) => (
                  <li key={i} className="text-[10.5px] text-white/45 leading-relaxed pl-3 relative before:content-['•'] before:absolute before:left-0 before:text-[#818cf8]">
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
