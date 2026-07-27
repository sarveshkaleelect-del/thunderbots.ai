'use client'
// ThunderBots Smart Shop Assistant — ProductImageManager (NEW, admin)
//
// Drag & drop AND click-to-upload onto the same dropzone. Every selected
// file shows an instant local preview (object URL) with an uploading
// spinner overlay — that's the "preview before saving" requirement — which
// swaps to the real server-processed (compressed) thumbnail the moment the
// upload call resolves. Existing images support click-to-set-cover and
// delete, with the star badge showing which one is currently the cover.
import { useCallback, useMemo, useRef, useState } from 'react'
import { Upload, Star, Trash2, Loader2, ImagePlus } from 'lucide-react'
import { shopAssistantApi } from '@/lib/api/shopAssistant'
import { useToast } from '@/components/ui/Toast'
import type { ProductImage } from '@/types/shopAssistant'

const MAX_IMAGES = 12
const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']

interface PendingUpload {
  key: string
  previewUrl: string
  status: 'uploading' | 'error'
  errorMessage?: string
}

export function ProductImageManager({
  shopId, productId, images: imagesProp, onImagesChange,
}: {
  shopId: string
  productId: string
  images?: ProductImage[] | null
  onImagesChange: (images: ProductImage[]) => void
}) {
  const { toast } = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [pending, setPending] = useState<PendingUpload[]>([])
  const [busyImageId, setBusyImageId] = useState<string | null>(null)

  // Defensive: treat a missing/null `images` prop as empty rather than
  // crashing every array operation below.
  // PERF FIX (v107): `imagesProp ?? []` created a brand-new array reference
  // every render whenever imagesProp was null/undefined — that unstable
  // reference was a dependency of uploadFiles's useCallback below, so it was
  // recreated (and re-passed to every child needing it) on every render
  // instead of only when the actual prop changed.
  const images = useMemo(() => imagesProp ?? [], [imagesProp])

  const remainingSlots = MAX_IMAGES - images.length - pending.length

  const uploadFiles = useCallback(async (files: File[]) => {
    const valid = files.filter((f) => ACCEPTED_TYPES.includes(f.type))
    const rejected = files.length - valid.length
    if (rejected > 0) {
      toast('error', `${rejected} file${rejected === 1 ? '' : 's'} skipped — only PNG, JPG, WEBP, or GIF images are allowed`)
    }
    const tooLarge = valid.filter((f) => f.size > 8 * 1024 * 1024)
    const withinSize = valid.filter((f) => f.size <= 8 * 1024 * 1024)
    if (tooLarge.length > 0) {
      toast('error', `${tooLarge.length} file${tooLarge.length === 1 ? '' : 's'} skipped — 8MB limit per image`)
    }
    const toUpload = withinSize.slice(0, Math.max(0, remainingSlots))
    if (withinSize.length > toUpload.length) {
      toast('error', `Only ${MAX_IMAGES} images allowed per product — some files were skipped`)
    }
    if (toUpload.length === 0) return

    const staged: PendingUpload[] = toUpload.map((f) => ({
      key: `${f.name}-${f.size}-${Math.random()}`, previewUrl: URL.createObjectURL(f), status: 'uploading',
    }))
    setPending((prev) => [...prev, ...staged])

    try {
      const uploaded = await shopAssistantApi.uploadProductImages(shopId, productId, toUpload)
      onImagesChange([...images, ...uploaded])
    } catch (e: any) {
      toast('error', e?.response?.data?.detail || 'Some images failed to upload')
    } finally {
      setPending((prev) => prev.filter((p) => !staged.some((s) => s.key === p.key)))
      staged.forEach((s) => URL.revokeObjectURL(s.previewUrl))
    }
  }, [images, onImagesChange, productId, remainingSlots, shopId, toast])

  const handleFiles = (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return
    uploadFiles(Array.from(fileList))
  }

  const setCover = async (imageId: string) => {
    setBusyImageId(imageId)
    try {
      const updated = await shopAssistantApi.setCoverImage(shopId, productId, imageId)
      onImagesChange(updated)
    } catch {
      toast('error', 'Could not change cover image')
    } finally {
      setBusyImageId(null)
    }
  }

  const deleteImage = async (imageId: string) => {
    setBusyImageId(imageId)
    try {
      await shopAssistantApi.deleteProductImage(shopId, productId, imageId)
      onImagesChange(images.filter((im) => im.id !== imageId))
    } catch {
      toast('error', 'Could not delete image')
    } finally {
      setBusyImageId(null)
    }
  }

  return (
    <div className="space-y-2">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files) }}
        onClick={() => fileInputRef.current?.click()}
        data-tutorial="shop-upload-images"
        className={`shop-dropzone ${dragging ? 'dragging' : ''} rounded-xl px-3 py-4 flex flex-col items-center justify-center gap-1 cursor-pointer text-center`}
      >
        <Upload className="w-4 h-4 text-white/30" />
        <p className="text-xs text-white/50">Drag & drop images, or click to browse</p>
        <p className="text-[10px] text-white/25">PNG, JPG, WEBP, GIF · up to 8MB · {remainingSlots} slot{remainingSlots === 1 ? '' : 's'} left</p>
        <input
          ref={fileInputRef} type="file" multiple accept="image/png,image/jpeg,image/webp,image/gif"
          className="hidden" onChange={(e) => { handleFiles(e.target.files); e.target.value = '' }}
        />
      </div>

      {(images.length > 0 || pending.length > 0) && (
        <div className="grid grid-cols-4 sm:grid-cols-5 gap-2">
          {images.map((im) => (
            <div key={im.id} className="relative aspect-square rounded-lg overflow-hidden group border border-white/10">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={im.thumbnail_url} alt="" className="w-full h-full object-cover" />
              {im.is_cover && (
                <span className="absolute top-1 left-1 bg-amber-400 text-black rounded-full p-0.5">
                  <Star className="w-2.5 h-2.5 fill-current" />
                </span>
              )}
              <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-1.5">
                {busyImageId === im.id ? (
                  <Loader2 className="w-4 h-4 text-white animate-spin" />
                ) : (
                  <>
                    {!im.is_cover && (
                      <button onClick={() => setCover(im.id)} title="Set as cover" className="w-6 h-6 rounded-full bg-white/15 hover:bg-white/25 flex items-center justify-center">
                        <Star className="w-3 h-3 text-white" />
                      </button>
                    )}
                    <button onClick={() => deleteImage(im.id)} title="Delete image" className="w-6 h-6 rounded-full bg-red-500/70 hover:bg-red-500 flex items-center justify-center">
                      <Trash2 className="w-3 h-3 text-white" />
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
          {pending.map((p) => (
            <div key={p.key} className="relative aspect-square rounded-lg overflow-hidden border border-white/10">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={p.previewUrl} alt="" className="w-full h-full object-cover opacity-50" />
              <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
                <Loader2 className="w-4 h-4 text-white animate-spin" />
              </div>
            </div>
          ))}
          {remainingSlots > 0 && images.length + pending.length > 0 && (
            <button
              onClick={() => fileInputRef.current?.click()}
              className="aspect-square rounded-lg border border-dashed border-white/15 flex items-center justify-center text-white/25 hover:text-white/50 hover:border-white/25"
            >
              <ImagePlus className="w-4 h-4" />
            </button>
          )}
        </div>
      )}
    </div>
  )
}
