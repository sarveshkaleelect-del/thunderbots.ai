'use client'
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { History, RotateCcw, Loader2, Clock, Check, AlertCircle, X } from 'lucide-react'
import { useWorkflowStore } from '@/store/workflowStore'
import { apiClient } from '@/lib/api/client'
import { getErrorMessage } from '@/lib/utils/errors'
import type { WorkflowVersion } from '@/types'
import type { Node, Edge } from 'reactflow'

// ── API helpers ───────────────────────────────────────────────────────────────

async function fetchVersions(workflowId: string): Promise<WorkflowVersion[]> {
  return apiClient.get(`/history/${workflowId}/versions`).then(r => r.data)
}

async function restoreVersion(workflowId: string, versionId: string): Promise<void> {
  await apiClient.post(`/history/${workflowId}/restore/${versionId}`)
}

/** Fetch the FULL version detail (nodes + edges + canvas_state) after a restore */
async function fetchVersionDetail(workflowId: string, versionId: string) {
  return apiClient.get(`/history/${workflowId}/versions/${versionId}`).then(r => r.data)
}

async function labelVersion(workflowId: string, versionId: string, label: string) {
  return apiClient.patch(`/history/${workflowId}/versions/${versionId}/label?label=${encodeURIComponent(label)}`).then(r => r.data)
}

// ── Component ─────────────────────────────────────────────────────────────────

