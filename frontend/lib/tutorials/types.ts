export type TutorialGesture = 'click' | 'touch' | 'drag' | 'drop' | 'save' | 'try' | 'none'

export interface TutorialStep {
  /** Unique within its feature. Matches a `data-tutorial="<id>"` attribute
   *  on the real element being taught — the selector-based approach the
   *  spec asks for, so steps always point at a real visible UI element. */
  id: string
  title: string
  /** Short instruction text, e.g. "Click here", "Drag here". */
  body: string
  gesture?: TutorialGesture
  /** Where the tooltip should prefer to sit relative to the target. The
   *  overlay falls back automatically if there isn't room. */
  placement?: 'top' | 'bottom' | 'left' | 'right' | 'auto'
  /** If true, step is skipped (auto-advanced) entirely if its target
   *  element never mounts — used for optional/conditional UI. */
  optional?: boolean
}

export interface TutorialConfig {
  /** Stable key used for progress persistence + registry lookup. */
  featureKey: string
  /** Human label shown in restart menus / settings. */
  label: string
  /** One or more path prefixes (from usePathname()) this tutorial applies
   *  to, or RegExp for more precise/specific matching. First match wins
   *  across the registry, preferring the most specific pattern. */
  paths: (string | RegExp)[]
  steps: TutorialStep[]
}
