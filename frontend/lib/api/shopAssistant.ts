// ============================================================
// ThunderBots — Smart Shop Assistant API Client (admin side)
// Independent product: not part of Workflows/Chatbot, Campaigns, or
// AI Call Agent. Mirrors the exact conventions of lib/api/teams.ts.
// ============================================================
import { apiClient } from './client'
import type {
  Shop, ShopProduct, ShopReservation, WaitlistEntry, ProductImage,
  LowStockAlert, OutOfStockPrediction, MoverStat, DeadStockItem,
  ReorderSuggestion, DemandTrendPoint, InventoryHealth, MovementRecord,
} from '@/types/shopAssistant'

export const shopAssistantApi = {
  listShops: async (): Promise<Shop[]> => {
    const { data } = await apiClient.get('/shop-assistant/shops')
    return data
  },

  createShop: async (name: string): Promise<Shop> => {
    const { data } = await apiClient.post('/shop-assistant/shops', { name })
    return data
  },

  getShop: async (shopId: string): Promise<Shop> => {
    const { data } = await apiClient.get(`/shop-assistant/shops/${shopId}`)
    return data
  },

  updateShopSettings: async (
    shopId: string,
    body: Partial<{ name: string; is_active: boolean; reservation_timeout_minutes: number; low_stock_threshold: number }>
  ): Promise<Shop> => {
    const { data } = await apiClient.patch(`/shop-assistant/shops/${shopId}`, body)
    return data
  },

  fetchQrSvg: async (shopId: string): Promise<string> => {
    const { data } = await apiClient.get(`/shop-assistant/shops/${shopId}/qr`, { responseType: 'text' })
    return data
  },

  listProducts: async (shopId: string): Promise<ShopProduct[]> => {
    const { data } = await apiClient.get(`/shop-assistant/shops/${shopId}/products`)
    return data
  },

  createProduct: async (
    shopId: string,
    body: {
      name: string; sku?: string | null; category?: string | null
      brand?: string | null; price?: number | null; quantity_available: number
      low_stock_threshold?: number | null; reorder_quantity?: number | null
    }
  ): Promise<ShopProduct> => {
    const { data } = await apiClient.post(`/shop-assistant/shops/${shopId}/products`, body)
    return data
  },

  updateProduct: async (
    shopId: string,
    productId: string,
    body: Partial<{
      name: string; sku: string | null; category: string | null
      brand: string | null; price: number | null; quantity_available: number
      low_stock_threshold: number | null; reorder_quantity: number | null
    }>
  ): Promise<ShopProduct> => {
    const { data } = await apiClient.patch(`/shop-assistant/shops/${shopId}/products/${productId}`, body)
    return data
  },

  deleteProduct: async (shopId: string, productId: string): Promise<void> => {
    await apiClient.delete(`/shop-assistant/shops/${shopId}/products/${productId}`)
  },

  exportProductsUrl: (shopId: string) => `/shop-assistant/shops/${shopId}/products/export`,

  // ── Product images (NEW — Product Image Support) ───────────────────────

  uploadProductImages: async (shopId: string, productId: string, files: File[]): Promise<ProductImage[]> => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    const { data } = await apiClient.post(`/shop-assistant/shops/${shopId}/products/${productId}/images`, form)
    return data
  },

  deleteProductImage: async (shopId: string, productId: string, imageId: string): Promise<void> => {
    await apiClient.delete(`/shop-assistant/shops/${shopId}/products/${productId}/images/${imageId}`)
  },

  setCoverImage: async (shopId: string, productId: string, imageId: string): Promise<ProductImage[]> => {
    const { data } = await apiClient.patch(`/shop-assistant/shops/${shopId}/products/${productId}/images/${imageId}/cover`)
    return data
  },

  importProducts: async (shopId: string, file: File): Promise<{ created: number; updated: number; total_rows: number }> => {
    const form = new FormData()
    form.append('file', file)
    const { data } = await apiClient.post(`/shop-assistant/shops/${shopId}/products/import`, form)
    return data
  },

  connectGoogleSheets: async (
    shopId: string,
    body: { spreadsheet_id: string; worksheet_name: string; service_account_json: string }
  ) => {
    const { data } = await apiClient.post(`/shop-assistant/shops/${shopId}/sync/google-sheets`, body)
    return data
  },

  pushGoogleSheets: async (shopId: string) => {
    const { data } = await apiClient.post(`/shop-assistant/shops/${shopId}/sync/google-sheets/push`)
    return data
  },

  pullGoogleSheets: async (shopId: string) => {
    const { data } = await apiClient.post(`/shop-assistant/shops/${shopId}/sync/google-sheets/pull`)
    return data
  },

  // ── Reservations (Smart Reservation System) ──────────────────────────

  listReservations: async (shopId: string, statusFilter?: string): Promise<ShopReservation[]> => {
    const { data } = await apiClient.get(`/shop-assistant/shops/${shopId}/reservations`, {
      params: statusFilter ? { status_filter: statusFilter } : undefined,
    })
    return data
  },

  getReservation: async (shopId: string, reservationId: string): Promise<ShopReservation> => {
    const { data } = await apiClient.get(`/shop-assistant/shops/${shopId}/reservations/${reservationId}`)
    return data
  },

  editReservation: async (
    shopId: string, reservationId: string, items: { product_id: string; quantity: number }[]
  ): Promise<ShopReservation> => {
    const { data } = await apiClient.patch(`/shop-assistant/shops/${shopId}/reservations/${reservationId}`, items)
    return data
  },

  confirmReservation: async (shopId: string, reservationId: string): Promise<ShopReservation> => {
    const { data } = await apiClient.patch(`/shop-assistant/shops/${shopId}/reservations/${reservationId}/confirm`)
    return data
  },

  markReservationReady: async (shopId: string, reservationId: string): Promise<ShopReservation> => {
    const { data } = await apiClient.patch(`/shop-assistant/shops/${shopId}/reservations/${reservationId}/ready`)
    return data
  },

  completeReservation: async (shopId: string, reservationId: string): Promise<ShopReservation> => {
    const { data } = await apiClient.patch(`/shop-assistant/shops/${shopId}/reservations/${reservationId}/complete`)
    return data
  },

  cancelReservation: async (shopId: string, reservationId: string): Promise<ShopReservation> => {
    const { data } = await apiClient.patch(`/shop-assistant/shops/${shopId}/reservations/${reservationId}/cancel`)
    return data
  },

  // ── Waiting list ───────────────────────────────────────────────────────

  listWaitlist: async (shopId: string, statusFilter?: string): Promise<WaitlistEntry[]> => {
    const { data } = await apiClient.get(`/shop-assistant/shops/${shopId}/waitlist`, {
      params: statusFilter ? { status_filter: statusFilter } : undefined,
    })
    return data
  },

  cancelWaitlistEntry: async (shopId: string, entryId: string): Promise<WaitlistEntry> => {
    const { data } = await apiClient.patch(`/shop-assistant/shops/${shopId}/waitlist/${entryId}/cancel`)
    return data
  },

  // ── AI Inventory Intelligence ───────────────────────────────────────────

  getLowStockAlerts: async (shopId: string): Promise<LowStockAlert[]> => {
    const { data } = await apiClient.get(`/shop-assistant/shops/${shopId}/intelligence/low-stock`)
    return data
  },

  getOutOfStockPredictions: async (shopId: string): Promise<OutOfStockPrediction[]> => {
    const { data } = await apiClient.get(`/shop-assistant/shops/${shopId}/intelligence/out-of-stock-predictions`)
    return data
  },

  getFastMovingProducts: async (shopId: string, limit = 10): Promise<MoverStat[]> => {
    const { data } = await apiClient.get(`/shop-assistant/shops/${shopId}/intelligence/fast-moving`, { params: { limit } })
    return data
  },

  getSlowMovingProducts: async (shopId: string, limit = 10): Promise<MoverStat[]> => {
    const { data } = await apiClient.get(`/shop-assistant/shops/${shopId}/intelligence/slow-moving`, { params: { limit } })
    return data
  },

  getDeadStock: async (shopId: string): Promise<DeadStockItem[]> => {
    const { data } = await apiClient.get(`/shop-assistant/shops/${shopId}/intelligence/dead-stock`)
    return data
  },

  getReorderSuggestions: async (shopId: string): Promise<ReorderSuggestion[]> => {
    const { data } = await apiClient.get(`/shop-assistant/shops/${shopId}/intelligence/reorder-suggestions`)
    return data
  },

  getBestSellers: async (shopId: string, limit = 10): Promise<MoverStat[]> => {
    const { data } = await apiClient.get(`/shop-assistant/shops/${shopId}/intelligence/best-sellers`, { params: { limit } })
    return data
  },

  getDemandTrend: async (shopId: string, productId?: string): Promise<DemandTrendPoint[]> => {
    const { data } = await apiClient.get(`/shop-assistant/shops/${shopId}/intelligence/demand-trend`, {
      params: productId ? { product_id: productId } : undefined,
    })
    return data
  },

  getInventoryHealth: async (shopId: string): Promise<InventoryHealth> => {
    const { data } = await apiClient.get(`/shop-assistant/shops/${shopId}/intelligence/health`)
    return data
  },

  getInventoryInsights: async (shopId: string): Promise<{ insights: string[] }> => {
    const { data } = await apiClient.get(`/shop-assistant/shops/${shopId}/intelligence/insights`)
    return data
  },

  getInventoryTimeline: async (shopId: string, limit = 200): Promise<MovementRecord[]> => {
    const { data } = await apiClient.get(`/shop-assistant/shops/${shopId}/intelligence/timeline`, { params: { limit } })
    return data
  },

  getProductMovements: async (shopId: string, productId: string, limit = 100): Promise<MovementRecord[]> => {
    const { data } = await apiClient.get(`/shop-assistant/shops/${shopId}/products/${productId}/movements`, { params: { limit } })
    return data
  },
}
