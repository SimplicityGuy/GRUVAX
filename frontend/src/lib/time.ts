/**
 * Shared time-formatting utilities for admin diagnostics UI.
 */

/**
 * Format a unix-epoch timestamp (seconds) as a relative-time string.
 * e.g. "3s ago", "12 min ago", "4h ago"
 */
export function formatRelativeTime(ts: number): string {
  const nowMs = Date.now()
  const diffMs = nowMs - ts * 1000
  const diffSec = Math.floor(diffMs / 1000)
  if (diffSec < 60) return `${diffSec}s ago`
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin} min ago`
  const diffHr = Math.floor(diffMin / 60)
  return `${diffHr}h ago`
}

/**
 * Format an ISO-8601 timestamp string as a relative-time string.
 * Returns "Never synced" when isoString is null.
 */
export function formatIsoRelativeTime(isoString: string | null): string {
  if (isoString === null) return 'Never synced'
  const epochSec = new Date(isoString).getTime() / 1000
  return formatRelativeTime(epochSec)
}

/**
 * Classify a sync age (in seconds) as ok / stale / outdated.
 * null/undefined → 'ok' (unknown, assume fresh).
 */
export function stalenessStatus(seconds: number | null): 'ok' | 'stale' | 'outdated' {
  if (seconds === null || seconds === undefined) return 'ok'
  if (seconds > 14 * 86400) return 'outdated'
  if (seconds > 3 * 86400) return 'stale'
  return 'ok'
}

/**
 * Compute staleness status from an ISO-8601 last_sync_at string.
 * null → 'ok' (never synced — treated as indeterminate, not outdated).
 */
export function stalenessStatusFromIso(isoString: string | null): 'ok' | 'stale' | 'outdated' {
  if (isoString === null) return 'ok'
  const ageSeconds = (Date.now() - new Date(isoString).getTime()) / 1000
  return stalenessStatus(ageSeconds)
}
