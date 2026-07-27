'use client'
import { create } from 'zustand'
import { tutorialApi, type TutorialStatus } from '@/lib/api/tutorial'

const STORAGE_KEY = 'tb-tutorial-progress'

export interface FeatureProgress {
  status: TutorialStatus
  currentStep: number
  completedSteps: number
}

type ProgressMap = Record<string, FeatureProgress>

function readLocal(): ProgressMap {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function writeLocal(map: ProgressMap) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(map))
  } catch {}
}

// Fire-and-forget backend sync — never blocks the UI, never throws into
// the caller. If the user is logged out or offline, localStorage alone
// still drives correct behaviour for the rest of the session.
function syncToBackend(featureKey: string, progress: FeatureProgress) {
  tutorialApi
    .upsert({
      feature_key: featureKey,
      status: progress.status,
      current_step: progress.currentStep,
      completed_steps: progress.completedSteps,
    })
    .catch(() => {})
}

interface TutorialStore {
  progress: ProgressMap
  hydrated: boolean
  /** feature key of the tutorial currently being shown, or null */
  activeFeature: string | null
  hydrate: () => Promise<void>
  getProgress: (featureKey: string) => FeatureProgress
  start: (featureKey: string) => void
  dismiss: () => void
  setStep: (featureKey: string, step: number, totalSteps: number) => void
  skip: (featureKey: string, totalSteps: number) => void
  finish: (featureKey: string, totalSteps: number) => void
  restart: (featureKey: string) => void
}

const DEFAULT_PROGRESS: FeatureProgress = { status: 'not_started', currentStep: 0, completedSteps: 0 }

export const useTutorialStore = create<TutorialStore>((set, get) => ({
  progress: {},
  hydrated: false,
  activeFeature: null,

  hydrate: async () => {
    const local = readLocal()
    set({ progress: local, hydrated: true })
    // Reconcile with backend in the background — a completed/skipped
    // tutorial on the server (e.g. on another device) should also stay
    // hidden here, but never downgrade a locally-completed one.
    try {
      const remote = await tutorialApi.list()
      set((s) => {
        const merged: ProgressMap = { ...s.progress }
        for (const r of remote) {
          const existing = merged[r.feature_key]
          const remoteFurtherAlong =
            !existing ||
            (r.status === 'completed' && existing.status !== 'completed') ||
            (r.status === 'skipped' && existing.status === 'not_started') ||
            r.completed_steps > existing.completedSteps
          if (remoteFurtherAlong) {
            merged[r.feature_key] = {
              status: r.status,
              currentStep: r.current_step,
              completedSteps: r.completed_steps,
            }
          }
        }
        writeLocal(merged)
        return { progress: merged }
      })
    } catch {
      // offline / logged out — localStorage-only is a fine fallback
    }
  },

  getProgress: (featureKey) => get().progress[featureKey] ?? DEFAULT_PROGRESS,

  start: (featureKey) => {
    const current = get().getProgress(featureKey)
    if (current.status === 'completed' || current.status === 'skipped') return
    set({ activeFeature: featureKey })
    if (current.status === 'not_started') {
      const next: ProgressMap = { ...get().progress, [featureKey]: { status: 'in_progress', currentStep: 0, completedSteps: 0 } }
      set({ progress: next })
      writeLocal(next)
      syncToBackend(featureKey, next[featureKey])
    }
  },

  dismiss: () => set({ activeFeature: null }),

  setStep: (featureKey, step, totalSteps) => {
    const progress: FeatureProgress = {
      status: 'in_progress',
      currentStep: step,
      completedSteps: Math.max(step, get().getProgress(featureKey).completedSteps),
    }
    const next = { ...get().progress, [featureKey]: progress }
    set({ progress: next })
    writeLocal(next)
    syncToBackend(featureKey, progress)
  },

  skip: (featureKey, totalSteps) => {
    const progress: FeatureProgress = { status: 'skipped', currentStep: 0, completedSteps: get().getProgress(featureKey).completedSteps }
    const next = { ...get().progress, [featureKey]: progress }
    set({ progress: next, activeFeature: null })
    writeLocal(next)
    syncToBackend(featureKey, progress)
  },

  finish: (featureKey, totalSteps) => {
    const progress: FeatureProgress = { status: 'completed', currentStep: totalSteps, completedSteps: totalSteps }
    const next = { ...get().progress, [featureKey]: progress }
    set({ progress: next, activeFeature: null })
    writeLocal(next)
    syncToBackend(featureKey, progress)
  },

  restart: (featureKey) => {
    const progress: FeatureProgress = { status: 'in_progress', currentStep: 0, completedSteps: 0 }
    const next = { ...get().progress, [featureKey]: progress }
    set({ progress: next, activeFeature: featureKey })
    writeLocal(next)
    tutorialApi.restart(featureKey).catch(() => {})
  },
}))
