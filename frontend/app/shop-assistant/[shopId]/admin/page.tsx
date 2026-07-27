'use client'
// ThunderBots Smart Shop Assistant — Shop Admin (independent product)
//
// The one page a shop owner needs: Live Inventory + Live Customer Bookings
// + Waiting List + AI Inventory Intelligence + this shop's QR code.
//
// v2 adds the Smart Reservation System's full lifecycle (confirm / ready /
// complete / cancel, partial-reservation flags, queue numbers) and the AI
// Inventory Intelligence dashboard — every number on it comes straight from
// shop_inventory_intelligence_service, which reads only the live product
// table and the append-only movement ledger.
import { useMemo, useRef, useState } from 'react'
import { useParams } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  QrCode, Plus, Trash2, Pencil, Check, X, Download, Upload,
  Sheet as SheetIcon, RefreshCw, Package, Users, Store, ExternalLink,
  Clock, BellRing, TrendingUp, TrendingDown, AlertTriangle, Sparkles,
  Settings as SettingsIcon, Activity, Archive,
} from 'lucide-react'
import Link from 'next/link'
import { Card, Badge } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input, FieldLabel } from '@/components/ui/Field'
import { SubPageBar } from '@/components/ui/TopBar'
import { Footer } from '@/components/ui/Footer'
import { useToast } from '@/components/ui/Toast'
import { shopAssistantApi } from '@/lib/api/shopAssistant'
import { useShopAssistantAdminWs } from '@/hooks/useShopAssistantWs'
import { ProductImage } from '@/components/shop/ProductImage'
import { ProductImageManager } from '@/components/shop/ProductImageManager'
import type {
  ShopProduct, ShopReservation, WaitlistEntry, ReservationStatus,
} from '@/types/shopAssistant'

const STATUS_TONE: Record<ReservationStatus, 'warning' | 'accent' | 'cyan' | 'success' | 'danger' | 'default'> = {
  pending: 'warning', confirmed: 'accent', ready: 'cyan', completed: 'success', cancelled: 'danger', expired: 'danger',
}

