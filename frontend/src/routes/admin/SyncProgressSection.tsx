/**
 * SyncProgressSection — in-drawer sync progress indicator.
 *
 * UI-SPEC Surface 3 inline progress (D4-17):
 *   - "Syncing…" label + animated 20px spinner (yellow ring on blue-faint)
 *   - Optional elapsed seconds counter "(Ns)" in DM Mono 14px muted (D4-17)
 *   - DM Mono item count that updates per poll: "{N,###} items processed"
 *
 * Shown while last_sync_status === 'in_progress'.
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { useEffect, useState } from 'react'

interface SyncProgressSectionProps {
  itemCount: number | null | undefined
  /** Date.now() epoch when sync was triggered. Drives the elapsed counter. Null when not syncing. */
  syncStartedAt?: number | null
}

export function SyncProgressSection({ itemCount, syncStartedAt }: SyncProgressSectionProps) {
  const [elapsed, setElapsed] = useState<number>(0)

  // Elapsed-seconds counter: increments every 1s while syncStartedAt is set.
  // Clears the interval on unmount or when syncStartedAt clears (D4-17).
  useEffect(() => {
    if (!syncStartedAt) {
      setElapsed(0) // eslint-disable-line react-hooks/set-state-in-effect
      return
    }
    // Set initial elapsed immediately so there's no 0→1 flicker on mount
    setElapsed(Math.floor((Date.now() - syncStartedAt) / 1000))
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - syncStartedAt) / 1000))
    }, 1000)
    return () => clearInterval(interval)
  }, [syncStartedAt])

  const countText = itemCount != null
    ? `${itemCount.toLocaleString('en-US')} items processed`
    : null

  return (
    <div className="sync-progress-section" aria-live="polite" aria-busy="true">
      <div className="sync-progress-row">
        <div className="sync-progress-spinner" aria-hidden="true" />
        <span className="sync-progress-label">
          Syncing…
          {syncStartedAt && (
            <span className="sync-progress-count"> ({elapsed}s)</span>
          )}
        </span>
      </div>
      {countText && (
        <p className="sync-progress-count">{countText}</p>
      )}
    </div>
  )
}
