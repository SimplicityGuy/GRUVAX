/**
 * RecentlyPulledStrip — horizontal chip strip below the shelf area (SRCH-09 / D-08).
 *
 * Returns null when items is empty — no empty-state placeholder rendered.
 * Chips are ordered most-recent-first (maintained by recentlyPulledStore addItem).
 *
 * Chip layout (per 08-UI-SPEC.md Surface 2):
 *   - Line 1: "{primary_artist} – {title}" (or just "{title}" when primary_artist empty)
 *   - Line 2: catalog_number in DM Mono
 *   - aria-label: "{primary_artist} – {title}, catalog number {catalog_number}"
 *
 * Tapping a chip calls setSelectedReleaseId(release_id) — the existing locate flow
 * resolves the cube highlight without navigation (D-06).
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { useRecentlyPulledStore } from '../../state/recentlyPulledStore'
import { useGruvaxStore } from '../../state/store'

export function RecentlyPulledStrip() {
  const items = useRecentlyPulledStore((s) => s.items)
  const setSelectedReleaseId = useGruvaxStore((s) => s.setSelectedReleaseId)

  // Returns null when list is empty — no reserved space in layout (D-08)
  if (items.length === 0) return null

  return (
    <div className="recently-pulled-strip">
      <span className="recently-pulled-strip__label">RECENTLY PULLED</span>

      <div
        className="recently-pulled-strip__chips"
        role="list"
        aria-label="Recently pulled records"
      >
        {items.map((item) => {
          const artistPrefix = item.primary_artist ? `${item.primary_artist} – ` : ''
          const chipLabel = `${artistPrefix}${item.title}, catalog number ${item.catalog_number}`

          return (
            <button
              key={item.release_id}
              type="button"
              role="listitem"
              className="recently-pulled-chip"
              aria-label={chipLabel}
              onClick={() => setSelectedReleaseId(item.release_id)}
            >
              <span className="recently-pulled-chip__primary">
                {item.primary_artist ? `${item.primary_artist} – ${item.title}` : item.title}
              </span>
              <span className="recently-pulled-chip__catalog">
                {item.catalog_number}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
