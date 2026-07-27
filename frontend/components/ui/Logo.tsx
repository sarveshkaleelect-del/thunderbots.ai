import { cn } from '@/lib/utils/cn'

/**
 * Single source of truth for the ThunderBots logo mark.
 * Renders the one shared SVG asset at /public/logo.svg as a plain <img>
 * so the vector stays perfectly sharp at any size (no rasterization,
 * no next/image optimization pass, no duplicated files). A lightweight
 * CSS-only drop-shadow glow (see .tb2-logo-glow in globals.css) sits on
 * top and brightens slightly on hover.
 *
 * Purely presentational — safe to drop into any page without touching
 * app logic, routing, or state.
 */
export function Logo({
  size = 32,
  glow = true,
  className,
}: {
  /** Rendered height in pixels; width follows the SVG's intrinsic aspect ratio. */
  size?: number
  /** Whether to apply the electric blue/purple hover glow. Defaults to on. */
  glow?: boolean
  className?: string
}) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- intentional: see docstring above, SVG needs no image-optimization pass
    <img
      src="/logo.svg"
      alt="ThunderBots"
      height={size}
      style={{ height: size, width: 'auto' }}
      className={cn(glow && 'tb2-logo-glow', className)}
      draggable={false}
    />
  )
}
