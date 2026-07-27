'use client'
// ============================================================
// ThunderGuide — Final Success Screen
// Lightweight, presentational only. Shown after a chatbot has been
// generated and successfully queued for import — the person confirms by
// clicking "Open Workflow" rather than being auto-navigated away, so they
// get a moment to see what was actually built before the Builder opens.
// ============================================================
import { CheckCircle2, Layers, Languages, Cpu, Gauge, ArrowRight, Timer, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import type { GenerationSummary } from '@/lib/thunderguide/summary'

interface ThunderGuideSuccessScreenProps {
  summary: GenerationSummary
  onOpenWorkflow: () => void
}

function SummaryRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-white/5 last:border-b-0">
      <div className="flex items-center gap-2 text-white/40">
        {icon}
        <span className="text-[11px]">{label}</span>
      </div>
      <span className="text-[11.5px] font-medium text-white/85">{value}</span>
    </div>
  )
}

const CONFIDENCE_COLOR: Record<string, string> = {
  Excellent: 'text-emerald-300',
  High: 'text-emerald-300',
  Good: 'text-amber-300',
  'Review Recommended': 'text-red-300',
}

export function ThunderGuideSuccessScreen({ summary, onOpenWorkflow }: ThunderGuideSuccessScreenProps) {
  const { confidence } = summary

  return (
    <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.04] p-4 space-y-3.5 tb2-rise">
      <div className="flex items-center gap-2">
        <CheckCircle2 size={16} className="text-emerald-400 flex-shrink-0" />
        <p className="text-sm font-semibold text-emerald-300">Chatbot Created Successfully</p>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-white/10 bg-[#111]">
          <Timer size={12} className="text-white/40" />
          <span className="text-[11px] text-white/70">
            Generated in <span className="font-medium text-white/90">{summary.generationTimeLabel}</span>
          </span>
        </div>
        <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-white/10 bg-[#111]">
          <span className="text-[12px] leading-none">{confidence.emoji}</span>
          <span className="text-[11px] text-white/70">
            AI Confidence <span className={`font-semibold ${CONFIDENCE_COLOR[confidence.label]}`}>{confidence.score}%</span>
            <span className="text-white/30"> · {confidence.label}</span>
          </span>
        </div>
      </div>

      {confidence.assumptionsMade && (
        <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20">
          <AlertTriangle size={13} className="text-amber-400 mt-0.5 flex-shrink-0" />
          <p className="text-[11px] text-amber-200/90 leading-snug">
            Some assumptions were made while generating this workflow. Please review the generated
            workflow before deployment.
          </p>
        </div>
      )}

      <div>
        <p className="text-[10px] font-semibold text-white/40 uppercase tracking-wider mb-1">Workflow Summary</p>
        <div className="rounded-lg border border-white/5 bg-[#111] px-3">
          <SummaryRow icon={<Layers size={12} />} label="Industry" value={summary.industry} />
          <SummaryRow icon={<Languages size={12} />} label="Language" value={summary.languageName} />
          <SummaryRow icon={<Cpu size={12} />} label="AI Provider" value={summary.aiProvider} />
          <SummaryRow icon={<Layers size={12} />} label="Total Nodes" value={String(summary.totalNodes)} />
          <SummaryRow icon={<Gauge size={12} />} label="Estimated Complexity" value={summary.complexity} />
          <SummaryRow icon={<CheckCircle2 size={12} />} label="Ready for Editing" value="Yes" />
        </div>
      </div>

      <Button className="w-full" icon={<ArrowRight size={14} />} onClick={onOpenWorkflow}>
        Open Workflow
      </Button>
    </div>
  )
}
