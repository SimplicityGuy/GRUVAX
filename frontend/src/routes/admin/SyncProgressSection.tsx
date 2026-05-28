/**
 * SyncProgressSection — in-drawer sync progress indicator.
 *
 * UI-SPEC Surface 3 inline progress:
 *   - "Syncing…" label + animated 20px spinner (yellow ring on blue-faint)
 *   - DM Mono item count that updates per poll: "{N,###} items processed"
 *
 * Shown while last_sync_status === 'in_progress'.
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

interface SyncProgressSectionProps {
  itemCount: number | null | undefined
}

export function SyncProgressSection({ itemCount }: SyncProgressSectionProps) {
  const countText = itemCount != null
    ? `${itemCount.toLocaleString('en-US')} items processed`
    : null

  return (
    <div className="sync-progress-section" aria-live="polite" aria-busy="true">
      <div className="sync-progress-row">
        <div className="sync-progress-spinner" aria-hidden="true" />
        <span className="sync-progress-label">Syncing…</span>
      </div>
      {countText && (
        <p className="sync-progress-count">{countText}</p>
      )}
    </div>
  )
}
