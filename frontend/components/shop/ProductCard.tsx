'use client'
// ThunderBots Smart Shop Assistant — ProductCard (NEW)
//
// The one card component used everywhere a customer browses products:
// exact-match search result, similar-products grid, related-products rail,
// and general browse. Never renders text-only — always shows the image
// slot (or the placeholder inside ProductImage) alongside name/price/
// brand/category/stock and a Reserve action.
import { useState } from 'react'
import { Plus, Minus, ShoppingBag, BellRing, Images } from 'lucide-react'
import { ProductImage } from './ProductImage'
import { ImageLightbox } from './ImageLightbox'
import type { ProductMatch } from '@/types/shopAssistant'

export function ProductCard({
  product, onAdd, onJoinWaitlist, featured = false,
}: {
  product: ProductMatch
  onAdd: (quantity: number) => void
  onJoinWaitlist?: () => void
  featured?: boolean
}) {
  const [qty, setQty] = useState(1)
  const [lightboxOpen, setLightboxOpen] = useState(false)
  const max = product.quantity_available
  const productImages = product.images ?? []
  const gallery = productImages.length > 0
    ? productImages
    : product.cover_image_url ? [{ url: product.cover_image_url, thumbnail_url: product.thumbnail_url ?? product.cover_image_url }] : []

  return (
    <div className={`shop-card rounded-2xl overflow-hidden flex flex-col ${featured ? 'sm:flex-row' : ''}`}>
      <div className={`relative ${featured ? 'sm:w-56 shrink-0' : ''}`}>
        <ProductImage
          src={product.thumbnail_url}
          alt={product.name}
          rounded="rounded-none"
          className={featured ? 'h-48 sm:h-full w-full' : 'aspect-square w-full'}
          onClick={gallery.length > 0 ? () => setLightboxOpen(true) : undefined}
        />
        {gallery.length > 1 && (
          <span className="absolute bottom-2 right-2 flex items-center gap-1 text-[10px] text-white bg-black/50 backdrop-blur-sm rounded-full px-2 py-0.5">
            <Images className="w-3 h-3" /> {gallery.length}
          </span>
        )}
        {!product.in_stock && (
          <span className="absolute top-2 left-2 text-[10px] font-semibold text-white bg-red-500/80 backdrop-blur-sm rounded-full px-2 py-0.5">
            Out of stock
          </span>
        )}
      </div>

      <div className="p-3.5 flex flex-col gap-1.5 flex-1 min-w-0">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-white truncate">{product.name}</p>
          <p className="text-[11px] text-white/40 truncate">
            {[product.brand, product.category].filter(Boolean).join(' · ') || '\u00A0'}
          </p>
        </div>

        <div className="flex items-center justify-between mt-0.5">
          {product.price !== null ? (
            <span className="text-base font-bold text-white">${product.price.toFixed(2)}</span>
          ) : <span />}
          {product.in_stock && (
            <span className="text-[11px] text-emerald-400">{max} in stock</span>
          )}
        </div>

        <div className="mt-auto pt-2">
          {product.in_stock ? (
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 bg-white/[0.06] border border-white/10 rounded-lg px-1">
                <button onClick={() => setQty((q) => Math.max(1, q - 1))} className="w-6 h-6 flex items-center justify-center text-white/70 hover:text-white">
                  <Minus className="w-3 h-3" />
                </button>
                <span className="text-xs text-white font-medium w-4 text-center">{qty}</span>
                <button onClick={() => setQty((q) => Math.min(max, q + 1))} className="w-6 h-6 flex items-center justify-center text-white/70 hover:text-white">
                  <Plus className="w-3 h-3" />
                </button>
              </div>
              <button
                onClick={() => onAdd(qty)}
                className="tb2-btn-primary flex-1 flex items-center justify-center gap-1.5 text-white text-xs font-semibold rounded-lg py-2 active:scale-95 transition-transform"
              >
                <ShoppingBag className="w-3.5 h-3.5" /> Reserve
              </button>
            </div>
          ) : onJoinWaitlist ? (
            <button
              onClick={onJoinWaitlist}
              className="w-full flex items-center justify-center gap-1.5 text-xs text-[#a5b4fc] border border-[#6366f1]/30 bg-[#6366f1]/[0.08] rounded-lg py-2 hover:bg-[#6366f1]/[0.14] active:scale-95 transition-all"
            >
              <BellRing className="w-3.5 h-3.5" /> Notify me
            </button>
          ) : null}
        </div>
      </div>

      {lightboxOpen && (
        <ImageLightbox
          images={gallery}
          title={product.name}
          onClose={() => setLightboxOpen(false)}
        />
      )}
    </div>
  )
}
