/**
 * SubCubeBar — horizontal position strip inside the primary cube.
 *
 * Shows where within the cube the record lives, driven by sub_cube_interval
 * from /api/locate. Confidence attenuates the bar's opacity.
 *
 * CUBE-10 / D-02 RECONCILIATION:
 *   REQUIREMENTS.md CUBE-10 literal says "tick-mark indicator". D-02 overrides
 *   this to a faint full-cube band for singletons. The implementation follows
 *   D-02: singletons render full-width at opacity 0.18 — never a tick or
 *   zero-width bar (Pitfall 21).
 *
 * Design tokens only — no hardcoded hex. All colors and radii are CSS vars.
 */

import type { CSSProperties } from 'react'
import type { SubInterval } from '../../api/types'

/** Confidence threshold below which the "~" text cue appears (D-03). */
const TEXT_CUE_THRESHOLD = 0.50

interface SubCubeBarProps {
  /** Sub-cube position interval from /api/locate */
  interval: SubInterval
  /** Confidence 0.0–1.0 — drives bar opacity and "~" cue */
  confidence: number
  /**
   * True when interval.start === 0 && interval.end === 1 (singleton label, D-02).
   * Renders a faint full-cube band instead of a proportional position bar.
   */
  isSingleton: boolean
}

/**
 * Horizontal position bar inside a cube cell.
 *
 * - Normal: width = (end - start) × 100%, left = start × 100%
 * - Singleton (D-02): full width at opacity 0.18 — reads "scan the whole cube"
 * - Opacity formula (normal): max(0.35, 0.35 + confidence × 0.65)
 * - "~" cue: visible only when confidence ≤ TEXT_CUE_THRESHOLD (0.50)
 */
export function SubCubeBar({ interval, confidence, isSingleton }: SubCubeBarProps) {
  const barLeft = isSingleton ? '0%' : `${interval.start * 100}%`
  const barWidth = isSingleton ? '100%' : `${(interval.end - interval.start) * 100}%`

  const showCue = confidence <= TEXT_CUE_THRESHOLD

  const style: CSSProperties = {
    left: barLeft,
    width: barWidth,
    // Pass confidence as CSS custom property — opacity formula lives in kiosk.css
    ['--confidence' as string]: confidence,
  }

  return (
    <div
      className={`sub-cube-bar${isSingleton ? ' sub-cube-bar--singleton' : ''}`}
      style={style}
      aria-label={showCue ? 'approximate position' : undefined}
    >
      {showCue && (
        <span className="sub-cube-bar__cue" aria-hidden="true">
          ~
        </span>
      )}
    </div>
  )
}
