'use client'
// ThunderBots Smart Shop Assistant — Customer page (independent product)
//
// No login, no dashboard chrome — this is exactly what opens when a
// customer scans the shop's QR code.
//
// v3 (Product Image Support): search and browse now render as premium
// image-first cards (ProductCard) instead of text rows — an exact name
// match gets a single featured "found it" card, anything else (typo
// matches, or truly nothing found) renders as a visually rich grid of
// real, live products, never a text-only list. Reservation lines and cart
// lines carry a thumbnail; clicking any product photo opens a full-screen,
// swipeable gallery (ImageLightbox).
import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import {
  Search, ShoppingBag, Loader2, CheckCircle2, ArrowLeft, Plus, Minus, Trash2,
  Clock, Users, History, X, AlertTriangle, BellRing, Sparkles,
} from 'lucide-react'
import { shopAssistantPublicApi } from '@/lib/api/shopAssistantPublic'
import { useShopAssistantPublicWs } from '@/hooks/useShopAssistantWs'
import { ProductCard } from '@/components/shop/ProductCard'
import { ProductImage } from '@/components/shop/ProductImage'
import type {
  ProductMatch, CartLine, ReservationItemPreview, PublicReservation,
} from '@/types/shopAssistant'

// ── localStorage history (no login — this is the only "account" a customer has) ──

function historyKey(slug: string) { return `tb_shop_reservations_${slug}` }

function loadHistoryCodes(slug: string): string[] {
  if (typeof window === 'undefined') return []
  try { return JSON.parse(localStorage.getItem(historyKey(slug)) || '[]') } catch { return [] }
}

function saveHistoryCode(slug: string, code: string) {
  if (typeof window === 'undefined') return
  const existing = loadHistoryCodes(slug)
  if (!existing.includes(code)) {
    localStorage.setItem(historyKey(slug), JSON.stringify([code, ...existing].slice(0, 30)))
  }
}

type View =
  | { name: 'search' }
  | { name: 'cart' }
  | { name: 'partial'; previews: ReservationItemPreview[] }
  | { name: 'name' }
  | { name: 'confirmed'; reservation: PublicReservation }
  | { name: 'history' }

// Narrow, centered wrapper for single-column/form-like steps (cart, name
// entry, confirmation, history) — as opposed to the wide grid used for
// search/browse results.
function Narrow({ children }: { children: React.ReactNode }) {
  return <div className="max-w-md mx-auto">{children}</div>
}

