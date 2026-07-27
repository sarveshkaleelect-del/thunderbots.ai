'use client'
import { Card } from '@/components/ui/Card'
import { QUICK_START_STEPS } from '@/lib/data/helpCenter'

export function QuickStartGuide() {
  return (
    <Card className="p-5">
      <p className="text-sm font-bold text-white/85 mb-4">Quick Start Guide</p>
      <ol className="space-y-4">
        {QUICK_START_STEPS.map((step, i) => (
          <li key={step.title} className="flex items-start gap-3">
            <div className="w-6 h-6 rounded-full bg-[#6366f1]/15 border border-[#6366f1]/25 flex items-center justify-center flex-shrink-0 mt-0.5">
              <span className="text-[10px] font-bold text-[#a5b4fc]">{i + 1}</span>
            </div>
            <div className="min-w-0">
              <p className="text-[13px] font-semibold text-white/80">{step.title}</p>
              <p className="text-[11px] text-white/35 mt-0.5">{step.description}</p>
            </div>
          </li>
        ))}
      </ol>
    </Card>
  )
}
