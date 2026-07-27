'use client'
import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useFeatureTutorial } from '@/hooks/useFeatureTutorial'
import {
  Database, Upload, Trash2, Plus, Loader2,
  FileText, CheckCircle2, AlertCircle, Clock, X, RotateCw,
} from 'lucide-react'
import { knowledgeApi } from '@/lib/api/knowledge'
import { getErrorMessage } from '@/lib/utils/errors'
import type { KnowledgeBase, KBDocument } from '@/types'

function StatusIcon({ status }: { status: string }) {
  if (status === 'ready') return <CheckCircle2 size={12} className="text-emerald-400" />
  if (status === 'error') return <AlertCircle size={12} className="text-red-400" />
  return <Loader2 size={12} className="animate-spin text-white/30" />
}

function DocumentRow({
  doc, onDelete, onRetry, isRetrying, deleteError,
}: {
  doc: KBDocument
  onDelete: () => void
  onRetry: () => void
  isRetrying: boolean
  deleteError?: string | null
}) {
  const sizeKb = Math.round(doc.file_size / 1024)
  return (
    <div className="group flex flex-col gap-1 px-3 py-2.5 rounded-lg hover:bg-[#161616] transition">
      <div className="flex items-center gap-2.5">
        <StatusIcon status={doc.status} />
        <div className="flex-1 min-w-0">
          <p className="text-xs text-white/70 truncate font-medium">{doc.filename}</p>
          <p className="text-[10px] text-white/25 mt-0.5">
            {doc.file_type.toUpperCase()} · {sizeKb}KB
            {doc.status === 'ready' && ` · ${doc.chunk_count} chunks`}
            {doc.status === 'processing' && ` · Processing…`}
          </p>
        </div>
        {doc.status === 'error' && (
          <button
            onClick={onRetry}
            disabled={isRetrying}
            title="Retry"
            className="opacity-0 group-hover:opacity-100 p-1 text-white/20 hover:text-[#818cf8] transition disabled:opacity-60"
          >
            <RotateCw size={11} className={isRetrying ? 'animate-spin' : ''} />
          </button>
        )}
        <button
          onClick={onDelete}
          className="opacity-0 group-hover:opacity-100 p-1 text-white/20 hover:text-red-400 transition"
        >
          <Trash2 size={11} />
        </button>
      </div>
      {doc.status === 'error' && doc.error_message && (
        <div className="ml-[18px] mt-0.5 px-2 py-1.5 rounded-md bg-red-500/10 border border-red-500/20">
          <p className="text-[10px] text-red-300 leading-snug">{doc.error_message}</p>
        </div>
      )}
      {deleteError && (
        <div className="ml-[18px] mt-0.5 px-2 py-1.5 rounded-md bg-red-500/10 border border-red-500/20">
          <p className="text-[10px] text-red-300 leading-snug">{deleteError}</p>
        </div>
      )}
    </div>
  )
}

