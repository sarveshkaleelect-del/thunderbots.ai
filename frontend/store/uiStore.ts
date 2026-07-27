'use client'
import { create } from 'zustand'

type RightPanel = 'config' | 'chat' | 'history' | 'knowledge' | 'deploy' | 'thunderguide' | 'simulator' | null

interface UIStore {
  rightPanel: RightPanel
  leftPanelOpen: boolean
  setRightPanel: (p: RightPanel) => void
  toggleLeftPanel: () => void
  setLeftPanel: (v: boolean) => void
}

export const useUIStore = create<UIStore>((set) => ({
  rightPanel: 'chat',
  leftPanelOpen: true,
  setRightPanel: (rightPanel) => set({ rightPanel }),
  toggleLeftPanel: () => set(s => ({ leftPanelOpen: !s.leftPanelOpen })),
  setLeftPanel: (v) => set({ leftPanelOpen: v }),
}))
