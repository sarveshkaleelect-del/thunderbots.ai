'use client'
/**
 * MediaAttachment — reusable optional image attachment control for
 * workflow builder nodes.
 *
 * Supports: upload, drag & drop, browse, preview, replace, remove.
 * Formats: PNG, JPG, JPEG, WEBP, SVG. Max size: 10MB.
 *
 * Fully self-contained and additive — nodes that don't render this
 * component behave exactly as before. Currently wired into the
 * Multiple Choice node only, but designed to be dropped into any
 * future node by passing a workflowId + current value + onChange.
 */
import { useRef, useState } from 'react'
import { ImagePlus, Loader2, X, RefreshCw } from 'lucide-react'
import { workflowsApi } from '@/lib/api/workflows'
import { getErrorMessage } from '@/lib/utils/errors'
import type { NodeMediaAttachment } from '@/types'

const ACCEPT_EXT = ['png', 'jpg', 'jpeg', 'webp', 'svg']
const ACCEPT = '.png,.jpg,.jpeg,.webp,.svg,image/png,image/jpeg,image/webp,image/svg+xml'
const MAX_SIZE_MB = 10

export function MediaAttachment({
  workflowId, value, onChange, label = 'Image (optional)',
}: {
  workflowId: string | null
  value: NodeMediaAttachment | null | undefined
  onChange: (image: NodeMediaAttachment | null) => void
  label?: string
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)

  function validate(file: File): string | null {
    const ext = file.name.split('.').pop()?.toLowerCase() || ''
    if (!ACCEPT_EXT.includes(ext)) {
      return 'Unsupported file type. Allowed: PNG, JPG, JPEG, WEBP, SVG'
    }
    if (file.size / (1024 * 1024) > MAX_SIZE_MB) {
      return `File size exceeds ${MAX_SIZE_MB}MB limit`
    }
    return null
  }

  async function handleFile(file: File) {
    setErr(null)
    if (!workflowId) {
      setErr('Save the workflow before attaching an image')
      return
    }
    const validationError = validate(file)
    if (validationError) {
      setErr(validationError)
      return
    }
    setBusy(true)
    try {
      const res = await workflowsApi.uploadNodeMedia(workflowId, file)
      onChange({
        url: res.url,
        filename: res.filename,
        size: res.size,
        mime_type: res.mime_type,
      })
    } catch (e) {
      setErr(getErrorMessage(e, 'Upload failed'))
    } finally {
      setBusy(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    e.stopPropagation()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleFile(file)
  }

  return (
    <div>
      <label className="text-[10px] font-semibold text-white/35 uppercase tracking-wider mb-1.5 block">
        {label}
      </label>

      {value?.url ? (
        <div className="relative rounded-lg overflow-hidden border border-[#222] bg-[#141414] group">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={value.url} alt={value.filename || 'attachment'} className="w-full max-h-40 object-contain" />
          {busy && (
            <div className="absolute inset-0 bg-black/60 flex items-center justify-center">
              <Loader2 size={16} className="animate-spin text-white/80" />
            </div>
          )}
          <div className="absolute top-1.5 right-1.5 flex gap-1 opacity-0 group-hover:opacity-100 transition">
            <button
              onClick={() => inputRef.current?.click()}
              disabled={busy}
              title="Replace image"
              className="p-1.5 rounded-md bg-black/70 text-white/70 hover:text-white transition disabled:opacity-40"
            >
              <RefreshCw size={12} />
            </button>
            <button
              onClick={() => onChange(null)}
              disabled={busy}
              title="Remove image"
              className="p-1.5 rounded-md bg-black/70 text-white/70 hover:text-red-400 transition disabled:opacity-40"
            >
              <X size={12} />
            </button>
          </div>
          {value.filename && (
            <p className="text-[10px] text-white/25 px-2 py-1 truncate border-t border-[#1e1e1e]">
              {value.filename}
            </p>
          )}
        </div>
      ) : (
        <div
          onClick={() => !busy && inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          className={`flex flex-col items-center justify-center gap-1.5 py-5 rounded-lg border border-dashed
                      cursor-pointer transition text-center
                      ${dragOver ? 'border-[#6366f1]/60 bg-[#6366f1]/5' : 'border-[#2a2a2a] hover:border-[#3a3a3a]'}`}
        >
          {busy ? (
            <Loader2 size={16} className="animate-spin text-white/40" />
          ) : (
            <ImagePlus size={16} className="text-white/25" />
          )}
          <p className="text-xs text-white/40">
            {busy ? 'Uploading…' : 'Drag & drop, or click to browse'}
          </p>
          <p className="text-[10px] text-white/20">PNG, JPG, JPEG, WEBP, SVG · max {MAX_SIZE_MB}MB</p>
        </div>
      )}

      {err && <p className="text-[10px] text-red-400 mt-1.5">{err}</p>}

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f) }}
      />
    </div>
  )
}