export default function ShopAdminPage() {
  const { shopId } = useParams<{ shopId: string }>()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [qrSvg, setQrSvg] = useState<string | null>(null)
  const [showQr, setShowQr] = useState(false)
  const [showSettings, setShowSettings] = useState(false)

  const { data: shop } = useQuery({
    queryKey: ['shop-assistant', 'shop', shopId],
    queryFn: () => shopAssistantApi.getShop(shopId),
    enabled: !!shopId,
  })

  const { data: products } = useQuery({
    queryKey: ['shop-assistant', 'products', shopId],
    queryFn: () => shopAssistantApi.listProducts(shopId),
    enabled: !!shopId,
  })

  const { data: reservations } = useQuery({
    queryKey: ['shop-assistant', 'reservations', shopId],
    queryFn: () => shopAssistantApi.listReservations(shopId),
    enabled: !!shopId,
  })

  const { data: waitlist } = useQuery({
    queryKey: ['shop-assistant', 'waitlist', shopId],
    queryFn: () => shopAssistantApi.listWaitlist(shopId, 'waiting'),
    enabled: !!shopId,
  })

  // Realtime — every event patches the react-query cache directly so every
  // panel updates instantly, whether the change came from this browser tab,
  // another admin tab, or a customer on the public page.
  useShopAssistantAdminWs(shopId ?? null, (event) => {
    if (event.type === 'inventory_update') {
      queryClient.setQueryData<ShopProduct[]>(['shop-assistant', 'products', shopId], (old) => {
        if (!old) return old
        const incoming = event.product as any
        if (incoming.deleted) return old.filter((p) => p.id !== incoming.id)
        const existing = old.find((p) => p.id === incoming.id)
        // The websocket payload doesn't always carry `images` (some backend
        // events only patch price/quantity/etc). Fall back to whatever we
        // already have cached, and only ever land on `[]` — never
        // `undefined` — so every `.images` access downstream stays safe.
        const merged = { ...existing, ...incoming, images: incoming.images ?? existing?.images ?? [] }
        return existing ? old.map((p) => (p.id === incoming.id ? merged : p)) : [...old, merged]
      })
      queryClient.invalidateQueries({ queryKey: ['shop-assistant', 'intelligence', shopId] })
    } else if (event.type === 'booking_update') {
      queryClient.setQueryData<ShopReservation[]>(['shop-assistant', 'reservations', shopId], (old) => {
        if (!old) return old
        const exists = old.some((r) => r.id === event.reservation.id)
        return exists
          ? old.map((r) => (r.id === event.reservation.id ? event.reservation : r))
          : [event.reservation, ...old]
      })
    } else if (event.type === 'waitlist_update') {
      queryClient.invalidateQueries({ queryKey: ['shop-assistant', 'waitlist', shopId] })
    } else if (event.type === 'inventory_alert') {
      toast('error', `Low stock: ${event.product_name} (${event.quantity_available} left)`)
    }
  })

  const pendingReservations = useMemo(
    () => (reservations ?? []).filter((r) => r.status === 'pending'),
    [reservations]
  )

  const toggleQr = async () => {
    if (!showQr && !qrSvg) {
      try {
        const svg = await shopAssistantApi.fetchQrSvg(shopId)
        setQrSvg(svg)
      } catch {
        toast('error', 'Could not load QR code')
        return
      }
    }
    setShowQr((v) => !v)
  }

  return (
    <div className="min-h-screen flex flex-col">
      <SubPageBar
        backHref="/shop-assistant"
        crumb={shop?.name ?? 'Shop Admin'}
        crumbIcon={<Store size={14} />}
        right={
          <>
            {shop?.public_url && (
              <a href={shop.public_url} target="_blank" rel="noreferrer">
                <Button variant="ghost" size="sm" icon={<ExternalLink className="w-3.5 h-3.5" />}>
                  Customer Page
                </Button>
              </a>
            )}
            <Link href={`/shop-assistant/${shopId}/advisor`}>
              <Button variant="secondary" size="sm" icon={<Sparkles className="w-3.5 h-3.5" />}>
                AI Business Advisor
              </Button>
            </Link>
            <Button variant="ghost" size="sm" icon={<SettingsIcon className="w-3.5 h-3.5" />} onClick={() => setShowSettings((v) => !v)}>
              Settings
            </Button>
            <Button variant="secondary" size="sm" icon={<QrCode className="w-3.5 h-3.5" />} onClick={toggleQr}>
              {showQr ? 'Hide QR' : 'Show QR'}
            </Button>
          </>
        }
      />

      <div className="flex-1 px-4 sm:px-5 py-6 sm:py-8 max-w-6xl mx-auto w-full">
        <p className="text-xs text-white/35 mb-6 truncate">{shop?.public_url}</p>

        {showSettings && shop && <SettingsPanel shopId={shopId} shop={shop} onClose={() => setShowSettings(false)} />}

        {showQr && qrSvg && (
          <Card className="p-6 mb-6 flex flex-col items-center gap-3">
            <div className="w-52 h-52 bg-white rounded-xl p-3" dangerouslySetInnerHTML={{ __html: qrSvg }} />
            <p className="text-xs text-white/40 text-center">Print this at the counter — scanning it opens {shop?.name}'s assistant</p>
          </Card>
        )}

        <IntelligencePanel shopId={shopId} />

        <div className="grid md:grid-cols-2 gap-6 mt-6">
          <InventoryPanel shopId={shopId} products={products ?? []} fileInputRef={fileInputRef} />
          <BookingsPanel shopId={shopId} reservations={reservations ?? []} pendingCount={pendingReservations.length} />
        </div>

        <div className="mt-6">
          <WaitlistPanel shopId={shopId} entries={waitlist ?? []} />
        </div>
      </div>

      <Footer />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Settings
// ─────────────────────────────────────────────────────────────────────────────

function SettingsPanel({ shopId, shop, onClose }: { shopId: string; shop: any; onClose: () => void }) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [timeout_, setTimeout_] = useState(shop.reservation_timeout_minutes)
  const [threshold, setThreshold] = useState(shop.low_stock_threshold)
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    try {
      await shopAssistantApi.updateShopSettings(shopId, {
        reservation_timeout_minutes: timeout_, low_stock_threshold: threshold,
      })
      queryClient.invalidateQueries({ queryKey: ['shop-assistant', 'shop', shopId] })
      toast('success', 'Settings saved')
      onClose()
    } catch {
      toast('error', 'Could not save settings')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="p-4 mb-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-white flex items-center gap-2"><SettingsIcon className="w-4 h-4 text-[#a5b4fc]" /> Shop Settings</h2>
        <button onClick={onClose} className="text-white/35 hover:text-white/80"><X className="w-4 h-4" /></button>
      </div>
      <div className="grid sm:grid-cols-2 gap-4">
        <div>
          <FieldLabel>Reservation hold timeout (minutes)</FieldLabel>
          <Input type="number" min={0} value={timeout_} onChange={(e) => setTimeout_(Math.max(0, parseInt(e.target.value) || 0))} />
          <p className="text-[11px] text-white/35 mt-1">How long a pending reservation holds stock before it auto-expires. 0 disables auto-expiry.</p>
        </div>
        <div>
          <FieldLabel>Default low-stock threshold</FieldLabel>
          <Input type="number" min={0} value={threshold} onChange={(e) => setThreshold(Math.max(0, parseInt(e.target.value) || 0))} />
          <p className="text-[11px] text-white/35 mt-1">Products at or below this quantity trigger a low-stock alert (per-product overrides available below).</p>
        </div>
      </div>
      <Button size="sm" className="mt-3" loading={saving} onClick={save}>Save settings</Button>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// AI Inventory Intelligence
// ─────────────────────────────────────────────────────────────────────────────

function IntelligencePanel({ shopId }: { shopId: string }) {
  const { data: insights } = useQuery({
    queryKey: ['shop-assistant', 'intelligence', shopId, 'insights'],
    queryFn: () => shopAssistantApi.getInventoryInsights(shopId),
    enabled: !!shopId,
  })
  const { data: health } = useQuery({
    queryKey: ['shop-assistant', 'intelligence', shopId, 'health'],
    queryFn: () => shopAssistantApi.getInventoryHealth(shopId),
    enabled: !!shopId,
  })
  const { data: lowStock } = useQuery({
    queryKey: ['shop-assistant', 'intelligence', shopId, 'low-stock'],
    queryFn: () => shopAssistantApi.getLowStockAlerts(shopId),
    enabled: !!shopId,
  })
  const { data: fastMoving } = useQuery({
    queryKey: ['shop-assistant', 'intelligence', shopId, 'fast-moving'],
    queryFn: () => shopAssistantApi.getFastMovingProducts(shopId, 5),
    enabled: !!shopId,
  })
  const { data: deadStock } = useQuery({
    queryKey: ['shop-assistant', 'intelligence', shopId, 'dead-stock'],
    queryFn: () => shopAssistantApi.getDeadStock(shopId),
    enabled: !!shopId,
  })
  const { data: reorders } = useQuery({
    queryKey: ['shop-assistant', 'intelligence', shopId, 'reorder'],
    queryFn: () => shopAssistantApi.getReorderSuggestions(shopId),
    enabled: !!shopId,
  })

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-white flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-[#a5b4fc]" /> AI Inventory Intelligence
        </h2>
        {health && (
          <Badge tone={health.health_score >= 80 ? 'success' : health.health_score >= 50 ? 'warning' : 'danger'}>
            Health {health.health_score}
          </Badge>
        )}
      </div>

      {insights && insights.insights.length > 0 && (
        <div className="rounded-xl bg-[#6366f1]/[0.06] border border-[#6366f1]/20 p-3 mb-4 space-y-1.5">
          {insights.insights.map((s, i) => (
            <p key={i} className="text-xs text-white/70 flex gap-1.5"><Sparkles className="w-3 h-3 text-[#a5b4fc] flex-shrink-0 mt-0.5" /> {s}</p>
          ))}
        </div>
      )}

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <IntelCard icon={<AlertTriangle className="w-3.5 h-3.5 text-amber-400" />} title="Low Stock / Out of Stock">
          {(lowStock ?? []).length === 0 && <EmptyRow text="All good" />}
          {(lowStock ?? []).slice(0, 5).map((a) => (
            <div key={a.product_id} className="flex items-center justify-between text-xs">
              <span className="text-white/70 truncate">{a.product_name}</span>
              <Badge tone={a.severity === 'out_of_stock' ? 'danger' : 'warning'}>{a.quantity_available}</Badge>
            </div>
          ))}
        </IntelCard>

        <IntelCard icon={<TrendingUp className="w-3.5 h-3.5 text-emerald-400" />} title="Fast Moving">
          {(fastMoving ?? []).length === 0 && <EmptyRow text="No sales data yet" />}
          {(fastMoving ?? []).map((m) => (
            <div key={m.product_id} className="flex items-center justify-between text-xs">
              <span className="text-white/70 truncate">{m.product_name}</span>
              <span className="text-emerald-400 font-medium">{m.units_sold}/{m.window_days}d</span>
            </div>
          ))}
        </IntelCard>

        <IntelCard icon={<Archive className="w-3.5 h-3.5 text-white/40" />} title="Dead Stock">
          {(deadStock ?? []).length === 0 && <EmptyRow text="None" />}
          {(deadStock ?? []).slice(0, 5).map((d) => (
            <div key={d.product_id} className="flex items-center justify-between text-xs">
              <span className="text-white/70 truncate">{d.product_name}</span>
              <span className="text-white/40">{d.days_since_last_sale === null ? 'never sold' : `${d.days_since_last_sale}d idle`}</span>
            </div>
          ))}
        </IntelCard>

        <IntelCard icon={<Activity className="w-3.5 h-3.5 text-cyan-300" />} title="Reorder Suggestions">
          {(reorders ?? []).length === 0 && <EmptyRow text="Nothing to reorder" />}
          {(reorders ?? []).slice(0, 5).map((r) => (
            <div key={r.product_id} className="flex items-center justify-between text-xs">
              <span className="text-white/70 truncate">{r.product_name}</span>
              <span className="text-cyan-300 font-medium">+{r.suggested_reorder_quantity}</span>
            </div>
          ))}
        </IntelCard>
      </div>
    </Card>
  )
}

function IntelCard({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl bg-white/[0.03] border border-white/10 p-3">
      <div className="flex items-center gap-1.5 mb-2">{icon}<h3 className="text-[11px] font-semibold text-white/60 uppercase tracking-wide">{title}</h3></div>
      <div className="space-y-1.5">{children}</div>
    </div>
  )
}

function EmptyRow({ text }: { text: string }) {
  return <p className="text-xs text-white/30">{text}</p>
}

// ─────────────────────────────────────────────────────────────────────────────
// Inventory
// ─────────────────────────────────────────────────────────────────────────────

function InventoryPanel({
  shopId, products, fileInputRef,
}: { shopId: string; products: ShopProduct[]; fileInputRef: React.RefObject<HTMLInputElement> }) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState({
    name: '', sku: '', category: '', brand: '', price: '',
    quantity_available: 0, low_stock_threshold: '', reorder_quantity: '',
  })
  const [editingImages, setEditingImages] = useState<ShopProduct['images']>([])
  const [syncing, setSyncing] = useState<'push' | 'pull' | null>(null)

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['shop-assistant', 'products', shopId] })
    queryClient.invalidateQueries({ queryKey: ['shop-assistant', 'intelligence', shopId] })
  }

  const startAdd = () => {
    setDraft({ name: '', sku: '', category: '', brand: '', price: '', quantity_available: 0, low_stock_threshold: '', reorder_quantity: '' })
    setEditingId(null)
    setAdding(true)
  }

  const startEdit = (p: ShopProduct) => {
    setDraft({
      name: p.name, sku: p.sku ?? '', category: p.category ?? '', brand: p.brand ?? '', price: p.price?.toString() ?? '',
      quantity_available: p.quantity_available,
      low_stock_threshold: p.low_stock_threshold?.toString() ?? '', reorder_quantity: p.reorder_quantity?.toString() ?? '',
    })
    setEditingImages(p.images ?? [])
    setEditingId(p.id)
    setAdding(false)
  }

  const cancelEdit = () => {
    setAdding(false)
    setEditingId(null)
  }

  const save = async () => {
    if (!draft.name.trim()) return
    const body = {
      name: draft.name.trim(), sku: draft.sku || null, category: draft.category || null,
      brand: draft.brand || null, price: draft.price === '' ? null : parseFloat(draft.price),
      quantity_available: draft.quantity_available,
      low_stock_threshold: draft.low_stock_threshold === '' ? null : parseInt(draft.low_stock_threshold),
      reorder_quantity: draft.reorder_quantity === '' ? null : parseInt(draft.reorder_quantity),
    }
    try {
      if (editingId) {
        await shopAssistantApi.updateProduct(shopId, editingId, body)
        cancelEdit()
      } else {
        const created = await shopAssistantApi.createProduct(shopId, body)
        // Jump straight into edit mode on the newly created product so the
        // owner can immediately add images without a second click.
        setAdding(false)
        startEdit(created)
      }
      invalidate()
    } catch {
      toast('error', 'Could not save product')
    }
  }

  const remove = async (id: string) => {
    try {
      await shopAssistantApi.deleteProduct(shopId, id)
      invalidate()
    } catch {
      toast('error', 'Could not delete product')
    }
  }

  const handleImport = async (file: File) => {
    try {
      const summary = await shopAssistantApi.importProducts(shopId, file)
      toast('success', `Imported: ${summary.created} new, ${summary.updated} updated`)
      invalidate()
    } catch (e: any) {
      toast('error', e?.response?.data?.detail || 'Import failed — check the file format')
    }
  }

  const runSync = async (direction: 'push' | 'pull') => {
    setSyncing(direction)
    try {
      const result = direction === 'push'
        ? await shopAssistantApi.pushGoogleSheets(shopId)
        : await shopAssistantApi.pullGoogleSheets(shopId)
      toast('success', direction === 'push' ? `Pushed ${result.pushed} products` : `Synced ${result.total_rows} rows`)
      invalidate()
    } catch (e: any) {
      toast('error', e?.response?.data?.detail || 'Google Sheets is not connected for this shop')
    } finally {
      setSyncing(null)
    }
  }

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Package className="w-4 h-4 text-[#a5b4fc]" />
          <h2 className="text-sm font-semibold text-white">Live Inventory</h2>
        </div>
        <div className="flex items-center gap-1.5">
          <a href={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1${shopAssistantApi.exportProductsUrl(shopId)}`}
             target="_blank" rel="noreferrer">
            <Button variant="ghost" size="sm" icon={<Download className="w-3.5 h-3.5" />}>Export</Button>
          </a>
          <Button variant="ghost" size="sm" icon={<Upload className="w-3.5 h-3.5" />} onClick={() => fileInputRef.current?.click()}>
            Import
          </Button>
          <input
            ref={fileInputRef} type="file" accept=".xlsx" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleImport(f); e.target.value = '' }}
          />
          <Button
            variant="ghost" size="sm" icon={<SheetIcon className="w-3.5 h-3.5" />}
            loading={syncing === 'pull'} onClick={() => runSync('pull')}
          >
            Pull
          </Button>
          <Button
            variant="ghost" size="sm" icon={<RefreshCw className="w-3.5 h-3.5" />}
            loading={syncing === 'push'} onClick={() => runSync('push')}
          >
            Push
          </Button>
        </div>
      </div>

      <div className="space-y-2 max-h-[480px] overflow-y-auto pr-1">
        {products.map((p) =>
          editingId === p.id ? (
            <ProductRowEditor
              key={p.id} draft={draft} setDraft={setDraft} onSave={save} onCancel={cancelEdit}
              shopId={shopId} productId={p.id} images={editingImages} onImagesChange={(imgs) => { setEditingImages(imgs); invalidate() }}
            />
          ) : (
            <div key={p.id} className="flex items-center justify-between gap-2 rounded-xl bg-white/[0.03] border border-white/10 px-3 py-2.5">
              <div className="flex items-center gap-2.5 min-w-0">
                <ProductImage
                  src={((p.images ?? []).find((im) => im.is_cover) ?? (p.images ?? [])[0])?.thumbnail_url}
                  alt={p.name} rounded="rounded-lg" className="w-9 h-9 shrink-0"
                />
                <div className="min-w-0">
                  <p className="text-sm text-white truncate">{p.name}</p>
                  <p className="text-[11px] text-white/35 truncate">{[p.brand, p.sku, p.category].filter(Boolean).join(' · ') || '—'}</p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Badge tone={p.quantity_available > (p.low_stock_threshold ?? 5) ? 'success' : p.quantity_available > 0 ? 'warning' : 'danger'}>{p.quantity_available} left</Badge>
                <button onClick={() => startEdit(p)} className="text-white/35 hover:text-white/80"><Pencil className="w-3.5 h-3.5" /></button>
                <button onClick={() => remove(p.id)} className="text-white/35 hover:text-red-400"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
            </div>
          )
        )}
        {adding && <ProductRowEditor draft={draft} setDraft={setDraft} onSave={save} onCancel={cancelEdit} />}
        {products.length === 0 && !adding && <p className="text-sm text-white/30 py-6 text-center">No products yet</p>}
      </div>

      {!adding && !editingId && (
        <Button variant="secondary" size="sm" icon={<Plus className="w-3.5 h-3.5" />} className="mt-3 w-full" onClick={startAdd} data-tutorial="shop-add-product">
          Add product
        </Button>
      )}
    </Card>
  )
}

function ProductRowEditor({
  draft, setDraft, onSave, onCancel, shopId, productId, images, onImagesChange,
}: {
  draft: { name: string; sku: string; category: string; brand: string; price: string; quantity_available: number; low_stock_threshold: string; reorder_quantity: string }
  setDraft: (d: any) => void
  onSave: () => void
  onCancel: () => void
  shopId?: string
  productId?: string
  images?: ShopProduct['images']
  onImagesChange?: (images: ShopProduct['images']) => void
}) {
  return (
    <div className="rounded-xl bg-white/[0.04] border border-white/15 p-3 space-y-3">
      <Input placeholder="Product name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} autoFocus />
      <div className="grid grid-cols-3 gap-2">
        <Input placeholder="Brand (optional)" value={draft.brand} onChange={(e) => setDraft({ ...draft, brand: e.target.value })} />
        <Input placeholder="Category (optional)" value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })} />
        <Input placeholder="SKU (optional)" value={draft.sku} onChange={(e) => setDraft({ ...draft, sku: e.target.value })} />
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Input
          type="number" min={0} step="0.01" placeholder="Price (optional)" value={draft.price}
          onChange={(e) => setDraft({ ...draft, price: e.target.value })}
        />
        <Input
          type="number" min={0} placeholder="Qty" value={draft.quantity_available}
          onChange={(e) => setDraft({ ...draft, quantity_available: Math.max(0, parseInt(e.target.value) || 0) })}
        />
        <Input
          placeholder="Low stock threshold" value={draft.low_stock_threshold}
          onChange={(e) => setDraft({ ...draft, low_stock_threshold: e.target.value })}
        />
      </div>
      <Input
        placeholder="Reorder quantity (auto-suggested if left blank)" value={draft.reorder_quantity}
        onChange={(e) => setDraft({ ...draft, reorder_quantity: e.target.value })}
      />

      {shopId && productId && onImagesChange ? (
        <ProductImageManager shopId={shopId} productId={productId} images={images ?? []} onImagesChange={onImagesChange} />
      ) : (
        <p className="text-[11px] text-white/30 italic">Save the product first, then you can add photos.</p>
      )}

      <div className="flex gap-2 justify-end">
        <Button size="sm" variant="ghost" icon={<X className="w-3.5 h-3.5" />} onClick={onCancel}>Cancel</Button>
        <Button size="sm" icon={<Check className="w-3.5 h-3.5" />} disabled={!draft.name.trim()} onClick={onSave}>Save</Button>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Bookings (Smart Reservation System)
// ─────────────────────────────────────────────────────────────────────────────

function BookingsPanel({
  shopId, reservations, pendingCount,
}: { shopId: string; reservations: ShopReservation[]; pendingCount: number }) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [busyId, setBusyId] = useState<string | null>(null)
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['shop-assistant', 'reservations', shopId] })

  const runAction = async (id: string, action: (id: string) => Promise<any>, errMsg: string) => {
    setBusyId(id)
    try { await action(id); invalidate() }
    catch { toast('error', errMsg) }
    finally { setBusyId(null) }
  }

  return (
    <Card className="p-4" data-tutorial="shop-reservations">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Users className="w-4 h-4 text-[#a5b4fc]" />
          <h2 className="text-sm font-semibold text-white">Live Customer Bookings</h2>
        </div>
        <Badge tone={pendingCount > 0 ? 'warning' : 'default'}>{pendingCount} pending</Badge>
      </div>

      <div className="space-y-2 max-h-[520px] overflow-y-auto pr-1">
        {reservations.map((r) => (
          <div key={r.id} className="rounded-xl bg-white/[0.03] border border-white/10 px-3 py-2.5">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm text-white truncate">
                  {r.customer_name} <span className="text-white/35">· #{r.queue_number}</span>
                  {r.is_partial && <span className="text-amber-400 text-[10px] ml-1">PARTIAL</span>}
                </p>
                <div className="text-[11px] text-white/40 mt-0.5">
                  {r.items.map((it) => (
                    <span key={it.product_id} className="mr-2">
                      {it.product_name} × {it.quantity}{it.quantity < it.requested_quantity ? ` (of ${it.requested_quantity})` : ''}
                    </span>
                  ))}
                </div>
                <p className="text-[11px] text-white/35 mt-0.5">Token {r.queue_token} · {new Date(r.created_at).toLocaleTimeString()}</p>
              </div>
              <Badge tone={STATUS_TONE[r.status]}>{r.status}</Badge>
            </div>

            {r.status === 'pending' && (
              <div className="flex gap-2 mt-2">
                <Button size="sm" variant="secondary" className="flex-1" loading={busyId === r.id}
                        onClick={() => runAction(r.id, (id) => shopAssistantApi.confirmReservation(shopId, id), 'Could not confirm reservation')}>
                  Confirm
                </Button>
                <Button size="sm" variant="ghost" className="flex-1" loading={busyId === r.id}
                        onClick={() => runAction(r.id, (id) => shopAssistantApi.cancelReservation(shopId, id), 'Could not cancel reservation')}>
                  Cancel
                </Button>
              </div>
            )}
            {r.status === 'confirmed' && (
              <div className="flex gap-2 mt-2">
                <Button size="sm" variant="secondary" className="flex-1" loading={busyId === r.id}
                        onClick={() => runAction(r.id, (id) => shopAssistantApi.markReservationReady(shopId, id), 'Could not mark ready')}>
                  Mark Ready
                </Button>
                <Button size="sm" variant="ghost" className="flex-1" loading={busyId === r.id}
                        onClick={() => runAction(r.id, (id) => shopAssistantApi.cancelReservation(shopId, id), 'Could not cancel reservation')}>
                  Cancel
                </Button>
              </div>
            )}
            {r.status === 'ready' && (
              <div className="flex gap-2 mt-2">
                <Button size="sm" variant="secondary" className="flex-1" loading={busyId === r.id}
                        onClick={() => runAction(r.id, (id) => shopAssistantApi.completeReservation(shopId, id), 'Could not complete reservation')}>
                  Picked Up
                </Button>
                <Button size="sm" variant="ghost" className="flex-1" loading={busyId === r.id}
                        onClick={() => runAction(r.id, (id) => shopAssistantApi.cancelReservation(shopId, id), 'Could not cancel reservation')}>
                  Cancel
                </Button>
              </div>
            )}
          </div>
        ))}
        {reservations.length === 0 && <p className="text-sm text-white/30 py-6 text-center">No bookings yet</p>}
      </div>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Waiting list
// ─────────────────────────────────────────────────────────────────────────────

function WaitlistPanel({ shopId, entries }: { shopId: string; entries: WaitlistEntry[] }) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [busyId, setBusyId] = useState<string | null>(null)

  const cancel = async (id: string) => {
    setBusyId(id)
    try {
      await shopAssistantApi.cancelWaitlistEntry(shopId, id)
      queryClient.invalidateQueries({ queryKey: ['shop-assistant', 'waitlist', shopId] })
    } catch {
      toast('error', 'Could not cancel waitlist entry')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <BellRing className="w-4 h-4 text-[#a5b4fc]" />
          <h2 className="text-sm font-semibold text-white">Waiting List</h2>
        </div>
        <Badge tone={entries.length > 0 ? 'warning' : 'default'}>{entries.length} waiting</Badge>
      </div>
      <div className="space-y-2 max-h-[320px] overflow-y-auto pr-1">
        {entries.map((e) => (
          <div key={e.id} className="flex items-center justify-between gap-2 rounded-xl bg-white/[0.03] border border-white/10 px-3 py-2.5">
            <div className="min-w-0">
              <p className="text-sm text-white truncate">{e.customer_name} <span className="text-white/35">· {e.product_name} × {e.quantity_requested}</span></p>
              <p className="text-[11px] text-white/35 mt-0.5 flex items-center gap-1"><Clock className="w-3 h-3" /> since {new Date(e.created_at).toLocaleString()}</p>
            </div>
            <Button size="sm" variant="ghost" loading={busyId === e.id} onClick={() => cancel(e.id)}>Remove</Button>
          </div>
        ))}
        {entries.length === 0 && <p className="text-sm text-white/30 py-6 text-center">No one is waiting on out-of-stock items right now</p>}
      </div>
    </Card>
  )
}
