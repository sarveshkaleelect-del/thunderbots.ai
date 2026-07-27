'use client'
import { useMemo, useState } from 'react'
import {
  Compass, ShieldCheck, Sparkles, RefreshCw, ChevronDown,
  AlertOctagon, AlertTriangle, Info, Network, Wrench,
} from 'lucide-react'
import { useWorkflowStore } from '@/store/workflowStore'
import { cn } from '@/lib/utils/cn'
import {
  validateWorkflow, computeWorkflowStats, computeHealthScore, basicOptimize,
} from '@/lib/thunderguide/analyzer'
import type { WorkflowIssue } from '@/lib/thunderguide/types'
import { ThunderGuideAITools } from './ThunderGuideAITools'

type Tab = 'free' | 'ai'

const SEVERITY_META: Record<WorkflowIssue['severity'], { icon: React.ElementType; cls: string; label: string }> = {
  critical: { icon: AlertOctagon, cls: 'text-red-400 border-red-500/25 bg-red-500/10', label: 'Critical' },
  warning: { icon: AlertTriangle, cls: 'text-amber-400 border-amber-500/25 bg-amber-500/10', label: 'Warning' },
  info: { icon: Info, cls: 'text-cyan-300 border-cyan-500/25 bg-cyan-500/10', label: 'Info' },
}

function gradeColor(grade: string) {
  if (grade === 'A') return '#22c55e'
  if (grade === 'B') return '#84cc16'
  if (grade === 'C') return '#f59e0b'
  if (grade === 'D') return '#f97316'
  return '#ef4444'
}

function HealthGauge({ score, grade }: { score: number; grade: string }) {
  const color = gradeColor(grade)
  const circumference = 2 * Math.PI * 26
  const offset = circumference - (score / 100) * circumference
  return (
    <div className="relative w-[68px] h-[68px] flex-shrink-0">
      <svg width="68" height="68" viewBox="0 0 68 68" className="-rotate-90">
        <circle cx="34" cy="34" r="26" fill="none" stroke="#1e1e1e" strokeWidth="6" />
        <circle
          cx="34" cy="34" r="26" fill="none" stroke={color} strokeWidth="6" strokeLinecap="round"
          strokeDasharray={circumference} strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-base font-bold text-white leading-none">{score}</span>
        <span className="text-[9px] text-white/30 mt-0.5">/ 100</span>
      </div>
    </div>
  )
}

