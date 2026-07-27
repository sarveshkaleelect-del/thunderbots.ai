'use client'
// ThunderBots Smart Shop Assistant — ProductImage (NEW)
//
// A single small component every product-image surface in the app shares
// (search cards, browse grid, reservation lines, admin image manager),
// so "skeleton while loading" and "placeholder when there's no image" only
// need to be built once.
import { useState } from 'react'
import { ImageOff } from 'lucide-react'

export function ProductImage({
  src, alt, className = '', rounded = 'rounded-xl', onClick,
}: {
  src?: string | null
  alt: string
  className?: string
  rounded?: string
  onClick?: () => void
}) {
  const [loaded, setLoaded] = useState(false)
  const [errored, setErrored] = useState(false)

  if (!src || errored) {
    return (
      <div className={`${rounded} ${className} bg-white/[0.04] border border-white/10 flex items-center justify-center`}>
        <ImageOff className="w-1/4 h-1/4 text-white/15 min-w-[16px] min-h-[16px]" strokeWidth={1.5} />
      </div>
    )
  }

  return (
    <div className={`relative overflow-hidden ${rounded} ${className}`}>
      {!loaded && <div className="absolute inset-0 shimmer" />}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={alt}
        loading="lazy"
        decoding="async"
        onLoad={() => setLoaded(true)}
        onError={() => setErrored(true)}
        onClick={onClick}
        className={`w-full h-full object-cover transition-all duration-500 ease-out
          ${loaded ? 'opacity-100 scale-100' : 'opacity-0 scale-105'}
          ${onClick ? 'cursor-zoom-in' : ''}`}
      />
    </div>
  )
}