function KBDetail({ kb, onBack }: { kb: KnowledgeBase; onBack: () => void }) {
  useFeatureTutorial('knowledge-base')
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const { data: docs = [], isLoading } = useQuery({
    queryKey: ['kb-docs', kb.id],
    queryFn: () => knowledgeApi.listDocuments(kb.id),
    refetchInterval: 5000,
  })

  const [deleteErrorFor, setDeleteErrorFor] = useState<{ id: string; message: string } | null>(null)

  const deleteMutation = useMutation({
    mutationFn: (docId: string) => knowledgeApi.deleteDocument(kb.id, docId),
    onSuccess: (_data, docId) => {
      setDeleteErrorFor(prev => (prev?.id === docId ? null : prev))
      qc.invalidateQueries({ queryKey: ['kb-docs', kb.id] })
      qc.invalidateQueries({ queryKey: ['knowledge-bases'] })
    },
    onError: (err, docId) => {
      setDeleteErrorFor({ id: docId, message: getErrorMessage(err, 'Could not delete this document.') })
    },
  })

  const retryMutation = useMutation({
    mutationFn: (docId: string) => knowledgeApi.retryDocument(kb.id, docId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['kb-docs', kb.id] }),
    onError: (err, docId) => {
      setDeleteErrorFor({ id: docId, message: getErrorMessage(err, 'Could not retry this document.') })
    },
  })

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadProgress(0)
    setUploadError(null)
    try {
      await knowledgeApi.upload(kb.id, file, setUploadProgress)
      qc.invalidateQueries({ queryKey: ['kb-docs', kb.id] })
      qc.invalidateQueries({ queryKey: ['knowledge-bases'] })
    } catch (err) {
      setUploadError(getErrorMessage(err, 'Upload failed. Please try again.'))
    } finally {
      setUploading(false)
      setUploadProgress(0)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[#1e1e1e] flex-shrink-0">
        <button onClick={onBack} className="text-white/30 hover:text-white/60 transition text-xs">←</button>
        <Database size={12} className="text-white/40" />
        <span className="text-xs font-semibold text-white/70 truncate">{kb.name}</span>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-2 p-3 border-b border-[#1e1e1e]">
        {[
          { label: 'Documents', value: kb.document_count },
          { label: 'Chunks', value: kb.chunk_count },
        ].map(s => (
          <div key={s.label} className="bg-[#111] border border-[#1e1e1e] rounded-lg p-2.5 text-center">
            <p className="text-base font-bold text-white">{s.value}</p>
            <p className="text-[10px] text-white/30">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Upload */}
      <div className="p-3 border-b border-[#1e1e1e]">
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.docx,.txt,.md"
          onChange={handleUpload}
          className="hidden"
          id="kb-upload"
        />
        <label
          htmlFor="kb-upload"
          data-tutorial="kb-upload"
          className="flex items-center justify-center gap-2 py-2.5 rounded-lg border border-dashed border-[#2a2a2a] hover:border-[#6366f1]/40 hover:bg-[#6366f1]/5 cursor-pointer transition text-xs text-white/30 hover:text-white/60"
        >
          {uploading ? (
            <>
              <Loader2 size={12} className="animate-spin" />
              Uploading {uploadProgress}%
            </>
          ) : (
            <>
              <Upload size={12} />
              Upload PDF, DOCX, TXT, or Markdown
            </>
          )}
        </label>
        {uploading && (
          <div className="mt-2 h-1 bg-[#1e1e1e] rounded-full overflow-hidden">
            <div
              className="h-full bg-[#6366f1] transition-all duration-300"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
        )}
        {uploadError && (
          <div className="mt-2 flex items-start gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20">
            <AlertCircle size={12} className="text-red-400 mt-0.5 flex-shrink-0" />
            <p className="text-[11px] text-red-300 leading-snug flex-1">{uploadError}</p>
            <button onClick={() => setUploadError(null)} className="text-red-400/50 hover:text-red-400 flex-shrink-0">
              <X size={11} />
            </button>
          </div>
        )}
      </div>

      {/* Documents */}
      <div className="flex-1 overflow-y-auto p-2" data-tutorial="kb-documents">
        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 size={16} className="animate-spin text-white/20" />
          </div>
        )}
        {!isLoading && docs.length === 0 && (
          <p className="text-center text-[11px] text-white/20 py-8">No documents yet</p>
        )}
        {docs.map((doc: KBDocument) => (
          <DocumentRow
            key={doc.id}
            doc={doc}
            onDelete={() => deleteMutation.mutate(doc.id)}
            onRetry={() => retryMutation.mutate(doc.id)}
            isRetrying={retryMutation.isPending && retryMutation.variables === doc.id}
            deleteError={deleteErrorFor?.id === doc.id ? deleteErrorFor.message : null}
          />
        ))}
      </div>
    </div>
  )
}

export function KnowledgePanel() {
  const qc = useQueryClient()
  const [selectedKB, setSelectedKB] = useState<KnowledgeBase | null>(null)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')

  const { data: kbs = [], isLoading, error: listError } = useQuery({
    queryKey: ['knowledge-bases'],
    queryFn: knowledgeApi.list,
    retry: 1,
  })

  const createMutation = useMutation({
    mutationFn: (name: string) => knowledgeApi.create(name),
    onSuccess: (kb) => {
      qc.invalidateQueries({ queryKey: ['knowledge-bases'] })
      setCreating(false)
      setNewName('')
      setSelectedKB(kb)
    },
  })

  const [deleteError, setDeleteError] = useState<string | null>(null)

  const deleteMutation = useMutation({
    mutationFn: (id: string) => knowledgeApi.delete(id),
    onSuccess: () => {
      setDeleteError(null)
      qc.invalidateQueries({ queryKey: ['knowledge-bases'] })
    },
    onError: (err) => setDeleteError(getErrorMessage(err, 'Could not delete this knowledge base.')),
  })

  if (selectedKB) {
    return (
      <KBDetail
        kb={selectedKB}
        onBack={() => setSelectedKB(null)}
      />
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e1e1e] flex-shrink-0">
        <div className="flex items-center gap-2">
          <Database size={13} className="text-white/40" />
          <span className="text-xs font-semibold text-white/60">Knowledge Bases</span>
        </div>
        <button
          onClick={() => setCreating(true)}
          className="p-1 text-white/30 hover:text-white/70 transition"
        >
          <Plus size={14} />
        </button>
      </div>

      {/* Create form */}
      {creating && (
        <div className="p-3 border-b border-[#1e1e1e] space-y-2">
          <input
            autoFocus
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && newName.trim()) createMutation.mutate(newName.trim())
              if (e.key === 'Escape') { setCreating(false); setNewName('') }
            }}
            placeholder="Knowledge base name"
            className="w-full bg-[#1a1a1a] text-xs text-white border border-[#2a2a2a] rounded-lg px-3 py-2 outline-none focus:border-[#6366f1]/50 transition"
          />
          {createMutation.isError && (
            <p className="text-[10px] text-red-400">{getErrorMessage(createMutation.error, 'Could not create knowledge base.')}</p>
          )}
          <div className="flex gap-2">
            <button
              onClick={() => { setCreating(false); setNewName('') }}
              className="flex-1 py-1.5 rounded-lg text-[11px] text-white/40 hover:text-white/60 border border-[#2a2a2a] transition"
            >
              Cancel
            </button>
            <button
              onClick={() => newName.trim() && createMutation.mutate(newName.trim())}
              disabled={!newName.trim() || createMutation.isPending}
              className="flex-1 py-1.5 rounded-lg text-[11px] bg-[#6366f1] hover:bg-[#5558e8] text-white transition disabled:opacity-40"
            >
              {createMutation.isPending ? <Loader2 size={10} className="animate-spin mx-auto" /> : 'Create'}
            </button>
          </div>
        </div>
      )}

      {listError && (
        <div className="m-3 flex items-start gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20">
          <AlertCircle size={12} className="text-red-400 mt-0.5 flex-shrink-0" />
          <p className="text-[11px] text-red-300 leading-snug">{getErrorMessage(listError, 'Could not load knowledge bases.')}</p>
        </div>
      )}

      {deleteError && (
        <div className="m-3 flex items-start gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20">
          <AlertCircle size={12} className="text-red-400 mt-0.5 flex-shrink-0" />
          <p className="text-[11px] text-red-300 leading-snug flex-1">{deleteError}</p>
          <button onClick={() => setDeleteError(null)} className="text-red-400/50 hover:text-red-400 flex-shrink-0">
            <X size={11} />
          </button>
        </div>
      )}

      {/* List */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 size={16} className="animate-spin text-white/20" />
          </div>
        )}
        {!isLoading && kbs.length === 0 && !creating && (
          <div className="text-center py-10">
            <Database size={22} className="text-white/10 mx-auto mb-2" />
            <p className="text-[11px] text-white/25">No knowledge bases yet</p>
            <button onClick={() => setCreating(true)}
              className="mt-3 text-[11px] text-[#818cf8] hover:underline">
              Create one
            </button>
          </div>
        )}
        {kbs.map((kb: KnowledgeBase) => (
          <div
            key={kb.id}
            className="group flex items-center gap-3 p-3 rounded-lg border border-[#1e1e1e] hover:border-[#2a2a2a] bg-[#111] hover:bg-[#141414] cursor-pointer transition"
            onClick={() => setSelectedKB(kb)}
          >
            <div className="w-7 h-7 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center flex-shrink-0">
              <Database size={12} className="text-emerald-400" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-white/80 truncate">{kb.name}</p>
              <p className="text-[10px] text-white/30">
                {kb.document_count} doc{kb.document_count !== 1 ? 's' : ''} · {kb.chunk_count} chunks
              </p>
            </div>
            <button
              onClick={e => {
                e.stopPropagation()
                if (confirm(`Delete "${kb.name}"?`)) deleteMutation.mutate(kb.id)
              }}
              className="opacity-0 group-hover:opacity-100 p-1 text-white/20 hover:text-red-400 transition"
            >
              <Trash2 size={12} />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
