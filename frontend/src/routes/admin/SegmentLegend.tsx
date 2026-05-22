/**
 * SegmentLegend — white-card legend rows below the full-size SegmentStrip.
 *
 * One row per segment in the bin. Shows color swatch, label, AUTO/OVERRIDE chip,
 * drift detection (>3pp from auto = drifted state with review hint), and straddle
 * caption when continues===true.
 *
 * Drift threshold per 05-UI-SPEC.md §C: 3 percentage points (DRIFT_THRESHOLD=0.03).
 *
 * Design tokens only — no hardcoded hex.
 */

import { AlertCircle } from 'lucide-react'
import type { Segment } from '../../api/cubeTypes'

const DRIFT_THRESHOLD = 0.03  // 3 percentage points

/** Blue-family swatch tokens parallel to SegmentStrip fill cycle. */
const SEGMENT_SWATCH_TOKENS = [
  '--gruvax-blue',
  '--gruvax-blue-light',
  '--gruvax-blue-dark',
] as const

interface SegmentLegendProps {
  segments: Segment[]
  /** Called when user taps "reset to N%" — syncs override to auto (does NOT remove). */
  onResync?: (label: string, autoFraction: number) => void
}

export function SegmentLegend({ segments, onResync }: SegmentLegendProps) {
  if (segments.length === 0) {
    return (
      <div className="seg-legend-empty">
        <p className="seg-legend-empty-text">
          No segments yet. Save your first boundary edit — segments are derived automatically from cut points.
        </p>
      </div>
    )
  }

  return (
    <div className="seg-legend" role="list" aria-label="Segment details">
      {segments.map((seg, i) => {
        const swatchToken = SEGMENT_SWATCH_TOKENS[i % SEGMENT_SWATCH_TOKENS.length]
        const overridePct = Math.round(seg.fraction * 100)
        const autoPct = Math.round(seg.auto_fraction * 100)
        const isDrifted = seg.is_override && Math.abs(seg.fraction - seg.auto_fraction) > DRIFT_THRESHOLD

        return (
          <div key={seg.label} className="seg-legend-row" role="listitem">
            {/* Color swatch */}
            <span
              className="seg-legend-swatch"
              style={{ background: `var(${swatchToken})` }}
              aria-hidden="true"
            />

            {/* Label */}
            <span className="seg-legend-label">{seg.label.toUpperCase()}</span>

            {/* Chip column */}
            <div className="seg-legend-chips">
              {!seg.is_override ? (
                <span className="seg-chip seg-chip--auto" role="status">
                  AUTO · {autoPct}% from row counts
                </span>
              ) : isDrifted ? (
                <span className="seg-chip seg-chip--override seg-chip--drifted" role="status">
                  <AlertCircle size={14} aria-hidden="true" />
                  {' '}OVERRIDE {overridePct}% · auto now {autoPct}% · review
                </span>
              ) : (
                <span className="seg-chip seg-chip--override" role="status">
                  OVERRIDE {overridePct}% · auto was {autoPct}%
                </span>
              )}

              {/* Resync action — only when drifted */}
              {isDrifted && onResync && (
                <button
                  type="button"
                  className="seg-chip-resync"
                  onClick={() => onResync(seg.label, seg.auto_fraction)}
                  aria-label={`Reset ${seg.label} override to auto ${autoPct}%`}
                >
                  reset to {autoPct}%
                </button>
              )}
            </div>

            {/* Straddle caption */}
            {seg.continues && (
              <p className="seg-legend-straddle">
                ↪ {seg.label} continues in next bin
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}
