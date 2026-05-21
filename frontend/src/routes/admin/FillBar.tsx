/**
 * FillBar — compact horizontal fill indicator for admin cube cards.
 *
 * Shows what fraction of a cube's nominal capacity is used.
 * Token-driven colors only — no hardcoded hex.
 *
 * Design:
 *   - A thin bar (default 3 px height) inside a track.
 *   - Fill color: var(--gruvax-yellow) at ≤80%, var(--gruvax-error) at >80%.
 *   - Empty (fill_level === 0): track only, no bar rendered.
 *   - Full (fill_level > 1.0): clamped to 100% width.
 */

import type { CSSProperties } from 'react'

interface FillBarProps {
  /** Fraction 0.0–1.0+ of nominal capacity (may exceed 1 if over-full). */
  fillLevel: number
  /** Height of the bar in pixels. Default: 3. */
  heightPx?: number
  /** Optional CSS class added to the track element. */
  className?: string
}

export function FillBar({ fillLevel, heightPx = 3, className }: FillBarProps) {
  const clampedFill = Math.min(1, Math.max(0, fillLevel))
  const isOverFull = fillLevel > 0.8

  const trackStyle: CSSProperties = {
    height: `${heightPx}px`,
  }

  const barStyle: CSSProperties = {
    width: `${clampedFill * 100}%`,
    height: '100%',
    // Color via CSS class toggling; the actual var() values live in admin.css
  }

  return (
    <div
      className={`fill-bar-track${className ? ` ${className}` : ''}`}
      style={trackStyle}
      role="meter"
      aria-valuenow={Math.round(fillLevel * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`Fill level ${Math.round(fillLevel * 100)}%`}
    >
      {clampedFill > 0 && (
        <div
          className={`fill-bar-fill${isOverFull ? ' fill-bar-fill--warn' : ''}`}
          style={barStyle}
        />
      )}
    </div>
  )
}
