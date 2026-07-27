'use client'
// ============================================================
// ThunderGuide — Progressive Generation indicator
// Lightweight, presentational only. Driven entirely by the `stage` (and
// optional `retry`) props — set from real onStage/onRetry callbacks in
// aiActions.ts — so it always reflects true progress and adds no delay
// or polling of its own. No new dependencies; transitions are plain CSS.
// ============================================================
import { Check, Loader2, Circle, RefreshCw, Wrench } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import {
  GENERATION_STAGE_ORDER, GENERATION_STAGE_LABELS, GENERATION_STAGE_EMOJI, GENERATION_STAGE_PROGRESS,
  type GenerationStage, type GenerationRetryInfo,
} from '@/lib/thunderguide/types'

interface ThunderGuideProgressProps {
  stage: GenerationStage | null
  /** Real 0-100 generation progress. Optional for backward compatibility with
   * existing callers — when omitted, it's derived from the real stage via
   * GENERATION_STAGE_PROGRESS below, never from a fake/timer-based value. */
  progress?: number
  /** Present only while ThunderGuide is auto-repairing and about to retry. */
  retry?: GenerationRetryInfo | null
}

export function ThunderGuideProgress({ stage, progress, retry }: ThunderGuideProgressProps) {
  if (!stage) return null
  const currentIndex = GENERATION_STAGE_ORDER.indexOf(stage)
  const pct = Math.max(0, Math.min(100, Math.round(progress ?? GENERATION_STAGE_PROGRESS[stage])))

  return (
    <div className="rounded-lg border border-[#2a2a2a] bg-[#111] p-2.5 space-y-1.5">
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1 rounded-full bg-white/10 overflow-hidden">
          <div
            className="h-full rounded-full bg-[#6366f1] transition-[width] duration-300 ease-out"
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="text-[10px] tabular-nums text-white/40 flex-shrink-0 w-8 text-right">{pct}%</span>
      </div>

      {GENERATION_STAGE_ORDER.map((s, i) => {
        const done = i < currentIndex
        const active = i === currentIndex
        return (
          <div
            key={s}
            className={cn(
              'flex items-center gap-2 transition-all duration-300 ease-out',
              active ? 'opacity-100 translate-x-0' : 'opacity-90'
            )}
          >
            {done && <Check size={11} className="text-emerald-400 flex-shrink-0" />}
            {active && <Loader2 size={11} className="text-[#a5b4fc] animate-spin flex-shrink-0" />}
            {!done && !active && <Circle size={6} className="text-white/15 flex-shrink-0 mx-[2.5px]" />}
            <span
              className={cn(
                'text-[10.5px] leading-none transition-colors duration-300',
                done && 'text-white/35',
                active && 'text-white/85 font-medium',
                !done && !active && 'text-white/20'
              )}
            >
              {GENERATION_STAGE_EMOJI[s]} {GENERATION_STAGE_LABELS[s]}
            </span>
          </div>
        )
      })}

      {retry && (
        <div className="mt-1.5 pt-1.5 border-t border-white/5 flex items-start gap-2 transition-opacity duration-300">
          <Wrench size={11} className="text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="min-w-0">
            <p className="text-[10.5px] text-amber-300/90 font-medium leading-snug">
              Auto Repair running... (attempt {retry.attempt + 1} of {retry.maxAttempts})
            </p>
            <p className="text-[10px] text-white/35 leading-snug mt-0.5 flex items-center gap-1">
              <RefreshCw size={9} className="animate-spin flex-shrink-0" />
              Regenerating workflow to fix: {retry.reasons[0]}
              {retry.reasons.length > 1 ? ` (+${retry.reasons.length - 1} more)` : ''}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
