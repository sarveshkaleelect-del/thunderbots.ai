// ============================================================
// ThunderBots — Smart Shop Assistant API Client (public/customer side)
// No auth — hits the anonymous /shop-assistant/public/* routes a customer
// reaches after scanning the shop's QR code. Mirrors lib/api/client.ts's
// plain-axios (non-apiClient) convention already used for other public
// customer-facing endpoints in this codebase.
// ============================================================
import axios from 'axios'
import type {
  ProductMatch, ReservationItemPreview, PublicReservation, PublicWaitlistEntry,
} from '@/types/shopAssistant'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const publicClient = axios.create({ baseURL: `${API_BASE}/api/v1/shop-assistant/public` })

export const shopAssistantPublicApi = {
  getShop: async (slug: string): Promise<{ name: string; is_active: boolean; reservation_timeout_minutes: number }> => {
    const { data } = await publicClient.get(`/shops/${slug}`)
    return data
  },

  searchProducts: async (slug: string, query: string): Promise<ProductMatch[]> => {
    const { data } = await publicClient.post(`/shops/${slug}/search`, { query })
    return data
  },

  getQueueStatus: async (slug: string): Promise<{ total_waiting: number }> => {
    const { data } = await publicClient.get(`/shops/${slug}/queue`)
    return data
  },

  browseProducts: async (slug: string, category?: string): Promise<ProductMatch[]> => {
    const { data } = await publicClient.get(`/shops/${slug}/products/browse`, {
      params: category ? { category } : undefined,
    })
    return data
  },

  previewReservation: async (
    slug: string, items: { product_id: string; quantity: number }[]
  ): Promise<ReservationItemPreview[]> => {
    const { data } = await publicClient.post(`/shops/${slug}/reservations/preview`, { items })
    return data
  },

  createReservation: async (
    slug: string, items: { product_id: string; quantity: number }[], customerName: string
  ): Promise<PublicReservation> => {
    const { data } = await publicClient.post(`/shops/${slug}/reservations`, { items, customer_name: customerName })
    return data
  },

  getReservationStatus: async (slug: string, lookupCode: string): Promise<PublicReservation> => {
    const { data } = await publicClient.get(`/shops/${slug}/reservations/${lookupCode}`)
    return data
  },

  getReservationHistory: async (slug: string, lookupCodes: string[]): Promise<PublicReservation[]> => {
    if (lookupCodes.length === 0) return []
    const { data } = await publicClient.get(`/shops/${slug}/reservations`, { params: { codes: lookupCodes.join(',') } })
    return data
  },

  editReservation: async (
    slug: string, lookupCode: string, items: { product_id: string; quantity: number }[], customerName: string
  ): Promise<PublicReservation> => {
    const { data } = await publicClient.patch(`/shops/${slug}/reservations/${lookupCode}`, { items, customer_name: customerName })
    return data
  },

  cancelReservation: async (slug: string, lookupCode: string): Promise<PublicReservation> => {
    const { data } = await publicClient.patch(`/shops/${slug}/reservations/${lookupCode}/cancel`)
    return data
  },

  joinWaitlist: async (
    slug: string, productId: string, quantityRequested: number, customerName: string
  ): Promise<PublicWaitlistEntry> => {
    const { data } = await publicClient.post(`/shops/${slug}/waitlist`, {
      product_id: productId, quantity_requested: quantityRequested, customer_name: customerName,
    })
    return data
  },

  getWaitlistStatus: async (slug: string, lookupCode: string): Promise<PublicWaitlistEntry> => {
    const { data } = await publicClient.get(`/shops/${slug}/waitlist/${lookupCode}`)
    return data
  },

  cancelWaitlistEntry: async (slug: string, lookupCode: string): Promise<PublicWaitlistEntry> => {
    const { data } = await publicClient.patch(`/shops/${slug}/waitlist/${lookupCode}/cancel`)
    return data
  },
}
