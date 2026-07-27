'use client'
import { create } from 'zustand'

export type ThemeId = 'dark' | 'light' | 'midnight' | 'thunder'

export const THEMES: { id: ThemeId; label: string; emoji: string }[] = [
  { id: 'dark',     label: 'Dark',     emoji: '🌙' },
  { id: 'light',    label: 'Light',    emoji: '☀️' },
  { id: 'midnight', label: 'Midnight', emoji: '🌌' },
  { id: 'thunder',  label: 'Thunder',  emoji: '⚡' },
]

const STORAGE_KEY = 'tb-theme'

function applyThemeToDOM(theme: ThemeId) {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  // brief transition window so the swap crossfades instead of snapping
  root.classList.add('tb-theme-transition')
  root.setAttribute('data-theme', theme)
  window.setTimeout(() => root.classList.remove('tb-theme-transition'), 280)
}

interface ThemeStore {
  theme: ThemeId
  hydrated: boolean
  /** Applies instantly to the DOM + localStorage. Does not touch the backend. */
  setLocalTheme: (theme: ThemeId) => void
  setHydrated: () => void
}

export const useThemeStore = create<ThemeStore>((set) => ({
  theme: 'dark',
  hydrated: false,
  setLocalTheme: (theme) => {
    applyThemeToDOM(theme)
    try { window.localStorage.setItem(STORAGE_KEY, theme) } catch {}
    set({ theme })
  },
  setHydrated: () => set({ hydrated: true }),
}))

export function readStoredTheme(): ThemeId {
  if (typeof window === 'undefined') return 'dark'
  try {
    const v = window.localStorage.getItem(STORAGE_KEY)
    if (v === 'dark' || v === 'light' || v === 'midnight' || v === 'thunder') return v
  } catch {}
  return 'dark'
}
