// ThunderBots Smart Shop Assistant — Types (independent product)

export interface Shop {
  id: string
  name: string
  public_slug: string
  public_url: string
  is_active: boolean
  reservation_timeout_minutes: number
  low_stock_threshold: number
}

// NEW — Product Image Support
export interface ProductImage {
  id: string
  url: string
  thumbnail_url: string
  width: number
  height: number
  is_cover: boolean
  sort_order: number
}

export interface ShopProduct {
  id: string
  name: string
  sku: string | null
  category: string | null
  brand: string | null
  price: number | null
  quantity_available: number
  low_stock_threshold: number | null
  reorder_quantity: number | null
  images: ProductImage[]
}

export type ReservationStatus = 'pending' | 'confirmed' | 'ready' | 'completed' | 'cancelled' | 'expired'

export interface ReservationItem {
  product_id: string
  product_name: string
  requested_quantity: number
  quantity: number
  cover_image_url?: string | null
}

// Admin-facing — includes full lifecycle timestamps.
export interface ShopReservation {
  id: string
  customer_name: string
  status: ReservationStatus
  queue_token: string
  queue_number: number
  lookup_code: string
  is_partial: boolean
  expires_at: string | null
  confirmed_at: string | null
  ready_at: string | null
  completed_at: string | null
  cancelled_at: string | null
  cancelled_reason: string | null
  created_at: string
  items: ReservationItem[]
}

// Customer-facing — no customer_name, adds queue_position.
export interface PublicReservation {
  lookup_code: string
  queue_token: string
  queue_number: number
  queue_position: number | null
  status: ReservationStatus
  is_partial: boolean
  expires_at: string | null
  items: ReservationItem[]
  unavailable_product_ids: string[]
}

export interface ProductMatch {
  id: string
  name: string
  sku: string | null
  category: string | null
  brand: string | null
  price: number | null
  quantity_available: number
  in_stock: boolean
  match_score: number
  is_exact_match: boolean
  cover_image_url: string | null
  thumbnail_url: string | null
  images: ProductImage[]
}

export interface ReservationItemPreview {
  product_id: string
  product_name: string
  requested_quantity: number
  fulfillable_quantity: number
  quantity_available: number
  is_partial: boolean
  is_unavailable: boolean
}

export interface CartLine {
  product_id: string
  product_name: string
  quantity: number
  quantity_available: number
  cover_image_url?: string | null
}

export type WaitlistStatus = 'waiting' | 'notified' | 'fulfilled' | 'cancelled'

export interface WaitlistEntry {
  id: string
  product_id: string
  product_name: string
  customer_name: string
  quantity_requested: number
  status: WaitlistStatus
  lookup_code: string
  created_at: string
  notified_at: string | null
}

export interface PublicWaitlistEntry {
  lookup_code: string
  product_id: string
  product_name: string
  quantity_requested: number
  status: WaitlistStatus
  fulfilled_reservation_lookup_code?: string | null
}

// ── AI Inventory Intelligence ──────────────────────────────────────────────

export interface LowStockAlert {
  product_id: string
  product_name: string
  quantity_available: number
  threshold: number
  severity: 'low' | 'out_of_stock'
}

export interface OutOfStockPrediction {
  product_id: string
  product_name: string
  quantity_available: number
  avg_daily_demand: number
  estimated_days_to_stockout: number
}

export interface MoverStat {
  product_id: string
  product_name: string
  quantity_available: number
  units_sold: number
  window_days: number
}

export interface DeadStockItem {
  product_id: string
  product_name: string
  quantity_available: number
  days_since_last_sale: number | null
}

export interface ReorderSuggestion {
  product_id: string
  product_name: string
  quantity_available: number
  threshold: number
  avg_daily_demand: number
  suggested_reorder_quantity: number
}

export interface DemandTrendPoint {
  date: string
  units: number
}

export interface InventoryHealth {
  total_products: number
  healthy_count: number
  low_stock_count: number
  out_of_stock_count: number
  dead_stock_count: number
  health_score: number
}

export interface MovementRecord {
  id: string
  product_id: string
  product_name?: string
  event_type: string
  quantity_delta: number
  units: number
  quantity_before: number
  quantity_after: number
  reference_id: string | null
  created_at: string
}

// ── Realtime ────────────────────────────────────────────────────────────────

export type ShopAssistantWSEvent =
  | {
      type: 'inventory_update'
      product:
        | (Partial<Omit<ShopProduct, 'images'>> & { id: string; deleted?: boolean; cover_image_url?: string | null; image_count?: number })
        | { id: string; deleted: true }
    }
  | { type: 'booking_update'; reservation: ShopReservation }
  | { type: 'reservation_update'; lookup_code: string; status: ReservationStatus; queue_token: string; queue_number: number; expires_at?: string | null }
  | { type: 'waitlist_notification'; lookup_code: string; queue_token: string; queue_number: number; status: string }
  | { type: 'waitlist_update'; lookup_code: string; queue_token: string; queue_number: number; status: string }
  | { type: 'queue_update'; total_waiting: number }
  | { type: 'inventory_alert'; product_id: string; product_name: string; quantity_available: number; threshold: number; severity: 'low' | 'out_of_stock' }
