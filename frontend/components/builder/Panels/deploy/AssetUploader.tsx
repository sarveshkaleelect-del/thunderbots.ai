'use client'
import { useRef, useState } from 'react'
import { ImagePlus, Loader2, X } from 'lucide-react'
import { deployApi } from '@/lib/api/deploy'
import { getErrorMessage } from '@/lib/utils/errors'

const ACCEPT = '.png,.jpg,.jpeg,.svg,.webp,image/png,image/jpeg,image/svg+xml,image/webp'

export function AssetUploader({
  workflowId, field, label, currentUrl, onUploaded, onCleared, shape = 'square',
}: {
  workflowId: string
  field: 'logo' | 'avatar' | 'favicon' | 'background_image' | 'launcher_icon'
  label: string
  currentUrl: string | null | undefined
  onUploaded: (url: string) => void
  onCleared?: () => void
  shape?: 'square' | 'round' | 'wide'
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function handleFile(file: File) {
    setErr(null)
    setBusy(true)
    try {
      const res = await deployApi.uploadAsset(workflowId, field, file)
      onUploaded(res.url)
    } catch (e) {
      setErr(getErrorMessage(e, 'Upload failed'))
    } finally {
      setBusy(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const shapeClass =
    shape === 'round' ? 'rounded-full w-12 h-12' :
    shape === 'wide'  ? 'rounded-lg w-full h-16' :
                        'rounded-lg w-12 h-12'

  return (
    <div>
      <label className="text-[10px] font-semibold text-white/35 uppercase tracking-wider mb-1.5 block">
        {label}
      </label>
      <div className="flex items-center gap-3">
        <div
          className={`relative flex-shrink-0 ${shapeClass} bg-[#1a1a1a] border border-[#2a2a2a] border-dashed
                      flex items-center justify-center overflow-hidden group cursor-pointer tb-hover-lift`}
          onClick={() => inputRef.current?.click()}
        >
          {currentUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={currentUrl} alt="" className="w-full h-full object-cover" />
          ) : busy ? (
            <Loader2 size={14} className="animate-spin text-white/30" />
          ) : (
            <ImagePlus size={14} className="text-white/25 group-hover:text-white/50 transition" />
          )}
          {busy && currentUrl && (
            <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
              <Loader2 size={14} className="animate-spin text-white/70" />
            </div>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <button
            onClick={() => inputRef.current?.click()}
            disabled={busy}
            className="text-xs text-white/50 hover:text-white/85 transition disabled:opacity-40"
          >
            {currentUrl ? 'Replace image' : 'Upload image'}
          </button>
          <p className="text-[10px] text-white/20 mt-0.5">PNG, JPG, SVG or WEBP · max 5MB</p>
          {err && <p className="text-[10px] text-red-400 mt-0.5">{err}</p>}
        </div>
        {currentUrl && onCleared && (
          <button
            onClick={onCleared}
            className="p-1.5 rounded-md text-white/20 hover:text-red-400 transition flex-shrink-0"
            title="Remove"
          >
            <X size={12} />
          </button>
        )}
      </div>
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
