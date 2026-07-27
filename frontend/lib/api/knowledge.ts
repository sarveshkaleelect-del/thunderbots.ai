import { apiClient } from './client'
import type { KnowledgeBase, KBDocument } from '@/types'

export const knowledgeApi = {
  list: () =>
    apiClient.get<KnowledgeBase[]>('/knowledge').then(r => r.data),

  // kb_type: NEW (Voice AI Part 4) — 'file' (default) | 'text'. Purely a
  // label; a "text" KB is the exact same KnowledgeBase row/collection,
  // just intended to only ever hold pasted-text entries (see createText below).
  create: (name: string, description?: string, kb_type: 'file' | 'text' = 'file') =>
    apiClient.post<KnowledgeBase>('/knowledge', { name, description, kb_type }).then(r => r.data),

  delete: (id: string) =>
    apiClient.delete(`/knowledge/${id}`),

  upload: (kbId: string, file: File, onProgress?: (pct: number) => void) => {
    const form = new FormData()
    form.append('file', file)
    // ROOT CAUSE FIX: no manual Content-Type header. Axios's browser (XHR)
    // adapter will NOT auto-attach the required multipart `boundary=` param
    // if Content-Type is already set explicitly — the body is then sent
    // without a boundary marker and every upload fails at the network/parse
    // layer before backend validation ever runs. Let Axios/the browser
    // detect the FormData body and set the header (with boundary) itself.
    return apiClient.post(`/knowledge/${kbId}/upload`, form, {
      timeout: 120_000, // FIX v5: large PDFs need more than the default 30s to transfer
      onUploadProgress: (e) => {
        if (onProgress && e.total) onProgress(Math.round((e.loaded * 100) / e.total))
      },
    }).then(r => r.data)
  },

  listDocuments: (kbId: string) =>
    apiClient.get<KBDocument[]>(`/knowledge/${kbId}/documents`).then(r => r.data),

  retryDocument: (kbId: string, docId: string) =>
    apiClient.post(`/knowledge/${kbId}/documents/${docId}/retry`).then(r => r.data),

  deleteDocument: (kbId: string, docId: string) =>
    apiClient.delete(`/knowledge/${kbId}/documents/${docId}`),

  search: (kbId: string, query: string, n_results = 5) =>
    apiClient.post(`/knowledge/${kbId}/search`, { query, n_results }).then(r => r.data),

  // ── Text Knowledge Base (NEW, Voice AI Part 4) ──────────────────────────
  // Paste text directly into a KB — shares the exact same KBDocument/
  // retrieval infra as file uploads above (see backend/app/api/v1/knowledge.py).

  createTextEntry: (kbId: string, title: string, content: string) =>
    apiClient.post(`/knowledge/${kbId}/text`, { title, content }).then(r => r.data),

  getTextEntry: (kbId: string, docId: string) =>
    apiClient.get<{ id: string; title: string; content: string; status: string; chunk_count: number }>(
      `/knowledge/${kbId}/text/${docId}`
    ).then(r => r.data),

  updateTextEntry: (kbId: string, docId: string, content: string, title?: string) =>
    apiClient.put(`/knowledge/${kbId}/text/${docId}`, { content, title }).then(r => r.data),

  appendTextEntry: (kbId: string, docId: string, content: string) =>
    apiClient.post(`/knowledge/${kbId}/text/${docId}/append`, { content }).then(r => r.data),
  // Deleting a text entry reuses deleteDocument() above — same endpoint,
  // same as an uploaded file.
}