export default function ShopCustomerPage() {
  const { slug } = useParams<{ slug: string }>()

  const { data: shop, isLoading: shopLoading, error: shopError } = useQuery({
    queryKey: ['shop-assistant-public', 'shop', slug],
    queryFn: () => shopAssistantPublicApi.getShop(slug),
    enabled: !!slug,
    retry: false,
  })

  const { data: browseResults, isLoading: browseLoading } = useQuery({
    queryKey: ['shop-assistant-public', 'browse', slug],
    queryFn: () => shopAssistantPublicApi.browseProducts(slug),
    enabled: !!slug,
  })

  const [view, setView] = useState<View>({ name: 'search' })
  const [query, setQuery] = useState('')
  const [matches, setMatches] = useState<ProductMatch[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [cart, setCart] = useState<CartLine[]>([])
  const [customerName, setCustomerName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [unavailableIds, setUnavailableIds] = useState<string[]>([])
  const [totalWaiting, setTotalWaiting] = useState<number | null>(null)

  const patchProduct = (list: ProductMatch[] | null, id: string, patch: Partial<ProductMatch>) =>
    list ? list.map((m) => (m.id === id ? { ...m, ...patch } : m)) : list

  // Live inventory + queue length, so results and the cart never show stale
  // numbers even if another customer books at the same moment.
  useShopAssistantPublicWs(slug ?? null, (event) => {
    if (event.type === 'inventory_update' && 'quantity_available' in event.product && typeof event.product.quantity_available === 'number') {
      const updated = event.product as { id: string; quantity_available: number }
      setMatches((prev) => patchProduct(prev, updated.id, { quantity_available: updated.quantity_available, in_stock: updated.quantity_available > 0 }))
      setCart((prev) => prev.map((c) => (c.product_id === updated.id ? { ...c, quantity_available: updated.quantity_available } : c)))
    }
    if (event.type === 'queue_update') {
      setTotalWaiting(event.total_waiting)
    }
    if (event.type === 'reservation_update' && view.name === 'confirmed' && view.reservation.lookup_code === event.lookup_code) {
      setView((v) => v.name === 'confirmed'
        ? { ...v, reservation: { ...v.reservation, status: event.status, queue_number: event.queue_number, expires_at: event.expires_at ?? v.reservation.expires_at ?? null } }
        : v)
    }
  })

  const runSearch = async () => {
    if (!query.trim()) return
    setSearching(true)
    setError(null)
    try {
      const results = await shopAssistantPublicApi.searchProducts(slug, query.trim())
      setMatches(results)
      setView({ name: 'search' })
    } catch {
      setError('Something went wrong — please try again.')
    } finally {
      setSearching(false)
    }
  }

  const addToCart = (m: ProductMatch, quantity: number) => {
    setCart((prev) => {
      const existing = prev.find((c) => c.product_id === m.id)
      if (existing) {
        return prev.map((c) => c.product_id === m.id ? { ...c, quantity: c.quantity + quantity } : c)
      }
      return [...prev, {
        product_id: m.id, product_name: m.name, quantity, quantity_available: m.quantity_available,
        cover_image_url: m.thumbnail_url,
      }]
    })
  }

  const updateCartQty = (productId: string, quantity: number) => {
    setCart((prev) => prev.map((c) => c.product_id === productId ? { ...c, quantity: Math.max(1, quantity) } : c))
  }

  const removeFromCart = (productId: string) => {
    setCart((prev) => prev.filter((c) => c.product_id !== productId))
  }

  const goToPreview = async () => {
    if (cart.length === 0) return
    setSubmitting(true)
    setError(null)
    try {
      const previews = await shopAssistantPublicApi.previewReservation(
        slug, cart.map((c) => ({ product_id: c.product_id, quantity: c.quantity }))
      )
      const hasIssue = previews.some((p) => p.is_partial || p.is_unavailable)
      setView(hasIssue ? { name: 'partial', previews } : { name: 'name' })
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Could not check availability — please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const acceptAvailableQuantities = (previews: ReservationItemPreview[]) => {
    setCart((prev) => prev
      .map((c) => {
        const p = previews.find((pv) => pv.product_id === c.product_id)
        if (!p) return c
        return { ...c, quantity: p.fulfillable_quantity }
      })
      .filter((c) => c.quantity > 0))
    setView({ name: 'name' })
  }

  const submitReservation = async () => {
    if (!customerName.trim() || cart.length === 0) return
    setSubmitting(true)
    setError(null)
    try {
      const reservation = await shopAssistantPublicApi.createReservation(
        slug, cart.map((c) => ({ product_id: c.product_id, quantity: c.quantity })), customerName.trim()
      )
      saveHistoryCode(slug, reservation.lookup_code)
      setUnavailableIds(reservation.unavailable_product_ids)
      setView({ name: 'confirmed', reservation })
      setCart([])
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Could not complete the reservation — please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (shopLoading) {
    return <CenteredMessage><Loader2 className="w-5 h-5 animate-spin text-white/40" /></CenteredMessage>
  }
  if (shopError || !shop || !shop.is_active) {
    return <CenteredMessage>This shop link isn't available right now.</CenteredMessage>
  }

  const cartCount = cart.reduce((n, c) => n + c.quantity, 0)
  const exactMatch = matches && matches.length > 0 && matches[0].is_exact_match ? matches[0] : null
  const relatedMatches = matches ? (exactMatch ? matches.slice(1) : matches) : null
  const isPureFallback = matches !== null && matches.length > 0 && !exactMatch && matches.every((m) => m.match_score === 0)

  return (
    <div className="min-h-screen bg-[var(--bg)] px-4 sm:px-6 py-8 sm:py-10">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <ShoppingBag className="w-5 h-5 text-[#a5b4fc]" />
            <h1 className="text-lg font-semibold text-white">{shop.name}</h1>
          </div>
          <button
            onClick={() => setView({ name: 'history' })}
            className="flex items-center gap-1 text-xs text-white/40 hover:text-white/70"
          >
            <History className="w-3.5 h-3.5" /> My Reservations
          </button>
        </div>
        {totalWaiting !== null && totalWaiting > 0 && (
          <p className="flex items-center gap-1.5 text-xs text-white/40 mb-2">
            <Users className="w-3 h-3" /> {totalWaiting} customer{totalWaiting === 1 ? '' : 's'} currently in the queue
          </p>
        )}

        {view.name === 'search' && (
          <div className="space-y-5 mt-5">
            <div className="flex gap-2 max-w-xl">
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && runSearch()}
                placeholder="What are you looking for?"
                className="tb2-field w-full text-sm text-white rounded-xl px-3.5 py-3 outline-none placeholder-white/25"
              />
              <button
                onClick={runSearch}
                disabled={searching || !query.trim()}
                className="tb2-btn-primary text-white font-semibold rounded-xl px-4 disabled:opacity-40"
              >
                {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              </button>
              {cartCount > 0 && (
                <button
                  onClick={() => setView({ name: 'cart' })}
                  className="flex items-center gap-1.5 text-sm text-white bg-white/[0.06] border border-white/10 rounded-xl px-4 shrink-0"
                >
                  <ShoppingBag className="w-4 h-4" /> {cartCount}
                </button>
              )}
            </div>
            {error && <p className="text-sm text-red-400">{error}</p>}

            {exactMatch && (
              <div className="max-w-xl animate-scale-in">
                <ProductCard
                  product={exactMatch} featured
                  onAdd={(qty) => addToCart(exactMatch, qty)}
                  onJoinWaitlist={() => setView({ name: 'search' })}
                />
              </div>
            )}

            {relatedMatches && relatedMatches.length > 0 && (
              <div className="animate-slide-up">
                <p className="text-xs font-medium text-white/40 uppercase tracking-wide mb-2.5 flex items-center gap-1.5">
                  {isPureFallback ? (
                    <><Sparkles className="w-3 h-3" /> Didn't find that — here's what's in stock</>
                  ) : exactMatch ? 'You might also like' : 'Similar products'}
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {relatedMatches.map((m) => (
                    <ProductCard
                      key={m.id} product={m}
                      onAdd={(qty) => addToCart(m, qty)}
                      onJoinWaitlist={() => setView({ name: 'search' })}
                    />
                  ))}
                </div>
              </div>
            )}

            {matches === null && (
              <div>
                <p className="text-xs font-medium text-white/40 uppercase tracking-wide mb-2.5">Browse what's here</p>
                {browseLoading ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {[...Array(6)].map((_, i) => <div key={i} className="shop-card rounded-2xl aspect-[3/4] shimmer" />)}
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {(browseResults ?? []).map((m) => (
                      <ProductCard key={m.id} product={m} onAdd={(qty) => addToCart(m, qty)} onJoinWaitlist={() => setView({ name: 'search' })} />
                    ))}
                    {(browseResults ?? []).length === 0 && (
                      <p className="text-sm text-white/30 col-span-full py-10 text-center">This shop hasn't added any products yet.</p>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {view.name === 'cart' && (
          <Narrow>
            <CartView
              cart={cart} error={error} submitting={submitting}
              onBack={() => setView({ name: 'search' })}
              onUpdateQty={updateCartQty} onRemove={removeFromCart} onContinue={goToPreview}
            />
          </Narrow>
        )}

        {view.name === 'partial' && (
          <Narrow>
            <PartialView
              previews={view.previews}
              onBack={() => setView({ name: 'cart' })}
              onAccept={() => acceptAvailableQuantities(view.previews)}
            />
          </Narrow>
        )}

        {view.name === 'name' && (
          <Narrow>
            <div className="space-y-4">
              <BackRow onBack={() => setView({ name: 'cart' })} label="Almost done" />
              <p className="text-sm text-white/70">What's your name?</p>
              <input
                autoFocus
                value={customerName}
                onChange={(e) => setCustomerName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && submitReservation()}
                placeholder="Your name"
                className="tb2-field w-full text-sm text-white rounded-xl px-3.5 py-3 outline-none placeholder-white/25"
              />
              {error && <p className="text-sm text-red-400">{error}</p>}
              <button
                onClick={submitReservation}
                disabled={submitting || !customerName.trim()}
                className="tb2-btn-primary text-white font-semibold rounded-xl px-4 py-3 w-full disabled:opacity-40"
              >
                {submitting ? 'Reserving…' : 'Reserve'}
              </button>
            </div>
          </Narrow>
        )}

        {view.name === 'confirmed' && (
          <Narrow>
            <ConfirmedView
              slug={slug}
              reservation={view.reservation}
              unavailableIds={unavailableIds}
              onNewSearch={() => { setQuery(''); setMatches(null); setView({ name: 'search' }) }}
              onUpdated={(r) => setView({ name: 'confirmed', reservation: r })}
            />
          </Narrow>
        )}

        {view.name === 'history' && (
          <Narrow>
            <HistoryView slug={slug} onBack={() => setView({ name: 'search' })} />
          </Narrow>
        )}
      </div>
    </div>
  )
}

function BackRow({ onBack, label }: { onBack: () => void; label: string }) {
  return (
    <button onClick={onBack} className="flex items-center gap-1.5 text-xs text-white/40 hover:text-white/70 mb-1">
      <ArrowLeft className="w-3.5 h-3.5" /> {label}
    </button>
  )
}

function WaitlistJoinButton({ productId, productName }: { productId: string; productName: string }) {
  const { slug } = useParams<{ slug: string }>()
  const [joined, setJoined] = useState(false)
  const [joining, setJoining] = useState(false)
  const [name, setName] = useState('')
  const [showNameField, setShowNameField] = useState(false)

  if (joined) {
    return <p className="text-xs text-emerald-400">You're on the waiting list for {productName} — we'll notify you here if it becomes available.</p>
  }
  if (showNameField) {
    return (
      <div className="flex gap-2">
        <input
          autoFocus value={name} onChange={(e) => setName(e.target.value)}
          placeholder="Your name" className="tb2-field flex-1 text-xs text-white rounded-lg px-3 py-2 outline-none placeholder-white/25"
        />
        <button
          disabled={joining || !name.trim()}
          onClick={async () => {
            setJoining(true)
            try {
              const entry = await shopAssistantPublicApi.joinWaitlist(slug, productId, 1, name.trim())
              saveHistoryCode(slug, entry.lookup_code) // reuse the same local list; harmless if it's a waitlist code
              setJoined(true)
            } finally { setJoining(false) }
          }}
          className="tb2-btn-primary text-white text-xs font-semibold rounded-lg px-3 py-2 disabled:opacity-40"
        >
          {joining ? '…' : 'Join'}
        </button>
      </div>
    )
  }
  return (
    <button onClick={() => setShowNameField(true)} className="flex items-center gap-1.5 text-xs text-[#a5b4fc] hover:underline">
      <BellRing className="w-3.5 h-3.5" /> Notify me when back in stock
    </button>
  )
}

function CartView({
  cart, error, submitting, onBack, onUpdateQty, onRemove, onContinue,
}: {
  cart: CartLine[]; error: string | null; submitting: boolean
  onBack: () => void; onUpdateQty: (id: string, qty: number) => void; onRemove: (id: string) => void; onContinue: () => void
}) {
  if (cart.length === 0) {
    return (
      <div className="space-y-3">
        <BackRow onBack={onBack} label="Your cart" />
        <p className="text-sm text-white/50">Your cart is empty — search for a product to add it.</p>
      </div>
    )
  }
  return (
    <div className="space-y-3">
      <BackRow onBack={onBack} label="Your cart" />
      {cart.map((c) => (
        <div key={c.product_id} className="flex items-center gap-3 rounded-xl bg-white/[0.04] border border-white/10 px-3 py-3">
          <ProductImage src={c.cover_image_url} alt={c.product_name} className="w-12 h-12 shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="text-sm text-white truncate">{c.product_name}</p>
            <p className="text-xs text-white/40">{c.quantity_available} available</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button onClick={() => onUpdateQty(c.product_id, c.quantity - 1)} className="w-7 h-7 rounded-lg bg-white/[0.06] border border-white/10 text-white"><Minus className="w-3 h-3 mx-auto" /></button>
            <span className="text-sm text-white font-semibold w-6 text-center">{c.quantity}</span>
            <button onClick={() => onUpdateQty(c.product_id, c.quantity + 1)} className="w-7 h-7 rounded-lg bg-white/[0.06] border border-white/10 text-white"><Plus className="w-3 h-3 mx-auto" /></button>
            <button onClick={() => onRemove(c.product_id)} className="w-7 h-7 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 ml-1"><Trash2 className="w-3 h-3 mx-auto" /></button>
          </div>
        </div>
      ))}
      {error && <p className="text-sm text-red-400">{error}</p>}
      <button
        onClick={onContinue}
        disabled={submitting}
        className="tb2-btn-primary text-white font-semibold rounded-xl px-4 py-3 w-full disabled:opacity-40"
      >
        {submitting ? 'Checking availability…' : 'Continue'}
      </button>
    </div>
  )
}

function PartialView({
  previews, onBack, onAccept,
}: { previews: ReservationItemPreview[]; onBack: () => void; onAccept: () => void }) {
  return (
    <div className="space-y-3">
      <BackRow onBack={onBack} label="Availability" />
      <div className="rounded-xl bg-amber-500/[0.06] border border-amber-500/20 px-4 py-3 flex gap-2">
        <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
        <p className="text-xs text-amber-200/80">Some items in your cart aren't fully available. Here's what we can actually hold for you right now.</p>
      </div>
      {previews.map((p) => (
        <div key={p.product_id} className="rounded-xl bg-white/[0.04] border border-white/10 px-4 py-3">
          <p className="text-sm text-white">{p.product_name}</p>
          <p className="text-xs text-white/40 mt-0.5">
            Requested {p.requested_quantity} — {p.is_unavailable ? 'none available' : `${p.fulfillable_quantity} available`}
          </p>
          {p.is_unavailable && <WaitlistJoinButton productId={p.product_id} productName={p.product_name} />}
        </div>
      ))}
      <button onClick={onAccept} className="tb2-btn-primary text-white font-semibold rounded-xl px-4 py-3 w-full">
        Reserve what's available
      </button>
    </div>
  )
}

function Countdown({ expiresAt }: { expiresAt: string }) {
  const [remaining, setRemaining] = useState(() => new Date(expiresAt).getTime() - Date.now())
  useEffect(() => {
    const id = setInterval(() => setRemaining(new Date(expiresAt).getTime() - Date.now()), 1000)
    return () => clearInterval(id)
  }, [expiresAt])
  if (remaining <= 0) return <span className="text-red-400">Hold expired</span>
  const mins = Math.floor(remaining / 60000)
  const secs = Math.floor((remaining % 60000) / 1000)
  return <span>{mins}:{secs.toString().padStart(2, '0')} remaining</span>
}

function statusLabel(status: string): string {
  return { pending: 'Pending', confirmed: 'Confirmed', ready: 'Ready for pickup', completed: 'Completed', cancelled: 'Cancelled', expired: 'Expired' }[status] || status
}

function ConfirmedView({
  slug, reservation, unavailableIds, onNewSearch, onUpdated,
}: {
  slug: string; reservation: PublicReservation; unavailableIds: string[]
  onNewSearch: () => void; onUpdated: (r: PublicReservation) => void
}) {
  const [cancelling, setCancelling] = useState(false)
  const isActive = ['pending', 'confirmed', 'ready'].includes(reservation.status)

  const cancel = async () => {
    if (!confirm('Cancel this reservation?')) return
    setCancelling(true)
    try {
      const updated = await shopAssistantPublicApi.cancelReservation(slug, reservation.lookup_code)
      onUpdated(updated)
    } finally {
      setCancelling(false)
    }
  }

  return (
    <div className="rounded-2xl bg-emerald-500/[0.06] border border-emerald-500/20 p-6 text-center space-y-3">
      <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto" />
      <p className="text-white font-semibold">{statusLabel(reservation.status)}</p>
      <div className="space-y-2">
        {reservation.items.map((it) => (
          <div key={it.product_id} className="flex items-center gap-2.5 bg-white/[0.03] rounded-lg px-3 py-2 text-left">
            <ProductImage src={it.cover_image_url} alt={it.product_name} className="w-9 h-9 shrink-0" />
            <p className="text-xs text-white/70">
              {it.product_name} × {it.quantity}{it.quantity < it.requested_quantity ? ` (of ${it.requested_quantity} requested)` : ''}
            </p>
          </div>
        ))}
      </div>
      <p className="text-2xl font-bold text-white tracking-wide mt-2">{reservation.queue_token}</p>
      {reservation.queue_position !== null && isActive && (
        <p className="flex items-center justify-center gap-1.5 text-xs text-white/50">
          <Users className="w-3.5 h-3.5" /> Position {reservation.queue_position} in queue
        </p>
      )}
      {reservation.expires_at && isActive && (
        <p className="flex items-center justify-center gap-1.5 text-xs text-amber-300/80">
          <Clock className="w-3.5 h-3.5" /> <Countdown expiresAt={reservation.expires_at} />
        </p>
      )}
      {reservation.is_partial && (
        <p className="text-xs text-amber-300/80">This is a partial reservation — some quantity wasn't available.</p>
      )}
      {unavailableIds.length > 0 && (
        <p className="text-xs text-white/40">Some items couldn't be reserved at all — search for them again to join the waiting list.</p>
      )}
      <p className="text-xs text-white/40">Show this token at the counter</p>
      {isActive && (
        <button
          onClick={cancel}
          disabled={cancelling}
          className="flex items-center gap-1.5 text-xs text-red-400 hover:underline mx-auto mt-2 disabled:opacity-40"
        >
          <X className="w-3.5 h-3.5" /> {cancelling ? 'Cancelling…' : 'Cancel reservation'}
        </button>
      )}
      <button onClick={onNewSearch} className="text-xs text-[#a5b4fc] hover:underline mt-3 block mx-auto">
        Search for something else
      </button>
    </div>
  )
}

function HistoryView({ slug, onBack }: { slug: string; onBack: () => void }) {
  const codes = useMemo(() => loadHistoryCodes(slug), [slug])
  const { data, isLoading } = useQuery({
    queryKey: ['shop-assistant-public', 'history', slug, codes],
    queryFn: () => shopAssistantPublicApi.getReservationHistory(slug, codes),
    enabled: codes.length > 0,
  })

  return (
    <div className="space-y-3">
      <BackRow onBack={onBack} label="My Reservations" />
      {codes.length === 0 && <p className="text-sm text-white/50">No reservations yet on this device.</p>}
      {isLoading && <Loader2 className="w-5 h-5 animate-spin text-white/40 mx-auto" />}
      {data?.map((r) => (
        <div key={r.lookup_code} className="rounded-xl bg-white/[0.04] border border-white/10 px-4 py-3">
          <div className="flex items-center justify-between">
            <p className="text-sm text-white font-semibold">{r.queue_token}</p>
            <span className="text-xs text-white/40">{statusLabel(r.status)}</span>
          </div>
          <div className="space-y-1.5 mt-1.5">
            {r.items.map((it) => (
              <div key={it.product_id} className="flex items-center gap-2">
                <ProductImage src={it.cover_image_url} alt={it.product_name} className="w-6 h-6 shrink-0" />
                <p className="text-xs text-white/50">{it.product_name} × {it.quantity}</p>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function CenteredMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[var(--bg)] flex items-center justify-center px-5 text-center text-sm text-white/50">
      {children}
    </div>
  )
}
