'use client'
/**
 * NEW (AI Call Agent — Voice AI Part 4) — Text Knowledge Base
 *
 * Lets an owner paste text directly into a Knowledge Base — no file/upload
 * round-trip — with append/replace/edit/delete, and supports multiple Text
 * Knowledge Bases. Reuses the exact same `knowledgeApi` / KnowledgeBase /
 * KBDocument infrastructure the Workflow Builder's KnowledgePanel already
 * uses (see backend/app/api/v1/knowledge.py) — this is a second UI surface
 * for the same backend, not a second Knowledge Base system. The Builder's
 * own panel is untouched.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Plus, Trash2, Pencil, Loader2, CheckCircle2, AlertCircle, X } from 'lucide-react'
import { knowledgeApi } from '@/lib/api/knowledge'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { FieldLabel, Input, Textarea } from '@/components/ui/Field'
import { useToast } from '@/components/ui/Toast'
import { getErrorMessage } from '@/lib/utils/errors'
import type { KnowledgeBase, KBDocument } from '@/types'

function StatusPill({ status }: { status: string }) {
  if (status === 'ready') return <span className="flex items-center gap-1 text-[11px] text-emerald-400"><CheckCircle2 size={11} />Indexed</span>
  if (status === 'error') return <span className="flex items-center gap-1 text-[11px] text-red-400"><AlertCircle size={11} />Error</span>
  return <span className="flex items-center gap-1 text-[11px] text-amber-400"><Loader2 size={11} className="animate-spin" />Indexing…</span>
}

function TextEntryEditor({
  kbId, entry, onClose,
}: { kbId: string; entry: KBDocument | null; onClose: () => void }) {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [title, setTitle] = useState(entry?.filename || '')
  const [content, setContent] = useState('')
  const [loadingFull, setLoadingFull] = useState(!!entry)

  useEffect(() => {
    if (entry) {
      knowledgeApi.getTextEntry(kbId, entry.id)
        .then(full => setContent(full.content))
        .catch(() => toast('error', 'Could not load the full text.'))
        .finally(() => setLoadingFull(false))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const saveMutation = useMutation({
    mutationFn: () =>
      entry
        ? knowledgeApi.updateTextEntry(kbId, entry.id, content, title)
        : knowledgeApi.createTextEntry(kbId, title, content),
    onSuccess: () => {
      toast('success', entry ? 'Text entry updated — re-indexing…' : 'Text entry added — indexing…')
      qc.invalidateQueries({ queryKey: ['knowledge', 'documents', kbId] })
      onClose()
    },
    onError: (err) => toast('error', getErrorMessage(err, 'Could not save this text entry.')),
  })

  return (
    <div className="border border-white/10 rounded-lg p-3 bg-white/[0.02] space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-white/60">{entry ? 'Edit text entry' : 'Paste new text'}</span>
        <button onClick={onClose} className="text-white/30 hover:text-white/60"><X size={14} /></button>
      </div>
      <Input
        placeholder="Title (e.g. Refund Policy, FAQ, Store Hours)"
        value={title} onChange={e => setTitle(e.target.value)}
      />
      <Textarea
        placeholder="Paste as much text as you need — there's effectively no length limit."
        rows={10}
        value={content}
        disabled={loadingFull}
        onChange={e => setContent(e.target.value)}
        className="font-mono text-xs"
      />
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-white/30">{content.length.toLocaleString()} characters</span>
        <Button
          size="sm" loading={saveMutation.isPending}
          disabled={!content.trim() || loadingFull}
          onClick={() => saveMutation.mutate()}
        >
          {entry ? 'Save changes' : 'Add & index'}
        </Button>
      </div>
    </div>
  )
}

function TextKBPanel({ kb }: { kb: KnowledgeBase }) {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [editing, setEditing] = useState<KBDocument | 'new' | null>(null)
  const [appendingId, setAppendingId] = useState<string | null>(null)
  const [appendText, setAppendText] = useState('')

  const { data: docs = [], isLoading } = useQuery({
    queryKey: ['knowledge', 'documents', kb.id],
    queryFn: () => knowledgeApi.listDocuments(kb.id),
    refetchInterval: (q) => (q.state.data || []).some(d => d.status === 'processing') ? 2000 : false,
  })

  const deleteMutation = useMutation({
    mutationFn: (docId: string) => knowledgeApi.deleteDocument(kb.id, docId),
    onSuccess: () => {
      toast('success', 'Text entry removed.')
      qc.invalidateQueries({ queryKey: ['knowledge', 'documents', kb.id] })
    },
    onError: (err) => toast('error', getErrorMessage(err, 'Could not delete this entry.')),
  })

  const appendMutation = useMutation({
    mutationFn: (docId: string) => knowledgeApi.appendTextEntry(kb.id, docId, appendText),
    onSuccess: () => {
      toast('success', 'Appended — re-indexing…')
      setAppendingId(null); setAppendText('')
      qc.invalidateQueries({ queryKey: ['knowledge', 'documents', kb.id] })
    },
    onError: (err) => toast('error', getErrorMessage(err, 'Could not append text.')),
  })

  return (
    <div className="space-y-2 pl-1">
      {isLoading && <p className="text-xs text-white/30">Loading entries…</p>}
      {!isLoading && docs.length === 0 && editing !== 'new' && (
        <p className="text-xs text-white/30">No text pasted into this Knowledge Base yet.</p>
      )}
      {docs.map(doc => (
        <div key={doc.id} className="border border-white/10 rounded-lg p-2.5 bg-black/20">
          {editing !== null && typeof editing === 'object' && editing.id === doc.id ? (
            <TextEntryEditor kbId={kb.id} entry={doc} onClose={() => setEditing(null)} />
          ) : (
            <>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm text-white/80 truncate">{doc.filename}</p>
                  <p className="text-[11px] text-white/30 mt-0.5 line-clamp-2">{doc.text_preview}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <StatusPill status={doc.status} />
                </div>
              </div>
              <div className="flex items-center gap-3 mt-2">
                <button onClick={() => setEditing(doc)} className="flex items-center gap-1 text-[11px] text-cyan-300/80 hover:text-cyan-200">
                  <Pencil size={11} />Edit / replace
                </button>
                <button onClick={() => setAppendingId(appendingId === doc.id ? null : doc.id)} className="flex items-center gap-1 text-[11px] text-cyan-300/80 hover:text-cyan-200">
                  <Plus size={11} />Append
                </button>
                <button
                  onClick={() => confirm('Delete this text entry?') && deleteMutation.mutate(doc.id)}
                  className="flex items-center gap-1 text-[11px] text-red-400/70 hover:text-red-400 ml-auto"
                >
                  <Trash2 size={11} />Delete
                </button>
              </div>
              {appendingId === doc.id && (
                <div className="mt-2 space-y-1.5">
                  <Textarea
                    placeholder="Text to append to this entry…"
                    rows={4} value={appendText}
                    onChange={e => setAppendText(e.target.value)}
                    className="font-mono text-xs"
                  />
                  <Button size="sm" loading={appendMutation.isPending} disabled={!appendText.trim()} onClick={() => appendMutation.mutate(doc.id)}>
                    Append & re-index
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      ))}
      {editing === 'new' ? (
        <TextEntryEditor kbId={kb.id} entry={null} onClose={() => setEditing(null)} />
      ) : (
        <Button size="sm" variant="secondary" icon={<Plus size={12} />} onClick={() => setEditing('new')}>
          Paste new text
        </Button>
      )}
    </div>
  )
}

export function TextKnowledgeBaseSection() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const { data: kbs = [], isLoading } = useQuery({
    queryKey: ['knowledge', 'list'],
    queryFn: knowledgeApi.list,
  })
  const textKBs = kbs.filter(kb => kb.kb_type === 'text')

  const createMutation = useMutation({
    mutationFn: () => knowledgeApi.create(newName, undefined, 'text'),
    onSuccess: (kb) => {
      toast('success', `"${kb.name}" Text Knowledge Base created.`)
      setNewName(''); setCreating(false); setExpandedId(kb.id)
      qc.invalidateQueries({ queryKey: ['knowledge', 'list'] })
    },
    onError: (err) => toast('error', getErrorMessage(err, 'Could not create this Knowledge Base.')),
  })

  const deleteKbMutation = useMutation({
    mutationFn: (id: string) => knowledgeApi.delete(id),
    onSuccess: () => {
      toast('success', 'Text Knowledge Base deleted.')
      qc.invalidateQueries({ queryKey: ['knowledge', 'list'] })
    },
    onError: (err) => toast('error', getErrorMessage(err, 'Could not delete this Knowledge Base.')),
  })

  return (
    <Card className="p-4 space-y-3 tb2-rise">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-white/50">
          <FileText size={14} />
          <span className="text-xs font-semibold uppercase tracking-wider">Text Knowledge Base</span>
        </div>
        {!creating && (
          <Button size="sm" variant="ghost" icon={<Plus size={12} />} onClick={() => setCreating(true)}>
            New
          </Button>
        )}
      </div>
      <p className="text-[11px] text-white/30 -mt-2">
        Paste FAQs, policies, or product info directly — no file needed. Assign any of these below under
        "Knowledge base selection" so the call agent answers from them.
      </p>

      {creating && (
        <div className="flex items-center gap-2">
          <Input placeholder="e.g. Refund Policy" value={newName} onChange={e => setNewName(e.target.value)} />
          <Button size="sm" loading={createMutation.isPending} disabled={!newName.trim()} onClick={() => createMutation.mutate()}>
            Create
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setCreating(false)}>Cancel</Button>
        </div>
      )}

      {isLoading && <p className="text-xs text-white/30">Loading…</p>}
      {!isLoading && textKBs.length === 0 && !creating && (
        <p className="text-xs text-white/30">No Text Knowledge Bases yet — create one to paste in text.</p>
      )}

      <div className="space-y-2">
        {textKBs.map(kb => (
          <div key={kb.id} className="border border-white/10 rounded-lg overflow-hidden">
            <button
              onClick={() => setExpandedId(expandedId === kb.id ? null : kb.id)}
              className="w-full flex items-center justify-between px-3 py-2 bg-white/[0.03] hover:bg-white/[0.05] text-left"
            >
              <span className="text-sm text-white/80">{kb.name}</span>
              <span className="flex items-center gap-3">
                <span className="text-[11px] text-white/30">{kb.document_count} entr{kb.document_count === 1 ? 'y' : 'ies'}</span>
                <Trash2
                  size={12}
                  className="text-red-400/50 hover:text-red-400"
                  onClick={(e) => { e.stopPropagation(); confirm(`Delete "${kb.name}" and all its text entries?`) && deleteKbMutation.mutate(kb.id) }}
                />
              </span>
            </button>
            {expandedId === kb.id && (
              <div className="p-3 border-t border-white/10">
                <TextKBPanel kb={kb} />
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  )
}
