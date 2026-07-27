'use client'
import { useEffect, useRef, useState, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { deployApi } from '@/lib/api/deploy'
import type { BotBranding, DesignConfig, ChatSettings, WidgetConfig, BrandingBundle } from '@/types'

const AUTOSAVE_DEBOUNCE_MS = 500

/**
 * Loads the draft branding/design/chat_settings/widget_config for a workflow
 * and exposes granular setters. Every setter updates local state IMMEDIATELY
 * (so the live preview never waits on the network) and schedules a debounced
 * PUT to persist the change — no publish required for it to show up live if
 * the bot is already published (handled server-side).
 */
export function useBrandingDraft(workflowId: string | null) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['branding-draft', workflowId],
    queryFn: () => deployApi.getBranding(workflowId!),
    enabled: !!workflowId,
    staleTime: Infinity, // local state is the source of truth once loaded
  })

  const [branding, setBrandingState]         = useState<BotBranding | null>(null)
  const [design, setDesignState]             = useState<DesignConfig | null>(null)
  const [chatSettings, setChatSettingsState] = useState<ChatSettings | null>(null)
  const [widgetConfig, setWidgetConfigState] = useState<WidgetConfig | null>(null)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')

  const hydrated = useRef(false)
  useEffect(() => {
    if (data && !hydrated.current) {
      setBrandingState(data.branding)
      setDesignState(data.design)
      setChatSettingsState(data.chat_settings)
      setWidgetConfigState(data.widget_config)
      hydrated.current = true
    }
  }, [data])

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pending = useRef<Partial<Pick<BrandingBundle, 'branding' | 'design' | 'chat_settings' | 'widget_config'>>>({})

  const flush = useCallback(() => {
    if (!workflowId || Object.keys(pending.current).length === 0) return
    const payload = pending.current
    pending.current = {}
    setSaveState('saving')
    deployApi.updateBranding(workflowId, payload)
      .then(() => setSaveState('saved'))
      .catch(() => setSaveState('error'))
  }, [workflowId])

  const schedule = useCallback((patch: Partial<Pick<BrandingBundle, 'branding' | 'design' | 'chat_settings' | 'widget_config'>>) => {
    pending.current = { ...pending.current, ...patch }
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(flush, AUTOSAVE_DEBOUNCE_MS)
  }, [flush])

  // ROOT CAUSE FIX (silent data loss): previously this only cleared the
  // pending debounce timer on unmount, so an edit made just before leaving
  // the Deploy panel (e.g. within the 500ms debounce window) was discarded
  // without ever being persisted or surfaced as an error. Flush any pending
  // patch immediately on unmount so in-flight edits are never dropped.
  useEffect(() => () => {
    if (timer.current) {
      clearTimeout(timer.current)
      flush()
    }
  }, [flush])

  const updateBranding = useCallback((patch: Partial<BotBranding>) => {
    setBrandingState(prev => {
      const next = { ...(prev as BotBranding), ...patch }
      schedule({ branding: next })
      return next
    })
  }, [schedule])

  const updateDesign = useCallback((patch: Partial<DesignConfig>) => {
    setDesignState(prev => {
      const next = { ...(prev as DesignConfig), ...patch }
      schedule({ design: next })
      return next
    })
  }, [schedule])

  const updateChatSettings = useCallback((patch: Partial<ChatSettings>) => {
    setChatSettingsState(prev => {
      const next = { ...(prev as ChatSettings), ...patch }
      schedule({ chat_settings: next })
      return next
    })
  }, [schedule])

  const updateWidgetConfig = useCallback((patch: Partial<WidgetConfig>) => {
    setWidgetConfigState(prev => {
      const next = { ...(prev as WidgetConfig), ...patch }
      schedule({ widget_config: next })
      return next
    })
  }, [schedule])

  /** For asset uploads: the backend both stores the file AND wires the URL
   * into the right bucket server-side; we just need to refresh local state
   * to match without waiting for the debounce timer. */
  const applyAssetUrl = useCallback((bucket: 'branding' | 'design' | 'widget_config', key: string, url: string) => {
    if (bucket === 'branding') setBrandingState(prev => prev ? { ...prev, [key]: url } : prev)
    if (bucket === 'design') setDesignState(prev => prev ? { ...prev, [key]: url } : prev)
    if (bucket === 'widget_config') setWidgetConfigState(prev => prev ? { ...prev, [key]: url } : prev)
    qc.invalidateQueries({ queryKey: ['branding-draft', workflowId] })
  }, [qc, workflowId])

  return {
    isLoading: isLoading || !hydrated.current,
    branding, design, chatSettings, widgetConfig,
    updateBranding, updateDesign, updateChatSettings, updateWidgetConfig,
    applyAssetUrl, saveState, flushNow: flush,
  }
}
