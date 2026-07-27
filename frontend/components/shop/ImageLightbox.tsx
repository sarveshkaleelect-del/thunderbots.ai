'use client'
// ThunderBots Smart Shop Assistant — ImageLightbox (NEW)
//
// Full-screen larger preview, opened by clicking any product image. Swipes
// (touch drag) and arrow buttons move between images when a product has
// more than one — this is the "swipeable gallery" requirement.
import { useEffect, useRef, useState } from 'react'
import { X, ChevronLeft, ChevronRight } from 'lucide-react'

export function ImageLightbox({
  images: imagesProp, startIndex = 0, title, onClose,
}: {
  images?: { url: string; thumbnail_url?: string }[] | null
  startIndex?: number
  title?: string
  onClose: () => void
}) {
  const images = imagesProp ?? []
  const [index, setIndex] = useState(startIndex)
  const touchStartX = useRef<number | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowRight') setIndex((i) => Math.min(images.length - 1, i + 1))
      if (e.key === 'ArrowLeft') setIndex((i) => Math.max(0, i - 1))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [images.length, onClose])

  if (images.length === 0) return null

  const goNext = () => setIndex((i) => Math.min(images.length - 1, i + 1))
  const goPrev = () => setIndex((i) => Math.max(0, i - 1))

  return (
    <div
      className="fixed inset-0 z-[100] bg-black/85 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in"
      onClick={onClose}
      onTouchStart={(e) => { touchStartX.current = e.touches[0].clientX }}
      onTouchEnd={(e) => {
        if (touchStartX.current === null) return
        const delta = e.changedTouches[0].clientX - touchStartX.current
        if (delta > 50) goPrev()
        else if (delta < -50) goNext()
        touchStartX.current = null
      }}
    >
      <button
        onClick={onClose}
        className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white"
      >
        <X className="w-5 h-5" />
      </button>

      {title && (
        <p className="absolute top-5 left-5 text-sm text-white/60">{title}</p>
      )}

      {images.length > 1 && (
        <button
          onClick={(e) => { e.stopPropagation(); goPrev() }}
          disabled={index === 0}
          className="absolute left-2 sm:left-6 w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white disabled:opacity-20"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
      )}

      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={images[index].url}
        alt={title || 'Product image'}
        onClick={(e) => e.stopPropagation()}
        className="max-w-[92vw] max-h-[82vh] object-contain rounded-2xl animate-scale-in select-none"
        draggable={false}
      />

      {images.length > 1 && (
        <button
          onClick={(e) => { e.stopPropagation(); goNext() }}
          disabled={index === images.length - 1}
          className="absolute right-2 sm:right-6 w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white disabled:opacity-20"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
      )}

      {images.length > 1 && (
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex gap-1.5">
          {images.map((_, i) => (
            <button
              key={i}
              onClick={(e) => { e.stopPropagation(); setIndex(i) }}
              className={`h-1.5 rounded-full transition-all ${i === index ? 'w-5 bg-white' : 'w-1.5 bg-white/30'}`}
            />
          ))}
        </div>
      )}
    </div>
  )
}
