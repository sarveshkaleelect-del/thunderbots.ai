'use client'
// ThunderBots Smart Shop Assistant — realtime WS hook (NEW)
// Auto-reconnects with backoff so a brief network blip on the shop floor
// doesn't require the owner (or a customer) to refresh the page.
import { useEffect, useRef } from 'react'
import { WS_URL } from '@/lib/api/client'
import type { ShopAssistantWSEvent } from '@/types/shopAssistant'

export function useShopAssistantAdminWs(shopId: string | null, onEvent: (e: ShopAssistantWSEvent) => void) {
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    if (!shopId) return
    const token = typeof window !== 'undefined' ? localStorage.getItem('tb_token') : null
    if (!token) return

    let socket: WebSocket | null = null
    let closedByUs = false
    let retryDelay = 1000

    const connect = () => {
      socket = new WebSocket(`${WS_URL}/ws/shop-assistant/admin/${shopId}?token=${encodeURIComponent(token)}`)
      socket.onmessage = (evt) => {
        try {
          onEventRef.current(JSON.parse(evt.data))
        } catch {
          // ignore malformed frames
        }
      }
      socket.onclose = () => {
        if (closedByUs) return
        setTimeout(connect, retryDelay)
        retryDelay = Math.min(retryDelay * 1.5, 15000)
      }
    }
    connect()

    return () => {
      closedByUs = true
      socket?.close()
    }
  }, [shopId])
}

export function useShopAssistantPublicWs(slug: string | null, onEvent: (e: ShopAssistantWSEvent) => void) {
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    if (!slug) return

    let socket: WebSocket | null = null
    let closedByUs = false
    let retryDelay = 1000

    const connect = () => {
      socket = new WebSocket(`${WS_URL}/ws/shop-assistant/public/${slug}`)
      socket.onmessage = (evt) => {
        try {
          onEventRef.current(JSON.parse(evt.data))
        } catch {
          // ignore malformed frames
        }
      }
      socket.onclose = () => {
        if (closedByUs) return
        setTimeout(connect, retryDelay)
        retryDelay = Math.min(retryDelay * 1.5, 15000)
      }
    }
    connect()

    return () => {
      closedByUs = true
      socket?.close()
    }
  }, [slug])
}
