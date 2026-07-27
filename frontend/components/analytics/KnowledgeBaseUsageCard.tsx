'use client'
import { memo } from 'react'
import { Loader2, FileText, Database } from 'lucide-react'
import type { TopDocument, KBUsage } from '@/types/analytics'

interface Props {
  documents: TopDocument[] | undefined
  documentsLoading?: boolean
  kbUsage: KBUsage | undefined
  kbLoading?: boolean
}

function KnowledgeBaseUsageCardImpl({ documents, documentsLoading, kbUsage, kbLoading }: Props) {
  const docs = documents || []
  const maxUses = Math.max(1, ...docs.map(d => d.uses))

  return (
    <div className="tb2-glass p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xs font-semibold text-white/60 uppercase tracking-wide">Knowledge Base Usage</h3>
        {(documentsLoading || kbLoading) && <Loader2 size={12} className="text-white/20 animate-spin" />}
      </div>

      {kbUsage && (
        <div className="grid grid-cols-3 gap-2 mb-4">
          <div className="bg-white/[0.03] rounded-xl p-2.5 text-center">
            <p className="text-sm font-bold text-white/80 tabular-nums">{kbUsage.knowledge_bases}</p>
            <p className="text-[9px] text-white/25 mt-0.5">Knowledge Bases</p>
          </div>
          <div className="bg-white/[0.03] rounded-xl p-2.5 text-center">
            <p className="text-sm font-bold text-white/80 tabular-nums">{kbUsage.documents}</p>
            <p className="text-[9px] text-white/25 mt-0.5">Documents</p>
          </div>
          <div className="bg-white/[0.03] rounded-xl p-2.5 text-center">
            <p className="text-sm font-bold text-emerald-400 tabular-nums">{kbUsage.grounding_rate}%</p>
            <p className="text-[9px] text-white/25 mt-0.5">Grounded</p>
          </div>
        </div>
      )}

      <p className="text-[10px] font-semibold text-white/25 uppercase tracking-wider mb-2">Top Documents</p>
      <div className="space-y-2">
        {docs.slice(0, 6).map(doc => (
          <div key={doc.document} className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded-lg bg-white/5 flex items-center justify-center flex-shrink-0">
              <FileText size={11} className="text-white/40" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[11px] text-white/60 truncate mb-1">{doc.document}</p>
              <div className="h-1 bg-white/5 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full bg-sky-400 transition-all"
                  style={{ width: `${(doc.uses / maxUses) * 100}%` }}
                />
              </div>
            </div>
            <span className="text-[10px] text-white/30 tabular-nums flex-shrink-0">{doc.uses}</span>
          </div>
        ))}
        {!documentsLoading && docs.length === 0 && (
          <div className="flex flex-col items-center py-6 gap-2">
            <Database size={18} className="text-white/15" />
            <p className="text-[11px] text-white/20 text-center">No document citations recorded yet</p>
          </div>
        )}
      </div>
    </div>
  )
}

export const KnowledgeBaseUsageCard = memo(KnowledgeBaseUsageCardImpl)