export function HistoryPanel() {
  // Granular selectors — avoids re-rendering this panel (queries, mutation
  // state, version list) on every unrelated node/edge change on the canvas.
  const workflowId = useWorkflowStore(s => s.workflowId)
  const workflowName = useWorkflowStore(s => s.workflowName)
  const qc = useQueryClient()
  const [restoring, setRestoring] = useState<string | null>(null)
  const [restored, setRestored] = useState<string | null>(null)
  const [restoreError, setRestoreError] = useState<string | null>(null)
  const [editingLabel, setEditingLabel] = useState<string | null>(null)
  const [labelDraft, setLabelDraft] = useState('')

  const { data: versions = [], isLoading } = useQuery({
    queryKey: ['history', workflowId],
    queryFn: () => fetchVersions(workflowId!),
    enabled: !!workflowId,
    refetchInterval: 15_000,
  })

  const restoreMutation = useMutation({
    mutationFn: async (versionId: string) => {
      // Step 1: Tell backend to restore
      await restoreVersion(workflowId!, versionId)
      // Step 2: Fetch full version data to update the canvas
      // (the restore endpoint only returns a confirmation, NOT the full workflow)
      return fetchVersionDetail(workflowId!, versionId)
    },
    onMutate: (id) => {
      setRestoring(id)
      setRestored(null)
    },
    onSuccess: (versionData) => {
      // Patch the Zustand store directly — no page reload needed
      useWorkflowStore.getState().setWorkflow(
        workflowId!,
        workflowName,
        (versionData.nodes ?? []) as Node[],
        (versionData.edges ?? []) as Edge[],
        versionData.canvas_state ?? { x: 0, y: 0, zoom: 1 },
      )
      setRestored(versionData.id)
      // Invalidate cached workflow so next load is fresh
      qc.invalidateQueries({ queryKey: ['workflow', workflowId] })
      qc.invalidateQueries({ queryKey: ['history', workflowId] })
    },
    onError: (err) => {
      console.error('Restore failed:', err)
      setRestoreError(getErrorMessage(err, 'Restore failed. Please try again.'))
    },
    onSettled: () => setRestoring(null),
  })

  const labelMutation = useMutation({
    mutationFn: ({ versionId, label }: { versionId: string; label: string }) =>
      labelVersion(workflowId!, versionId, label),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['history', workflowId] })
      setEditingLabel(null)
      setLabelDraft('')
    },
  })

  const formatDate = (iso: string) => {
    const d = new Date(iso)
    const diffMs = Date.now() - d.getTime()
    const mins = Math.floor(diffMs / 60_000)
    if (mins < 1) return 'Just now'
    if (mins < 60) return `${mins}m ago`
    const hrs = Math.floor(mins / 60)
    if (hrs < 24) return `${hrs}h ago`
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[#1e1e1e] flex-shrink-0">
        <History size={13} className="text-white/40" />
        <span className="text-xs font-semibold text-white/60">Version History</span>
      </div>

      {/* Restore error banner */}
      {restoreError && (
        <div className="mx-3 mt-3 flex items-start gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20">
          <AlertCircle size={12} className="text-red-400 mt-0.5 flex-shrink-0" />
          <p className="text-[11px] text-red-300 leading-snug flex-1">{restoreError}</p>
          <button onClick={() => setRestoreError(null)} className="text-red-400/50 hover:text-red-400">
            <X size={11} />
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={18} className="animate-spin text-white/20" />
          </div>
        )}

        {!isLoading && versions.length === 0 && (
          <div className="text-center py-12 px-4">
            <Clock size={24} className="text-white/10 mx-auto mb-3" />
            <p className="text-xs text-white/25">No versions saved yet</p>
            <p className="text-[10px] text-white/15 mt-1">
              Versions are created automatically on each save
            </p>
          </div>
        )}

        {versions.length > 0 && (
          <div className="p-3 space-y-1.5">
            {versions.map((v, i) => (
              <div
                key={v.id}
                className="group flex items-start gap-3 p-3 rounded-lg border border-[#1e1e1e] hover:border-[#2a2a2a] bg-[#111] hover:bg-[#141414] transition-all"
              >
                {/* Timeline dot */}
                <div className="flex flex-col items-center gap-1 flex-shrink-0 pt-0.5">
                  <div
                    className={`w-2 h-2 rounded-full flex-shrink-0 ${
                      restored === v.id
                        ? 'bg-emerald-400'
                        : i === 0
                        ? 'bg-[#6366f1]'
                        : 'bg-[#2a2a2a]'
                    }`}
                  />
                  {i < versions.length - 1 && (
                    <div className="w-px h-3 bg-[#1e1e1e]" />
                  )}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-xs font-medium text-white/70">
                      v{v.version_number}
                    </span>

                    {/* Label — click to edit */}
                    {editingLabel === v.id ? (
                      <input
                        autoFocus
                        value={labelDraft}
                        onChange={e => setLabelDraft(e.target.value)}
                        onBlur={() => {
                          if (labelDraft.trim()) labelMutation.mutate({ versionId: v.id, label: labelDraft.trim() })
                          else { setEditingLabel(null); setLabelDraft('') }
                        }}
                        onKeyDown={e => {
                          if (e.key === 'Enter' && labelDraft.trim()) labelMutation.mutate({ versionId: v.id, label: labelDraft.trim() })
                          if (e.key === 'Escape') { setEditingLabel(null); setLabelDraft('') }
                        }}
                        placeholder="Add label…"
                        className="text-[10px] px-1.5 py-0.5 rounded bg-[#1e1e1e] border border-[#6366f1]/40 text-white outline-none w-28"
                      />
                    ) : (
                      <button
                        onClick={() => { setEditingLabel(v.id); setLabelDraft(v.label || '') }}
                        className="text-[10px] px-1.5 py-0.5 rounded hover:bg-[#1e1e1e] text-white/20 hover:text-white/50 transition truncate max-w-[100px]"
                      >
                        {v.label || '+ label'}
                      </button>
                    )}

                    {restored === v.id && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-0.5 ml-auto flex-shrink-0">
                        <Check size={8} /> Restored
                      </span>
                    )}
                    {i === 0 && restored !== v.id && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#6366f1]/10 text-[#818cf8] border border-[#6366f1]/20 ml-auto flex-shrink-0">
                        Latest
                      </span>
                    )}
                  </div>
                  <p className="text-[10px] text-white/25 mt-0.5">{formatDate(v.created_at)}</p>
                </div>

                {/* Restore button — show on all versions, disable on latest */}
                <button
                  onClick={() => {
                    if (i === 0) return
                    if (window.confirm(`Restore to version ${v.version_number}?\n\nThis will overwrite your current canvas. Your current state is saved as the latest version.`)) {
                      restoreMutation.mutate(v.id)
                    }
                  }}
                  disabled={restoring === v.id || i === 0}
                  title={i === 0 ? 'Already at latest version' : `Restore to v${v.version_number}`}
                  className="opacity-0 group-hover:opacity-100 flex items-center gap-1 text-[10px] px-2 py-1 rounded-md bg-[#1e1e1e] hover:bg-[#2a2a2a] text-white/40 hover:text-white/80 transition disabled:opacity-20 disabled:cursor-not-allowed flex-shrink-0"
                >
                  {restoring === v.id
                    ? <Loader2 size={10} className="animate-spin" />
                    : <RotateCcw size={10} />
                  }
                  {i === 0 ? 'Current' : 'Restore'}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="p-3 border-t border-[#1e1e1e] flex-shrink-0">
        <p className="text-[10px] text-white/20 text-center">
          Up to 50 versions stored · Click a label to rename
        </p>
      </div>
    </div>
  )
}