function IssueGroup({ issues }: { issues: WorkflowIssue[] }) {
  const [open, setOpen] = useState(true)
  if (issues.length === 0) return null
  return (
    <div className="rounded-xl border border-[#1e1e1e] bg-[#0d0d0d] overflow-hidden">
      <button onClick={() => setOpen(o => !o)} className="w-full flex items-center justify-between p-3 hover:bg-[#141414] transition">
        <span className="text-xs font-semibold text-white/70">Issues Found ({issues.length})</span>
        <ChevronDown size={13} className={cn('text-white/25 transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-2 tb2-rise">
          {issues.map(issue => {
            const meta = SEVERITY_META[issue.severity]
            const Icon = meta.icon
            return (
              <div key={issue.id} className={cn('flex items-start gap-2.5 p-2.5 rounded-lg border', meta.cls)}>
                <Icon size={13} className="mt-0.5 flex-shrink-0" />
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold leading-snug">{issue.title}</p>
                  <p className="text-[10px] opacity-70 leading-snug mt-0.5">{issue.description}</p>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-[#111] border border-[#1e1e1e] rounded-lg p-2.5 text-center">
      <p className="text-base font-bold text-white">{value}</p>
      <p className="text-[9px] text-white/30 mt-0.5 leading-tight">{label}</p>
    </div>
  )
}

function FreeTools() {
  const nodes = useWorkflowStore(s => s.nodes)
  const edges = useWorkflowStore(s => s.edges)
  const [spinning, setSpinning] = useState(false)
  const [, setTick] = useState(0)

  // PERF FIX (v107): these are pure functions of nodes/edges alone — `tick`
  // was in the dependency arrays purely so clicking "Re-run" felt like it
  // did something, but since the output is fully determined by nodes/edges,
  // recomputing on an unchanged tick just re-derives the identical result.
  // Dropping it from the deps means "Re-run" on an unchanged workflow now
  // correctly skips the recompute instead of redoing identical work.
  const validation = useMemo(() => validateWorkflow(nodes, edges), [nodes, edges])
  const stats = useMemo(() => computeWorkflowStats(nodes, edges), [nodes, edges])
  const health = useMemo(() => computeHealthScore(nodes, edges), [nodes, edges])
  const optimizations = useMemo(() => basicOptimize(nodes, edges), [nodes, edges])

  const rerun = () => {
    setSpinning(true)
    setTick(t => t + 1)
    setTimeout(() => setSpinning(false), 400)
  }

  return (
    <div className="flex-1 overflow-y-auto p-3 space-y-3">
      {/* Health Score */}
      <div className="rounded-xl border border-[#1e1e1e] bg-[#0d0d0d] p-3.5 flex items-center gap-3.5">
        <HealthGauge score={health.score} grade={health.grade} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-xs font-semibold text-white/80">Workflow Health</p>
            <span
              className="text-[9px] font-bold px-1.5 py-0.5 rounded-full border"
              style={{ color: gradeColor(health.grade), borderColor: `${gradeColor(health.grade)}40`, background: `${gradeColor(health.grade)}15` }}
            >
              Grade {health.grade}
            </span>
          </div>
          <p className="text-[10px] text-white/30 mt-1 leading-snug">
            {validation.valid ? 'No critical issues found.' : 'Critical issues need attention.'}
          </p>
          <button
            onClick={rerun}
            className="mt-2 flex items-center gap-1.5 text-[10px] text-[#818cf8] hover:text-cyan-300 transition"
          >
            <RefreshCw size={10} className={cn(spinning && 'animate-spin')} /> Re-analyze
          </button>
        </div>
      </div>

      {/* Validate Workflow status strip */}
      <div className={cn(
        'flex items-center gap-2.5 px-3 py-2.5 rounded-xl border text-[11px] font-medium',
        validation.valid
          ? 'bg-emerald-500/8 border-emerald-500/20 text-emerald-300'
          : 'bg-red-500/8 border-red-500/20 text-red-300'
      )}>
        <ShieldCheck size={13} className="flex-shrink-0" />
        {validation.valid ? 'Workflow passes validation' : 'Workflow has validation errors'}
      </div>

      {/* Statistics */}
      <div className="rounded-xl border border-[#1e1e1e] bg-[#0d0d0d] p-3">
        <div className="flex items-center gap-2 mb-2.5">
          <Network size={12} className="text-white/40" />
          <span className="text-[10px] font-semibold text-white/40 uppercase tracking-wider">Statistics</span>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <StatTile label="Nodes" value={stats.totalNodes} />
          <StatTile label="Connections" value={stats.totalEdges} />
          <StatTile label="Max Depth" value={stats.maxDepth} />
          <StatTile label="Branch Points" value={stats.branchingNodes} />
          <StatTile label="AI Agents" value={stats.aiAgentNodes} />
          <StatTile label="Unreachable" value={stats.unreachableNodes} />
        </div>
      </div>

      {/* Issues */}
      <IssueGroup issues={validation.issues} />

      {/* Basic Optimization */}
      <div className="rounded-xl border border-[#1e1e1e] bg-[#0d0d0d] p-3">
        <div className="flex items-center gap-2 mb-2.5">
          <Wrench size={12} className="text-white/40" />
          <span className="text-[10px] font-semibold text-white/40 uppercase tracking-wider">
            Basic Optimization ({optimizations.length})
          </span>
        </div>
        {optimizations.length === 0 ? (
          <p className="text-[11px] text-white/25 text-center py-3">No optimization suggestions — looking good.</p>
        ) : (
          <div className="space-y-2">
            {optimizations.map(s => (
              <div key={s.id} className="p-2.5 rounded-lg border border-[#1e1e1e] bg-[#111]">
                <p className="text-[11px] font-semibold text-white/70">{s.title}</p>
                <p className="text-[10px] text-white/30 leading-snug mt-0.5">{s.detail}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export function ThunderGuidePanel() {
  const [tab, setTab] = useState<Tab>('free')

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2.5 px-4 py-3 border-b border-[#1e1e1e] flex-shrink-0">
        <div className="w-7 h-7 rounded-lg bg-[#6366f1]/15 border border-[#6366f1]/25 flex items-center justify-center">
          <Compass size={13} className="text-[#a5b4fc]" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-bold text-white/85 leading-none">ThunderGuide</p>
          <p className="text-[9px] text-white/25 mt-0.5">Workflow Assistant</p>
        </div>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-1 mx-3 mt-3 p-0.5 bg-[#111] rounded-lg border border-[#1e1e1e] flex-shrink-0">
        <button
          onClick={() => setTab('free')}
          className={cn(
            'flex-1 flex items-center justify-center gap-1.5 text-[11px] font-semibold py-1.5 rounded-md transition',
            tab === 'free' ? 'bg-[#6366f1]/20 text-[#a5b4fc]' : 'text-white/30 hover:text-white/60'
          )}
        >
          <ShieldCheck size={11} /> Free Tools
        </button>
        <button
          onClick={() => setTab('ai')}
          className={cn(
            'flex-1 flex items-center justify-center gap-1.5 text-[11px] font-semibold py-1.5 rounded-md transition',
            tab === 'ai' ? 'bg-[#6366f1]/20 text-[#a5b4fc]' : 'text-white/30 hover:text-white/60'
          )}
        >
          <Sparkles size={11} /> AI Tools
        </button>
      </div>

      {tab === 'free' ? <FreeTools /> : <ThunderGuideAITools />}
    </div>
  )
}
